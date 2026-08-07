"""Plotly chart builders for the aerospace engineering dashboard.

Includes synchronized multi-plot timelines, Sankey power flow diagrams,
Pareto explorer tools, and sensitivity radar (spider) charts.
"""

from __future__ import annotations

from typing import Any, Dict, List
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from components.theme import palette, plotly_template
from models import ModelAssumptions


def _segment_ranges(df: pd.DataFrame) -> List[tuple[str, float, float]]:
    if df.empty or "segment" not in df:
        return []
    changes = df["segment"].ne(df["segment"].shift()).cumsum()
    ranges = []
    for _, group in df.groupby(changes):
        ranges.append((
            str(group["segment"].iloc[0]),
            float(group["time_h"].iloc[0]),
            float(group["time_h"].iloc[-1])
        ))
    return ranges


def mission_timeline_figure(df: pd.DataFrame, soc_floor: float = 0.20) -> go.Figure:
    """Build a shared-x mission timeline with 5 synchronized subplots.

    Subplots:
    1. Power demand (kW)
    2. Source power split (kW) (Stacked area: Generator + Battery Discharge / Charge)
    3. Battery SoC (%)
    4. Fuel remaining (kg)
    5. Flight weight (kg)
    """
    p = palette()
    fig = make_subplots(
        rows=5,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        subplot_titles=(
            "Power Demand & Turbine Shaft",
            "Generator / Battery Source Split",
            "Battery State of Charge",
            "Fuel Remaining",
            "Aircraft Weight Profile",
        ),
        row_heights=[0.20, 0.23, 0.19, 0.19, 0.19],
    )
    if df.empty:
        return fig

    x = df["time_h"]

    # 1. Power Demand
    fig.add_trace(
        go.Scatter(
            x=x,
            y=df["demand_kw"],
            mode="lines",
            name="Propeller Shaft Demand",
            line={"width": 2.2, "color": p["primary"]}
        ),
        row=1, col=1
    )
    # Estimate turbine shaft power
    if "generator_kw" in df and "generator_eta" in df:
        # Avoid divide by zero
        turbine_kw = df["generator_kw"] / df["generator_eta"].replace(0.0, 1.0)
        fig.add_trace(
            go.Scatter(
                x=x,
                y=turbine_kw,
                mode="lines",
                name="Turbine Shaft Power",
                line={"width": 1.5, "color": p["amber"], "dash": "dash"}
            ),
            row=1, col=1
        )

    # 2. Source Split (Generator, Battery Discharge, Battery Charge)
    fig.add_trace(
        go.Scatter(
            x=x,
            y=df["generator_kw"],
            mode="lines",
            stackgroup="sources",
            name="Generator output",
            line={"color": p["primary"], "width": 1.0},
            fillcolor=p["primary"]
        ),
        row=2, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=df["battery_discharge_kw"],
            mode="lines",
            stackgroup="sources",
            name="Battery discharge",
            line={"color": p["amber"], "width": 1.0},
            fillcolor=p["amber"]
        ),
        row=2, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=-df["battery_charge_kw"],
            mode="lines",
            name="Battery charge",
            line={"color": p["green"], "width": 1.8}
        ),
        row=2, col=1
    )

    # 3. Battery SoC
    soc_color = p["red"] if float(df["soc"].min()) < soc_floor else p["green"]
    fig.add_trace(
        go.Scatter(
            x=x,
            y=df["soc"],
            mode="lines",
            name="Battery SoC",
            line={"width": 2.2, "color": soc_color}
        ),
        row=3, col=1
    )
    fig.add_hline(
        y=soc_floor,
        line_dash="dash",
        line_color=p["red"],
        annotation_text="20% Floor",
        row=3, col=1
    )

    # SoC Breach Highlight
    breached = df[df["soc"] < soc_floor]
    if not breached.empty:
        fig.add_trace(
            go.Scatter(
                x=breached["time_h"],
                y=breached["soc"],
                fill="tozeroy",
                mode="none",
                name="SoC breach area",
                fillcolor="rgba(239,68,68,0.25)",
                showlegend=False
            ),
            row=3, col=1
        )

    # 4. Fuel Remaining
    fig.add_trace(
        go.Scatter(
            x=x,
            y=df["fuel_remaining_kg"],
            mode="lines",
            name="Fuel Weight",
            line={"width": 2.2, "color": "#a855f7"}
        ),
        row=4, col=1
    )

    # 5. Aircraft Weight Profile
    if "weight_kg" in df:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=df["weight_kg"],
                mode="lines",
                name="Aircraft Weight",
                line={"width": 2.2, "color": "#06b6d4"}
            ),
            row=5, col=1
        )

    # Shade segments and add labels at top
    ymax = float(df["demand_kw"].max()) * 1.15
    for label, x0, x1 in _segment_ranges(df):
        shade = "rgba(59,130,246,0.06)" if label != "Loiter" else "rgba(245,158,11,0.08)"
        fig.add_vrect(x0=x0, x1=x1, fillcolor=shade, opacity=1.0, line_width=0, layer="below", row="all", col=1)
        fig.add_annotation(
            x=(x0 + x1) / 2,
            y=ymax,
            text=label,
            showarrow=False,
            row=1, col=1,
            font={"size": 10, "color": p["muted"], "weight": "bold"}
        )

    fig.update_layout(
        template=plotly_template(),
        height=1000,
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        margin={"l": 65, "r": 25, "t": 70, "b": 55},
    )

    # Synchronize zoom / x axes
    fig.update_xaxes(matches='x')
    
    # Configure axes labels
    fig.update_yaxes(title_text="Power (kW)", row=1, col=1)
    fig.update_yaxes(title_text="Power (kW)", row=2, col=1)
    fig.update_yaxes(title_text="SoC (%)", range=[0, 1.05], tickformat=".0%", row=3, col=1)
    fig.update_yaxes(title_text="Fuel (kg)", row=4, col=1)
    if "weight_kg" in df:
        fig.update_yaxes(title_text="Weight (kg)", row=5, col=1)
    
    fig.update_xaxes(title_text="Mission Time (h)", row=5, col=1)
    return fig


