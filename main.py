"""CLI entry point for baseline validation, optimization, and plots."""

from __future__ import annotations

import argparse
from pathlib import Path

from ems import RuleBasedEMS
from mission_sim import MissionProfile, climb_energy_balance, simulate_mission
from models import HardwareConfig, ModelAssumptions
from optimize import OptimizationConfig, run_optimization, select_knee_point


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hybrid-electric UAV propulsion simulation and NSGA-II optimization")
    parser.add_argument("--output-dir", default="outputs", help="Directory for CSV and plot outputs")
    parser.add_argument("--pop", type=int, default=24, help="NSGA-II population size")
    parser.add_argument("--gens", type=int, default=12, help="NSGA-II generations")
    parser.add_argument("--seed", type=int, default=7, help="Random seed")
    parser.add_argument("--skip-optimization", action="store_true", help="Run baseline validation only")
    parser.add_argument("--skip-plots", action="store_true", help="Do not generate matplotlib plots")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    assumptions = ModelAssumptions()
    mission = MissionProfile()
    from utils.data_loader import _adjust_config_to_mission
    config = _adjust_config_to_mission(HardwareConfig(), mission, assumptions)
    ems = RuleBasedEMS(generator_setpoint_kw=58.0, target_soc_low=0.35, target_soc_high=0.90)

    result = simulate_mission(config, ems, mission=mission, assumptions=assumptions)
    print("Baseline validation: Tier 1 EMS, baseline hardware")
    print(f"  success: {result.success}")
    print(f"  first violation: {result.first_violation or 'none'}")
    print(f"  endurance: {result.endurance_h:.2f} h")
    print(f"  fuel burned: {result.fuel_burned_kg:.2f} kg")
    print(f"  final SoC: {result.final_soc:.3f}")
    print(f"  mission average efficiency: {result.mission_avg_efficiency:.3f}")
    print(f"  degradation proxy: {result.degradation_proxy:.5f}")
    print(f"  total mass: {result.total_mass_kg:.1f} kg")

    balance = climb_energy_balance(config, ems, mission, assumptions)
    print("\nClimb segment sanity-check energy balance")
    for key, value in balance.items():
        print(f"  {key}: {value:.3f}")

    if not args.skip_plots:
        try:
            from plots import plot_fuel_remaining, plot_mission_timeline, plot_power_split, plot_soc_profile

            plot_mission_timeline(result.history, out)
            plot_soc_profile(result.history, out)
            plot_fuel_remaining(result.history, out)
            plot_power_split(result.history, out)
        except ImportError as exc:
            print(f"\nPlot generation skipped: {exc}")

    if args.skip_optimization:
        return

    opt_cfg = OptimizationConfig(
        population_size=args.pop,
        generations=args.gens,
        seed=args.seed,
        output_dir=str(out),
    )
    try:
        pareto, hv_log = run_optimization(opt_cfg, mission, assumptions)
    except ImportError as exc:
        print(f"\nOptimization skipped: {exc}")
        return
    knee = select_knee_point(pareto)
    print("\nNSGA-II complete")
    print(f"  Pareto points: {len(pareto)}")
    print(f"  CSV: {out / 'pareto_front.csv'}")
    print(f"  Hypervolume log: {out / 'hypervolume_log.csv'}")
    print("  Recommended knee-point candidate:")
    for key in ["endurance_h", "fuel_burned_kg", "degradation_proxy", "efficiency", "total_mass_kg", "ems_tier"]:
        print(f"    {key}: {knee[key]}")

    if not args.skip_plots:
        try:
            from plots import plot_pareto_front

            plot_pareto_front(pareto, out)
        except ImportError as exc:
            print(f"\nPareto plot skipped: {exc}")


if __name__ == "__main__":
    main()
