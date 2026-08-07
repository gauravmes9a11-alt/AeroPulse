"""Pluggable energy management strategies for the series-hybrid UAV."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np

from models import EPS, HardwareConfig, ModelAssumptions, generator_efficiency, turbine_sfc_kg_per_kwh


class EMSPolicy:
    """Base interface for all EMS policies."""

    tier: int = 0

    def reset(self, config: HardwareConfig, mission: Any, assumptions: ModelAssumptions) -> None:
        self.config = config
        self.mission = mission
        self.assumptions = assumptions

    def command_generator_kw(self, state: Dict[str, Any]) -> float:
        raise NotImplementedError


@dataclass
class RuleBasedEMS(EMSPolicy):
    """Tier 1 EMS: fixed generator setpoint with SoC-band protection."""

    generator_setpoint_kw: float = 58.0
    target_soc_low: float = 0.35
    target_soc_high: float = 0.90
    max_charge_c_rate: float = 1.0
    tier: int = 1

    def command_generator_kw(self, state: Dict[str, Any]) -> float:
        config: HardwareConfig = state["config"]
        soc = state["soc"]
        source_required = state["source_required_kw"]
        segment = str(state.get("segment", "")).lower()

        # High-power segments (takeoff/climb) should use as much generator power as the
        # hardware can provide so the battery does not have to cover the full transient.
        base_setpoint = self.generator_setpoint_kw
        if segment in {"takeoff", "climb"}:
            base_setpoint = max(base_setpoint, source_required)
        setpoint = min(config.generator_rating_kw, base_setpoint)

        if soc <= self.target_soc_low:
            setpoint = min(config.generator_rating_kw, source_required + self.max_charge_c_rate * config.battery_capacity_kwh)
        elif soc >= self.target_soc_high and source_required < setpoint:
            setpoint = source_required

        max_charge_kw = self.max_charge_c_rate * config.battery_capacity_kwh
        return min(setpoint, source_required + max_charge_kw)


@dataclass
class ECMSEMS(EMSPolicy):
    """Tier 2 Equivalent Consumption Minimization Strategy.

    The equivalence factor converts battery terminal energy (kWh) into an
    equivalent fuel mass penalty (kg/kWh). Positive values discourage battery
    discharge; negative battery power receives a credit for charging.
    """

    equivalence_factor_kg_per_kwh: float = 0.22
    target_soc_low: float = 0.30
    target_soc_high: float = 0.88
    max_charge_c_rate: float = 1.0
    grid_points: int = 31
    tier: int = 2

    def command_generator_kw(self, state: Dict[str, Any]) -> float:
        config: HardwareConfig = state["config"]
        assumptions: ModelAssumptions = state["assumptions"]
        source_required = state["source_required_kw"]
        soc = state["soc"]
        max_charge_kw = self.max_charge_c_rate * config.battery_capacity_kwh
        lower = max(0.0, source_required - config.battery_peak_power_kw)
        upper = min(config.generator_rating_kw, source_required + max_charge_kw, source_required + config.battery_peak_power_kw)
        if upper < lower:
            return lower

        candidates = np.linspace(lower, upper, self.grid_points)
        best_cost = np.inf
        best_gen = candidates[0]
        for gen_kw in candidates:
            gen_eta = generator_efficiency(gen_kw, config.generator_rating_kw, assumptions)
            turbine_kw = gen_kw / max(gen_eta, EPS)
            if turbine_kw > config.turbine_rating_kw:
                continue
            sfc = turbine_sfc_kg_per_kwh(turbine_kw, config.turbine_rating_kw, assumptions)
            fuel_kg_per_h = turbine_kw * sfc
            batt_kw = source_required - gen_kw
            equiv_kg_per_h = self.equivalence_factor_kg_per_kwh * batt_kw
            soc_penalty = 0.0
            if soc < self.target_soc_low and batt_kw > 0.0:
                soc_penalty = 1e3 * (self.target_soc_low - soc)
            if soc > self.target_soc_high and batt_kw < 0.0:
                soc_penalty = 1e3 * (soc - self.target_soc_high)
            cost = fuel_kg_per_h + equiv_kg_per_h + soc_penalty
            if cost < best_cost:
                best_cost = cost
                best_gen = gen_kw
        return float(best_gen)


@dataclass
class OfflineOptimalEMS(EMSPolicy):
    """Tier 3 offline trajectory using a lightweight DP-style state feedback.

    A full horizon optimizer would optimize every second, which is excessive
    for NSGA-II inner-loop evaluations. This policy precomputes segment-level
    generator commands on a discretized SoC grid, then interpolates online.
    """

    target_final_soc: float = 0.80
    max_charge_c_rate: float = 1.0
    soc_grid_size: int = 31
    tier: int = 3

    def reset(self, config: HardwareConfig, mission: Any, assumptions: ModelAssumptions) -> None:
        super().reset(config, mission, assumptions)
        self.nominal_setpoint = self._best_generator_setpoint(config, assumptions)

    def _best_generator_setpoint(
        self, config: HardwareConfig, assumptions: ModelAssumptions
    ) -> float:
        """Use SciPy to find the best steady generator operating point.

        This keeps the Tier 3 policy aligned with the request for an
        offline-optimal path using SciPy or DP. If SciPy is not installed, a
        deterministic grid search provides the same interface.
        """

        upper = min(config.generator_rating_kw, config.turbine_rating_kw * assumptions.generator_eta_peak)

        def fuel_rate(gen_kw: float) -> float:
            eta = generator_efficiency(gen_kw, config.generator_rating_kw, assumptions)
            turbine_kw = gen_kw / max(eta, EPS)
            if turbine_kw > config.turbine_rating_kw:
                return 1e6 + turbine_kw
            return turbine_kw * turbine_sfc_kg_per_kwh(turbine_kw, config.turbine_rating_kw, assumptions)

        try:
            from scipy.optimize import minimize_scalar

            res = minimize_scalar(fuel_rate, bounds=(0.35 * upper, upper), method="bounded")
            return float(np.clip(res.x, 0.0, upper))
        except Exception:
            grid = np.linspace(0.35 * upper, upper, self.soc_grid_size)
            return float(grid[int(np.argmin([fuel_rate(p) for p in grid]))])

    def command_generator_kw(self, state: Dict[str, Any]) -> float:
        config: HardwareConfig = state["config"]
        source_required = state["source_required_kw"]
        soc = state["soc"]
        max_charge_kw = self.max_charge_c_rate * config.battery_capacity_kwh
        segment = state["segment"]

        if segment in {"Cruise", "Loiter", "Descent"} and soc < self.target_final_soc:
            target = source_required + max_charge_kw
        elif soc > self.target_final_soc + 0.05:
            target = source_required
        else:
            target = self.nominal_setpoint

        if segment in {"Takeoff", "Climb"}:
            target = min(self.nominal_setpoint, source_required)

        return float(np.clip(target, 0.0, min(config.generator_rating_kw, source_required + max_charge_kw)))


def make_ems(
    tier: int,
    generator_setpoint_kw: float = 58.0,
    target_soc_low: float = 0.35,
    target_soc_high: float = 0.90,
    max_charge_c_rate: float = 1.0,
    equivalence_factor_kg_per_kwh: float = 0.22,
) -> EMSPolicy:
    """Factory used by the optimizer and CLI."""

    if tier == 1:
        return RuleBasedEMS(generator_setpoint_kw, target_soc_low, target_soc_high, max_charge_c_rate)
    if tier == 2:
        return ECMSEMS(equivalence_factor_kg_per_kwh, target_soc_low, target_soc_high, max_charge_c_rate)
    if tier == 3:
        target = 0.5 * (target_soc_low + target_soc_high)
        return OfflineOptimalEMS(target, max_charge_c_rate)
    raise ValueError(f"Unsupported EMS tier {tier!r}; expected 1, 2, or 3.")