def sankey_power_flow(row: pd.Series, assumptions: ModelAssumptions) -> go.Figure:
    """Build a Sankey Diagram showing instantaneous power flow.

    Nodes:
    0: Fuel Tank (Chemical Energy)
    1: Gas Turbine Engine (Mechanical Energy)
    2: Generator (Electrical output)
    3: Battery (Stored electrochemical energy)
    4: DC Bus (Electrical Distribution)
    5: Inverter & Motor (Electro-mechanical conversion)
    6: Propeller / Thrust (Aerodynamic Load)
    7: Losses (Dissipated heat)
    """
    p = palette()
    
    # Capture values from telemetry
    demand_kw = float(row.get("demand_kw", 0.0))
    gen_kw = float(row.get("generator_kw", 0.0))
    battery_kw = float(row.get("battery_kw", 0.0))  # positive = discharging, negative = charging
    fuel_flow_kg_h = float(row.get("fuel_flow_kg_h", 0.0))
    
    # Efficiencies
    motor_eta = float(row.get("motor_eta", assumptions.motor_inv_eta_peak))
    gen_eta = float(row.get("generator_eta", assumptions.generator_eta_peak))
    
    # 1. Fuel chemical power input
    fuel_power = fuel_flow_kg_h * assumptions.fuel_lhv_kwh_per_kg  # kg/h * kWh/kg = kW
    
    # 2. Turbine shaft output
    turbine_shaft = gen_kw / max(gen_eta, 1e-6) if gen_kw > 0 else 0.0
    turbine_loss = max(0.0, fuel_power - turbine_shaft)
    
    # 3. Generator electrical output
    generator_loss = max(0.0, turbine_shaft - gen_kw)
    
    # 4. DC Bus wiring loss
    eta_bus = 1.0 - assumptions.bus_loss_frac
    bus_loss = 0.0
    
    # Setup source and target arrays
    sources = []
    targets = []
    values = []
    labels = [
        "Fuel Input",          # 0
        "Gas Turbine",         # 1
        "Generator",           # 2
        "Battery Storage",     # 3
        "DC Bus",              # 4
        "Motor & Inverter",    # 5
        "Propeller / Thrust",  # 6
        "System Losses"        # 7
    ]
    
    # Connect Fuel -> Turbine
    if fuel_power > 1e-3:
        sources.append(0)
        targets.append(1)
        values.append(fuel_power)
        
        # Turbine loss
        sources.append(1)
        targets.append(7)
        values.append(turbine_loss)
        
    # Connect Turbine -> Generator
    if turbine_shaft > 1e-3:
        sources.append(1)
        targets.append(2)
        values.append(turbine_shaft)
        
        # Generator loss
        sources.append(2)
        targets.append(7)
        values.append(generator_loss)
        
    # Connect Generator -> DC Bus
    if gen_kw > 1e-3:
        sources.append(2)
        targets.append(4)
        values.append(gen_kw)
        
    # Connect Battery to Bus or Bus to Battery
    # Let's see: battery terminal power
    # If battery_kw > 0 (Discharging): Battery -> DC Bus
    # If battery_kw < 0 (Charging): DC Bus -> Battery
    if battery_kw > 1e-3:
        sources.append(3)
        targets.append(4)
        values.append(battery_kw)
    elif battery_kw < -1e-3:
        sources.append(4)
        targets.append(3)
        values.append(-battery_kw)

    # Bus losses
    load_dc = demand_kw / max(motor_eta, 1e-6)
    bus_loss = max(0.0, (gen_kw + max(battery_kw, 0.0) - max(-battery_kw, 0.0)) - load_dc)
    if bus_loss > 1e-3:
        sources.append(4)
        targets.append(7)
        values.append(bus_loss)
        
    # Connect DC Bus -> Motor
    if load_dc > 1e-3:
        sources.append(4)
        targets.append(5)
        values.append(load_dc)
        
    # Motor losses
    motor_loss = max(0.0, load_dc - demand_kw)
    if motor_loss > 1e-3:
        sources.append(5)
        targets.append(7)
        values.append(motor_loss)
        
    # Motor -> Propeller
    if demand_kw > 1e-3:
        sources.append(5)
        targets.append(6)
        values.append(demand_kw)

    # Color nodes
    node_colors = [
        "#a855f7",  # Fuel (Purple)
        "#f59e0b",  # Turbine (Amber)
        p["primary"],  # Generator (Blue)
        p["green"],  # Battery (Green)
        "#06b6d4",  # DC Bus (Cyan)
        "#6366f1",  # Motor (Indigo)
        "#10b981",  # Propeller (Emerald)
        p["red"]    # Losses (Red)
    ]

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color=p["border"], width=0.5),
            label=labels,
            color=node_colors
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color="rgba(142, 163, 194, 0.25)"  # light muted link color
        )
    )])
    
    fig.update_layout(
        template=plotly_template(),
        title_text="Power Flow Distribution (kW)",
        font_size=12,
        height=400,
        margin={"l": 20, "r": 20, "t": 45, "b": 20}
    )
    return fig


