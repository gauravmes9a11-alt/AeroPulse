"""Disturbance Engine for Failure Injection and What-If Analysis.

Modifies HardwareConfig, ModelAssumptions, and MissionProfile based on real-world
mission disturbance parameters without altering the core simulation engine.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Tuple
import math
import numpy as np

from models import HardwareConfig, ModelAssumptions, total_aircraft_mass_kg
from mission_sim import MissionProfile, MissionSegment, SimulationResult, simulate_mission


@dataclass
class DisturbanceScenario:
    """Parameters defining mission disturbances and component failures."""
    altitude_m: float = 0.0              # 0 to 6000 m
    ambient_temp_c: float = 15.0         # -20 to +50 °C (ISA baseline 15 °C)
    headwind_kmh: float = 0.0            # -50 to +50 km/h
    payload_delta_kg: float = 0.0        # -50 to +100 kg
    battery_cell_failure_pct: float = 0.0# 0, 5, 10, 20, 30 %
    generator_failed: bool = False       # True/False
    motor_failure_mode: str = "none"      # "none" | "degraded" | "failed"
    propeller_damage_pct: float = 0.0    # 0 to 30 %


def isa_density_ratio(altitude_m: float) -> float:
    """Calculate atmospheric density ratio ρ/ρ₀ using International Standard Atmosphere (ISA)."""
    h = max(0.0, altitude_m)
    t_ratio = max(0.1, 1.0 - 2.25577e-5 * h)
    return float(t_ratio ** 4.25588)


def apply_disturbances(
    base_config: HardwareConfig,
    base_assumptions: ModelAssumptions,
    base_mission: MissionProfile,
    scenario: DisturbanceScenario,
    payload_mass_kg: float = 200.0,
    num_motors: int = 1,
) -> Tuple[HardwareConfig, ModelAssumptions, MissionProfile, float, int]:
    """Return perturbed copies of config, assumptions, mission, payload, and num_motors."""

    # 1. Payload modification
    adj_payload_kg = max(0.0, payload_mass_kg + scenario.payload_delta_kg)

    # 2. Battery cell failure -> capacity & peak power drop
    cell_loss_frac = max(0.0, min(1.0, scenario.battery_cell_failure_pct / 100.0))
    adj_batt_cap = base_config.battery_capacity_kwh * (1.0 - cell_loss_frac)
    adj_batt_peak = base_config.battery_peak_power_kw * (1.0 - cell_loss_frac)

    # 3. Generator failure -> power rating zeroed
    adj_gen_kw = 0.0 if scenario.generator_failed else base_config.generator_rating_kw
    adj_turbine_kw = 0.0 if scenario.generator_failed else base_config.turbine_rating_kw

    # 4. Motor failure -> rating & motor count adjustment
    adj_motor_kw = base_config.motor_rating_kw
    adj_num_motors = max(1, num_motors)

    if scenario.motor_failure_mode == "degraded":
        adj_motor_kw = base_config.motor_rating_kw * (1.0 - 0.25 / adj_num_motors)
    elif scenario.motor_failure_mode == "failed":
        if adj_num_motors > 1:
            adj_motor_kw = base_config.motor_rating_kw * (adj_num_motors - 1) / adj_num_motors
        else:
            adj_motor_kw = 0.0

    adj_config = replace(
        base_config,
        battery_capacity_kwh=adj_batt_cap,
        battery_peak_power_kw=adj_batt_peak,
        generator_rating_kw=adj_gen_kw,
        turbine_rating_kw=adj_turbine_kw,
        motor_rating_kw=adj_motor_kw,
    )

    # 5. Ambient temperature effects on efficiency
    batt_eta_penalty = 0.0
    if scenario.ambient_temp_c < 20.0:
        batt_eta_penalty = 0.003 * (20.0 - scenario.ambient_temp_c)
    elif scenario.ambient_temp_c > 35.0:
        batt_eta_penalty = 0.003 * (scenario.ambient_temp_c - 35.0)

    adj_batt_eta = max(0.50, base_assumptions.battery_roundtrip_eta - batt_eta_penalty)

    gen_temp_penalty = 0.0
    if scenario.ambient_temp_c > 40.0:
        gen_temp_penalty = 0.002 * (scenario.ambient_temp_c - 40.0)

    adj_gen_eta_peak = max(0.70, base_assumptions.generator_eta_peak - gen_temp_penalty)

    adj_assumptions = replace(
        base_assumptions,
        battery_roundtrip_eta=adj_batt_eta,
        generator_eta_peak=adj_gen_eta_peak,
    )

    # 6. Mission & Power Profile Perturbations
    sigma = isa_density_ratio(scenario.altitude_m)
    prop_damage_factor = 1.0 / max(0.70, 1.0 - scenario.propeller_damage_pct / 100.0)
    density_power_factor = (1.0 / math.sqrt(sigma)) * (1.0 / (sigma ** 0.1))

    base_mtow = total_aircraft_mass_kg(base_config, base_assumptions, payload_mass_kg, num_motors=num_motors)
    adj_mtow = total_aircraft_mass_kg(adj_config, adj_assumptions, adj_payload_kg, num_motors=adj_num_motors)
    weight_power_factor = (adj_mtow / max(1.0, base_mtow)) ** 1.5

    power_multiplier = density_power_factor * prop_damage_factor * weight_power_factor

    v_cruise = 250.0
    v_ground = max(50.0, v_cruise - scenario.headwind_kmh)
    cruise_time_factor = v_cruise / v_ground
    adj_cruise_s = int(base_mission.cruise_s * cruise_time_factor)

    adj_mission = replace(
        base_mission,
        cruise_s=adj_cruise_s,
    )

    return adj_config, adj_assumptions, adj_mission, adj_payload_kg, adj_num_motors


def run_disturbed_simulation(
    base_config: HardwareConfig,
    ems_policy: Any,
    base_mission: MissionProfile,
    base_assumptions: ModelAssumptions,
    scenario: DisturbanceScenario,
    payload_mass_kg: float = 200.0,
    num_motors: int = 1,
    motor_allocation: str = "even_split",
) -> Tuple[SimulationResult, Dict[str, Any]]:
    """Execute simulation under scenario perturbations."""

    adj_cfg, adj_assumptions, adj_mission, adj_payload_kg, adj_num_motors = apply_disturbances(
        base_config, base_assumptions, base_mission, scenario, payload_mass_kg, num_motors
    )

    sigma = isa_density_ratio(scenario.altitude_m)
    prop_damage_factor = 1.0 / max(0.70, 1.0 - scenario.propeller_damage_pct / 100.0)
    density_power_factor = (1.0 / math.sqrt(sigma)) * (1.0 / (sigma ** 0.1))

    base_mtow = total_aircraft_mass_kg(base_config, base_assumptions, payload_mass_kg, num_motors=num_motors)
    adj_mtow = total_aircraft_mass_kg(adj_cfg, adj_assumptions, adj_payload_kg, num_motors=adj_num_motors)
    weight_power_factor = (adj_mtow / max(1.0, base_mtow)) ** 1.5

    power_mult = density_power_factor * prop_damage_factor * weight_power_factor

    class PerturbedMissionProfile(MissionProfile):
        def fixed_segments(self) -> List[MissionSegment]:
            return [
                MissionSegment("Takeoff", 120.0 * power_mult, self.takeoff_s),
                MissionSegment("Climb", 105.0 * power_mult, self.climb_s),
                MissionSegment("Cruise", 53.0 * power_mult, self.cruise_s),
            ]
        def loiter_segment(self) -> MissionSegment:
            return MissionSegment("Loiter", 38.0 * power_mult, None)
        def terminal_segments(self) -> List[MissionSegment]:
            return [
                MissionSegment("Descent", 8.0 * power_mult, self.descent_s),
                MissionSegment("Landing", 15.0 * power_mult, self.landing_s),
            ]

    perturbed_mission_inst = PerturbedMissionProfile(
        takeoff_s=adj_mission.takeoff_s,
        climb_s=adj_mission.climb_s,
        cruise_s=adj_mission.cruise_s,
        descent_s=adj_mission.descent_s,
        landing_s=adj_mission.landing_s,
        max_loiter_s=adj_mission.max_loiter_s,
        terminal_fuel_reserve_kg=adj_mission.terminal_fuel_reserve_kg,
        terminal_soc_reserve=adj_mission.terminal_soc_reserve,
    )

    res = simulate_mission(
        adj_cfg,
        ems_policy,
        mission=perturbed_mission_inst,
        assumptions=adj_assumptions,
        stop_on_violation=False,
        payload_mass_kg=adj_payload_kg,
        allocated_structure_mass_kg=430.0,
        num_motors=adj_num_motors,
        motor_allocation=motor_allocation,
    )

    metadata = {
        "perturbed_config": adj_cfg,
        "perturbed_assumptions": adj_assumptions,
        "perturbed_mission": perturbed_mission_inst,
        "perturbed_payload_kg": adj_payload_kg,
        "perturbed_num_motors": adj_num_motors,
        "power_multiplier": power_mult,
    }
    return res, metadata


def generate_warnings(
    result: SimulationResult,
    scenario: DisturbanceScenario,
    config: HardwareConfig,
) -> List[Dict[str, str]]:
    """Return intelligent list of warnings based on simulation results and scenario."""

    warnings: List[Dict[str, str]] = []

    # Generator status
    if scenario.generator_failed:
        warnings.append({
            "severity": "critical",
            "title": "GENERATOR FAILURE DETECTED",
            "message": "Generator power set to 0 kW. Bus relying 100% on battery discharge reserve."
        })
    elif result.history is not None and "generator_kw" in result.history:
        peak_gen = float(np.max(result.history["generator_kw"])) if len(result.history["generator_kw"]) > 0 else 0.0
        if config.generator_rating_kw > 0 and peak_gen > config.generator_rating_kw * 0.95:
            pct = (peak_gen / config.generator_rating_kw - 1.0) * 100
            if pct > 0:
                warnings.append({
                    "severity": "warning",
                    "title": "GENERATOR OVERLOADED",
                    "message": f"Generator output reached {peak_gen:.1f} kW ({pct:.1f}% above continuous rating)."
                })

    # Battery Cell Failure
    if scenario.battery_cell_failure_pct > 0:
        warnings.append({
            "severity": "warning",
            "title": "BATTERY CAPACITY DEGRADED",
            "message": f"{scenario.battery_cell_failure_pct:.0f}% battery cell failure injected. Pack capacity reduced."
        })

    # Battery SoC & Peak Power
    if result.history is not None and "battery_kw" in result.history:
        peak_batt_discharge = float(np.max(result.history["battery_kw"])) if len(result.history["battery_kw"]) > 0 else 0.0
        if peak_batt_discharge > config.battery_peak_power_kw:
            warnings.append({
                "severity": "critical",
                "title": "BATTERY DISCHARGE RATE EXCEEDED",
                "message": f"Peak battery terminal power ({peak_batt_discharge:.1f} kW) exceeds maximum discharge rating ({config.battery_peak_power_kw:.1f} kW)."
            })

    if result.final_soc < 0.20:
        warnings.append({
            "severity": "critical",
            "title": "BATTERY SOC BELOW EMERGENCY RESERVE",
            "message": f"Final battery State of Charge reached {result.final_soc*100:.1f}% (below 20% safety threshold)."
        })

    # Motor Failure / Power Limits
    if scenario.motor_failure_mode != "none":
        warnings.append({
            "severity": "critical" if scenario.motor_failure_mode == "failed" else "warning",
            "title": "MOTOR DEGRADATION / FAILURE ACTIVE",
            "message": f"Propulsion motor status: '{scenario.motor_failure_mode.upper()}'. Load redistributed across active motors."
        })

    # Thermal / Ambient
    if scenario.ambient_temp_c > 40.0:
        warnings.append({
            "severity": "warning",
            "title": "HIGH AMBIENT TEMPERATURE WARNING",
            "message": f"Ambient temperature {scenario.ambient_temp_c:.1f}°C degrades generator cooling and battery efficiency."
        })
    elif scenario.ambient_temp_c < 0.0:
        warnings.append({
            "severity": "info",
            "title": "SUB-ZERO AMBIENT TEMPERATURE",
            "message": f"Ambient temperature {scenario.ambient_temp_c:.1f}°C increases internal battery resistance."
        })

    # Altitude / Density
    if scenario.altitude_m >= 3000.0:
        warnings.append({
            "severity": "info",
            "title": "HIGH ALTITUDE OPERATION",
            "message": f"Operating altitude {scenario.altitude_m:.0f} m reduces air density, increasing required thrust power."
        })

    # Mission Completion
    if not result.success:
        viol = result.first_violation or "Mission envelope boundary exceeded."
        warnings.append({
            "severity": "critical",
            "title": "MISSION INFEASIBLE",
            "message": f"Mission cannot complete successfully. First violation: {viol}"
        })

    return warnings


def compute_constraint_health(
    result: SimulationResult,
    config: HardwareConfig,
    scenario: DisturbanceScenario,
) -> Dict[str, Dict[str, Any]]:
    """Assess constraint status and return green/yellow/red status dict."""

    health: Dict[str, Dict[str, Any]] = {}
    hist = result.history

    # 1. Battery SoC Floor (20%)
    min_soc = result.diagnostics.get("min_soc", result.final_soc)
    if min_soc >= 0.25:
        soc_status = "green"
        soc_msg = f"Min SoC: {min_soc*100:.1f}% (Healthy)"
    elif min_soc >= 0.20:
        soc_status = "yellow"
        soc_msg = f"Min SoC: {min_soc*100:.1f}% (Near Reserve)"
    else:
        soc_status = "red"
        soc_msg = f"Min SoC: {min_soc*100:.1f}% (Violated <20%)"
    health["Battery SoC Floor"] = {"status": soc_status, "detail": soc_msg}

    # 2. Generator Power Limit
    if scenario.generator_failed:
        health["Generator Output"] = {"status": "red", "detail": "FAILED (0 kW output)"}
    elif hist is not None and "generator_kw" in hist and len(hist["generator_kw"]) > 0:
        peak_gen = float(np.max(hist["generator_kw"]))
        gen_rat = max(0.1, config.generator_rating_kw)
        ratio = peak_gen / gen_rat
        if ratio <= 0.90:
            health["Generator Output"] = {"status": "green", "detail": f"Peak: {peak_gen:.1f} kW / {gen_rat:.1f} kW ({ratio*100:.0f}%)"}
        elif ratio <= 1.00:
            health["Generator Output"] = {"status": "yellow", "detail": f"Peak: {peak_gen:.1f} kW / {gen_rat:.1f} kW ({ratio*100:.0f}%)"}
        else:
            health["Generator Output"] = {"status": "red", "detail": f"Peak: {peak_gen:.1f} kW > Rating {gen_rat:.1f} kW"}
    else:
        health["Generator Output"] = {"status": "green", "detail": "Nominal"}

    # 3. Motor Power Limit
    if hist is not None and "demand_kw" in hist and len(hist["demand_kw"]) > 0:
        peak_demand = float(np.max(hist["demand_kw"]))
        mot_rat = max(0.1, config.motor_rating_kw)
        ratio = peak_demand / mot_rat
        if ratio <= 0.85:
            health["Motor Rating"] = {"status": "green", "detail": f"Peak: {peak_demand:.1f} kW / {mot_rat:.1f} kW ({ratio*100:.0f}%)"}
        elif ratio <= 1.00:
            health["Motor Rating"] = {"status": "yellow", "detail": f"Peak: {peak_demand:.1f} kW / {mot_rat:.1f} kW ({ratio*100:.0f}%)"}
        else:
            health["Motor Rating"] = {"status": "red", "detail": f"Demand {peak_demand:.1f} kW > Rating {mot_rat:.1f} kW"}
    else:
        health["Motor Rating"] = {"status": "green", "detail": "Nominal"}

    # 4. Battery Peak Discharge
    if hist is not None and "battery_kw" in hist and len(hist["battery_kw"]) > 0:
        peak_dis = float(np.max(hist["battery_kw"]))
        batt_peak_rat = max(0.1, config.battery_peak_power_kw)
        ratio = peak_dis / batt_peak_rat
        if ratio <= 0.85:
            health["Battery Discharge Rate"] = {"status": "green", "detail": f"Peak: {peak_dis:.1f} kW / {batt_peak_rat:.1f} kW ({ratio*100:.0f}%)"}
        elif ratio <= 1.00:
            health["Battery Discharge Rate"] = {"status": "yellow", "detail": f"Peak: {peak_dis:.1f} kW / {batt_peak_rat:.1f} kW ({ratio*100:.0f}%)"}
        else:
            health["Battery Discharge Rate"] = {"status": "red", "detail": f"Peak: {peak_dis:.1f} kW > Limit {batt_peak_rat:.1f} kW"}
    else:
        health["Battery Discharge Rate"] = {"status": "green", "detail": "Nominal"}

    # 5. Aircraft MTOW Limit
    mtow = result.total_mass_kg
    if mtow <= 950.0:
        health["MTOW Limit (1000 kg)"] = {"status": "green", "detail": f"MTOW: {mtow:.1f} kg (Margin: {1000.0-mtow:.1f} kg)"}
    elif mtow <= 1000.0:
        health["MTOW Limit (1000 kg)"] = {"status": "yellow", "detail": f"MTOW: {mtow:.1f} kg (Tight Margin)"}
    else:
        health["MTOW Limit (1000 kg)"] = {"status": "red", "detail": f"MTOW: {mtow:.1f} kg (> 1000 kg limit!)"}

    # 6. Fuel Reserve Safety
    rem_fuel = config.fuel_mass_kg - result.fuel_burned_kg
    if rem_fuel >= 15.0:
        health["Fuel Reserve"] = {"status": "green", "detail": f"Remaining: {rem_fuel:.1f} kg"}
    elif rem_fuel >= 10.0:
        health["Fuel Reserve"] = {"status": "yellow", "detail": f"Remaining: {rem_fuel:.1f} kg (Reserve Margin)"}
    else:
        health["Fuel Reserve"] = {"status": "red", "detail": f"Remaining: {rem_fuel:.1f} kg (<10 kg Reserve)"}

    return health


def compute_mission_success_probability(
    result: SimulationResult,
    config: HardwareConfig,
    scenario: DisturbanceScenario,
) -> float:
    """Compute weighted 0–100% mission success probability score."""

    score = 100.0

    min_soc = result.diagnostics.get("min_soc", result.final_soc)
    if min_soc < 0.20:
        score -= min(40.0, (0.20 - min_soc) * 200.0)

    if scenario.generator_failed:
        score -= 25.0
    elif result.history is not None and "generator_kw" in result.history and len(result.history["generator_kw"]) > 0:
        peak_gen = float(np.max(result.history["generator_kw"]))
        if peak_gen > config.generator_rating_kw and config.generator_rating_kw > 0:
            over = (peak_gen / config.generator_rating_kw - 1.0)
            score -= min(25.0, over * 50.0)

    if scenario.motor_failure_mode == "failed":
        score -= 30.0
    elif scenario.motor_failure_mode == "degraded":
        score -= 15.0

    rem_fuel = config.fuel_mass_kg - result.fuel_burned_kg
    if rem_fuel < 10.0:
        score -= min(30.0, (10.0 - rem_fuel) * 3.0)

    if not result.success:
        score -= 20.0

    return float(max(0.0, min(100.0, score)))
