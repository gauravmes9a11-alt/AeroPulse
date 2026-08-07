"""One-Hz mission simulator for the fixed-wing series-hybrid UAV.

The mission power profile is given by the PDR/request. Durations are explicit
adjustable assumptions because the prompt specifies powers but not times.
Loiter is extended until fuel, SoC floor, or a protective maximum duration
binds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

from models import (
    EPS,
    HardwareConfig,
    ModelAssumptions,
    battery_degradation_proxy,
    dc_bus_input_required,
    generator_efficiency,
    motor_inverter_efficiency,
    motor_inverter_efficiency_multi,
    total_aircraft_mass_kg,
    turbine_sfc_kg_per_kwh,
    update_battery_soc,
)

import math


@dataclass(frozen=True)
class MissionSegment:
    name: str
    power_kw: float
    duration_s: Optional[int]


@dataclass(frozen=True)
class MissionProfile:
    """Baseline mission profile.

    Power levels are given/literature-supported Section 5.1 values. Durations
    are adjustable study assumptions selected for a small fixed-wing UAV:
    takeoff 2 min, climb 15 min, cruise 2 h, descent 10 min, landing 3 min.
    Loiter duration is solved by the simulator.
    """

    takeoff_s: int = 120
    climb_s: int = 900
    cruise_s: int = 7200
    descent_s: int = 600
    landing_s: int = 180
    max_loiter_s: int = 24 * 3600
    terminal_fuel_reserve_kg: float = 10.0
    terminal_soc_reserve: float = 0.05

    def fixed_segments(self) -> List[MissionSegment]:
        return [
            MissionSegment("Takeoff", 120.0, self.takeoff_s),
            MissionSegment("Climb", 105.0, self.climb_s),
            MissionSegment("Cruise", 53.0, self.cruise_s),
        ]

    def loiter_segment(self) -> MissionSegment:
        return MissionSegment("Loiter", 38.0, None)

    def terminal_segments(self) -> List[MissionSegment]:
        return [
            MissionSegment("Descent", 8.0, self.descent_s),
            MissionSegment("Landing", 15.0, self.landing_s),
        ]


@dataclass
class SimulationResult:
    success: bool
    first_violation: Optional[str]
    fuel_burned_kg: float
    endurance_h: float
    final_soc: float
    mission_avg_efficiency: float
    degradation_proxy: float
    total_mass_kg: float
    history: Dict[str, np.ndarray]
    diagnostics: Dict[str, Any]


def _make_violation(name: str, t: int, detail: str) -> str:
    return f"{name} at t={t}s: {detail}"


def simulate_mission(
    config: HardwareConfig,
    ems_policy: Any,
    mission: MissionProfile | None = None,
    assumptions: ModelAssumptions | None = None,
    dt_s: int = 1,
    soc_initial: float = 1.0,
    soc_floor: float = 0.20,
    stop_on_violation: bool = True,
    payload_mass_kg: float = 200.0,
    allocated_structure_mass_kg: float = 430.0,
    num_motors: int = 1,
    motor_allocation: str = "even_split",
) -> SimulationResult:
    """Run a 1 Hz time-stepped mission with hard constraints.

    The EMS policy is any object exposing ``command_generator_kw(state)`` and
    optionally ``reset(...)``. It receives current SoC, fuel, demand, segment,
    and elapsed time.

    Parameters
    ----------
    num_motors : int
        Number of propulsion motors sharing the total motor rating.
    motor_allocation : str
        ``"even_split"`` distributes load equally across all motors.
        ``"efficiency_optimal"`` shuts down motors during low-power segments
        to keep active motors closer to peak efficiency (minimum 1 active).
    """

    mission = mission or MissionProfile()
    assumptions = assumptions or ModelAssumptions()
    if hasattr(ems_policy, "reset"):
        ems_policy.reset(config, mission, assumptions)

    n_motors = max(int(num_motors), 1)
    fuel_remaining = float(config.fuel_mass_kg)
    soc = float(soc_initial)
    t = 0
    first_violation = None
    success = True
    source_energy_kwh = 0.0
    shaft_energy_kwh = 0.0
    battery_throughput_kwh = 0.0
    min_soc = soc
    max_soc = soc

    history: Dict[str, list] = {
        "time_s": [],
        "segment": [],
        "demand_kw": [],
        "generator_kw": [],
        "battery_kw": [],
        "soc": [],
        "fuel_remaining_kg": [],
        "motor_eta": [],
        "generator_eta": [],
        "fuel_flow_kg_h": [],
        "per_motor_kw": [],
        "active_motors": [],
    }

    def _pick_active_motors(demand_kw: float, segment_name: str) -> int:
        """Choose how many motors to run for efficiency-optimal allocation."""
        if n_motors == 1 or motor_allocation != "efficiency_optimal":
            return n_motors
        per_motor_max = config.motor_rating_kw / n_motors
        min_active = max(1, math.ceil(demand_kw / per_motor_max))
        # Only optimise during low-power segments; use all motors at
        # high power to respect per-motor peak limits.
        if segment_name in {"Takeoff", "Climb"}:
            return n_motors
        best_n = n_motors
        best_eta = 0.0
        for candidate_n in range(min_active, n_motors + 1):
            eta = motor_inverter_efficiency_multi(
                demand_kw, config.motor_rating_kw * candidate_n / n_motors,
                candidate_n, assumptions,
            )
            if eta > best_eta:
                best_eta = eta
                best_n = candidate_n
        return best_n

    def step(segment: MissionSegment) -> bool:
        nonlocal fuel_remaining, soc, t, first_violation, success
        nonlocal source_energy_kwh, shaft_energy_kwh, battery_throughput_kwh
        nonlocal min_soc, max_soc

        demand_kw = float(segment.power_kw)

        # --- Multi-motor allocation ---
        active = _pick_active_motors(demand_kw, segment.name)
        # Effective motor rating for the active subset
        active_rating_kw = config.motor_rating_kw * active / n_motors
        motor_eta = motor_inverter_efficiency_multi(
            demand_kw, active_rating_kw, active, assumptions,
        )
        per_motor_kw = demand_kw / max(active, 1)

        load_dc_kw = demand_kw / max(motor_eta, EPS)
        source_required_kw = dc_bus_input_required(load_dc_kw, assumptions)
        state = {
            "time_s": t,
            "segment": segment.name,
            "demand_kw": demand_kw,
            "source_required_kw": source_required_kw,
            "soc": soc,
            "fuel_remaining_kg": fuel_remaining,
            "config": config,
            "assumptions": assumptions,
        }
        gen_cmd_kw = float(ems_policy.command_generator_kw(state))
        gen_cmd_kw = max(gen_cmd_kw, 0.0)
        gen_kw = min(gen_cmd_kw, config.generator_rating_kw)
        gen_eta = generator_efficiency(gen_kw, config.generator_rating_kw, assumptions)
        turbine_shaft_kw = gen_kw / max(gen_eta, EPS)
        sfc = turbine_sfc_kg_per_kwh(turbine_shaft_kw, config.turbine_rating_kw, assumptions)
        fuel_burn_kg = turbine_shaft_kw * sfc * dt_s / 3600.0
        battery_kw = source_required_kw - gen_kw

        next_soc = update_battery_soc(soc, battery_kw, dt_s, config.battery_capacity_kwh, assumptions)
        next_fuel = fuel_remaining - fuel_burn_kg

        violations: list[str] = []
        if demand_kw > config.motor_rating_kw + 1e-6:
            violations.append(f"motor demand {demand_kw:.1f} kW > rating {config.motor_rating_kw:.1f} kW")
        if gen_kw > config.generator_rating_kw + 1e-6:
            violations.append(f"generator {gen_kw:.1f} kW > rating {config.generator_rating_kw:.1f} kW")
        if turbine_shaft_kw > config.turbine_rating_kw + 1e-6:
            violations.append(
                f"turbine shaft {turbine_shaft_kw:.1f} kW > rating {config.turbine_rating_kw:.1f} kW"
            )
        if abs(battery_kw) > config.battery_peak_power_kw + 1e-6:
            violations.append(
                f"battery terminal {battery_kw:.1f} kW exceeds peak {config.battery_peak_power_kw:.1f} kW"
            )
        if next_soc < soc_floor - 1e-6:
            violations.append(f"SoC {next_soc:.3f} < floor {soc_floor:.3f}")
        if next_soc > 1.0 + 1e-6:
            violations.append(f"SoC {next_soc:.3f} > 1.000")
        if next_fuel < -1e-6:
            violations.append(f"fuel remaining {next_fuel:.3f} kg < 0")

        history["time_s"].append(t)
        history["segment"].append(segment.name)
        history["demand_kw"].append(demand_kw)
        history["generator_kw"].append(gen_kw)
        history["battery_kw"].append(battery_kw)
        history["soc"].append(soc)
        history["fuel_remaining_kg"].append(fuel_remaining)
        history["motor_eta"].append(motor_eta)
        history["generator_eta"].append(gen_eta)
        history["fuel_flow_kg_h"].append(fuel_burn_kg * 3600.0 / dt_s)
        history["per_motor_kw"].append(per_motor_kw)
        history["active_motors"].append(active)

        if violations and first_violation is None:
            first_violation = _make_violation(segment.name, t, "; ".join(violations))
            success = False
            if stop_on_violation:
                return False

        soc = min(max(next_soc, -1.0), 1.2)
        fuel_remaining = next_fuel
        t += dt_s
        source_energy_kwh += max(gen_kw, 0.0) * dt_s / 3600.0
        shaft_energy_kwh += demand_kw * dt_s / 3600.0
        battery_throughput_kwh += abs(battery_kw) * dt_s / 3600.0
        min_soc = min(min_soc, soc)
        max_soc = max(max_soc, soc)
        return True

    def run_segment(segment: MissionSegment, duration_s: int) -> bool:
        for _ in range(0, int(duration_s), dt_s):
            if not step(segment):
                return False
        return True

    for seg in mission.fixed_segments():
        if not run_segment(seg, seg.duration_s or 0):
            break

    if success or not stop_on_violation:
        loiter = mission.loiter_segment()
        for _ in range(0, int(mission.max_loiter_s), dt_s):
            if fuel_remaining <= mission.terminal_fuel_reserve_kg or soc <= soc_floor + mission.terminal_soc_reserve:
                break
            if not step(loiter):
                if (
                    first_violation
                    and first_violation.startswith("Loiter")
                    and ("SoC" in first_violation or "fuel remaining" in first_violation)
                    and "battery terminal" not in first_violation
                    and "turbine shaft" not in first_violation
                    and "generator" not in first_violation
                    and "motor demand" not in first_violation
                ):
                    first_violation = None
                    success = True
                break

    if success or not stop_on_violation:
        for seg in mission.terminal_segments():
            if not run_segment(seg, seg.duration_s or 0):
                break

    for key, values in history.items():
        history[key] = np.asarray(values)

    fuel_burned = max(config.fuel_mass_kg - fuel_remaining, 0.0)
    fuel_energy_kwh = fuel_burned * assumptions.fuel_lhv_kwh_per_kg
    battery_net_kwh = max((soc_initial - soc) * config.battery_capacity_kwh, 0.0)
    input_energy_kwh = fuel_energy_kwh + battery_net_kwh
    mission_avg_eff = shaft_energy_kwh / max(input_energy_kwh, EPS)
    dod = max_soc - min_soc
    eq_cycles = battery_throughput_kwh / max(2.0 * config.battery_capacity_kwh, EPS)
    mean_c_rate = battery_throughput_kwh / max(config.battery_capacity_kwh * max(t / 3600.0, EPS), EPS)
    degradation = battery_degradation_proxy(dod, mean_c_rate, eq_cycles, assumptions)
    total_mass = total_aircraft_mass_kg(
        config, assumptions, payload_mass_kg, allocated_structure_mass_kg,
        num_motors=n_motors,
    )

    diagnostics = {
        "source_energy_kwh": source_energy_kwh,
        "shaft_energy_kwh": shaft_energy_kwh,
        "fuel_energy_kwh": fuel_energy_kwh,
        "battery_throughput_kwh": battery_throughput_kwh,
        "min_soc": min_soc,
        "max_soc": max_soc,
    }
    return SimulationResult(
        success=success,
        first_violation=first_violation,
        fuel_burned_kg=fuel_burned,
        endurance_h=t / 3600.0,
        final_soc=soc,
        mission_avg_efficiency=mission_avg_eff,
        degradation_proxy=degradation,
        total_mass_kg=total_mass,
        history=history,
        diagnostics=diagnostics,
    )


def climb_energy_balance(
    config: HardwareConfig,
    ems_policy: Any,
    mission: MissionProfile | None = None,
    assumptions: ModelAssumptions | None = None,
    num_motors: int = 1,
) -> Dict[str, float]:
    """Return a sanity-check energy balance for the climb segment."""

    mission = mission or MissionProfile()
    assumptions = assumptions or ModelAssumptions()
    if hasattr(ems_policy, "reset"):
        ems_policy.reset(config, mission, assumptions)
    p_shaft = 105.0
    dt_h = mission.climb_s / 3600.0
    motor_eta = motor_inverter_efficiency_multi(
        p_shaft, config.motor_rating_kw, num_motors, assumptions,
    )
    source_required_kw = dc_bus_input_required(p_shaft / motor_eta, assumptions)
    state = {
        "time_s": mission.takeoff_s,
        "segment": "Climb",
        "demand_kw": p_shaft,
        "source_required_kw": source_required_kw,
        "soc": 1.0,
        "fuel_remaining_kg": config.fuel_mass_kg,
        "config": config,
        "assumptions": assumptions,
    }
    gen_kw = min(float(ems_policy.command_generator_kw(state)), config.generator_rating_kw)
    batt_kw = source_required_kw - gen_kw
    return {
        "climb_duration_h": dt_h,
        "shaft_energy_kwh": p_shaft * dt_h,
        "dc_source_required_kwh": source_required_kw * dt_h,
        "generator_electric_kwh": gen_kw * dt_h,
        "battery_terminal_kwh": batt_kw * dt_h,
        "motor_inverter_eta": motor_eta,
        "bus_eta": 1.0 - assumptions.bus_loss_frac,
    }
