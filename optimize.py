"""NSGA-II multi-objective sizing and EMS optimization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from ems import make_ems
from mission_sim import MissionProfile, simulate_mission
from models import HardwareConfig, ModelAssumptions, propulsion_mass_kg, total_aircraft_mass_kg


@dataclass(frozen=True)
class OptimizationConfig:
    population_size: int = 24
    generations: int = 12
    seed: int = 7
    crossover_prob: float = 0.9
    mutation_eta: float = 20.0
    output_dir: str = "outputs"
    mtow_limit_kg: float = 1000.0
    payload_mass_kg: float = 200.0
    allocated_structure_mass_kg: float = 430.0
    # Bounds: engine, generator, battery capacity, batt peak, fuel, EMS tier,
    # gen setpoint, low SoC, high SoC, max charge C-rate, ECMS factor,
    # num_motors (continuous proxy — discretized in decode_design).
    xl: Tuple[float, ...] = (45.0, 50.0, 10.0, 45.0, 30.0, 1.0, 45.0, 0.25, 0.75, 0.25, 0.05, 0.5)
    xu: Tuple[float, ...] = (90.0, 95.0, 80.0, 120.0, 180.0, 3.99, 85.0, 0.45, 0.98, 2.50, 0.60, 4.49)


DV_NAMES = [
    "turbine_rating_kw",
    "generator_rating_kw",
    "battery_capacity_kwh",
    "battery_peak_power_kw",
    "fuel_mass_kg",
    "ems_tier_raw",
    "generator_setpoint_kw",
    "target_soc_low",
    "target_soc_high",
    "max_charge_c_rate",
    "ecms_equivalence_factor",
    "num_motors_raw",  # continuous [0.5, 4.49]; discretized to {1, 2, 4}
]

OBJ_NAMES = ["neg_endurance_h", "fuel_burned_kg", "degradation_proxy", "neg_efficiency", "total_mass_kg"]

# Candidate motor counts for discretization.
_MOTOR_COUNT_CANDIDATES = [1, 2, 4]


def decode_design(x: np.ndarray) -> tuple[HardwareConfig, Any, Dict[str, float], int]:
    """Map continuous NSGA-II variables into hardware, EMS, and motor count.

    Returns ``(config, ems_policy, vals_dict, num_motors)``.
    """

    vals = {name: float(value) for name, value in zip(DV_NAMES, x)}
    tier = int(np.clip(np.floor(vals["ems_tier_raw"]), 1, 3))
    low = min(vals["target_soc_low"], vals["target_soc_high"] - 0.05)
    high = max(vals["target_soc_high"], low + 0.05)

    # Discretize continuous motor-count proxy to nearest candidate {1, 2, 4}.
    raw_n = vals.get("num_motors_raw", 1.0)
    num_motors = int(min(_MOTOR_COUNT_CANDIDATES, key=lambda c: abs(c - raw_n)))

    # Redundancy note: N >= 2 enables single-motor-failure survivability.
    # This is surfaced as a qualitative note in results rather than a modeled
    # objective.  If a 6th "redundancy score" objective is desired, it can be
    # added here as:  redundancy_score = 1.0 if num_motors >= 2 else 0.0
    # and appended to OBJ_NAMES / objectives.  Not implemented unless asked.

    cfg = HardwareConfig(
        turbine_rating_kw=vals["turbine_rating_kw"],
        generator_rating_kw=vals["generator_rating_kw"],
        battery_capacity_kwh=vals["battery_capacity_kwh"],
        battery_peak_power_kw=vals["battery_peak_power_kw"],
        fuel_mass_kg=vals["fuel_mass_kg"],
    )
    ems = make_ems(
        tier=tier,
        generator_setpoint_kw=vals["generator_setpoint_kw"],
        target_soc_low=low,
        target_soc_high=min(high, 1.0),
        max_charge_c_rate=vals["max_charge_c_rate"],
        equivalence_factor_kg_per_kwh=vals["ecms_equivalence_factor"],
    )
    vals["ems_tier"] = tier
    vals["target_soc_low"] = low
    vals["target_soc_high"] = min(high, 1.0)
    vals["num_motors"] = num_motors
    return cfg, ems, vals, num_motors


def evaluate_design(
    x: np.ndarray,
    mission: MissionProfile,
    assumptions: ModelAssumptions,
    opt_cfg: OptimizationConfig,
) -> tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    cfg, ems, vals, num_motors = decode_design(x)
    result = simulate_mission(
        cfg,
        ems,
        mission=mission,
        assumptions=assumptions,
        stop_on_violation=True,
        payload_mass_kg=opt_cfg.payload_mass_kg,
        allocated_structure_mass_kg=opt_cfg.allocated_structure_mass_kg,
        num_motors=num_motors,
    )
    # Use num_motors-aware mass for the f5 mass objective.
    total_mass = total_aircraft_mass_kg(
        cfg, assumptions, opt_cfg.payload_mass_kg,
        opt_cfg.allocated_structure_mass_kg, num_motors=num_motors,
    )
    objectives = np.array(
        [
            -result.endurance_h,
            result.fuel_burned_kg,
            result.degradation_proxy,
            -result.mission_avg_efficiency,
            total_mass,
        ],
        dtype=float,
    )
    mtow_violation = max(0.0, total_mass - opt_cfg.mtow_limit_kg)
    sim_violation = 0.0 if result.success else 1.0
    constraints = np.array([mtow_violation, sim_violation], dtype=float)
    row = {
        **vals,
        **{name: obj for name, obj in zip(OBJ_NAMES, objectives)},
        "endurance_h": result.endurance_h,
        "efficiency": result.mission_avg_efficiency,
        "mission_success": result.success,
        "first_violation": result.first_violation or "",
        "final_soc": result.final_soc,
        "total_mass_kg": total_mass,
        "num_motors": num_motors,
        "redundancy_note": "Single-motor-failure survivable" if num_motors >= 2 else "No motor redundancy",
    }
    return objectives, constraints, row


def _import_pymoo() -> Dict[str, Any]:
    try:
        from pymoo.algorithms.moo.nsga2 import NSGA2
        from pymoo.core.problem import ElementwiseProblem
        from pymoo.indicators.hv import HV
        from pymoo.operators.crossover.sbx import SBX
        from pymoo.operators.mutation.pm import PM
        from pymoo.optimize import minimize
        from pymoo.termination import get_termination
    except ImportError as exc:
        raise ImportError(
            "pymoo is required for NSGA-II. Install dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc
    return locals()


def run_optimization(
    opt_cfg: OptimizationConfig | None = None,
    mission: MissionProfile | None = None,
    assumptions: ModelAssumptions | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run NSGA-II and write Pareto CSV plus hypervolume log."""

    opt_cfg = opt_cfg or OptimizationConfig()
    mission = mission or MissionProfile()
    assumptions = assumptions or ModelAssumptions()
    pymoo = _import_pymoo()
    ElementwiseProblem = pymoo["ElementwiseProblem"]

    class HybridUAVProblem(ElementwiseProblem):
        def __init__(self) -> None:
            super().__init__(
                n_var=len(DV_NAMES),
                n_obj=len(OBJ_NAMES),
                n_ieq_constr=2,
                xl=np.array(opt_cfg.xl),
                xu=np.array(opt_cfg.xu),
            )

        def _evaluate(self, x: np.ndarray, out: Dict[str, Any], *args: Any, **kwargs: Any) -> None:
            f, g, _ = evaluate_design(x, mission, assumptions, opt_cfg)
            out["F"] = f
            out["G"] = g

    algorithm = pymoo["NSGA2"](
        pop_size=opt_cfg.population_size,
        crossover=pymoo["SBX"](prob=opt_cfg.crossover_prob, eta=15),
        mutation=pymoo["PM"](eta=opt_cfg.mutation_eta),
        eliminate_duplicates=True,
    )
    termination = pymoo["get_termination"]("n_gen", opt_cfg.generations)
    problem = HybridUAVProblem()
    res = pymoo["minimize"](
        problem,
        algorithm,
        termination,
        seed=opt_cfg.seed,
        save_history=True,
        verbose=False,
    )

    rows: List[Dict[str, Any]] = []
    for x in np.atleast_2d(res.X):
        _, _, row = evaluate_design(x, mission, assumptions, opt_cfg)
        rows.append(row)
    pareto = pd.DataFrame(rows)

    hv_rows = []
    ref = np.array([0.0, 250.0, 2.0, 0.0, opt_cfg.mtow_limit_kg + 250.0])
    hv_indicator = pymoo["HV"](ref_point=ref)
    for gen_idx, hist in enumerate(res.history, start=1):
        feasible = hist.pop.get("feasible").ravel()
        fvals = hist.pop.get("F")
        hv = float(hv_indicator(fvals[feasible])) if np.any(feasible) else 0.0
        hv_rows.append({"generation": gen_idx, "hypervolume": hv})
    hv_log = pd.DataFrame(hv_rows)

    out_dir = Path(opt_cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pareto.to_csv(out_dir / "pareto_front.csv", index=False)
    hv_log.to_csv(out_dir / "hypervolume_log.csv", index=False)
    return pareto, hv_log


def select_knee_point(pareto: pd.DataFrame) -> pd.Series:
    """Select a recommended compromise by distance to normalized utopia point."""

    cols = ["neg_endurance_h", "fuel_burned_kg", "degradation_proxy", "neg_efficiency", "total_mass_kg"]
    data = pareto[cols].astype(float)
    span = (data.max() - data.min()).replace(0.0, 1.0)
    normalized = (data - data.min()) / span
    idx = (normalized**2).sum(axis=1).idxmin()
    return pareto.loc[idx]
