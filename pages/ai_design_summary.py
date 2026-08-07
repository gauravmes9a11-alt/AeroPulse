"""AI Design Summary Page - Automated Technical Report & Engineering Synthesis."""

from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from components.theme import kpi_card, palette, plotly_template
from models import ModelAssumptions
from utils.data_loader import config_from_state, run_simulation_cached
from ai_summarizer import (
    generate_ai_design_report,
    export_markdown_report,
    export_json_report,
)


def render() -> None:
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #064e3b 0%, #047857 50%, #059669 100%); padding: 1.5rem 2rem; border-radius: 12px; border: 1px solid #10b981; margin-bottom: 1.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.25);">
            <h1 style="color: #ffffff; margin: 0; font-size: 2.1rem; font-weight: 700; letter-spacing: -0.02em;">
                AI Design Summary & Technical Synthesis
            </h1>
            <p style="color: #a7f3d0; margin: 0.35rem 0 0 0; font-size: 0.95rem; font-weight: 500;">
                Automated executive technical evaluation, risk matrix, design insights, and engineering score.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cfg_state = st.session_state.get("selected_config") or {}
    if not cfg_state:
        st.info("Please configure hardware parameters in the sidebar first.")
        return

    base_cfg, base_ems = config_from_state(cfg_state)
    assumptions = ModelAssumptions()

    # Load active simulation summary & history
    summary = st.session_state.get("last_simulation")
    if summary is None:
        st.info("👈 Run a mission simulation from the **Mission Overview** page first to generate the AI Design Summary.")
        return

    # Reconstruct SimulationResult proxy object for report generator
    from mission_sim import SimulationResult
    res_obj = SimulationResult(
        success=bool(summary["success"]),
        first_violation=summary.get("first_violation") or None,
        fuel_burned_kg=float(summary["fuel_burned_kg"]),
        endurance_h=float(summary["endurance_h"]),
        final_soc=float(summary["final_soc"]),
        mission_avg_efficiency=float(summary["mission_avg_efficiency"]),
        degradation_proxy=float(summary["degradation_proxy"]),
        total_mass_kg=float(summary["total_mass_kg"]),
        history=st.session_state.get("last_history_df"),
        diagnostics=summary.get("diagnostics") or {},
    )

    # Generate AI Design Report
    report = generate_ai_design_report(res_obj, base_cfg, assumptions, cfg_state)

    p = palette()

    # 1. Top Section: Score Gauge & Grade Card + Executive Summary
    c_left, c_right = st.columns([4, 8])

    with c_left:
        st.markdown("### Overall Engineering Score")

        # Color based on grade
        if report.grade in {"A+", "A"}:
            grade_color = p["green"]
            grade_bg = "rgba(16, 185, 129, 0.15)"
        elif report.grade == "B":
            grade_color = p["primary"]
            grade_bg = "rgba(59, 130, 246, 0.15)"
        elif report.grade == "C":
            grade_color = p["amber"]
            grade_bg = "rgba(245, 158, 11, 0.15)"
        else:
            grade_color = p["red"]
            grade_bg = "rgba(239, 68, 68, 0.15)"

        # Gauge Chart
        gauge_fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=report.score,
            number={"suffix": "/100", "font": {"color": p["text"], "size": 38, "family": "JetBrains Mono"}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": p["border"]},
                "bar": {"color": grade_color},
                "bgcolor": p["panel"],
                "borderwidth": 1,
                "bordercolor": p["border"],
                "steps": [
                    {"range": [0, 60], "color": "rgba(239, 68, 68, 0.25)"},
                    {"range": [60, 75], "color": "rgba(245, 158, 11, 0.25)"},
                    {"range": [75, 85], "color": "rgba(59, 130, 246, 0.25)"},
                    {"range": [85, 100], "color": "rgba(16, 185, 129, 0.25)"},
                ],
            }
        ))
        gauge_fig.update_layout(
            template=plotly_template(),
            height=250,
            margin={"l": 25, "r": 25, "t": 25, "b": 10}
        )
        st.plotly_chart(gauge_fig, width="stretch", config={"displaylogo": False})

        st.markdown(
            f'<div style="background: {grade_bg}; border: 1px solid {grade_color}; border-radius: 8px; padding: 0.75rem; text-align: center; margin-top: -0.5rem;"><span style="color: var(--dash-muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em;">DESIGN EVALUATION GRADE</span><br><span style="font-size: 2.2rem; font-weight: 800; color: {grade_color}; font-family: \'JetBrains Mono\', monospace;">{report.grade}</span></div>',
            unsafe_allow_html=True,
        )

    with c_right:
        st.markdown("### Executive Engineering Summary")
        st.markdown(
            f'<div style="background: var(--dash-panel); border: 1px solid var(--dash-border); border-radius: 10px; padding: 1.25rem; font-family: \'JetBrains Mono\', monospace; font-size: 0.88rem; line-height: 1.6; white-space: pre-wrap; color: var(--dash-text); box-shadow: 0 4px 6px rgba(0,0,0,0.1);">{report.executive_summary}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")

    # 2. Design Insights & Engineering Recommendations
    c_ins, c_recs = st.columns(2)

    with c_ins:
        st.markdown("### 💡 Automated Design Insights")
        ins_html = '<div style="display: flex; flex-direction: column; gap: 0.65rem;">'
        for ins in report.insights:
            ins_html += f'<div style="background: var(--dash-panel); border: 1px solid var(--dash-border); border-left: 4px solid var(--dash-primary); border-radius: 6px; padding: 0.8rem 1rem; font-size: 0.9rem; color: var(--dash-text);">{ins}</div>'
        ins_html += '</div>'
        st.markdown(ins_html, unsafe_allow_html=True)

    with c_recs:
        st.markdown("### 🔧 Engineering Recommendations")
        recs_html = '<div style="display: flex; flex-direction: column; gap: 0.65rem;">'
        for rec in report.recommendations:
            recs_html += f'<div style="background: var(--dash-panel); border: 1px solid var(--dash-border); border-left: 4px solid var(--dash-green); border-radius: 6px; padding: 0.8rem 1rem; font-size: 0.9rem; color: var(--dash-text);">{rec}</div>'
        recs_html += '</div>'
        st.markdown(recs_html, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")

    # 3. Risk Analysis Matrix
    st.markdown("### 🛡️ Subsystem Risk Analysis Matrix")
    
    r_cols = st.columns(3)
    idx = 0
    for sys_name, r_info in report.risk_analysis.items():
        col = r_cols[idx % 3]
        lvl = r_info["level"]
        detail = r_info["detail"]

        if lvl == "LOW":
            lvl_html = '<span style="background: rgba(16,185,129,0.15); border: 1px solid var(--dash-green); color: var(--dash-green); border-radius: 4px; padding: 2px 8px; font-weight: 600; font-size: 0.75rem;">LOW RISK</span>'
        elif lvl == "MEDIUM":
            lvl_html = '<span style="background: rgba(245,158,11,0.15); border: 1px solid var(--dash-amber); color: var(--dash-amber); border-radius: 4px; padding: 2px 8px; font-weight: 600; font-size: 0.75rem;">MEDIUM RISK</span>'
        else:
            lvl_html = '<span style="background: rgba(239,68,68,0.15); border: 1px solid var(--dash-red); color: var(--dash-red); border-radius: 4px; padding: 2px 8px; font-weight: 600; font-size: 0.75rem;">HIGH RISK</span>'

        with col:
            st.markdown(
                f'<div style="background: var(--dash-panel); border: 1px solid var(--dash-border); border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem;"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;"><span style="font-weight: 600; font-size: 0.95rem; color: var(--dash-text);">{sys_name}</span>{lvl_html}</div><div style="color: var(--dash-muted); font-size: 0.82rem; line-height: 1.4;">{detail}</div></div>',
                unsafe_allow_html=True,
            )
        idx += 1

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")

    # 4. Input Context Summary & Export Panel
    st.markdown("### 📄 Design Report Export & Documentation")
    
    exp_col1, exp_col2 = st.columns([7, 5])

    with exp_col1:
        st.markdown("##### Configuration Parameters & Sizing Summary")
        summary_items = report.input_summary
        
        df_summary = pd.DataFrame([
            {"Parameter": k.replace("_", " ").title(), "Value": f"{v:.2f}" if isinstance(v, float) else str(v)}
            for k, v in summary_items.items()
        ])
        st.dataframe(df_summary, height=280, use_container_width=True, hide_index=True)

    with exp_col2:
        st.markdown("##### Download Technical Documentation")
        st.caption("Export the complete AI design synthesis report in standard aerospace formats:")
        
        md_text = export_markdown_report(report)
        json_text = export_json_report(report)
        txt_text = report.executive_summary

        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            "📥 Download Report (Markdown .md)",
            data=md_text,
            file_name="uav_ai_design_summary.md",
            mime="text/markdown",
            use_container_width=True,
        )
        st.download_button(
            "📥 Download Data Schema (JSON .json)",
            data=json_text,
            file_name="uav_ai_design_summary.json",
            mime="application/json",
            use_container_width=True,
        )
        st.download_button(
            "📥 Download Executive Summary (Text .txt)",
            data=txt_text,
            file_name="executive_summary.txt",
            mime="text/plain",
            use_container_width=True,
        )


render()
