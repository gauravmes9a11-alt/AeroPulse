"""Sensitivity Analysis Page displaying tornado and spider radar charts."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px

from components.charts import sensitivity_tornado, sensitivity_spider_chart
from components.theme import palette, plotly_template
from sensitivity import run_fixed_baseline_sensitivity
from utils.data_loader import load_sensitivity_csv


def render() -> None:
    st.title("Propulsion Sensitivity Analysis")
    st.caption("Investigate how perturbations in subsystem efficiency, SFC, and battery specific energy density shift the overall UAV design objectives.")

    # 1. Trigger sweep button
    st.markdown("### 1. Perform Sensitivity Sweep")
    c1, c2 = st.columns([2.5, 7.5])
    
    with c1:
        run_sweep = st.button("Run Sizing Sensitivity Sweep", type="primary", width="stretch")
    with c2:
        st.markdown(
            "<div style='margin-top: 0.5rem; color: var(--dash-muted); font-size: 0.85rem; font-style: italic;'>"
            "Runs a fixed-baseline 1Hz simulation sweep (SFC, battery Wh/kg, motor efficiency, generator efficiency at ±10%)."
            "</div>",
            unsafe_allow_html=True
        )

    if run_sweep:
        with st.spinner("Executing sensitivity simulations (±10% perturbations)..."):
            try:
                df = run_fixed_baseline_sensitivity("outputs")
                load_sensitivity_csv.clear()
                st.success(f"Fixed-baseline sensitivity sweep completed. Sized {len(df)} design perturbations.")
                st.rerun()
            except Exception as exc:
                st.error(f"Sensitivity sweep failed: {exc}")

    # 2. Check if sensitivity CSV exists
    df = load_sensitivity_csv()
    if df.empty:
        st.markdown(
            """
            <div style="background: rgba(245, 158, 11, 0.08); border: 1px solid var(--dash-amber); border-radius: 8px; padding: 1.5rem; text-align: center; margin-top: 1.5rem;">
                <h4 style="color: var(--dash-amber); margin: 0 0 0.5rem 0;">Sensitivity data is not available.</h4>
                <p style="color: var(--dash-text); margin: 0 0 1.5rem 0;">Run the fixed-baseline sweep above to generate the sensitivity profile.</p>
            </div>
            """,
            unsafe_allow_html=True
        )
        return

    st.markdown("---")

    # 3. Dynamic Charts Tab System
    tab1, tab2, tab3 = st.tabs(["Tornado Plot (Per Objective)", "Spider / Radar Plot (Per Parameter)", "Linear Parameter Sweeps"])
    
    with tab1:
        st.markdown("##### Sizing Sensitivity Tornado Chart")
        st.write("Visualizes how a ±10% shift in each subsystem parameter impacts a selected mission objective.")
        
        objective_options = {
            "Endurance (hrs)": "endurance_h_shift_pct",
            "Fuel Burned (kg)": "fuel_burned_kg_shift_pct",
            "Battery Degradation": "degradation_proxy_shift_pct",
            "Average Efficiency (%)": "efficiency_shift_pct",
            "Total Aircraft Mass (kg)": "total_mass_kg_shift_pct",
        }
        
        label = st.radio("Select Target Objective", list(objective_options), index=0, horizontal=True)
        shift_col = objective_options[label]
        
        st.plotly_chart(
            sensitivity_tornado(df, shift_col), 
            width="stretch", 
            config={"displaylogo": False}
        )
        
    with tab2:
        st.markdown("##### Multi-objective Spider / Radar Chart")
        st.write("Compare the relative impacts of one input parameter across all five objectives simultaneously.")
        
        params = list(df["parameter"].unique())
        selected_param = st.selectbox("Select Sizing Parameter to analyze", params, format_func=lambda x: x.replace('_', ' ').upper())
        
        st.plotly_chart(
            sensitivity_spider_chart(df, selected_param), 
            width="stretch", 
            config={"displaylogo": False}
        )
        
    with tab3:
        st.markdown("##### Parameter Sensitivity Sweeps")
        st.write("Line chart visualizing objective shift trend across the sweep variables.")
        
        sweep_cols = st.columns(2)
        obj_sel = sweep_cols[0].selectbox("Objective to Plot", ["endurance_h_shift_pct", "fuel_burned_kg_shift_pct", "degradation_proxy_shift_pct", "efficiency_shift_pct", "total_mass_kg_shift_pct"], format_func=lambda x: x.replace('_shift_pct', '').replace('_', ' ').upper())
        
        p = palette()
        sweep_fig = px.line(
            df,
            x="delta_pct",
            y=obj_sel,
            color="parameter",
            markers=True,
            template=plotly_template(),
            labels={
                "delta_pct": "Parameter Perturbation (%)",
                obj_sel: "Objective Shift (%)"
            }
        )
        sweep_fig.update_layout(height=400, margin={"l": 40, "r": 20, "t": 30, "b": 45})
        sweep_fig.update_traces(line=dict(width=2.5), marker=dict(size=8))
        st.plotly_chart(sweep_fig, width="stretch", config={"displaylogo": False})

    # 4. Data Details Preview
    with st.expander("Show Sensitivity Sizing Matrix Dataframe"):
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config={
                "parameter": "Perturbed Parameter",
                "delta_pct": st.column_config.NumberColumn("Perturbation", format="%+d%%"),
                "endurance_h_shift_pct": st.column_config.NumberColumn("Endurance Shift", format="%+.2f%%"),
                "fuel_burned_kg_shift_pct": st.column_config.NumberColumn("Fuel Shift", format="%+.2f%%"),
                "degradation_proxy_shift_pct": st.column_config.NumberColumn("Degradation Shift", format="%+.2f%%"),
                "efficiency_shift_pct": st.column_config.NumberColumn("Efficiency Shift", format="%+.2f%%"),
                "total_mass_kg_shift_pct": st.column_config.NumberColumn("MTOW Shift", format="%+.2f%%"),
            }
        )


render()
