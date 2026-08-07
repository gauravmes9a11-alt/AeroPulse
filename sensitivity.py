"""One-parameter-at-a-time sensitivity sweeps."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable, List

import pandas as pd

from ems import RuleBasedEMS
from mission_sim import MissionProfile, simulate_mission
from models import HardwareConfig, ModelAssumptions
from optimize import OptimizationConfig, run_optimization, select_knee_point
from utils.data_loader import _adjust_config_to_mission


def _objective_row(label: str, result) -> dict:
    return {
        "case": label,
        "endurance_h": result.endurance_h,
        "fuel_burned_kg": result.fuel_burned_kg,
        "degradation_proxy": result.degradation_proxy,
        "efficiency": result.mission_avg_efficiency,
        "total_mass_kg": result.total_mass_kg,
    }


def run_fixed_baseline_sensitivity(
    output_dir: str | Path = "outputs",
    deltas: Iterable[float] = (-0.10, 0.0, 0.10),
) -> pd.DataFrame:
    """Sweep SFC, battery specific energy, and motor efficiency on baseline hardware."""

    base_assumptions = ModelAssumptions()
    base_config = HardwareConfig()
    mission = MissionProfile()
    rows: List[dict] = []
    adjusted_base_config = _adjust_config_to_mission(base_config, mission, base_assumptions)
    base = simulate_mission(adjusted_base_config, RuleBasedEMS(), mission, base_assumptions)
    base_row = _objective_row("baseline", base)

    sweeps = {
        "sfc_ref": "sfc_ref_kg_per_kwh",
        "battery_specific_energy": "battery_specific_energy_wh_per_kg",
        "motor_inv_eta_peak": "motor_inv_eta_peak",
        "generator_eta_peak": "generator_eta_peak",
    }
    for sweep_name, attr in sweeps.items():
        nominal = getattr(base_assumptions, attr)
        for delta in deltas:
            assumptions = replace(base_assumptions, **{attr: nominal * (1.0 + delta)})
            adjusted_config = _adjust_config_to_mission(base_config, mission, assumptions)
            result = simulate_mission(adjusted_config, RuleBasedEMS(), mission, assumptions)
            row = _objective_row(f"{sweep_name}_{delta:+.0%}", result)
            row["parameter"] = sweep_name
            row["delta_pct"] = 100.0 * delta
            for obj in ["endurance_h", "fuel_burned_kg", "degradation_proxy", "efficiency", "total_mass_kg"]:
                denom = base_row[obj] if abs(base_row[obj]) > 1e-12 else 1.0
                row[f"{obj}_shift_pct"] = 100.0 * (row[obj] - base_row[obj]) / denom
            rows.append(row)

    df = pd.DataFrame(rows)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "sensitivity_fixed_baseline.csv", index=False)
    return df


def run_optimizer_sensitivity(
    output_dir: str | Path = "outputs",
    deltas: Iterable[float] = (-0.10, 0.10),
    opt_cfg: OptimizationConfig | None = None,
) -> pd.DataFrame:
    """Re-run optimizer for selected parameter perturbations and compare knee points."""

    base_assumptions = ModelAssumptions()
    opt_cfg = opt_cfg or OptimizationConfig(population_size=16, generations=6, output_dir=str(Path(output_dir) / "sens_base"))
    base_pareto, _ = run_optimization(opt_cfg, assumptions=base_assumptions)
    base_knee = select_knee_point(base_pareto)
    rows = []
    sweeps = {
        "sfc_ref": "sfc_ref_kg_per_kwh",
        "battery_specific_energy": "battery_specific_energy_wh_per_kg",
        "motor_inv_eta_peak": "motor_inv_eta_peak",
    }
    for sweep_name, attr in sweeps.items():
        nominal = getattr(base_assumptions, attr)
        for delta in deltas:
            assumptions = replace(base_assumptions, **{attr: nominal * (1.0 + delta)})
            case_dir = Path(output_dir) / f"sens_{sweep_name}_{delta:+.0%}"
            case_cfg = replace(opt_cfg, output_dir=str(case_dir))
            pareto, _ = run_optimization(case_cfg, assumptions=assumptions)
            knee = select_knee_point(pareto)
            row = {"parameter": sweep_name, "delta_pct": 100.0 * delta}
            for obj in ["endurance_h", "fuel_burned_kg", "degradation_proxy", "efficiency", "total_mass_kg"]:
                denom = float(base_knee[obj]) if abs(float(base_knee[obj])) > 1e-12 else 1.0
                row[f"{obj}_shift_pct"] = 100.0 * (float(knee[obj]) - float(base_knee[obj])) / denom
            rows.append(row)
    df = pd.DataFrame(rows)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "sensitivity_optimizer_knee.csv", index=False)
    return df
