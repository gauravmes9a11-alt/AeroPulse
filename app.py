"""Streamlit dashboard entry point and page router."""

from __future__ import annotations

import base64
import streamlit as st
import streamlit.components.v1 as components

from components.theme import inject_css
from utils.data_loader import (
    ALLOCATION_KEY_TO_LABEL,
    ALLOCATION_LABEL_TO_KEY,
    EMS_LABEL_TO_TIER,
    ensure_session_defaults,
)


from pathlib import Path


def get_base64_image(image_path: str) -> str:
    try:
        path = Path(__file__).parent / image_path
        if not path.exists():
            path = Path(image_path)
        with open(path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode("utf-8")
    except Exception:
        return ""


st.set_page_config(
    page_title="Hybrid UAV Propulsion Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_session_defaults()

# CRITICAL: Initialize sidebar toggle state in session_state
if "sidebar_toggle_state" not in st.session_state:
    st.session_state["sidebar_toggle_state"] = True

# Inject CSS FIRST (before any UI elements)
inject_css()

hal_b64 = get_base64_image("assets/hal_logo.png")

# ---------------------------------------------------------------------------
# Sidebar toggle button & top header with HAL logo
# ---------------------------------------------------------------------------
components.html(
    f"""
    <script>
    const doc = window.parent.document;

    function initSidebarHeader() {{
        const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
        if (!sidebar) return;

        let header = doc.getElementById('custom-sidebar-header');
        if (!header) {{
            header = doc.createElement('div');
            header.id = 'custom-sidebar-header';
            header.style.cssText = `
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 0.6rem 0.85rem;
                border-bottom: 1px solid var(--dash-border, #1e375c);
                background: linear-gradient(135deg, #060d19 0%, #142542 100%);
                margin-bottom: 0rem;
            `;
            header.innerHTML = `
                <button id="custom-sidebar-toggle" title="Toggle sidebar" style="
                    width: 36px;
                    height: 36px;
                    border-radius: 6px;
                    background: var(--dash-panel-2, #1e2530);
                    border: 1px solid var(--dash-border, #333);
                    color: var(--dash-text, #fff);
                    cursor: pointer;
                    font-size: 16px;
                    line-height: 1;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    flex-shrink: 0;
                ">&#9776;</button>
                <div style="background: #ffffff; padding: 3px; border-radius: 6px; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
                    <img src="data:image/png;base64,{hal_b64}" style="max-width: 100%; max-height: 100%; object-fit: contain;">
                </div>
                <div>
                    <div style="font-weight: 700; font-size: 0.92rem; color: #f1f5f9; line-height: 1.1; letter-spacing: -0.01em;">HAL Aerothon</div>
                    <div style="font-size: 0.68rem; color: #8ea3c2; font-weight: 500; margin-top: 2px;">UAV Propulsion Sizing</div>
                </div>
            `;
            sidebar.insertBefore(header, sidebar.firstChild);

            const btn = doc.getElementById('custom-sidebar-toggle');
            if (btn) {{
                btn.addEventListener('mouseenter', function () {{
                    btn.style.background = 'var(--dash-primary, #3b82f6)';
                    btn.style.borderColor = 'var(--dash-primary, #3b82f6)';
                }});
                btn.addEventListener('mouseleave', function () {{
                    btn.style.background = 'var(--dash-panel-2, #1e2530)';
                    btn.style.borderColor = 'var(--dash-border, #333)';
                }});
                btn.addEventListener('click', function () {{
                    const native =
                        doc.querySelector('[data-testid="stSidebarCollapseButton"] button') ||
                        doc.querySelector('[data-testid="stSidebarCollapsedControl"] button') ||
                        doc.querySelector('[data-testid="stSidebarCollapseButton"]') ||
                        doc.querySelector('[data-testid="stSidebarCollapsedControl"]');
                    if (native) native.click();
                }});
            }}
        }}
    }}

    initSidebarHeader();

    const observer = new MutationObserver(initSidebarHeader);
    observer.observe(doc.body, {{ childList: true, subtree: true }});
    </script>
    """,
    height=0,
    width=0,
)

st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] {
        background: var(--dash-panel);
        border-right: 1px solid var(--dash-border);
    }

    section[data-testid="stSidebar"] * {
        color: var(--dash-text);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.session_state["theme_mode"] = st.radio(
        "Theme",
        ["Dark", "Light"],
        index=["Dark", "Light"].index(st.session_state.get("theme_mode", "Dark")),
        horizontal=True,
    )


def sidebar_configuration() -> None:
    """Shared hardware sizing and power-sharing input panel."""

    cfg = st.session_state["selected_config"]
    # Backward compat: ensure new keys exist for old cached configs.
    cfg.setdefault("num_motors", 1)
    cfg.setdefault("motor_allocation", "even_split")

    with st.sidebar:
        # ---------------------------------------------------------------
        # Section 1: Hardware Sizing
        # ---------------------------------------------------------------
        st.markdown("### Hardware Sizing")
        cfg["turbine_rating_kw"] = st.number_input(
            "Turbine rating (kW)",
            min_value=30.0,
            max_value=120.0,
            value=float(cfg["turbine_rating_kw"]),
            step=1.0,
        )
        cfg["generator_rating_kw"] = st.number_input(
            "Generator rating (kW)",
            min_value=30.0,
            max_value=130.0,
            value=float(cfg["generator_rating_kw"]),
            step=1.0,
        )
        cfg["battery_capacity_kwh"] = st.number_input(
            "Battery capacity (kWh)",
            min_value=1.0,
            max_value=120.0,
            value=float(cfg["battery_capacity_kwh"]),
            step=1.0,
        )
        cfg["battery_peak_power_kw"] = st.number_input(
            "Battery peak power (kW)",
            min_value=10.0,
            max_value=180.0,
            value=float(cfg["battery_peak_power_kw"]),
            step=1.0,
        )
        cfg["fuel_mass_kg"] = st.number_input(
            "Fuel mass (kg)",
            min_value=1.0,
            max_value=250.0,
            value=float(cfg["fuel_mass_kg"]),
            step=1.0,
        )

        # Motor count — design variable
        motor_options = [1, 2, 4]
        current_n = int(cfg.get("num_motors", 1))
        if current_n not in motor_options:
            current_n = 1
        cfg["num_motors"] = st.selectbox(
            "Number of propulsion motors",
            motor_options,
            index=motor_options.index(current_n),
        )
        st.caption("Number of motors sharing the total 120 kW motor power.")

        # ---------------------------------------------------------------
        # Section 2: Power Sharing Strategy
        # ---------------------------------------------------------------
        st.markdown("---")
        st.markdown("### Power Sharing Strategy")

        # 1. EMS tier selector
        ems_labels = list(EMS_LABEL_TO_TIER)
        cfg["ems_label"] = st.selectbox(
            "EMS tier",
            ems_labels,
            index=ems_labels.index(cfg.get("ems_label", "Rule-Based")),
        )
        st.caption("Selects how the generator and battery split electrical load.")

        # 2. Generator setpoint (only for Rule-Based)
        if cfg["ems_label"] == "Rule-Based":
            gen_rating = float(cfg["generator_rating_kw"])
            gen_sp_min = round(0.5 * gen_rating, 1)
            gen_sp_max = round(gen_rating, 1)
            gen_sp_default = round(gen_rating * 0.9, 1)
            # Clamp current value into the valid range
            current_sp = float(cfg.get("generator_setpoint_kw", gen_sp_default))
            current_sp = max(gen_sp_min, min(current_sp, gen_sp_max))
            cfg["generator_setpoint_kw"] = st.slider(
                "Generator target setpoint (kW)",
                min_value=gen_sp_min,
                max_value=gen_sp_max,
                value=current_sp,
                step=1.0,
            )
            st.caption("Steady-state generator power output target during cruise.")

        # 3. Target battery SoC band
        soc_low, soc_high = st.slider(
            "Target SoC band",
            min_value=0.20,
            max_value=1.00,
            value=(
                float(cfg.get("target_soc_low", 0.35)),
                float(cfg.get("target_soc_high", 0.90)),
            ),
            step=0.01,
        )
        cfg["target_soc_low"] = soc_low
        cfg["target_soc_high"] = soc_high
        st.caption("Desired battery charge range \u2014 generator compensates outside this band.")

        # 4. Max charge C-rate
        cfg["max_charge_c_rate"] = st.slider(
            "Max charge C-rate",
            min_value=0.5,
            max_value=2.0,
            value=float(cfg.get("max_charge_c_rate", 1.0)),
            step=0.1,
        )
        st.caption("How fast the generator is allowed to recharge the battery.")

        # 5. ECMS equivalence factor (only for ECMS)
        if cfg["ems_label"] == "ECMS":
            cfg["ecms_equivalence_factor"] = st.slider(
                "ECMS equivalence factor (kg/kWh)",
                min_value=0.0,
                max_value=1.0,
                value=float(cfg.get("ecms_equivalence_factor", 0.22)),
                step=0.01,
            )
            st.caption("Penalty factor converting battery energy to equivalent fuel cost.")

        # 6. Motor allocation strategy (only when num_motors > 1)
        if int(cfg.get("num_motors", 1)) > 1:
            alloc_labels = list(ALLOCATION_LABEL_TO_KEY.keys())
            current_alloc = cfg.get("motor_allocation", "even_split")
            current_label = ALLOCATION_KEY_TO_LABEL.get(current_alloc, alloc_labels[0])
            if current_label not in alloc_labels:
                current_label = alloc_labels[0]
            selected_label = st.selectbox(
                "Motor allocation strategy",
                alloc_labels,
                index=alloc_labels.index(current_label),
            )
            cfg["motor_allocation"] = ALLOCATION_LABEL_TO_KEY[selected_label]
            st.caption("How total motor power is distributed across individual motors.")
        else:
            cfg["motor_allocation"] = "even_split"
            st.caption("Enable multiple motors above to configure allocation.")

        st.session_state["selected_config"] = cfg


sidebar_configuration()

pages = [
    st.Page("pages/mission_overview.py", title="1. Mission Overview"),
    st.Page("pages/mission_timeline.py", title="2. Mission Timeline"),
    st.Page("pages/energy_management.py", title="3. Energy Management"),
    st.Page("pages/optimization_pareto.py", title="4. Optimization Explorer"),
    st.Page("pages/sensitivity_analysis.py", title="5. Sensitivity Analysis"),
    st.Page("pages/analytics_dashboard.py", title="6. Analytics Dashboard"),
    st.Page("pages/design_summary_export.py", title="7. Design Report"),
    st.Page("pages/failure_injection.py", title="8. Failure & What-If"),
    st.Page("pages/ai_design_summary.py", title="9. AI Design Summary"),
]

pg = st.navigation(pages, position="sidebar")
pg.run()