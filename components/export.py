"""Export utilities for generating professional PDF design summaries and CSV sheets."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Dict
import pandas as pd

from models import ModelAssumptions


def build_design_summary_pdf(
    config: Dict[str, Any],
    summary: Dict[str, Any] | None,
    pareto_row: pd.Series | None = None,
    assumptions: ModelAssumptions | None = None
) -> bytes:
    """Generate a highly polished, two-page engineering report PDF.

    Contains configuration metrics, mission summary, diagnostics, and
    underlying study assumptions.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise ImportError(
            "reportlab is required for PDF export. Install it with `pip install reportlab`."
        ) from exc

    assumptions = assumptions or ModelAssumptions()
    buffer = BytesIO()
    
    # 0.5 inch margins (36 points)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=15
    )
    
    h2_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#1e3a8a"),
        spaceBefore=10,
        spaceAfter=6,
        keepWithNext=True
    )
    
    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=10,
        textColor=colors.HexColor("#1e293b")
    )
    
    cell_bold_style = ParagraphStyle(
        "TableCellBold",
        parent=cell_style,
        fontName="Helvetica-Bold"
    )
    
    cell_mono_style = ParagraphStyle(
        "TableCellMono",
        parent=cell_style,
        fontName="Courier",
        fontSize=8.5,
        leading=10
    )

    story = []
    
    # Header block
    story.append(Paragraph("HAL × IIT Indore Aerothon", ParagraphStyle("HeaderOrg", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#2563eb"))))
    story.append(Paragraph("Hybrid-Electric UAV Propulsion Sizing Study", title_style))
    story.append(Paragraph("System Sizing Report & Performance Verification Summary", subtitle_style))
    story.append(Spacer(1, 8))
    
    # Section 1: Propulsion Design Configuration
    story.append(Paragraph("1. Propulsion Chain Hardware Sizing", h2_style))
    
    cfg_headers = ["Design Variable", "Engineering Value", "Description / Bounds"]
    cfg_data = [
        [Paragraph(h, cell_bold_style) for h in cfg_headers],
        [
            Paragraph("Turbine Rating", cell_style),
            Paragraph(f"{config.get('turbine_rating_kw', 0.0):.1f} kW", cell_mono_style),
            Paragraph("Auxiliary gas turbine shaft power output [30 - 120 kW]", cell_style),
        ],
        [
            Paragraph("Generator Rating", cell_style),
            Paragraph(f"{config.get('generator_rating_kw', 0.0):.1f} kW", cell_mono_style),
            Paragraph("Permanent magnet generator shaft power rating [30 - 130 kW]", cell_style),
        ],
        [
            Paragraph("Battery Capacity", cell_style),
            Paragraph(f"{config.get('battery_capacity_kwh', 0.0):.1f} kWh", cell_mono_style),
            Paragraph("Battery pack total energy storage capacity [1 - 120 kWh]", cell_style),
        ],
        [
            Paragraph("Battery Peak Power", cell_style),
            Paragraph(f"{config.get('battery_peak_power_kw', 0.0):.1f} kW", cell_mono_style),
            Paragraph("Battery peak power delivery capability [10 - 180 kW]", cell_style),
        ],
        [
            Paragraph("Fuel Mass Load", cell_style),
            Paragraph(f"{config.get('fuel_mass_kg', 0.0):.1f} kg", cell_mono_style),
            Paragraph("Liquid fuel capacity for range extension [1 - 250 kg]", cell_style),
        ],
        [
            Paragraph("EMS Strategy", cell_style),
            Paragraph(str(config.get('ems_label', 'Rule-Based')), cell_bold_style),
            Paragraph("Tier 1 (Rule-Based), Tier 2 (ECMS), or Tier 3 (Offline-Optimal)", cell_style),
        ]
    ]
    
    # Check if there are EMS specific values to report
    if config.get("ems_label") == "Rule-Based" or config.get("ems_label") == "Offline-Optimal":
        cfg_data.append([
            Paragraph("Generator Setpoint", cell_style),
            Paragraph(f"{config.get('generator_setpoint_kw', 58.0):.1f} kW", cell_mono_style),
            Paragraph("Fixed charging / baseline generator operating point", cell_style),
        ])
    elif config.get("ems_label") == "ECMS":
        cfg_data.append([
            Paragraph("ECMS Equiv. Factor", cell_style),
            Paragraph(f"{config.get('ecms_equivalence_factor', 0.22):.3f} kg/kWh", cell_mono_style),
            Paragraph("Penalization cost mapping battery charge vs fuel", cell_style),
        ])
        
    cfg_data.append([
        Paragraph("SoC Control Band", cell_style),
        Paragraph(f"{config.get('target_soc_low', 0.35):.2f} - {config.get('target_soc_high', 0.90):.2f}", cell_mono_style),
        Paragraph("Target charge-depleting/sustaining boundary bands", cell_style),
    ])
    
    # 3 columns layout: 130 points, 100 points, 310 points (total 540 = letter width 612 - 72 margins)
    cfg_table = Table(cfg_data, colWidths=[130, 100, 310])
    cfg_table.setStyle(_table_style(colors))
    story.append(cfg_table)
    story.append(Spacer(1, 15))
    
    # Section 2: Mission Telemetry & Performance
    story.append(Paragraph("2. Mission Evaluation & Sizing Objectives", h2_style))
    
    if summary:
        success_text = "PASSED" if summary.get("success") else "FAILED"
        success_color = "#16a34a" if summary.get("success") else "#dc2626"
        violation = summary.get("first_violation") or "No constraint violations detected."
        
        perf_headers = ["Key Sizing Metric", "Simulation Value", "Status / Constraint Diagnostic"]
        perf_data = [
            [Paragraph(h, cell_bold_style) for h in perf_headers],
            [
                Paragraph("Mission Flight Success", cell_style),
                Paragraph(success_text, ParagraphStyle("Succ", parent=cell_bold_style, textColor=colors.HexColor(success_color))),
                Paragraph(violation, cell_style),
            ],
            [
                Paragraph("Mission Endurance", cell_style),
                Paragraph(f"{summary.get('endurance_h', 0.0):.2f} hours", cell_mono_style),
                Paragraph("Total continuous flight time until reserves bound", cell_style),
            ],
            [
                Paragraph("Fuel Consumed", cell_style),
                Paragraph(f"{summary.get('fuel_burned_kg', 0.0):.2f} kg", cell_mono_style),
                Paragraph(f"Reserve limit: {10.0} kg reserve threshold", cell_style),
            ],
            [
                Paragraph("Final Battery SoC", cell_style),
                Paragraph(f"{100 * summary.get('final_soc', 0.0):.1f}%", cell_mono_style),
                Paragraph("Battery state of charge at mission termination (floor 20%)", cell_style),
            ],
            [
                Paragraph("Average Power Efficiency", cell_style),
                Paragraph(f"{100 * summary.get('mission_avg_efficiency', 0.0):.1f}%", cell_mono_style),
                Paragraph("Integrated energy conversion efficiency across chain", cell_style),
            ],
            [
                Paragraph("Degradation Proxy Index", cell_style),
                Paragraph(f"{summary.get('degradation_proxy', 0.0):.5f}", cell_mono_style),
                Paragraph("Surrogate aging score (cycles, depth of discharge, C-rate)", cell_style),
            ],
            [
                Paragraph("Estimated Aircraft Mass", cell_style),
                Paragraph(f"{summary.get('total_mass_kg', 0.0):.1f} kg", cell_mono_style),
                Paragraph("Maximum Aircraft Sized Takeoff Weight (MTOW limit 1000 kg)", cell_style),
            ]
        ]
        
        perf_table = Table(perf_data, colWidths=[130, 100, 310])
        perf_table.setStyle(_table_style(colors))
        story.append(perf_table)
    else:
        story.append(Paragraph("No simulation history available in current workspace session. Please run simulation in dashboard.", cell_style))
        
    story.append(Spacer(1, 15))
    
    # Section 3: Engineering Modeling Assumptions
    story.append(Paragraph("3. Reference Modeling Assumptions (Section 5.2 Parameters)", h2_style))
    
    asm_headers = ["Subsystem Parameter", "Reference Assumption", "Description / Model Curve Spec"]
    asm_data = [
        [Paragraph(h, cell_bold_style) for h in asm_headers],
        [
            Paragraph("Turbine Reference SFC", cell_style),
            Paragraph(f"{assumptions.sfc_ref_kg_per_kwh:.3f} kg/kWh", cell_mono_style),
            Paragraph("Turbine SFC at rated shaft power (adjusted by k1 part-load)", cell_style),
        ],
        [
            Paragraph("Generator Peak Efficiency", cell_style),
            Paragraph(f"{100 * assumptions.generator_eta_peak:.1f}%", cell_mono_style),
            Paragraph("Peak shaft-to-electric conversion efficiency of generator", cell_style),
        ],
        [
            Paragraph("Motor+Inverter Peak Efficiency", cell_style),
            Paragraph(f"{100 * assumptions.motor_inv_eta_peak:.1f}%", cell_mono_style),
            Paragraph("Combined efficiency of traction PMSM and SiC inverter", cell_style),
        ],
        [
            Paragraph("Battery Specific Energy", cell_style),
            Paragraph(f"{assumptions.battery_specific_energy_wh_per_kg:.1f} Wh/kg", cell_mono_style),
            Paragraph("Specific energy density of cells for pack weight scaling", cell_style),
        ],
        [
            Paragraph("Battery Round-trip Efficiency", cell_style),
            Paragraph(f"{100 * assumptions.battery_roundtrip_eta:.1f}%", cell_mono_style),
            Paragraph("Symmetric round-trip charge/discharge efficiency (square root)", cell_style),
        ],
        [
            Paragraph("DC Bus Loss Fraction", cell_style),
            Paragraph(f"{100 * assumptions.bus_loss_frac:.1f}%", cell_mono_style),
            Paragraph("Integrated losses in DC distribution wiring and terminal connectors", cell_style),
        ]
    ]
    
    asm_table = Table(asm_data, colWidths=[150, 110, 280])
    asm_table.setStyle(_table_style(colors))
    story.append(asm_table)
    
    doc.build(story)
    return buffer.getvalue()


def _table_style(colors_module) -> TableStyle:
    try:
        from reportlab.platypus import TableStyle
    except Exception as exc:  # pragma: no cover - defensive
        raise ImportError(
            "reportlab is required for PDF export. Install it with `pip install reportlab`."
        ) from exc

    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors_module.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors_module.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors_module.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors_module.white, colors_module.HexColor("#f8fafc")]),
        ]
    )
