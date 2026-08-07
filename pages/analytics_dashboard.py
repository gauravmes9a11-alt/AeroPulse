"""Analytics Dashboard displaying detailed performance summaries and constraint satisfactions."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from components.theme import palette, plotly_template, kpi_card
from models import ModelAssumptions, propulsion_mass_kg
from utils.data_loader import config_from_state


def peak_discharge_str(val: float) -> str:
    return f"{val:.1f} kW" if val > 0.05 else "0.0 kW"


def peak_charge_str(val: float) -> str:
    return f"{val:.1f} kW" if val > 0.05 else "0.0 kW"


def render() -> None:
    st.title("Mission Analytics Dashboard")
    st.caption("Comprehensive analysis of mission metrics, energy balance, component efficiencies, and regulatory constraint diagnostics.")

    history = st.session_state.get("last_history_df")
    if history is None or history.empty:
        st.info("💡 Run a mission simulation from the **Mission Overview** page first to generate analytics reports.")
        return

    summary = st.session_state.get("last_simulation")
    cfg = st.session_state.get("selected_config") or {}
    assumptions = ModelAssumptions()
    if not cfg:
        st.info("No hardware configuration is available yet. Run a simulation from Mission Overview first.")
        return

    # 1. FEASIBILITY & REGULATORY CONSTRAINTS SATISFACTION
    st.markdown("### 1. Sizing Constraint Evaluation")
    
    # We will construct a clean table showing each constraint and whether it was violated
    constraints = []
    
    # Constraint 1: Aircraft Sized Weight (MTOW limit)
    sized_mass = summary["total_mass_kg"]
    mass_ok = sized_mass <= 1000.0
    constraints.append({
        "Constraint Area": "MTOW Sized Weight Limit",
        "Threshold Value": "≤ 1,000.0 kg",
        "Simulation Peak": f"{sized_mass:.1f} kg",
        "Feasibility Status": "PASS" if mass_ok else "VIOLATED"
    })
    
    # Constraint 2: Motor power demand vs rating
    peak_demand = history["demand_kw"].max()
    motor_rated = 120.0
    motor_ok = peak_demand <= motor_rated + 1e-6
    constraints.append({
        "Constraint Area": "Traction Motor Load Peak",
        "Threshold Value": f"≤ {motor_rated:.1f} kW",
        "Simulation Peak": f"{peak_demand:.1f} kW",
        "Feasibility Status": "PASS" if motor_ok else "VIOLATED"
    })
    
    # Constraint 3: Generator load vs rating
    peak_gen = history["generator_kw"].max()
    gen_rated = cfg["generator_rating_kw"]
    gen_ok = peak_gen <= gen_rated + 1e-6
    constraints.append({
        "Constraint Area": "Generator Load Peak",
        "Threshold Value": f"≤ {gen_rated:.1f} kW",
        "Simulation Peak": f"{peak_gen:.1f} kW",
        "Feasibility Status": "PASS" if gen_ok else "VIOLATED"
    })
    
    # Constraint 4: Turbine shaft load vs rating
    # Turbine power is generator_kw / generator_efficiency
    turbine_shafts = history["generator_kw"] / history["generator_eta"].replace(0.0, 1.0)
    peak_turbine = turbine_shafts.max()
    turbine_rated = cfg["turbine_rating_kw"]
    turbine_ok = peak_turbine <= turbine_rated + 1e-6
    constraints.append({
        "Constraint Area": "Aux. Turbine Shaft Load Peak",
        "Threshold Value": f"≤ {turbine_rated:.1f} kW",
        "Simulation Peak": f"{peak_turbine:.1f} kW",
        "Feasibility Status": "PASS" if turbine_ok else "VIOLATED"
    })
    
    # Constraint 5: Battery peak power vs limit
    peak_batt_discharge = history["battery_discharge_kw"].max()
    peak_batt_charge = history["battery_charge_kw"].max()
    batt_peak_pwr = cfg["battery_peak_power_kw"]
    batt_ok = max(peak_batt_discharge, peak_batt_charge) <= batt_peak_pwr + 1e-6
    constraints.append({
        "Constraint Area": "Battery Power Peak (Chg/Disch)",
        "Threshold Value": f"≤ {batt_peak_pwr:.1f} kW",
        "Simulation Peak": f"Disch: {peak_discharge_str(peak_batt_discharge)} | Chg: {peak_charge_str(peak_batt_charge)}",
        "Feasibility Status": "PASS" if batt_ok else "VIOLATED"
    })
    
    # Constraint 6: SoC Floor limits
    min_soc = history["soc"].min()
    soc_floor_ok = min_soc >= 0.20 - 1e-6
    constraints.append({
        "Constraint Area": "Battery Minimum State of Charge",
        "Threshold Value": "≥ 20.0%",
        "Simulation Peak": f"{min_soc*100.0:.2f}%",
        "Feasibility Status": "PASS" if soc_floor_ok else "VIOLATED"
    })
    
    # Constraint 7: Fuel depletion
    min_fuel = history["fuel_remaining_kg"].min()
    fuel_ok = min_fuel >= -1e-6
    constraints.append({
        "Constraint Area": "Sized Fuel Margin Reserve",
        "Threshold Value": "≥ 0.00 kg",
        "Simulation Peak": f"{min_fuel:.2f} kg",
        "Feasibility Status": "PASS" if fuel_ok else "VIOLATED"
    })
    
    # Show dataframe with status styling
    c_df = pd.DataFrame(constraints)
    
    # Style helper function
    def highlight_status(val):
        if val == "PASS":
            return "background-color: rgba(16, 185, 129, 0.15); color: var(--dash-green); font-weight: bold;"
        return "background-color: rgba(239, 68, 68, 0.15); color: var(--dash-red); font-weight: bold;"
        
    st.dataframe(
        c_df.style.map(highlight_status, subset=["Feasibility Status"]),
        width="stretch",
        hide_index=True
    )

    st.markdown("---")

    # 2. ENERGY BALANCE ANALYSIS (PIE CHART & STATISTICS)
    st.markdown("### 2. Sizing Integrated Energy Balance")
    
    # Calculate source contributions (Fuel LHV vs Battery Net Energy)
    fuel_burned = summary["fuel_burned_kg"]
    fuel_lhv = assumptions.fuel_lhv_kwh_per_kg
    fuel_energy_kwh = fuel_burned * fuel_lhv
    
    initial_soc = 1.0  # assumed baseline
    final_soc = summary["final_soc"]
    battery_net_discharge_kwh = max(0.0, (initial_soc - final_soc) * cfg["battery_capacity_kwh"])
    
    total_energy_input = fuel_energy_kwh + battery_net_discharge_kwh
    
    col1, col2 = st.columns([6, 4])
    
    with col1:
        st.markdown("##### Energy Inputs Contribution")
        p = palette()
        
        # Energy Pie Chart
        energy_fig = go.Figure(data=[go.Pie(
            labels=["Liquid Fuel Chemical Energy", "Battery Electrochemical Energy"],
            values=[fuel_energy_kwh, battery_net_discharge_kwh],
            hole=.4,
            marker=dict(colors=["#a855f7", p["green"]]),
            textinfo='percent+label'
        )])
        
        energy_fig.update_layout(
            template=plotly_template(),
            height=320,
            margin={"l": 20, "r": 20, "t": 30, "b": 20},
            showlegend=False
        )
        st.plotly_chart(energy_fig, width="stretch", config={"displaylogo": False})
        
    with col2:
        st.markdown("##### Energy Sizing Metrics")
        st.write(f"**Total Energy Ingested**: `{total_energy_input:.2f} kWh`")
        st.write(f"**Fuel LHV Ingested**: `{fuel_energy_kwh:.2f} kWh` ({100*fuel_energy_kwh/max(total_energy_input, 1e-6):.1f}%)")
        st.write(f"**Battery Net Discharge**: `{battery_net_discharge_kwh:.2f} kWh` ({100*battery_net_discharge_kwh/max(total_energy_input, 1e-6):.1f}%)")
        
        # Sized propulsion weight breakdown
        prop_masses = propulsion_mass_kg(
            config_from_state(cfg)[0],
            assumptions,
        )
        
        st.markdown("##### Propulsion Sized Masses")
        st.write(f"**Propulsion Sized Total Weight**: `{prop_masses['total_propulsion']:.1f} kg`")
        st.write(f"  - **Turbine Engine**: `{prop_masses['turbine']:.1f} kg`")
        st.write(f"  - **Generator**: `{prop_masses['generator']:.1f} kg`")
        st.write(f"  - **Battery Pack**: `{prop_masses['battery']:.1f} kg`")
        st.write(f"  - **Motor + Power Electronics**: `{prop_masses['motor'] + prop_masses['power_electronics']:.1f} kg`")

    st.markdown("---")

    # 3. COMPONENT EFFICIENCY SWEEPS
    st.markdown("### 3. Integrated Efficiencies & Component Wear")
    
    eff_cols = st.columns(3)
    
    with eff_cols[0]:
        st.markdown("##### Average Efficiencies")
        avg_motor_eff = history["motor_eta"].mean()
        avg_gen_eff = history["generator_eta"].mean()
        
        st.metric("Avg Motor/Inverter Efficiency", f"{100 * avg_motor_eff:.1f}%")
        st.metric("Avg Generator Efficiency", f"{100 * avg_gen_eff:.1f}%")
        st.metric("Overall Sizing average efficiency", f"{100 * summary['mission_avg_efficiency']:.1f}%")
        
    with eff_cols[1]:
        st.markdown("##### Battery Aging Metrics")
        
        # Calculate C-rate peaks
        battery_capacity = cfg["battery_capacity_kwh"]
        max_discharge_c = history["battery_discharge_kw"].max() / max(battery_capacity, 1e-6)
        max_charge_c = history["battery_charge_kw"].max() / max(battery_capacity, 1e-6)
        
        # Equivalent cycles
        batt_throughput = summary["diagnostics"]["battery_throughput_kwh"]
        eq_cycles = batt_throughput / max(2.0 * battery_capacity, 1e-6)
        
        st.metric("Peak Discharge C-rate", f"{max_discharge_c:.2f} C")
        st.metric("Peak Charge C-rate", f"{max_charge_c:.2f} C")
        st.metric("Equivalent Sizing Cycles", f"{eq_cycles:.5f}")
        st.metric("Degradation Proxy Index", f"{summary['degradation_proxy']:.5f}")
        
    with eff_cols[2]:
        st.markdown("##### Fuel Consumption Summary")
        avg_sfc = (
            history["fuel_flow_kg_h"].mean()
            / max(history["generator_kw"].mean() / max(avg_gen_eff, 1e-6), 1e-6)
            if history["generator_kw"].mean() > 0.1
            else 0.0
        )
        
        st.metric("Total Fuel Burned", f"{fuel_burned:.2f} kg")
        st.metric("Fuel Remaining Reserves", f"{min_fuel:.2f} kg")
        st.metric("Est. Mission Average SFC", f"{avg_sfc:.3f} kg/kWh", help="Estimate for turbine shaft output")


render()
