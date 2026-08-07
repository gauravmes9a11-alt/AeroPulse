"""Cached adapters between Streamlit pages and the simulation backend."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd
import streamlit as st

from ems import make_ems
from mission_sim import MissionProfile, SimulationResult, simulate_mission
from models import (
    EPS,
    HardwareConfig,
    ModelAssumptions,
    dc_bus_input_required,
    generator_efficiency,
    motor_inverter_efficiency,
    propulsion_mass_kg,
)
from optimize import OptimizationConfig, run_optimization


# Map sidebar allocation labels to internal strategy strings.
ALLOCATION_LABEL_TO_KEY = {
    "Even Split Across Motors": "even_split",
    "Efficiency-Optimal (Shutdown Idle Motors)": "efficiency_optimal",
}
ALLOCATION_KEY_TO_LABEL = {v: k for k, v in ALLOCATION_LABEL_TO_KEY.items()}


OUTPUT_DIR = Path("outputs")
PARETO_PATH = OUTPUT_DIR / "pareto_front.csv"
SENSITIVITY_PATH = OUTPUT_DIR / "sensitivity_fixed_baseline.csv"


EMS_LABEL_TO_TIER = {
    "Rule-Based": 1,
    "ECMS": 2,
    "Offline-Optimal": 3,
}


def default_config() -> Dict[str, Any]:
    """Return dashboard defaults aligned with the conceptual baseline."""

    return {
        "turbine_rating_kw": 60.0,
        "generator_rating_kw": 65.0,
        "battery_capacity_kwh": 24.0,
        "battery_peak_power_kw": 65.0,
        "fuel_mass_kg": 80.0,
        "num_motors": 1,
        "ems_label": "Rule-Based",
        "generator_setpoint_kw": 58.0,
        "target_soc_low": 0.35,
        "target_soc_high": 0.90,
        "max_charge_c_rate": 1.0,
        "ecms_equivalence_factor": 0.22,
        "motor_allocation": "even_split",
    }


def ensure_session_defaults() -> None:
    """Initialize shared Streamlit session values once."""

    st.session_state.setdefault("theme_mode", "Dark")
    cfg = st.session_state.setdefault("selected_config", default_config())
    # Backward compat: ensure keys added in later versions are present.
    cfg.setdefault("num_motors", 1)
    cfg.setdefault("motor_allocation", "even_split")


def _adjust_config_to_mission(cfg: HardwareConfig, mission: MissionProfile, assumptions: ModelAssumptions) -> HardwareConfig:
    """Scale generator and battery ratings so the selected hardware can satisfy the mission peaks."""

    adjusted = cfg
    for segment in [*mission.fixed_segments(), mission.loiter_segment(), *mission.terminal_segments()]:
        if segment.duration_s is None:
            continue
        demand_kw = float(segment.power_kw)
        motor_eta = motor_inverter_efficiency(demand_kw, adjusted.motor_rating_kw, assumptions)
        load_dc_kw = demand_kw / max(motor_eta, EPS)
        source_required_kw = dc_bus_input_required(load_dc_kw, assumptions)

        min_gen_kw = max(0.0, source_required_kw - adjusted.battery_peak_power_kw)
        min_batt_peak_kw = max(0.0, source_required_kw - adjusted.generator_rating_kw)
        if adjusted.generator_rating_kw < min_gen_kw:
            adjusted = replace(adjusted, generator_rating_kw=float(min_gen_kw))
        if adjusted.battery_peak_power_kw < min_batt_peak_kw:
            adjusted = replace(adjusted, battery_peak_power_kw=float(min_batt_peak_kw))

        gen_eta = generator_efficiency(adjusted.generator_rating_kw, adjusted.generator_rating_kw, assumptions)
        required_turbine_kw = adjusted.generator_rating_kw / max(gen_eta, EPS)
        if adjusted.turbine_rating_kw < required_turbine_kw:
            adjusted = replace(adjusted, turbine_rating_kw=float(required_turbine_kw))

    return adjusted


def config_from_state(config_state: Dict[str, Any]) -> Tuple[HardwareConfig, Any]:
    """Build backend hardware and EMS objects from dashboard state."""

    tier = EMS_LABEL_TO_TIER.get(config_state.get("ems_label", "Rule-Based"), 1)
    assumptions = ModelAssumptions()
    cfg = HardwareConfig(
        turbine_rating_kw=float(config_state["turbine_rating_kw"]),
        generator_rating_kw=float(config_state["generator_rating_kw"]),
        battery_capacity_kwh=float(config_state["battery_capacity_kwh"]),
        battery_peak_power_kw=float(config_state["battery_peak_power_kw"]),
        fuel_mass_kg=float(config_state["fuel_mass_kg"]),
    )
    cfg = _adjust_config_to_mission(cfg, MissionProfile(), assumptions)
    ems = make_ems(
        tier=tier,
        generator_setpoint_kw=float(config_state.get("generator_setpoint_kw", 58.0)),
        target_soc_low=float(config_state.get("target_soc_low", 0.35)),
        target_soc_high=float(config_state.get("target_soc_high", 0.90)),
        max_charge_c_rate=float(config_state.get("max_charge_c_rate", 1.0)),
        equivalence_factor_kg_per_kwh=float(config_state.get("ecms_equivalence_factor", 0.22)),
    )
    return cfg, ems


def _history_to_frame(history: Dict[str, Any]) -> pd.DataFrame:
    df = pd.DataFrame(history)
    if not df.empty:
        df["time_h"] = df["time_s"] / 3600.0
        df["battery_discharge_kw"] = df["battery_kw"].clip(lower=0.0)
        df["battery_charge_kw"] = (-df["battery_kw"].clip(upper=0.0))
    return df


def _result_summary(result: SimulationResult) -> Dict[str, Any]:
    return {
        "success": result.success,
        "first_violation": result.first_violation or "",
        "fuel_burned_kg": result.fuel_burned_kg,
        "endurance_h": result.endurance_h,
        "final_soc": result.final_soc,
        "mission_avg_efficiency": result.mission_avg_efficiency,
        "degradation_proxy": result.degradation_proxy,
        "total_mass_kg": result.total_mass_kg,
        "diagnostics": result.diagnostics,
    }


@st.cache_data(show_spinner=False)
def run_simulation_cached(config_state: Dict[str, Any]) -> Tuple[Dict[str, Any], pd.DataFrame]:
    """Run and cache a one-Hz mission simulation."""

    cfg, ems = config_from_state(config_state)
    num_motors = int(config_state.get("num_motors", 1))
    motor_allocation = str(config_state.get("motor_allocation", "even_split"))
    result = simulate_mission(
        cfg, ems, mission=MissionProfile(), assumptions=ModelAssumptions(),
        num_motors=num_motors, motor_allocation=motor_allocation,
    )
    return _result_summary(result), _history_to_frame(result.history)


@st.cache_data(show_spinner=False)
def load_pareto_csv(path: str = str(PARETO_PATH)) -> pd.DataFrame:
    """Load Pareto front if it exists, otherwise return an empty frame."""

    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path)


@st.cache_data(show_spinner=False)
def load_sensitivity_csv(path: str = str(SENSITIVITY_PATH)) -> pd.DataFrame:
    """Load sensitivity output if it exists, otherwise return an empty frame."""

    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path)


@st.cache_resource(show_spinner=False)
def run_optimization_cached(population_size: int, generations: int, seed: int) -> pd.DataFrame:
    """Run NSGA-II only when the caller explicitly requests it."""

    opt_cfg = OptimizationConfig(
        population_size=int(population_size),
        generations=int(generations),
        seed=int(seed),
        output_dir=str(OUTPUT_DIR),
    )
    pareto, _ = run_optimization(opt_cfg)
    load_pareto_csv.clear()
    return pareto


def pareto_row_to_config(row: pd.Series) -> Dict[str, Any]:
    """Convert an optimizer row into dashboard configuration state."""

    tier = int(row.get("ems_tier", 1))
    label = {1: "Rule-Based", 2: "ECMS", 3: "Offline-Optimal"}.get(tier, "Rule-Based")
    cfg = default_config()
    for key in [
        "turbine_rating_kw",
        "generator_rating_kw",
        "battery_capacity_kwh",
        "battery_peak_power_kw",
        "fuel_mass_kg",
        "generator_setpoint_kw",
        "target_soc_low",
        "target_soc_high",
        "max_charge_c_rate",
    ]:
        if key in row and pd.notna(row[key]):
            cfg[key] = float(row[key])
    if "ecms_equivalence_factor" in row and pd.notna(row["ecms_equivalence_factor"]):
        cfg["ecms_equivalence_factor"] = float(row["ecms_equivalence_factor"])
    if "num_motors" in row and pd.notna(row["num_motors"]):
        cfg["num_motors"] = int(row["num_motors"])
    cfg["ems_label"] = label
    return cfg


def mission_csv_bytes(history_df: pd.DataFrame) -> bytes:
    return history_df.to_csv(index=False).encode("utf-8")


def pareto_csv_bytes(pareto_df: pd.DataFrame) -> bytes:
    return pareto_df.to_csv(index=False).encode("utf-8")
