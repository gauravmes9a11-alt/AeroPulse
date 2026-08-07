"""Theme and shared Streamlit UI helpers with premium aerospace/military design language.

Inspired by Tesla, NASA Mission Control, Ansys, and MATLAB App Designer.
"""

from __future__ import annotations

from typing import Any
import streamlit as st
import streamlit.components.v1 as components

# Premium color palettes (Navy Blue, Steel Blue, Amber Warnings, Red Violations)
DARK = {
    "bg": "#060d19",
    "panel": "#0c172a",
    "panel_2": "#142542",
    "text": "#f1f5f9",
    "muted": "#8ea3c2",
    "border": "#1e375c",
    "primary": "#3b82f6",
    "primary_hover": "#60a5fa",
    "amber": "#f59e0b",
    "red": "#ef4444",
    "green": "#10b981",
}

LIGHT = {
    "bg": "#f8fafc",
    "panel": "#ffffff",
    "panel_2": "#f1f5f9",
    "text": "#0f172a",
    "muted": "#64748b",
    "border": "#cbd5e1",
    "primary": "#2563eb",
    "primary_hover": "#1d4ed8",
    "amber": "#d97706",
    "red": "#dc2626",
    "green": "#16a34a",
}


def palette() -> dict[str, str]:
    return DARK if st.session_state.get("theme_mode", "Dark") == "Dark" else LIGHT


def plotly_template() -> dict[str, Any]:
    p = palette()
    return {
        "layout": {
            "paper_bgcolor": p["bg"],
            "plot_bgcolor": p["panel"],
            "font": {"color": p["text"], "family": "Inter, system-ui, -apple-system, sans-serif"},
            "colorway": [p["primary"], p["amber"], p["green"], "#a855f7", "#06b6d4"],
            "xaxis": {
                "gridcolor": p["border"],
                "zerolinecolor": p["border"],
                "linecolor": p["border"],
                "ticks": "outside",
            },
            "yaxis": {
                "gridcolor": p["border"],
                "zerolinecolor": p["border"],
                "linecolor": p["border"],
                "ticks": "outside",
            },
        }
    }


