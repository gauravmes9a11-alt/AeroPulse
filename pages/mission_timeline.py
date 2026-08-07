"""Mission timeline dashboard with interactive synchronized charts."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from components.charts import mission_timeline_figure


def render() -> None:
    st.title("Mission Profile Timeline")
    st.caption("Synchronized multi-plot telemetry visualizing power demands, source splits, state of charge, fuel depletion, and aircraft flight weight.")

    history = st.session_state.get("last_history_df")
    if history is None or history.empty:
        st.info("💡 Run a mission simulation from the **Mission Overview** page first to populate this timeline.")
        return

    summary = st.session_state.get("last_simulation", {})
    
    # 1. Alert for violations
    if summary and not summary.get("success", True):
        violation = summary.get("first_violation") or "Mission constraint violation detected."
        st.markdown(
            f"""
            <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid var(--dash-red); border-radius: 8px; padding: 0.8rem 1.2rem; margin-bottom: 1.5rem;">
                <span style="font-weight: bold; color: var(--dash-red);">⚠️ PERFORMANCE BOUND BREACHED:</span>
                <span style="color: var(--dash-text); font-family: monospace;">{violation}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    # 2. Render Synchronized Plotly charts
    st.markdown("### 1. Interactive Flight Telemetry")
    fig = mission_timeline_figure(history)
    st.plotly_chart(
        fig,
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}
    )

    st.markdown("---")

    # 3. Flight Phase Summary / Breakdown
    st.markdown("### 2. Flight Phase Breakdown")
    
    # Group history by segment to calculate average and cumulative values
    if "segment" in history.columns:
        phases = []
        for segment_name, grp in history.groupby("segment", sort=False):
            duration_s = len(grp)
            mean_demand = grp["demand_kw"].mean()
            mean_gen = grp["generator_kw"].mean()
            mean_battery = grp["battery_kw"].mean()
            min_soc_phase = grp["soc"].min()
            fuel_burned = grp["fuel_flow_kg_h"].mean() * (duration_s / 3600.0)
            
            phases.append({
                "Phase": segment_name,
                "Duration (min)": duration_s / 60.0,
                "Avg Demand (kW)": mean_demand,
                "Avg Gen Output (kW)": mean_gen,
                "Avg Battery (kW)": mean_battery,
                "Min SoC (%)": min_soc_phase * 100.0,
                "Fuel Burned (kg)": fuel_burned,
            })
            
        phase_df = pd.DataFrame(phases)
        
        st.dataframe(
            phase_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Duration (min)": st.column_config.NumberColumn("Duration (min)", format="%.1f"),
                "Avg Demand (kW)": st.column_config.NumberColumn("Avg Demand (kW)", format="%.1f"),
                "Avg Gen Output (kW)": st.column_config.NumberColumn("Avg Gen (kW)", format="%.1f"),
                "Avg Battery (kW)": st.column_config.NumberColumn("Avg Battery Net (kW)", format="%.1f", help="Positive = discharging, Negative = charging"),
                "Min SoC (%)": st.column_config.NumberColumn("Min SoC (%)", format="%.1f%%"),
                "Fuel Burned (kg)": st.column_config.NumberColumn("Fuel Burned (kg)", format="%.2f"),
            }
        )

    # 4. Preview raw data
    with st.expander("Preview Raw Sizing Telemetry (First 200 points)"):
        st.dataframe(
            history.head(200),
            width="stretch",
            hide_index=True,
            column_config={
                "time_h": st.column_config.NumberColumn("Time (h)", format="%.4f"),
                "segment": "Flight Segment",
                "demand_kw": st.column_config.NumberColumn("Demand (kW)", format="%.2f"),
                "generator_kw": st.column_config.NumberColumn("Generator (kW)", format="%.2f"),
                "battery_kw": st.column_config.NumberColumn("Battery Net (kW)", format="%.2f"),
                "soc": st.column_config.ProgressColumn("SoC", min_value=0.0, max_value=1.0, format="%.3f"),
                "fuel_remaining_kg": st.column_config.NumberColumn("Fuel (kg)", format="%.2f"),
                "weight_kg": st.column_config.NumberColumn("Weight (kg)", format="%.2f"),
            },
        )


render()
