"""UAV Sizing and Mission Overview landing page."""

from __future__ import annotations

import streamlit as st

from components.theme import inject_css, kpi_card, status_badge
from utils.data_loader import run_simulation_cached


def render() -> None:
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%); padding: 1.5rem 2rem; border-radius: 12px; border: 1px solid #1e375c; margin-bottom: 2rem; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
            <h1 style="color: #ffffff; margin: 0; font-size: 2.1rem; font-weight: 700; letter-spacing: -0.02em;">
                Hybrid-Electric UAV Propulsion Sizing Dashboard
            </h1>
            <p style="color: #93c5fd; margin: 0.35rem 0 0 0; font-size: 0.95rem; font-weight: 500;">
                HAL Aerothon Optimization Framework
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 1. UAV Sizing Constraints Envelope
    st.markdown("### 1. UAV Mission Specifications")
    top_cols = st.columns(4)
    with top_cols[0]:
        kpi_card("Maximum Takeoff Weight", "1,000 kg", "MTOW structural limit")
    with top_cols[1]:
        kpi_card("Payload Capacity", "200 kg", "Fixed mission payload")
    with top_cols[2]:
        kpi_card("Nominal Cruise Speed", "250 km/h", "Fixed operational speed")
    with top_cols[3]:
        kpi_card("Operating Cruise Altitude", "3,000 m", "Density altitude baseline")

    st.markdown("---")

    # 2. Selected Sizing Ratings
    st.markdown("### 2. Active Sizing Configuration (Hardware & EMS)")
    cfg = st.session_state.get("selected_config") or {}
    if not cfg:
        st.info("The hardware configuration has not been initialized yet. Please wait for the dashboard to load.")
        return
    
    # Render component details in a clean card layout
    c_cols = st.columns(6)
    with c_cols[0]:
        st.metric("Turbine Rating", f"{cfg['turbine_rating_kw']:.1f} kW", help="Rated shaft power of auxiliary turbine")
    with c_cols[1]:
        st.metric("Generator Rating", f"{cfg['generator_rating_kw']:.1f} kW", help="Continuous generator power rating")
    with c_cols[2]:
        st.metric("Battery capacity", f"{cfg['battery_capacity_kwh']:.1f} kWh", help="Energy capacity of battery pack")
    with c_cols[3]:
        st.metric("Battery peak power", f"{cfg['battery_peak_power_kw']:.1f} kW", help="Short-term discharge peak power limit")
    with c_cols[4]:
        st.metric("Fuel mass load", f"{cfg['fuel_mass_kg']:.1f} kg", help="Usable liquid fuel mass")
    with c_cols[5]:
        st.metric("EMS Strategy", str(cfg["ems_label"]), help="Energy management tier strategy")

    # 3. Execution Trigger
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([1.5, 8.5])
    with c1:
        run_clicked = st.button("Run Simulation", type="primary", width="stretch")
    with c2:
        st.markdown(
            "<div style='margin-top: 0.5rem; color: var(--dash-muted); font-size: 0.85rem; font-style: italic;'>"
            "Note: Modifying hardware parameters in the sidebar resets simulation results. Run simulation to verify your configuration."
            "</div>",
            unsafe_allow_html=True
        )

    if run_clicked:
        with st.spinner("Running 1 Hz time-stepped mission simulation..."):
            summary, history = run_simulation_cached(cfg)
            
            # Extract prop mass to compute aircraft weight profile
            # Let's import the specific helper
            from models import ModelAssumptions, propulsion_mass_kg
            assumptions = ModelAssumptions()
            from utils.data_loader import config_from_state
            hw_cfg, _ = config_from_state(cfg)
            prop_mass = propulsion_mass_kg(hw_cfg, assumptions)["total_propulsion"]
            
            # Structural + Payload + Prop + Fuel
            history["weight_kg"] = 430.0 + 200.0 + prop_mass + history["fuel_remaining_kg"]
            
        st.session_state["last_simulation"] = summary
        st.session_state["last_history_df"] = history
        st.toast("Simulation executed successfully!", icon="🛫")

    st.markdown("<br>", unsafe_allow_html=True)

    # 4. Simulation Results Summary
    summary = st.session_state.get("last_simulation")
    if not summary:
        st.info("👈 Set hardware parameters in the sidebar and click **Run Simulation** to compute flight telemetry.")
        return

    st.markdown("### 3. Verification & Sizing Results")
    
    # Status Alert Panel
    is_success = bool(summary["success"])
    if is_success:
        st.markdown(
            f"""
            <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid var(--dash-green); border-radius: 8px; padding: 0.85rem 1.25rem; margin-bottom: 1.25rem; display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 1.1rem;">✅</span>
                <span style="font-weight: 600; color: var(--dash-green);">CONFIGURATION VERIFICATION PASSED:</span>
                <span style="color: var(--dash-text);">Propulsion sizing is feasible. All thermal, power, and fuel limits satisfied.</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        violation = summary["first_violation"] or "Constraint violation detected."
        st.markdown(
            f"""
            <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid var(--dash-red); border-radius: 8px; padding: 0.85rem 1.25rem; margin-bottom: 1.25rem; display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 1.1rem;">⚠️</span>
                <span style="font-weight: 600; color: var(--dash-red);">CONSTRAINT VIOLATION:</span>
                <span style="color: var(--dash-text); font-family: monospace;">{violation}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    res_cols = st.columns(5)
    with res_cols[0]:
        kpi_card("Mission Endurance", f"{summary['endurance_h']:.2f} hrs", "Target: maximize endurance")
    with res_cols[1]:
        kpi_card("Fuel Burned", f"{summary['fuel_burned_kg']:.2f} kg", f"Remaining: {cfg['fuel_mass_kg'] - summary['fuel_burned_kg']:.1f} kg")
    with res_cols[2]:
        kpi_card("Final Battery SoC", f"{100 * summary['final_soc']:.1f}%", f"Min SoC during flight: {100 * summary['diagnostics']['min_soc']:.1f}%")
    with res_cols[3]:
        kpi_card("Avg Chain Efficiency", f"{100 * summary['mission_avg_efficiency']:.1f}%", "Chemical/electrical integration")
    with res_cols[4]:
        kpi_card("Aircraft Weight Sized", f"{summary['total_mass_kg']:.1f} kg", "Limit: 1,000.0 kg MTOW")

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("Detailed timelines and power distribution profiles are available on the **Mission Timeline** and **Energy Management** pages.")


render()
