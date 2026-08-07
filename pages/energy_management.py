"""Energy Management System (EMS) Analysis and Interactive Power Flow page."""

from __future__ import annotations

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from components.theme import palette, plotly_template
from components.charts import sankey_power_flow
from models import ModelAssumptions, turbine_sfc_kg_per_kwh, generator_efficiency, motor_inverter_efficiency
from utils.data_loader import config_from_state


def render() -> None:
    st.title("Energy Management System (EMS)")
    st.caption("Detailed evaluation of the series hybrid power splitting strategy, instantaneous power distribution flow, and component operating efficiencies.")

    history = st.session_state.get("last_history_df")
    if history is None or history.empty:
        st.info("💡 Run a mission simulation from the **Mission Overview** page first to activate EMS diagnostics.")
        return

    summary = st.session_state.get("last_simulation")
    cfg = st.session_state.get("selected_config") or {}
    assumptions = ModelAssumptions()
    if not cfg:
        st.info("No hardware configuration is available yet. Run the simulation from the Mission Overview page first.")
        return

    # 1. Slider to scrub through time
    st.markdown("### 1. Instantaneous Power Flow Telemetry")
    
    total_steps = len(history) - 1
    
    # We can create a nice layout with columns: slider and segment label
    scrub_col1, scrub_col2 = st.columns([8, 2])
    
    with scrub_col1:
        step_idx = st.slider(
            "Mission Time scrub control",
            min_value=0,
            max_value=total_steps,
            value=0,
            format="Step %d (1Hz)",
            label_visibility="collapsed"
        )
        
    row = history.iloc[step_idx]
    time_s = int(row["time_s"])
    hours = time_s // 3600
    minutes = (time_s % 3600) // 60
    seconds = time_s % 60
    time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    with scrub_col2:
        st.markdown(
            f"""
            <div style="background: var(--dash-panel-2); border: 1px solid var(--dash-border); border-radius: 6px; padding: 0.35rem 0.75rem; text-align: center;">
                <span style="color: var(--dash-muted); font-size: 0.75rem; text-transform: uppercase;">Time (H:M:S)</span><br>
                <span style="font-family: monospace; font-weight: bold; font-size: 1rem; color: var(--dash-text);">{time_str}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    # 2. Live metrics for the selected time step
    st.markdown("<br>", unsafe_allow_html=True)
    m_cols = st.columns(6)
    
    with m_cols[0]:
        st.metric("Flight Phase", str(row["segment"]))
    with m_cols[1]:
        st.metric("Propeller Demand", f"{row['demand_kw']:.1f} kW")
    with m_cols[2]:
        st.metric("Generator Output", f"{row['generator_kw']:.1f} kW")
    with m_cols[3]:
        # Determine battery state (charging vs discharging)
        batt_pwr = row["battery_kw"]
        if batt_pwr > 0.05:
            state_label = "Discharging"
            delta_color = "normal"
        elif batt_pwr < -0.05:
            state_label = "Charging"
            delta_color = "inverse"
        else:
            state_label = "Idle"
            delta_color = "off"
        st.metric("Battery Net", f"{abs(batt_pwr):.1f} kW", delta=state_label, delta_color=delta_color)
    with m_cols[4]:
        st.metric("Battery SoC", f"{100 * row['soc']:.1f}%")
    with m_cols[5]:
        st.metric("Fuel Burn Rate", f"{row['fuel_flow_kg_h']:.2f} kg/h")

    # 3. Sankey Power Flow & Operating Points
    st.markdown("<br>", unsafe_allow_html=True)
    chart_col1, chart_col2 = st.columns([6, 4])
    
    with chart_col1:
        st.plotly_chart(
            sankey_power_flow(row, assumptions),
            width="stretch",
            config={"displaylogo": False}
        )
        
    with chart_col2:
        # Engine operating point on SFC curve
        st.markdown("##### Gas Turbine SFC Operating Point")
        
        # Calculate turbine shaft power for the current step
        gen_kw = float(row["generator_kw"])
        gen_eta = float(row["generator_eta"])
        turbine_kw = gen_kw / max(gen_eta, 1e-6) if gen_kw > 0 else 0.0
        
        # Build SFC curve
        rated_turbine = float(cfg["turbine_rating_kw"])
        powers = np.linspace(rated_turbine * 0.05, rated_turbine * 1.25, 100)
        sfcs = [turbine_sfc_kg_per_kwh(p, rated_turbine, assumptions) for p in powers]
        
        p = palette()
        sfc_fig = go.Figure()
        
        # Plot SFC curve
        sfc_fig.add_trace(go.Scatter(
            x=powers,
            y=sfcs,
            mode="lines",
            name="SFC curve spec",
            line=dict(color=p["primary"], width=2.5)
        ))
        
        # Plot current operating point
        if turbine_kw > 0.1:
            current_sfc = turbine_sfc_kg_per_kwh(turbine_kw, rated_turbine, assumptions)
            sfc_fig.add_trace(go.Scatter(
                x=[turbine_kw],
                y=[current_sfc],
                mode="markers+text",
                name="Operating Point",
                text=[f"{current_sfc:.3f}"],
                textposition="top center",
                marker=dict(color=p["red"], size=10, symbol="circle", line=dict(color="#ffffff", width=1))
            ))
            
        sfc_fig.update_layout(
            template=plotly_template(),
            xaxis_title="Turbine Shaft Power (kW)",
            yaxis_title="SFC (kg/kWh)",
            height=320,
            margin={"l": 50, "r": 20, "t": 30, "b": 45},
            showlegend=False
        )
        st.plotly_chart(sfc_fig, width="stretch", config={"displaylogo": False})

    st.markdown("---")

    # 4. Component Efficiency & Utilization Profiles
    st.markdown("### 2. Sizing Component Utilizations")
    util_cols = st.columns(3)
    
    with util_cols[0]:
        st.markdown("##### Generator Sizing Load")
        # Peak and average generator power
        peak_gen = float(history["generator_kw"].max())
        avg_gen = float(history["generator_kw"].mean())
        gen_rated = float(cfg["generator_rating_kw"])
        
        st.write(f"**Rated capacity**: `{gen_rated:.1f} kW`")
        st.write(f"**Average output**: `{avg_gen:.1f} kW` ({100 * avg_gen / gen_rated:.1f}% load)")
        st.write(f"**Peak output**: `{peak_gen:.1f} kW` ({100 * peak_gen / gen_rated:.1f}% load)")
        st.progress(min(max(avg_gen / gen_rated, 0.0), 1.0))
        
    with util_cols[1]:
        st.markdown("##### Battery Peak Thermal Sizing")
        peak_charge = float(history["battery_charge_kw"].max())
        peak_discharge = float(history["battery_discharge_kw"].max())
        batt_rated_power = float(cfg["battery_peak_power_kw"])
        batt_capacity = float(cfg["battery_capacity_kwh"])
        
        st.write(f"**Rated power**: `{batt_rated_power:.1f} kW`")
        st.write(f"**Peak discharge**: `{peak_discharge:.1f} kW` ({100 * peak_discharge / batt_rated_power:.1f}% load)")
        st.write(f"**Peak charge**: `{peak_charge:.1f} kW` ({100 * peak_charge / batt_rated_power:.1f}% load)")
        st.progress(min(max(max(peak_discharge, peak_charge) / batt_rated_power, 0.0), 1.0))
        
    with util_cols[2]:
        st.markdown("##### Motor / Inverter Sizing Load")
        peak_demand = float(history["demand_kw"].max())
        avg_demand = float(history["demand_kw"].mean())
        motor_rated = 120.0  # Fixed in this study
        
        st.write(f"**Rated capacity**: `{motor_rated:.1f} kW`")
        st.write(f"**Average demand**: `{avg_demand:.1f} kW` ({100 * avg_demand / motor_rated:.1f}% load)")
        st.write(f"**Peak demand**: `{peak_demand:.1f} kW` ({100 * peak_demand / motor_rated:.1f}% load)")
        st.progress(min(max(avg_demand / motor_rated, 0.0), 1.0))


render()
