"""Parametric subsystem models for the HAL Aerothon hybrid UAV study.

Units are kW, kWh, kg, seconds, and fractions unless noted otherwise.

Default values follow the conceptual design document:
- Given/literature baseline data from Section 5.1: 60 kW turbine, 65 kW
  generator, 120 kW motor, 65 kW battery peak power, 1000 kg MTOW,
  200 kg fixed payload.
- Adjustable Section 5.2 assumptions: turbine SFC 0.35-0.45 kg/kWh,
  generator efficiency 92-95%, motor+inverter efficiency 90-94%,
  battery specific energy 200-260 Wh/kg, battery round-trip efficiency
  94-96%, and DC bus/wiring losses 1-2%.

The functions are deliberately map-like and side-effect free so that a HAL
engineer can replace the simple curve fits with test-derived maps later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


EPS = 1e-9


@dataclass(frozen=True)
class ModelAssumptions:
    """Adjustable conceptual-level modeling assumptions.

    The numerical ranges are literature/design-team assumptions in Section 5.2
    of the PDR, not immutable requirements. Sensitivity studies should vary
    these values before any detailed-design conclusion is drawn.
    """

    sfc_ref_kg_per_kwh: float = 0.39
    sfc_part_load_k1: float = 0.32
    generator_eta_peak: float = 0.94
    generator_eta_min: float = 0.82
    generator_rolloff: float = 0.09
    motor_inv_eta_peak: float = 0.92
    motor_inv_eta_min: float = 0.82
    motor_inv_rolloff: float = 0.08
    battery_roundtrip_eta: float = 0.95
    bus_loss_frac: float = 0.015
    battery_specific_energy_wh_per_kg: float = 230.0
    fuel_lhv_kwh_per_kg: float = 11.9

    # Conceptual mass model assumptions.
    turbine_specific_power_kw_per_kg: float = 2.0
    generator_specific_power_kw_per_kg: float = 4.0
    motor_specific_power_kw_per_kg: float = 5.0
    battery_power_specific_kw_per_kg: float = 2.5
    power_electronics_specific_kw_per_kg: float = 8.0
    fixed_propulsion_accessory_mass_kg: float = 20.0

    # Battery degradation surrogate coefficients.
    degradation_dod_exponent: float = 1.35
    degradation_crate_exponent: float = 1.15
    degradation_scale: float = 1.0


@dataclass(frozen=True)
class HardwareConfig:
    """Candidate hardware design.

    Motor rating is fixed at 120 kW by the given baseline because the request
    keeps the motor outside the optimization variables. Other ratings are
    design variables in ``optimize.py``.
    """

    turbine_rating_kw: float = 60.0
    generator_rating_kw: float = 65.0
    motor_rating_kw: float = 120.0
    battery_capacity_kwh: float = 24.0
    battery_peak_power_kw: float = 65.0
    fuel_mass_kg: float = 80.0


def clamp(value: float, low: float, high: float) -> float:
    return float(min(max(value, low), high))


def turbine_sfc_kg_per_kwh(power_kw: float, rated_kw: float, assumptions: ModelAssumptions) -> float:
    """Return turbine SFC for shaft power.

    Uses the requested conceptual equation:
    ``SFC(P) = SFC_ref * (1 + k1 * (1 - P/P_rated)^2)``.
    ``SFC_ref`` is an adjustable Section 5.2 assumption representative of
    small turboshaft/APU-derived units.
    """

    if power_kw <= EPS or rated_kw <= EPS:
        return 0.0
    part_load = clamp(power_kw / rated_kw, 0.05, 1.25)
    return assumptions.sfc_ref_kg_per_kwh * (
        1.0 + assumptions.sfc_part_load_k1 * (1.0 - part_load) ** 2
    )


def quadratic_efficiency(
    power_kw: float,
    rated_kw: float,
    eta_peak: float,
    eta_min: float,
    rolloff: float,
) -> float:
    """Generic quadratic roll-off around rated power."""

    if power_kw <= EPS or rated_kw <= EPS:
        return eta_min
    part_load = clamp(power_kw / rated_kw, 0.0, 1.25)
    eta = eta_peak - rolloff * (1.0 - part_load) ** 2
    return clamp(eta, eta_min, eta_peak)


def generator_efficiency(power_kw: float, rated_kw: float, assumptions: ModelAssumptions) -> float:
    """Permanent-magnet generator efficiency, default 92-95% near rating."""

    return quadratic_efficiency(
        power_kw,
        rated_kw,
        assumptions.generator_eta_peak,
        assumptions.generator_eta_min,
        assumptions.generator_rolloff,
    )


def motor_inverter_efficiency(power_kw: float, rated_kw: float, assumptions: ModelAssumptions) -> float:
    """Combined PMSM + SiC inverter efficiency, default 90-94%."""

    return quadratic_efficiency(
        power_kw,
        rated_kw,
        assumptions.motor_inv_eta_peak,
        assumptions.motor_inv_eta_min,
        assumptions.motor_inv_rolloff,
    )


def motor_inverter_efficiency_multi(
    total_power_kw: float,
    motor_rating_kw: float,
    num_motors: int,
    assumptions: ModelAssumptions,
) -> float:
    """Per-motor efficiency when *total_power_kw* is split across *num_motors*.

    Each motor is sized to ``motor_rating_kw / num_motors``.  The load is
    distributed evenly so each motor sees ``total_power_kw / num_motors``.
    The quadratic roll-off curve is evaluated per-motor against the per-motor
    rated power.

    Falls back to the single-motor path when ``num_motors == 1``.
    """

    n = max(int(num_motors), 1)
    if n == 1:
        return motor_inverter_efficiency(total_power_kw, motor_rating_kw, assumptions)
    per_motor_power = total_power_kw / n
    per_motor_rating = motor_rating_kw / n
    return quadratic_efficiency(
        per_motor_power,
        per_motor_rating,
        assumptions.motor_inv_eta_peak,
        assumptions.motor_inv_eta_min,
        assumptions.motor_inv_rolloff,
    )


def motor_mass_per_unit(rated_power_kw: float) -> float:
    """Non-linear mass estimate for a single motor of *rated_power_kw*.

    Uses a power-law form with a fixed overhead term::

        mass = a * rated_power^b + c_fixed

    Smaller motors carry proportionally more fixed overhead (mounts,
    connectors, controller housing), so total motor mass does NOT scale
    perfectly as ``motor_rating / N``.

    The constants below are placeholder engineering assumptions — replace
    with vendor data or regression fits when available.
    """

    # --- Tunable engineering assumptions ---
    a = 0.18          # scaling coefficient  (kg / kW^b)
    b = 0.85          # sub-linear exponent  (< 1 → heavier per-kW at small sizes)
    c_fixed = 2.0     # fixed per-motor overhead mass (kg): mounts, connectors, ESC housing
    # ----------------------------------------

    return a * max(rated_power_kw, 0.0) ** b + c_fixed


def battery_charge_discharge_eta(assumptions: ModelAssumptions) -> tuple[float, float]:
    """Return symmetric charge/discharge efficiencies from round-trip value."""

    eta = float(np.sqrt(clamp(assumptions.battery_roundtrip_eta, 0.5, 1.0)))
    return eta, eta


def update_battery_soc(
    soc: float,
    battery_terminal_kw: float,
    dt_s: float,
    capacity_kwh: float,
    assumptions: ModelAssumptions,
) -> float:
    """Integrate battery SoC for terminal power.

    Positive terminal power discharges the battery. Negative terminal power
    charges it. The Section 5.2 round-trip efficiency assumption is split into
    separate charge and discharge efficiencies so replacements can use distinct
    values later.
    """

    if capacity_kwh <= EPS:
        return -np.inf
    eta_charge, eta_discharge = battery_charge_discharge_eta(assumptions)
    dt_h = dt_s / 3600.0
    if battery_terminal_kw >= 0.0:
        delta_kwh = battery_terminal_kw * dt_h / eta_discharge
        return soc - delta_kwh / capacity_kwh
    delta_kwh = (-battery_terminal_kw) * dt_h * eta_charge
    return soc + delta_kwh / capacity_kwh


def dc_bus_input_required(load_dc_kw: float, assumptions: ModelAssumptions) -> float:
    """Source-side DC bus power needed after 1-2% bus/wiring loss."""

    eta_bus = 1.0 - assumptions.bus_loss_frac
    return load_dc_kw / max(eta_bus, EPS)


def battery_degradation_proxy(
    dod: float,
    mean_c_rate: float,
    equivalent_cycles: float,
    assumptions: ModelAssumptions,
) -> float:
    """Conceptual degradation surrogate.

    This is a Section 5.2/15-style proxy because no cell-level test data is
    available at PDR. It increases with depth of discharge, C-rate, and
    equivalent full cycles. The value is dimensionless and intended only for
    relative comparison inside the optimizer.
    """

    dod_term = max(dod, 0.0) ** assumptions.degradation_dod_exponent
    c_term = (1.0 + max(mean_c_rate, 0.0)) ** assumptions.degradation_crate_exponent
    return assumptions.degradation_scale * dod_term * c_term * max(equivalent_cycles, 0.0)


def propulsion_mass_kg(
    config: HardwareConfig,
    assumptions: ModelAssumptions,
    num_motors: int = 1,
) -> Dict[str, float]:
    """Estimate propulsion mass from conceptual specific-power assumptions.

    When *num_motors* > 1 the motor line-item uses the non-linear
    ``motor_mass_per_unit`` model instead of the simple specific-power
    ratio, reflecting the fact that smaller motors carry proportionally
    more fixed overhead mass.
    """

    n = max(int(num_motors), 1)
    battery_energy_mass = (
        config.battery_capacity_kwh * 1000.0 / assumptions.battery_specific_energy_wh_per_kg
    )
    battery_power_mass = config.battery_peak_power_kw / assumptions.battery_power_specific_kw_per_kg
    battery_mass = max(battery_energy_mass, battery_power_mass)

    # Motor mass: use power-law model for multi-motor, keep legacy linear
    # model for N == 1 to preserve exact backward compatibility.
    if n == 1:
        motor_mass = config.motor_rating_kw / assumptions.motor_specific_power_kw_per_kg
    else:
        per_motor_rating = config.motor_rating_kw / n
        motor_mass = n * motor_mass_per_unit(per_motor_rating)

    masses = {
        "turbine": config.turbine_rating_kw / assumptions.turbine_specific_power_kw_per_kg,
        "generator": config.generator_rating_kw / assumptions.generator_specific_power_kw_per_kg,
        "motor": motor_mass,
        "motor_count": float(n),
        "battery": battery_mass,
        "power_electronics": config.motor_rating_kw / assumptions.power_electronics_specific_kw_per_kg,
        "accessories": assumptions.fixed_propulsion_accessory_mass_kg,
    }
    masses["total_propulsion"] = float(
        sum(v for k, v in masses.items() if k != "motor_count")
    )
    return masses


def total_aircraft_mass_kg(
    config: HardwareConfig,
    assumptions: ModelAssumptions,
    payload_mass_kg: float = 200.0,
    allocated_structure_mass_kg: float = 430.0,
    num_motors: int = 1,
) -> float:
    """Return MTOW estimate for optimizer constraint accounting."""

    return (
        payload_mass_kg
        + allocated_structure_mass_kg
        + config.fuel_mass_kg
        + propulsion_mass_kg(config, assumptions, num_motors=num_motors)["total_propulsion"]
    )
