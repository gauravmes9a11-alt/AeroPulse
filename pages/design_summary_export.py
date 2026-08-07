"""Design Summary and Export page for generating report deliverables."""

from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path

from components.export import build_design_summary_pdf
from components.theme import status_badge, kpi_card
from models import ModelAssumptions
from utils.data_loader import load_pareto_csv, mission_csv_bytes, pareto_csv_bytes


def render() -> None:
    st.title("Design Summary & Engineering Report")
    st.caption("Review flight specifications, engineering modeling assumptions, and export publication-ready reports (PDF, CSV, and PNG charts).")

    cfg = st.session_state.get("selected_config") or {}
    summary = st.session_state.get("last_simulation")
    if not cfg:
        st.info("The hardware configuration is not available yet. Please return to Mission Overview and run a simulation first.")
        return
    history = st.session_state.get("last_history_df")
    pareto = load_pareto_csv()
    assumptions = ModelAssumptions()

    # 1. Engineering Sizing Summary Card
    st.markdown("### 1. Sizing Summary Report")
    
    col1, col2 = st.columns([6, 4])
    
    with col1:
        st.markdown("##### Recommended Configuration Specification")
        st.write(
            f"The current series hybrid-electric UAV propulsion system design has been configured "
            f"using a **{cfg['ems_label']}** energy-management strategy. The primary mechanical "
            f"shaft power source is rated at **{cfg['turbine_rating_kw']:.1f} kW** driving a "
            f"**{cfg['generator_rating_kw']:.1f} kW** generator, coupled with a "
            f"**{cfg['battery_capacity_kwh']:.1f} kWh** battery pack supplying up to "
            f"**{cfg['battery_peak_power_kw']:.1f} kW** peak electrical load."
        )
        
        # Display small config metrics table
        cfg_rows = [
            ("Turbine Shaft Power", f"{cfg['turbine_rating_kw']:.1f} kW"),
            ("Generator Sized Power", f"{cfg['generator_rating_kw']:.1f} kW"),
            ("Battery Pack Energy Capacity", f"{cfg['battery_capacity_kwh']:.1f} kWh"),
            ("Battery Peak Output Power", f"{cfg['battery_peak_power_kw']:.1f} kW"),
            ("Liquid Fuel Capacity Sized", f"{cfg['fuel_mass_kg']:.1f} kg"),
            ("EMS Strategy Tier", f"{cfg['ems_label']}"),
        ]
        cfg_df = pd.DataFrame(cfg_rows, columns=["Design Parameter", "Sized Value"])
        st.dataframe(cfg_df, width="stretch", hide_index=True)
        
    with col2:
        st.markdown("##### Sized Objective Metrics")
        if summary:
            # Show target metrics
            st.metric("Total Mission Flight Time", f"{summary['endurance_h']:.2f} hrs")
            st.metric("Liquid Fuel Depleted", f"{summary['fuel_burned_kg']:.2f} kg")
            st.metric("Integrated Chain Efficiency", f"{100 * summary['mission_avg_efficiency']:.1f}%")
            
            is_pass = bool(summary["success"])
            st.markdown("<div class='kpi-label'>Feasibility Verdict</div>", unsafe_allow_html=True)
            status_badge(is_pass)
            if not is_pass:
                st.error(summary["first_violation"] or "Constraint violation detected.")
        else:
            st.info("💡 Sized performance telemetry will be displayed once a simulation is executed.")

    st.markdown("---")

    # 2. Sizing Modeling Assumptions Log
    st.markdown("### 2. Sizing Modeling Assumptions (Section 5.2 Parameters)")
    
    asm_cols = st.columns(3)
    
    with asm_cols[0]:
        st.metric("Ref. Specific Fuel Consumption (SFC)", f"{assumptions.sfc_ref_kg_per_kwh:.3f} kg/kWh")
        st.metric("Generator Peak Efficiency", f"{100 * assumptions.generator_eta_peak:.1f}%")
    with asm_cols[1]:
        st.metric("Battery energy density", f"{assumptions.battery_specific_energy_wh_per_kg:.1f} Wh/kg")
        st.metric("Motor + Inverter Peak Efficiency", f"{100 * assumptions.motor_inv_eta_peak:.1f}%")
    with asm_cols[2]:
        st.metric("Battery round-trip efficiency", f"{100 * assumptions.battery_roundtrip_eta:.1f}%")
        st.metric("DC distribution bus efficiency", f"{100 * (1.0 - assumptions.bus_loss_frac):.1f}%")

    st.markdown("---")

    # 3. Deliverables Exporter
    st.markdown("### 3. Sizing Framework Deliverables Exporter")
    
    ex_cols = st.columns(3)
    
    # Col A: PDF Summaries
    with ex_cols[0]:
        st.markdown("##### PDF Engineering Report")
        st.write("Generates a publication-quality double-page report documenting configurations, margins, and study parameters.")
        
        if summary:
            pdf_bytes = build_design_summary_pdf(cfg, summary, assumptions=assumptions)
            st.download_button(
                "Export Design Report PDF",
                data=pdf_bytes,
                file_name="hybrid_uav_sizing_report.pdf",
                mime="application/pdf",
                width="stretch"
            )
        else:
            st.caption("⚠️ PDF report available after running a simulation.")
            
    # Col B: CSV Datasets
    with ex_cols[1]:
        st.markdown("##### CSV Telemetry & Pareto Sets")
        st.write("Download flight telemetry time-series logs or the optimization Pareto front dataset.")
        
        if history is not None and not history.empty:
            st.download_button(
                "Download Sizing Telemetry CSV",
                data=mission_csv_bytes(history),
                file_name="propulsion_sizing_telemetry.csv",
                mime="text/csv",
                width="stretch"
            )
        else:
            st.caption("⚠️ Mission CSV telemetry available after simulation.")
            
        if not pareto.empty:
            st.download_button(
                "Download Sizing Pareto CSV",
                data=pareto_csv_bytes(pareto),
                file_name="propulsion_sizing_pareto.csv",
                mime="text/csv",
                width="stretch"
            )
        else:
            st.caption("⚠️ Pareto CSV available after optimization.")

    # Col C: PNG Chart Packages
    with ex_cols[2]:
        st.markdown("##### Matplotlib PNG Charts")
        st.write("Render high-resolution Matplotlib PNG charts for sizing timelines, SoC tracking, and power splits.")
        
        if history is not None and not history.empty:
            if st.button("Generate Sizing PNG Charts", width="stretch"):
                with st.spinner("Rendering Matplotlib graphics..."):
                    try:
                        from plots import plot_fuel_remaining, plot_mission_timeline, plot_power_split, plot_soc_profile
                        
                        # Convert history DF to dict of ndarrays
                        h_dict = {col: history[col].values for col in history.columns}
                        
                        out_dir = Path("outputs")
                        plot_mission_timeline(h_dict, out_dir)
                        plot_soc_profile(h_dict, out_dir)
                        plot_fuel_remaining(h_dict, out_dir)
                        plot_power_split(h_dict, out_dir)
                        
                        st.success("Sizing charts rendered successfully to `outputs/` folder!")
                        
                        # Show files and let user download them
                        st.session_state["png_rendered"] = True
                    except Exception as e:
                        st.error(f"Error rendering charts: {e}")
                        
            if st.session_state.get("png_rendered", False):
                # We can read and offer individual download buttons for the PNGs
                for png_name, file_base in [
                    ("Mission Timeline Chart", "mission_timeline.png"),
                    ("SoC Profile Chart", "soc_profile.png"),
                    ("Fuel Depletion Chart", "fuel_remaining.png"),
                    ("Power Split Chart", "power_split.png"),
                ]:
                    f_path = Path("outputs") / file_base
                    if f_path.exists():
                        with open(f_path, "rb") as f:
                            st.download_button(
                                f"Download {png_name}",
                                data=f.read(),
                                file_name=file_base,
                                mime="image/png",
                                width="stretch"
                            )
        else:
            st.caption("⚠️ Sizing charts can be exported after running a simulation.")


render()