def pareto_parallel_figure(df: pd.DataFrame) -> go.Figure:
    p = palette()
    dims = []
    for col, label in [
        ("endurance_h", "Endurance (h)"),
        ("fuel_burned_kg", "Fuel Burned (kg)"),
        ("degradation_proxy", "Degradation"),
        ("efficiency", "Avg Efficiency"),
        ("total_mass_kg", "Mass (kg)"),
    ]:
        if col in df:
            dims.append({"label": label, "values": df[col]})
            
    color_col = "endurance_h" if "endurance_h" in df else df.select_dtypes("number").columns[0]
    fig = go.Figure(
        data=[
            go.Parcoords(
                line={"color": df[color_col], "colorscale": "Blues", "showscale": True, "colorbar": {"title": "Endurance (h)"}},
                dimensions=dims,
            )
        ]
    )
    fig.update_layout(
        template=plotly_template(),
        height=520,
        margin={"l": 60, "r": 60, "t": 40, "b": 40},
        paper_bgcolor=p["bg"]
    )
    return fig


def pareto_scatter_matrix(df: pd.DataFrame, color_by: str) -> go.Figure:
    cols = [c for c in ["endurance_h", "fuel_burned_kg", "degradation_proxy", "efficiency", "total_mass_kg"] if c in df]
    fig = px.scatter_matrix(
        df,
        dimensions=cols,
        color=color_by if color_by in df else None,
        template=plotly_template(),
        labels={
            "endurance_h": "Endurance (h)",
            "fuel_burned_kg": "Fuel (kg)",
            "degradation_proxy": "Degr.",
            "efficiency": "Eff.",
            "total_mass_kg": "Mass (kg)"
        }
    )
    fig.update_layout(height=720, margin={"l": 40, "r": 40, "t": 45, "b": 45})
    fig.update_traces(diagonal_visible=False, marker={"size": 5, "opacity": 0.75})
    return fig


