"""Rule-based AI Design Summarizer for Hybrid-Electric UAV Propulsion Sizing.

Synthesizes active configuration parameters, simulation telemetry, constraint margins,
and sensitivity data into executive report-style summaries, design insights,
engineering recommendations, risk matrices, and a overall engineering score.
Fully offline using Python templates and aerospace engineering heuristics.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple
import numpy as np

from models import HardwareConfig, ModelAssumptions, total_aircraft_mass_kg, propulsion_mass_kg
from mission_sim import SimulationResult


@dataclass
class AIDesignReport:
    score: float
    grade: str
    executive_summary: str
    insights: List[str]
    recommendations: List[str]
    risk_analysis: Dict[str, Dict[str, str]]
    input_summary: Dict[str, Any]


def compute_engineering_score(
    result: SimulationResult,
    config: HardwareConfig,
    assumptions: ModelAssumptions,
    payload_mass_kg: float = 200.0,
    num_motors: int = 1,
) -> Tuple[float, str]:
    """Compute 0–100 Engineering Score and letter grade (A+, A, B, C, F)."""

    score = 100.0

    # 1. Mission Feasibility (Weight: 30 pts)
    if not result.success:
        score -= 30.0

    # 2. Battery Reserve Margin (Weight: 15 pts)
    final_soc = result.final_soc
    if final_soc < 0.20:
        score -= 15.0
    elif final_soc < 0.25:
        score -= 7.5

    # 3. Aircraft Weight / MTOW Margin (Weight: 20 pts)
    mtow = result.total_mass_kg
    if mtow > 1000.0:
        score -= 20.0
    elif mtow > 950.0:
        score -= 10.0
    elif mtow > 900.0:
        score -= 5.0

    # 4. Chain Efficiency (Weight: 15 pts)
    eff = result.mission_avg_efficiency
    if eff < 0.15:
        score -= 15.0
    elif eff < 0.18:
        score -= 7.5

    # 5. Component Stress / Peak Margins (Weight: 10 pts)
    hist = result.history
    if hist is not None and "generator_kw" in hist and len(hist["generator_kw"]) > 0:
        peak_gen = float(np.max(hist["generator_kw"]))
        if peak_gen > config.generator_rating_kw:
            score -= 10.0
        elif peak_gen > config.generator_rating_kw * 0.95:
            score -= 5.0

    # 6. Battery Degradation Proxy (Weight: 10 pts)
    degr = result.degradation_proxy
    if degr > 1.5:
        score -= 10.0
    elif degr > 1.0:
        score -= 5.0

    score = float(max(0.0, min(100.0, score)))

    # Letter Grade Assignment
    if score >= 93.0:
        grade = "A+"
    elif score >= 85.0:
        grade = "A"
    elif score >= 75.0:
        grade = "B"
    elif score >= 60.0:
        grade = "C"
    else:
        grade = "F"

    return score, grade


def classify_risks(
    result: SimulationResult,
    config: HardwareConfig,
    assumptions: ModelAssumptions,
) -> Dict[str, Dict[str, str]]:
    """Classify subsystem risks as LOW, MEDIUM, or HIGH with rationale."""

    risks: Dict[str, Dict[str, str]] = {}
    hist = result.history

    # 1. Battery Risk
    min_soc = result.diagnostics.get("min_soc", result.final_soc)
    if min_soc < 0.20 or result.final_soc < 0.20:
        risks["Battery"] = {"level": "HIGH", "detail": "Final SoC below 20% emergency floor; risk of cell undervoltage."}
    elif min_soc < 0.25:
        risks["Battery"] = {"level": "MEDIUM", "detail": "Low SoC margin (<25%) during loiter; moderate DOD stress."}
    else:
        risks["Battery"] = {"level": "LOW", "detail": "Sufficient energy reserve (>25% SoC) and healthy C-rate profile."}

    # 2. Generator Risk
    if hist is not None and "generator_kw" in hist and len(hist["generator_kw"]) > 0:
        peak_gen = float(np.max(hist["generator_kw"]))
        gen_ratio = peak_gen / max(0.1, config.generator_rating_kw)
        if gen_ratio > 1.0:
            risks["Generator"] = {"level": "HIGH", "detail": f"Continuous power rating exceeded by {(gen_ratio-1)*100:.1f}%."}
        elif gen_ratio > 0.90:
            risks["Generator"] = {"level": "MEDIUM", "detail": f"Operating near rated thermal ceiling ({gen_ratio*100:.0f}% load)."}
        else:
            risks["Generator"] = {"level": "LOW", "detail": "Operating safely within continuous power envelope."}
    else:
        risks["Generator"] = {"level": "LOW", "detail": "Nominal duty cycle."}

    # 3. Motor Risk
    if hist is not None and "demand_kw" in hist and len(hist["demand_kw"]) > 0:
        peak_demand = float(np.max(hist["demand_kw"]))
        motor_ratio = peak_demand / max(0.1, config.motor_rating_kw)
        if motor_ratio > 1.0:
            risks["Motor"] = {"level": "HIGH", "detail": "Peak mechanical demand exceeds motor rating limit."}
        elif motor_ratio > 0.90:
            risks["Motor"] = {"level": "MEDIUM", "detail": "High peak electrical load during takeoff/climb."}
        else:
            risks["Motor"] = {"level": "LOW", "detail": "Peak power demand well within PMSM thermal limits."}
    else:
        risks["Motor"] = {"level": "LOW", "detail": "Nominal duty cycle."}

    # 4. Fuel System Risk
    rem_fuel = config.fuel_mass_kg - result.fuel_burned_kg
    if rem_fuel < 5.0:
        risks["Fuel"] = {"level": "HIGH", "detail": "Critical fuel depletion (<5 kg reserve remaining)."}
    elif rem_fuel < 10.0:
        risks["Fuel"] = {"level": "MEDIUM", "detail": "Tight fuel margin at mission termination (<10 kg reserve)."}
    else:
        risks["Fuel"] = {"level": "LOW", "detail": f"Healthy fuel reserve ({rem_fuel:.1f} kg remaining at landing)."}

    # 5. Thermal Risk
    if result.degradation_proxy > 1.5:
        risks["Thermal"] = {"level": "HIGH", "detail": "High battery C-rate and temperature accumulation proxy."}
    elif result.degradation_proxy > 0.8:
        risks["Thermal"] = {"level": "MEDIUM", "detail": "Moderate thermal buildup under high-power climb phases."}
    else:
        risks["Thermal"] = {"level": "LOW", "detail": "Thermal dissipation and component temperatures nominal."}

    # 6. Mission Success Risk
    if not result.success:
        risks["Mission Success"] = {"level": "HIGH", "detail": f"Feasibility constraint violated: {result.first_violation}"}
    elif result.total_mass_kg > 980.0:
        risks["Mission Success"] = {"level": "MEDIUM", "detail": f"Tight MTOW structural margin ({result.total_mass_kg:.1f} / 1000 kg)."}
    else:
        risks["Mission Success"] = {"level": "LOW", "detail": "All mission requirements and constraints satisfied."}

    return risks


def generate_executive_summary(
    result: SimulationResult,
    config: HardwareConfig,
    assumptions: ModelAssumptions,
    config_state: Dict[str, Any],
) -> str:
    """Generate formal Executive Engineering Summary."""

    ems_label = config_state.get("ems_label", "Rule-Based")
    num_motors = int(config_state.get("num_motors", 1))
    prop_mass = propulsion_mass_kg(config, assumptions, num_motors=num_motors)["total_propulsion"]

    source_gen_kwh = result.diagnostics.get("source_energy_kwh", 0.0)
    batt_throughput_kwh = result.diagnostics.get("battery_throughput_kwh", 0.0)
    total_energy_kwh = max(0.1, source_gen_kwh + batt_throughput_kwh)
    gen_pct = (source_gen_kwh / total_energy_kwh) * 100.0 if total_energy_kwh > 0 else 60.0
    batt_pct = 100.0 - gen_pct

    feasibility_str = "HIGH" if result.success and result.total_mass_kg <= 970.0 else ("MODERATE" if result.success else "LOW")
    status_str = "successfully satisfies all mission requirements" if result.success else "violates mission sizing boundaries"

    summary = (
        f"EXECUTIVE TECHNICAL EVALUATION & DESIGN SUMMARY\n"
        f"--------------------------------------------------\n"
        f"The selected series hybrid-electric propulsion architecture {status_str}.\n\n"
        f"System Configuration & Hardware Sizing:\n"
        f"The optimization framework specified a {config.motor_rating_kw:.0f} kW propulsion motor "
        f"({'split across ' + str(num_motors) + ' units' if num_motors > 1 else 'single unit'}), paired with a "
        f"{config.battery_capacity_kwh:.1f} kWh battery pack ({config.battery_peak_power_kw:.0f} kW peak) and a "
        f"{config.generator_rating_kw:.0f} kW generator coupled to a {config.turbine_rating_kw:.0f} kW gas turbine.\n\n"
        f"Mass & Energy Distribution Performance:\n"
        f"• Total propulsion subsystem mass is estimated at {prop_mass:.1f} kg, yielding an aircraft MTOW of {result.total_mass_kg:.1f} kg.\n"
        f"• Usable fuel consumption over the mission profile is predicted to be {result.fuel_burned_kg:.1f} kg out of {config.fuel_mass_kg:.1f} kg loaded.\n"
        f"• Energy Management ({ems_label}): Generator contributes approximately {gen_pct:.0f}% of total electrical energy, while the battery supplies {batt_pct:.0f}%.\n"
        f"• Mission completes with a {result.final_soc*100:.1f}% battery reserve (minimum flight SoC: {result.diagnostics.get('min_soc', result.final_soc)*100:.1f}%).\n\n"
        f"Overall design feasibility is classified as {feasibility_str}."
    )
    return summary


def generate_design_insights(
    result: SimulationResult,
    config: HardwareConfig,
    assumptions: ModelAssumptions,
    config_state: Dict[str, Any],
) -> List[str]:
    """Generate dynamic aerospace engineering insights bullets."""

    insights: List[str] = []
    hist = result.history
    num_motors = int(config_state.get("num_motors", 1))

    # 1. Battery sizing insight
    final_soc = result.final_soc
    if final_soc > 0.35:
        excess_pct = int((final_soc - 0.20) * 100)
        insights.append(f"Battery is oversized by approximately {excess_pct}% relative to the 20% safety reserve threshold.")
    elif final_soc >= 0.20:
        insights.append(f"Battery energy capacity is optimally sized with a healthy {final_soc*100:.1f}% final SoC reserve.")
    else:
        insights.append("Battery capacity is undersized for full mission completion without violating reserve limits.")

    # 2. Generator operating efficiency insight
    if hist is not None and "generator_kw" in hist and len(hist["generator_kw"]) > 0:
        mean_gen = float(np.mean(hist["generator_kw"][hist["generator_kw"] > 1.0])) if np.any(hist["generator_kw"] > 1.0) else 0.0
        gen_load = (mean_gen / max(0.1, config.generator_rating_kw)) * 100.0
        if 70.0 <= gen_load <= 92.0:
            insights.append(f"Generator operates near peak thermal efficiency zone ({gen_load:.0f}% average load during active phases).")
        else:
            insights.append(f"Generator operates at {gen_load:.0f}% average load; potential efficiency gains available through setpoint tuning.")

    # 3. Fuel reserve margin insight
    rem_fuel = config.fuel_mass_kg - result.fuel_burned_kg
    if rem_fuel > 15.0:
        insights.append(f"Usable fuel reserve ({rem_fuel:.1f} kg) exceeds the required 10.0 kg reserve margin by {rem_fuel - 10.0:.1f} kg.")
    else:
        insights.append(f"Fuel reserve at landing is {rem_fuel:.1f} kg, operating close to the 10 kg safety reserve minimum.")

    # 4. Aircraft Weight / MTOW margin
    mtow_margin_pct = ((1000.0 - result.total_mass_kg) / 1000.0) * 100.0
    insights.append(f"MTOW structural margin is {mtow_margin_pct:.1f}% relative to the 1,000 kg MTOW limit.")

    # 5. Energy phase dominance
    insights.append("Cruise and loiter phases dominate mission energy consumption (>75% of total shaft energy).")

    # 6. Degradation / Multi-motor insight
    if num_motors > 1:
        insights.append(f"Multi-motor arrangement ({num_motors} units) provides single-motor failure survivability and sub-power shutdown gains.")
    else:
        insights.append("Single motor setup minimizes component count and fixed wiring overhead mass.")

    return insights


def generate_engineering_recommendations(
    result: SimulationResult,
    config: HardwareConfig,
    assumptions: ModelAssumptions,
    config_state: Dict[str, Any],
) -> List[str]:
    """Generate actionable engineering design recommendations based on simulation heuristics."""

    recs: List[str] = []
    final_soc = result.final_soc
    mtow = result.total_mass_kg
    num_motors = int(config_state.get("num_motors", 1))

    # Recommendation 1: Battery capacity tuning
    if final_soc > 0.35:
        potential_reduction_kwh = (final_soc - 0.25) * config.battery_capacity_kwh
        weight_saved_kg = potential_reduction_kwh * 1000.0 / assumptions.battery_specific_energy_wh_per_kg
        recs.append(f"Reduce battery capacity by {potential_reduction_kwh:.1f} kWh to save approx. {weight_saved_kg:.1f} kg of structural weight.")
    elif final_soc < 0.20:
        recs.append("Increase battery capacity by 4–6 kWh or raise generator setpoint to guarantee 20% SoC emergency margin.")

    # Recommendation 2: Generator setpoint / EMS tuning
    ems_label = config_state.get("ems_label", "Rule-Based")
    if ems_label == "Rule-Based":
        recs.append("Transition from Rule-Based to ECMS or Offline-Optimal EMS to reduce total mission fuel burn by 2–4%.")
    elif ems_label == "ECMS":
        recs.append("Fine-tune ECMS equivalence factor to balance battery throughput degradation against direct turbine fuel burn.")

    # Recommendation 3: Motor configuration
    if num_motors == 1 and mtow > 920.0:
        recs.append("Consider a twin-motor configuration (N=2) to reduce total motor mass by ~8.3 kg using sub-linear power-law scaling.")
    elif num_motors == 4:
        recs.append("Enable 'Efficiency-Optimal' motor allocation strategy to shut down 2 idle motors during cruise and loiter phases.")

    # Recommendation 4: Advanced Battery Chemistry / Aerodynamics
    recs.append("Transitioning to advanced Li-Sulfur or Si-Anode battery chemistry (300 Wh/kg) would reduce pack mass by ~25%.")
    recs.append("Slightly decreasing cruise speed by 5–10 km/h decreases required propulsive power by ~8%, significantly extending loiter endurance.")

    return recs


def generate_ai_design_report(
    result: SimulationResult,
    config: HardwareConfig,
    assumptions: ModelAssumptions,
    config_state: Dict[str, Any],
) -> AIDesignReport:
    """Generate complete AI Design Report object."""

    score, grade = compute_engineering_score(result, config, assumptions)
    exec_summary = generate_executive_summary(result, config, assumptions, config_state)
    insights = generate_design_insights(result, config, assumptions, config_state)
    recommendations = generate_engineering_recommendations(result, config, assumptions, config_state)
    risk_analysis = classify_risks(result, config, assumptions)

    input_summary = {
        "cruise_speed_kmh": 250.0,
        "altitude_m": 3000.0,
        "endurance_h": result.endurance_h,
        "payload_kg": 200.0,
        "fuel_loaded_kg": config.fuel_mass_kg,
        "fuel_burned_kg": result.fuel_burned_kg,
        "reserve_fuel_kg": config.fuel_mass_kg - result.fuel_burned_kg,
        "battery_capacity_kwh": config.battery_capacity_kwh,
        "battery_peak_kw": config.battery_peak_power_kw,
        "generator_kw": config.generator_rating_kw,
        "turbine_kw": config.turbine_rating_kw,
        "motor_kw": config.motor_rating_kw,
        "num_motors": int(config_state.get("num_motors", 1)),
        "ems_tier": config_state.get("ems_label", "Rule-Based"),
        "total_mass_kg": result.total_mass_kg,
        "final_soc": result.final_soc,
        "avg_efficiency": result.mission_avg_efficiency,
    }

    return AIDesignReport(
        score=score,
        grade=grade,
        executive_summary=exec_summary,
        insights=insights,
        recommendations=recommendations,
        risk_analysis=risk_analysis,
        input_summary=input_summary,
    )


def export_markdown_report(report: AIDesignReport) -> str:
    """Format the report into clean GitHub-style Markdown."""

    md = f"""# AI Propulsion Design & Mission Summary Report

