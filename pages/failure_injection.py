"""Failure Injection & What-If Analysis Page."""

from __future__ import annotations

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from components.theme import kpi_card, palette, plotly_template
from components.charts import mission_timeline_figure
from models import ModelAssumptions
from mission_sim import MissionProfile, simulate_mission
from utils.data_loader import config_from_state, run_simulation_cached
from disturbance_engine import (
    DisturbanceScenario,
    compute_constraint_health,
    compute_mission_success_probability,
    generate_warnings,
    run_disturbed_simulation,
)


def render() -> None:
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%); padding: 1.5rem 2rem; border-radius: 12px; border: 1px solid #4338ca; margin-bottom: 1.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.25);">
            <h1 style="color: #ffffff; margin: 0; font-size: 2.1rem; font-weight: 700; letter-spacing: -0.02em;">
                Failure Injection & What-If Analysis
            </h1>
            <p style="color: #c7d2fe; margin: 0.35rem 0 0 0; font-size: 0.95rem; font-weight: 500;">
                Simulate real-world environmental disturbances, structural degradation, and component failures.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cfg_state = st.session_state.get("selected_config") or {}
    if not cfg_state:
        st.info("Please configure hardware parameters in the sidebar first.")
        return

    # Baseline calculation
    base_cfg, base_ems = config_from_state(cfg_state)
    base_assumptions = ModelAssumptions()
    base_mission = MissionProfile()
    num_motors = int(cfg_state.get("num_motors", 1))
    motor_allocation = str(cfg_state.get("motor_allocation", "even_split"))

    base_summary, base_history = run_simulation_cached(cfg_state)

    # State key management for Reset Button
    if "dist_alt" not in st.session_state:
        st.session_state["dist_alt"] = 0
    if "dist_temp" not in st.session_state:
        st.session_state["dist_temp"] = 15
    if "dist_wind" not in st.session_state:
        st.session_state["dist_wind"] = 0
    if "dist_payload" not in st.session_state:
        st.session_state["dist_payload"] = 0
    if "dist_batt_fail" not in st.session_state:
        st.session_state["dist_batt_fail"] = "None"
    if "dist_gen_fail" not in st.session_state:
        st.session_state["dist_gen_fail"] = False
    if "dist_motor_fail" not in st.session_state:
        st.session_state["dist_motor_fail"] = "No failure"
    if "dist_prop_damage" not in st.session_state:
        st.session_state["dist_prop_damage"] = 0

    # 1. Mission Disturbance Injection Panel
    with st.expander("⚠️ Mission Disturbance Injection Controls", expanded=True):
        st.markdown("<span style='color: var(--dash-muted); font-size: 0.9rem;'>Inject real-world operational stressors and subsystem failures to test sizing robustness.</span><br><br>", unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)

        with c1:
            alt = st.slider(
                "1. Altitude Increase (m)",
                min_value=0,
                max_value=6000,
                step=250,
                key="dist_alt",
                help="Reduces air density ρ; increases required propulsive power."
            )
            temp = st.slider(
                "2. Ambient Temperature (°C)",
                min_value=-20,
                max_value=50,
                step=5,
                key="dist_temp",
                help="Alters battery electrochemistry & generator thermal cooling efficiency."
            )
            wind = st.slider(
                "3. Headwind (+) / Tailwind (-) (km/h)",
                min_value=-50,
                max_value=50,
                step=5,
                key="dist_wind",
                help="Changes ground speed, cruise time, and endurance required."
            )
            payload_delta = st.slider(
                "4. Payload Mass Shift (kg)",
                min_value=-50,
                max_value=100,
                step=5,
                key="dist_payload",
                help="Adjusts total takeoff weight (MTOW) and thrust demand."
            )

        with c2:
            batt_fail_str = st.selectbox(
                "5. Battery Cell Failure (% lost)",
                ["None", "5%", "10%", "20%", "30%"],
                key="dist_batt_fail",
                help="Simulates sudden cell string isolation / capacity drop."
            )
            gen_failed = st.checkbox(
                "6. Generator Failure (Total shutdown)",
                key="dist_gen_fail",
                help="Forces hybrid system into 100% battery emergency discharge mode."
            )
            motor_fail_str = st.selectbox(
                "7. Motor Failure Mode",
                ["No failure", "One motor degraded", "One motor failed"],
                key="dist_motor_fail",
                help="Simulates electrical degradation or complete outage of motor units."
            )
            prop_damage = st.slider(
                "8. Propeller Structural Damage (%)",
                min_value=0,
                max_value=30,
                step=5,
                key="dist_prop_damage",
                help="Degrades propeller aerodynamic efficiency; increases shaft power required."
            )

        r_btn_col1, r_btn_col2 = st.columns([2, 8])
        with r_btn_col1:
            if st.button("🔄 Reset Disturbances", type="secondary", use_container_width=True):
                st.session_state["dist_alt"] = 0
                st.session_state["dist_temp"] = 15
                st.session_state["dist_wind"] = 0
                st.session_state["dist_payload"] = 0
                st.session_state["dist_batt_fail"] = "None"
                st.session_state["dist_gen_fail"] = False
                st.session_state["dist_motor_fail"] = "No failure"
                st.session_state["dist_prop_damage"] = 0
                st.rerun()

    # Map string selections to disturbance scenario fields
    batt_fail_pct = 0.0
    if batt_fail_str != "None":
        batt_fail_pct = float(batt_fail_str.replace("%", ""))

    motor_mode_map = {
        "No failure": "none",
        "One motor degraded": "degraded",
        "One motor failed": "failed"
    }
    motor_mode = motor_mode_map.get(motor_fail_str, "none")

    scenario = DisturbanceScenario(
        altitude_m=float(alt),
        ambient_temp_c=float(temp),
        headwind_kmh=float(wind),
        payload_delta_kg=float(payload_delta),
        battery_cell_failure_pct=batt_fail_pct,
        generator_failed=gen_failed,
        motor_failure_mode=motor_mode,
        propeller_damage_pct=float(prop_damage),
    )

    # Execute disturbed simulation
    dist_res, dist_meta = run_disturbed_simulation(
        base_cfg,
        base_ems,
        base_mission,
        base_assumptions,
        scenario,
        payload_mass_kg=200.0,
        num_motors=num_motors,
        motor_allocation=motor_allocation,
    )

    dist_history = dist_res.history
    dist_history_df = pd.DataFrame(dist_history)
    if not dist_history_df.empty:
        dist_history_df["time_h"] = dist_history_df["time_s"] / 3600.0
        dist_history_df["battery_discharge_kw"] = dist_history_df["battery_kw"].clip(lower=0.0)
        dist_history_df["battery_charge_kw"] = (-dist_history_df["battery_kw"].clip(upper=0.0))
        dist_history_df["weight_kg"] = (
            430.0 + dist_meta["perturbed_payload_kg"] + dist_res.total_mass_kg - 430.0 - dist_meta["perturbed_payload_kg"] - base_cfg.fuel_mass_kg + dist_history_df["fuel_remaining_kg"]
        )

    # 2. Intelligent Warning System
    warnings = generate_warnings(dist_res, scenario, base_cfg)
    if warnings:
        st.markdown("### 1. Diagnostic Warning Console")
        for w in warnings:
            if w["severity"] == "critical":
                st.error(f"**{w['title']}**: {w['message']}")
            elif w["severity"] == "warning":
                st.warning(f"**{w['title']}**: {w['message']}")
            else:
                st.info(f"**{w['title']}**: {w['message']}")

    st.markdown("<br>", unsafe_allow_html=True)

    # 3. Before vs After Comparison Cards & Mission Success Gauge
    st.markdown("### 2. Sizing Impact Comparison")
    
    top_col1, top_col2 = st.columns([7, 3])

    with top_col1:
        st.markdown("##### Baseline vs Disturbed Sizing Telemetry")
        
        # Calculate metric deltas
        base_pwr = float(base_history["demand_kw"].max()) if "demand_kw" in base_history else 120.0
        dist_pwr = float(dist_history_df["demand_kw"].max()) if not dist_history_df.empty else base_pwr
        pwr_delta_pct = ((dist_pwr - base_pwr) / base_pwr) * 100.0

        base_fuel = base_summary["fuel_burned_kg"]
        dist_fuel = dist_res.fuel_burned_kg
        fuel_delta_pct = ((dist_fuel - base_fuel) / base_fuel) * 100.0 if base_fuel > 0 else 0.0

        base_soc = base_summary["final_soc"] * 100.0
        dist_soc = dist_res.final_soc * 100.0

        base_mtow = base_summary["total_mass_kg"]
        dist_mtow = dist_res.total_mass_kg

        base_endurance = base_summary["endurance_h"]
        dist_endurance = dist_res.endurance_h

        # Ground speed range estimate (km)
        v_ground = max(50.0, 250.0 - wind)
        dist_range_km = dist_endurance * v_ground
        base_range_km = base_endurance * 250.0

        m_cols1 = st.columns(3)
        with m_cols1[0]:
            kpi_card(
                "Peak Power Demand",
                f"{dist_pwr:.1f} kW",
                f"Baseline: {base_pwr:.1f} kW ({pwr_delta_pct:+.1f}%)"
            )
        with m_cols1[1]:
            kpi_card(
                "Fuel Consumed",
                f"{dist_fuel:.1f} kg",
                f"Baseline: {base_fuel:.1f} kg ({fuel_delta_pct:+.1f}%)"
            )
        with m_cols1[2]:
            kpi_card(
                "Final Battery SoC",
                f"{dist_soc:.1f}%",
                f"Baseline: {base_soc:.1f}% ({dist_soc - base_soc:+.1f}%)"
            )

        st.markdown("<br>", unsafe_allow_html=True)
        m_cols2 = st.columns(3)
        with m_cols2[0]:
            kpi_card(
                "Aircraft MTOW",
                f"{dist_mtow:.1f} kg",
                f"Baseline: {base_mtow:.1f} kg ({dist_mtow - base_mtow:+.1f} kg)"
            )
        with m_cols2[1]:
            kpi_card(
                "Effective Range",
                f"{dist_range_km:.0f} km",
                f"Baseline: {base_range_km:.0f} km ({dist_range_km - base_range_km:+.0f} km)"
            )
        with m_cols2[2]:
            kpi_card(
                "Mission Duration",
                f"{dist_endurance:.2f} hrs",
                f"Baseline: {base_endurance:.2f} hrs ({dist_endurance - base_endurance:+.2f} hrs)"
            )

    with top_col2:
        st.markdown("##### Mission Success Probability")
        prob_score = compute_mission_success_probability(dist_res, base_cfg, scenario)
        
        p = palette()
        gauge_fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=prob_score,
            number={"suffix": "%", "font": {"color": p["text"], "size": 36}},
            title={"text": "Survivability Index", "font": {"size": 14, "color": p["muted"]}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": p["border"]},
                "bar": {"color": p["primary"]},
                "bgcolor": p["panel"],
                "borderwidth": 1,
                "bordercolor": p["border"],
                "steps": [
                    {"range": [0, 50], "color": "rgba(239, 68, 68, 0.35)"},
                    {"range": [50, 80], "color": "rgba(245, 158, 11, 0.35)"},
                    {"range": [80, 100], "color": "rgba(16, 185, 129, 0.35)"},
                ],
            }
        ))
        gauge_fig.update_layout(
            template=plotly_template(),
            height=280,
            margin={"l": 20, "r": 20, "t": 30, "b": 20}
        )
        st.plotly_chart(gauge_fig, width="stretch", config={"displaylogo": False})

    st.markdown("---")

    # 4. Constraint Health Dashboard
    st.markdown("### 3. Sizing Constraint Health")
    health = compute_constraint_health(dist_res, base_cfg, scenario)

    h_cols = st.columns(3)
    idx = 0
    for title, info in health.items():
        col = h_cols[idx % 3]
        status = info["status"]
        detail = info["detail"]

        if status == "green":
            badge_html = '<span style="background: rgba(16,185,129,0.15); border: 1px solid var(--dash-green); color: var(--dash-green); border-radius: 4px; padding: 2px 8px; font-weight: 600; font-size: 0.75rem;">PASS</span>'
        elif status == "yellow":
            badge_html = '<span style="background: rgba(245,158,11,0.15); border: 1px solid var(--dash-amber); color: var(--dash-amber); border-radius: 4px; padding: 2px 8px; font-weight: 600; font-size: 0.75rem;">WARNING</span>'
        else:
            badge_html = '<span style="background: rgba(239,68,68,0.15); border: 1px solid var(--dash-red); color: var(--dash-red); border-radius: 4px; padding: 2px 8px; font-weight: 600; font-size: 0.75rem;">FAIL</span>'

        with col:
            st.markdown(
                f"""
                <div style="background: var(--dash-panel); border: 1px solid var(--dash-border); border-radius: 8px; padding: 0.9rem; margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                        <span style="font-weight: 600; font-size: 0.9rem; color: var(--dash-text);">{title}</span>
                        {badge_html}
                    </div>
                    <div style="color: var(--dash-muted); font-size: 0.8rem; font-family: monospace;">{detail}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
        idx += 1

    st.markdown("<br>", unsafe_allow_html=True)

    # 5. Disturbed Mission Timeline with Failure Annotations
    st.markdown("### 4. Disturbed Flight Telemetry & Timeline")
    
    if not dist_history_df.empty:
        fig = mission_timeline_figure(dist_history_df, soc_floor=0.20)
        
        # Annotate failure events on timeline
        p = palette()
        if scenario.generator_failed:
            fig.add_annotation(
                text="⚡ Generator Outage Injected",
                x=0.05,
                y=0,
                xref="paper",
                yref="paper",
                showarrow=True,
                arrowhead=2,
                arrowcolor=p["red"],
                font=dict(color=p["red"], size=12, weight="bold")
            )
        if scenario.battery_cell_failure_pct > 0:
            fig.add_annotation(
                text=f"🔋 Cell Loss ({scenario.battery_cell_failure_pct:.0f}%)",
                x=0.01,
                y=0.9,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(color=p["amber"], size=11, weight="bold")
            )
        if scenario.motor_failure_mode != "none":
            fig.add_annotation(
                text=f"⚙️ Motor {scenario.motor_failure_mode.upper()}",
                x=0.5,
                y=0.95,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(color=p["red"], size=11, weight="bold")
            )

        st.plotly_chart(fig, width="stretch", config={"displaylogo": False})


render()