def sensitivity_tornado(df: pd.DataFrame, objective_shift_col: str) -> go.Figure:
    p = palette()
    plot_df = df.copy()
    if objective_shift_col not in plot_df:
        return go.Figure()

    # Ensure numeric values and drop invalid rows
    plot_df[objective_shift_col] = pd.to_numeric(plot_df[objective_shift_col], errors="coerce").fillna(0.0)
    plot_df["case_label"] = plot_df["parameter"].astype(str) + " " + plot_df["delta_pct"].map(lambda x: f"{x:+.0f}%")
    plot_df = plot_df.sort_values(objective_shift_col)

    # Build visible RGBA colors with border for dark themes
    def _rgba(hexcol: str, alpha: float = 0.9) -> str:
        hexcol = hexcol.lstrip("#")
        r, g, b = int(hexcol[0:2], 16), int(hexcol[2:4], 16), int(hexcol[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    colors = [(_rgba(p["red"]) if v < 0 else _rgba(p["primary"])) for v in plot_df[objective_shift_col]]
    line_colors = [p["border"] for _ in plot_df.index]

    fig = go.Figure(go.Bar(
        x=plot_df[objective_shift_col],
        y=plot_df["case_label"],
        orientation="h",
        marker={"color": colors, "line": {"color": line_colors, "width": 0.8}},
    ))

    # If all shifts are near zero, add a message to the plot to avoid empty visual
    if plot_df[objective_shift_col].abs().max() < 1e-6:
        fig.add_annotation(text="No measurable sensitivity (all shifts ≈ 0%)", x=0, y=0.5, showarrow=False, xref="paper", yref="paper", font={"color": p["muted"]})

    fig.add_vline(x=0, line_color=p["border"], line_width=1)
    fig.update_layout(
        template=plotly_template(),
        height=max(320, 38 * len(plot_df)),
        xaxis_title="% Shift Relative to Baseline",
        yaxis_title="Input Parameter Perturbation",
        margin={"l": 170, "r": 30, "t": 30, "b": 55},
    )
    return fig


def sensitivity_spider_chart(df: pd.DataFrame, selected_parameter: str) -> go.Figure:
    """Build a radar/spider chart showing how parameter shifts impact all objectives.

    X-axis/polar angles are objectives: Endurance, Fuel Burned, Degradation, Efficiency, Mass.
    Radial distance is the % shift.
    """
    p = palette()
    plot_df = df[df["parameter"] == selected_parameter]
    if plot_df.empty:
        return go.Figure()
        
    objectives = ["endurance_h", "fuel_burned_kg", "degradation_proxy", "efficiency", "total_mass_kg"]
    labels = ["Endurance", "Fuel Burned", "Battery Degradation", "Average Efficiency", "Total Mass"]
    
    fig = go.Figure()
    
    # We want to trace a loop so we repeat the first element at the end of each radar trace
    radar_labels = labels + [labels[0]]
    
    for _, row in plot_df.iterrows():
        delta = row["delta_pct"]
        # extract shifts
        shifts = []
        for obj in objectives:
            shifts.append(float(row[f"{obj}_shift_pct"]))
        shifts.append(shifts[0])  # close the loop
        
        trace_color = p["primary"] if delta > 0 else p["amber"]
        fig.add_trace(go.Scatterpolar(
            r=shifts,
            theta=radar_labels,
            fill='toself',
            name=f"Perturbation: {delta:+.0f}%",
            line=dict(color=trace_color, width=2),
            fillcolor=f"rgba({10 if delta > 0 else 245}, {130 if delta > 0 else 158}, {246 if delta > 0 else 11}, 0.15)"
        ))
        
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                ticksuffix="%",
                gridcolor=p["border"],
                angle=90
            ),
            angularaxis=dict(
                gridcolor=p["border"]
            ),
            bgcolor=p["panel"]
        ),
        template=plotly_template(),
        showlegend=True,
        title=f"Sensitivity Profile for {selected_parameter.replace('_', ' ').title()}",
        height=480,
        margin={"l": 60, "r": 60, "t": 60, "b": 40}
    )
    return fig