def inject_css() -> None:
    p = palette()
    # Google Font imports and premium UI adjustments
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

        :root {{
          --dash-bg: {p["bg"]};
          --dash-panel: {p["panel"]};
          --dash-panel-2: {p["panel_2"]};
          --dash-text: {p["text"]};
          --dash-muted: {p["muted"]};
          --dash-border: {p["border"]};
          --dash-primary: {p["primary"]};
          --dash-primary-hover: {p["primary_hover"]};
          --dash-amber: {p["amber"]};
          --dash-red: {p["red"]};
          --dash-green: {p["green"]};
        }}

        /* App container background and font */
        .stApp {{
          background: var(--dash-bg);
          color: var(--dash-text);
          font-family: 'Inter', system-ui, -apple-system, sans-serif;
        }}

        /* Hide Streamlit branding but keep header transparent */
        header[data-testid="stHeader"] {{
          background: transparent !important;
        }}
        div[data-testid="stToolbar"], footer, #MainMenu {{
          visibility: hidden !important;
          height: 0 !important;
        }}

        /* Sidebar Styling */
        section[data-testid="stSidebar"] {{
          background: var(--dash-panel) !important;
          border-right: 1px solid var(--dash-border) !important;
          overflow-y: auto !important;
        }}
        section[data-testid="stSidebar"] > div {{
          padding-top: 0rem !important;
        }}
        div[data-testid="stSidebarNav"], div[data-testid="stSidebarUserContent"] {{
          padding-top: 0rem !important;
          margin-top: 0rem !important;
        }}
        section[data-testid="stSidebar"] * {{
          color: var(--dash-text);
        }}

        /* Hide the collapse button inside the sidebar so user can't close it */
        [data-testid="stSidebarCollapseButton"] {{
          display: none !important;
        }}

        /* Spacing and container widths */
        .block-container {{
          padding-top: 1.5rem;
          padding-bottom: 2rem;
          max-width: 1440px;
        }}

        /* Headings & Text */
        h1, h2, h3, h4, h5, h6 {{
          color: var(--dash-text);
          font-weight: 600;
          letter-spacing: -0.025em;
        }}
        p, label, span, li {{
          color: var(--dash-text);
        }}

        /* Custom Cards (KPI & Soft Panel) */
        .kpi-card {{
          background: var(--dash-panel);
          border: 1px solid var(--dash-border);
          border-radius: 10px;
          padding: 1rem 1.2rem;
          min-height: 100px;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
          transition: border-color 0.2s ease-in-out, transform 0.2s ease-in-out;
        }}
        .kpi-card:hover {{
          border-color: var(--dash-border);
          transform: translateY(-2px);
        }}
        .kpi-label {{
          color: var(--dash-muted);
          font-size: 0.78rem;
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          margin-bottom: 0.35rem;
        }}
        .kpi-value {{
          color: var(--dash-text);
          font-family: 'JetBrains Mono', 'Cascadia Mono', monospace;
          font-size: 1.75rem;
          font-weight: 700;
          line-height: 1.1;
          white-space: nowrap;
        }}
        .kpi-note {{
          color: var(--dash-muted);
          font-size: 0.75rem;
          margin-top: 0.35rem;
        }}

        /* Status Badges */
        .status-badge {{
          display: inline-flex;
          align-items: center;
          border-radius: 6px;
          padding: 0.3rem 0.75rem;
          font-weight: 600;
          font-size: 0.85rem;
          border: 1px solid transparent;
          text-transform: uppercase;
          letter-spacing: 0.02em;
        }}
        .status-ok {{
          background: rgba(16, 185, 129, 0.15);
          border-color: var(--dash-green);
          color: var(--dash-green);
        }}
        .status-bad {{
          background: rgba(239, 68, 68, 0.15);
          border-color: var(--dash-red);
          color: var(--dash-red);
        }}
        .status-warning {{
          background: rgba(245, 158, 11, 0.15);
          border-color: var(--dash-amber);
          color: var(--dash-amber);
        }}

        .soft-panel {{
          background: var(--dash-panel);
          border: 1px solid var(--dash-border);
          border-radius: 10px;
          padding: 1.25rem;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        }}
        .muted {{
          color: var(--dash-muted);
        }}

        /* Streamlit Default Component Overrides */
        div[data-testid="stMetric"] {{
          background: var(--dash-panel);
          border: 1px solid var(--dash-border);
          border-radius: 10px;
          padding: 0.9rem 1.1rem;
          box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }}
        div[data-testid="stMetric"] label {{
          color: var(--dash-muted) !important;
          font-size: 0.8rem;
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }}
        div[data-testid="stMetricValue"] {{
          font-family: 'JetBrains Mono', 'Cascadia Mono', monospace;
          color: var(--dash-text) !important;
          font-size: 1.8rem !important;
          font-weight: 700 !important;
        }}
        div[data-testid="stMetricDelta"] {{
          font-size: 0.85rem !important;
        }}

        /* Buttons & Dynamic Controls */
        .stButton > button, .stDownloadButton > button {{
          border-radius: 8px;
          border: 1px solid var(--dash-border);
          background: var(--dash-panel-2);
          color: var(--dash-text);
          font-weight: 600;
          font-size: 0.9rem;
          padding: 0.5rem 1.2rem;
          transition: all 0.2s ease-in-out;
        }}
        .stButton > button:hover, .stDownloadButton > button:hover {{
          border-color: var(--dash-primary);
          background: var(--dash-primary);
          color: #ffffff !important;
          box-shadow: 0 0 12px rgba(59, 130, 246, 0.4);
        }}
        
        /* Make Primary buttons stand out by default */
        .stButton > button[kind="primary"] {{
          background: var(--dash-primary);
          border-color: var(--dash-primary);
          color: #ffffff;
        }}
        .stButton > button[kind="primary"]:hover {{
          background: var(--dash-primary-hover);
          border-color: var(--dash-primary-hover);
          box-shadow: 0 0 15px rgba(59, 130, 246, 0.5);
        }}

        /* Tabs styling */
        div[data-baseweb="tab-list"] {{
          gap: 8px;
          border-bottom: 1px solid var(--dash-border);
        }}
        button[data-baseweb="tab"] {{
          background: transparent !important;
          color: var(--dash-muted) !important;
          border-radius: 6px 6px 0 0 !important;
          padding: 10px 18px !important;
          font-weight: 500 !important;
          border: 1px solid transparent !important;
          border-bottom: none !important;
          margin-bottom: -1px !important;
        }}
        button[data-baseweb="tab"][aria-selected="true"] {{
          color: var(--dash-text) !important;
          border-color: var(--dash-border) !important;
          background: var(--dash-panel) !important;
          font-weight: 600 !important;
        }}

        /* Code and table outputs */
        code {{
          font-family: 'JetBrains Mono', monospace;
          background: var(--dash-panel-2);
          border-radius: 4px;
          padding: 0.15rem 0.35rem;
          font-size: 0.85em;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    components.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;

            function keepSidebarOpen() {
                // Find the expand/open button that only exists when sidebar is collapsed
                const expandBtn = doc.querySelector(
                    '[data-testid="stSidebarCollapsedControl"] button'
                ) || doc.querySelector(
                    'button[aria-label="Expand sidebar"]'
                ) || doc.querySelector(
                    'button[aria-label="Open sidebar"]'
                );

                // If an expand button exists and is visible, the sidebar is collapsed — click it
                if (expandBtn && expandBtn.offsetParent !== null) {
                    expandBtn.click();
                }
            }

            // Run immediately + keep checking every 500ms forever
            keepSidebarOpen();
            setInterval(keepSidebarOpen, 500);
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def kpi_card(label: str, value: str, note: str = "") -> None:
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value">{value}</div>
          <div class="kpi-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge(success: bool, text: str | None = None) -> None:
    cls = "status-ok" if success else "status-bad"
    label = text or ("Mission Success" if success else "Constraint Violation")
    st.markdown(f'<span class="status-badge {cls}">{label}</span>', unsafe_allow_html=True)
