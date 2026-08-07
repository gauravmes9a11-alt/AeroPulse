"""NSGA-II Sizing Optimization & Pareto Explorer Page."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px

from components.charts import pareto_parallel_figure, pareto_scatter_matrix
from components.theme import palette, plotly_template, kpi_card
from utils.data_loader import (
    load_pareto_csv,
    pareto_row_to_config,
    run_optimization_cached,
)


def render() -> None:
    st.title("Optimization & Pareto Explorer")
    st.caption("Interact with the NSGA-II sizing Pareto front, compare sizing trade-offs, and load candidate configurations directly into the simulator.")

    # 1. Check if Pareto exists
    pareto = load_pareto_csv()
    
    # 2. Re-optimization Settings Expander
    with st.expander("Sizing Optimizer Control Panel (NSGA-II)", expanded=pareto.empty):
        st.markdown(
            "Configure NSGA-II parameters. A small population size/generation count is recommended for quick test runs inside the browser."
        )
        c1, c2, c3 = st.columns(3)
        pop = c1.number_input("Population Size", min_value=4, max_value=300, value=24, step=4, help="Number of design candidates per generation")
        gens = c2.number_input("Generations", min_value=1, max_value=300, value=10, step=1, help="Number of optimizer iterations")
        seed = c3.number_input("Random Seed", min_value=0, max_value=9999, value=7, step=1)
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Run Multi-Objective Optimization", type="primary", width="stretch"):
            with st.spinner("Running NSGA-II Sizing Optimization (this can take 5-15 seconds)..."):
                try:
                    pareto = run_optimization_cached(int(pop), int(gens), int(seed))
                    st.success(f"Sizing optimization complete: {len(pareto)} Pareto-optimal candidates generated and cached.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Optimization error: {exc}")
                    
    # Empty State check
    if pareto.empty:
        st.markdown(
            """
            <div style="background: rgba(245, 158, 11, 0.08); border: 1px solid var(--dash-amber); border-radius: 8px; padding: 1.5rem; text-align: center; margin-top: 1.5rem;">
                <h4 style="color: var(--dash-amber); margin: 0 0 0.5rem 0;">Optimization has not been executed yet.</h4>
                <p style="color: var(--dash-text); margin: 0 0 1rem 0;">Use the Sizing Optimizer Control Panel above to run the multi-objective optimization framework or run from your command terminal.</p>
            </div>
            """,
            unsafe_allow_html=True
        )
        return

    # 3. Interactive Filtering
    st.markdown("---")
    st.markdown("### 1. Filter Design Space")
    
    # Simple slider filters for the objectives
    f_cols = st.columns(3)
    
    min_end, max_end = float(pareto["endurance_h"].min()), float(pareto["endurance_h"].max())
    min_fuel, max_fuel = float(pareto["fuel_burned_kg"].min()), float(pareto["fuel_burned_kg"].max())
    min_mass, max_mass = float(pareto["total_mass_kg"].min()), float(pareto["total_mass_kg"].max())
    
    with f_cols[0]:
        filter_endurance = st.slider(
            "Minimum Endurance (hrs)", 
            min_value=min_end, 
            max_value=max_end, 
            value=min_end, 
            step=0.1
        )
    with f_cols[1]:
        filter_fuel = st.slider(
            "Maximum Fuel Burned (kg)", 
            min_value=min_fuel, 
            max_value=max_fuel, 
            value=max_fuel, 
            step=1.0
        )
    with f_cols[2]:
        filter_mass = st.slider(
            "Maximum Aircraft Mass (kg)", 
            min_value=min_mass, 
            max_value=max_mass, 
            value=max_mass, 
            step=1.0
        )
        
    filtered_pareto = pareto[
        (pareto["endurance_h"] >= filter_endurance) & 
        (pareto["fuel_burned_kg"] <= filter_fuel) & 
        (pareto["total_mass_kg"] <= filter_mass)
    ]
    
    st.caption(f"Showing {len(filtered_pareto)} of {len(pareto)} Pareto-optimal designs.")

    # 4. Multi-objective Tradeoff Tabs
    tab1, tab2, tab3 = st.tabs(["Parallel Coordinates", "Scatter Matrix Plot", "Pareto Frontier (2D)"])
    
    with tab1:
        st.plotly_chart(
            pareto_parallel_figure(filtered_pareto), 
            width="stretch", 
            config={"displaylogo": False}
        )
    with tab2:
        numeric_cols = list(filtered_pareto.select_dtypes("number").columns)
        default = "endurance_h" if "endurance_h" in numeric_cols else numeric_cols[0]
        color_by = st.selectbox("Color points by parameter", numeric_cols, index=numeric_cols.index(default))
        st.plotly_chart(
            pareto_scatter_matrix(filtered_pareto, color_by), 
            width="stretch", 
            config={"displaylogo": False}
        )
    with tab3:
        # Custom 2D Scatter plot
        st.markdown("##### Sizing Pareto Trade-off Frontier")
        trade_cols = st.columns(3)
        x_axis = trade_cols[0].selectbox("X Axis (Minimize)", ["fuel_burned_kg", "total_mass_kg", "degradation_proxy"], index=0)
        y_axis = trade_cols[1].selectbox("Y Axis (Maximize)", ["endurance_h", "efficiency"], index=0)
        c_by = trade_cols[2].selectbox("Color Map", ["turbine_rating_kw", "battery_capacity_kwh", "ems_tier"], index=1)
        
        p = palette()
        front_fig = px.scatter(
            filtered_pareto,
            x=x_axis,
            y=y_axis,
            color=c_by,
            hover_data=["turbine_rating_kw", "generator_rating_kw", "battery_capacity_kwh", "fuel_mass_kg", "ems_tier"],
            template=plotly_template(),
            labels={
                "fuel_burned_kg": "Fuel Burned (kg)",
                "total_mass_kg": "Aircraft Mass (kg)",
                "degradation_proxy": "Degradation Index",
                "endurance_h": "Endurance (hrs)",
                "efficiency": "Average Efficiency (%)"
            }
        )
        front_fig.update_layout(height=480)
        front_fig.update_traces(marker=dict(size=8, line=dict(color=p["border"], width=1)))
        st.plotly_chart(front_fig, width="stretch", config={"displaylogo": False})

    # 5. Candidate Selector Table
    st.markdown("---")
    st.markdown("### 2. Sizing Suffix Selection Table")
    st.info("Select a design candidate below to **automatically** load its hardware/EMS config and run the 1Hz flight simulator.")
    
    view_cols = [
        c for c in [
            "endurance_h", "fuel_burned_kg", "degradation_proxy", "efficiency", "total_mass_kg", 
            "ems_tier", "turbine_rating_kw", "generator_rating_kw", "battery_capacity_kwh", 
            "battery_peak_power_kw", "fuel_mass_kg"
        ] if c in filtered_pareto.columns
    ]
    
    event = st.dataframe(
        filtered_pareto[view_cols],
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )
    
    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        row = filtered_pareto.iloc[selected_rows[0]]
        cfg = pareto_row_to_config(row)
        st.session_state["selected_config"] = cfg
        
        # Run simulator instantly
        with st.spinner("Instantly simulating selected candidate..."):
            from utils.data_loader import run_simulation_cached
            summary, history = run_simulation_cached(cfg)
            
            # Sizing structural weights
            from models import ModelAssumptions, propulsion_mass_kg
            assumptions = ModelAssumptions()
            from utils.data_loader import config_from_state
            hw_cfg, _ = config_from_state(cfg)
            prop_mass = propulsion_mass_kg(hw_cfg, assumptions)["total_propulsion"]
            history["weight_kg"] = 430.0 + 200.0 + prop_mass + history["fuel_remaining_kg"]
            
            st.session_state["last_simulation"] = summary
            st.session_state["last_history_df"] = history
            
        st.success(
            f"✅ Config loaded! Turbine: {cfg['turbine_rating_kw']:.1f}kW | "
            f"Battery: {cfg['battery_capacity_kwh']:.1f}kWh. "
            "Telemetry updated for all pages."
        )
        
        # Show constraint report for selected design
        st.markdown("##### Candidate Performance Review")
        diag_cols = st.columns(4)
        with diag_cols[0]:
            kpi_card("Selected Endurance", f"{summary['endurance_h']:.2f} hrs")
        with diag_cols[1]:
            kpi_card("Selected Fuel", f"{summary['fuel_burned_kg']:.1f} kg")
        with diag_cols[2]:
            kpi_card("Selected MTOW", f"{summary['total_mass_kg']:.1f} kg")
        with diag_cols[3]:
            # Feasibility
            badge_text = "Feasible" if summary["success"] else "Infeasible"
            badge_val = summary["first_violation"] or "All constraints satisfied."
            kpi_card("Feasibility Status", badge_text, badge_val)


render()