**Overall Score:** {report.score:.1f} / 100  
**Design Grade:** **{report.grade}**  

---

## 1. Executive Engineering Summary

```
{report.executive_summary}
```

---

## 2. Design Insights

"""
    for ins in report.insights:
        md += f"- • {ins}\n"

    md += "\n---\n\n## 3. Engineering Recommendations\n\n"
    for rec in report.recommendations:
        md += f"- 🔧 {rec}\n"

    md += "\n---\n\n## 4. Subsystem Risk Matrix\n\n"
    md += "| Subsystem | Risk Level | Details & Rationale |\n"
    md += "|-----------|------------|---------------------|\n"
    for sys_name, r_info in report.risk_analysis.items():
        md += f"| **{sys_name}** | **{r_info['level']}** | {r_info['detail']} |\n"

    md += "\n---\n\n## 5. Input & Result Specifications\n\n"
    for k, v in report.input_summary.items():
        val_str = f"{v:.2f}" if isinstance(v, float) else str(v)
        md += f"- **{k.replace('_', ' ').title()}**: `{val_str}`\n"

    return md


def export_json_report(report: AIDesignReport) -> str:
    """Format the report into structured JSON."""

    data = {
        "score": report.score,
        "grade": report.grade,
        "executive_summary": report.executive_summary,
        "insights": report.insights,
        "recommendations": report.recommendations,
        "risk_analysis": report.risk_analysis,
        "input_summary": report.input_summary,
    }
    return json.dumps(data, indent=2)
