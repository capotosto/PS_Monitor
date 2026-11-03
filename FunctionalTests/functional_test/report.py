from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .analysis import (
    latest_attempt_by_rail, latest_rail_observations, mean_field, merged_test_step_results,
    overall_system_test_status, run_records, system_test_matrix_statuses,
)
from .config import (
    CURRENT_PERCENT_TOL, LTC2945_SENSE_FULL_SCALE_V, LTC2945_TUE_FS, RAILS,
    RAIL_ORDER, SHUNT_TOLERANCE, SYSTEM_TESTS,
)
from .plots import build_rail_current_error_plot, build_rail_current_plot, build_rail_voltage_plot
from .storage import latest_checklist_by_test, load_checklist_csv, load_csv
from .utils import (
    as_bool, compact_instrument_id, ltc2945_voltage_datasheet_error_v, now_timestamp,
    timestamped_report_path,
)

STATUS_FILL_RL = {
    "PASS": colors.HexColor("#D9EAD3"),
    "FAIL": colors.HexColor("#F4CCCC"),
    "INCOMPLETE": colors.HexColor("#FFF2CC"),
}

def status_category(value: object) -> Optional[str]:
    """Normalize report/result text to PASS, FAIL, or INCOMPLETE for highlighting."""
    text = str(value or "").strip().upper()
    if not text:
        return None
    if text.startswith("PASS") or text in {"YES", "RECORDED"}:
        return "PASS"
    if text.startswith("FAIL") or text == "NO":
        return "FAIL"
    if text in {
        "INCOMPLETE", "NOT TESTED", "NOT RECORDED", "PENDING", "ABORTED",
        "RETEST", "NO CHECKLIST DATA",
    }:
        return "INCOMPLETE"
    return None

def status_background_commands(
    table_data: Sequence[Sequence[object]],
    column_indices: Sequence[int],
    start_row: int = 1,
) -> List[Tuple[str, Tuple[int, int], Tuple[int, int], object]]:
    """Return ReportLab BACKGROUND commands for status/result cells."""
    commands = []
    for row_index in range(start_row, len(table_data)):
        row = table_data[row_index]
        for column_index in column_indices:
            if column_index < 0 or column_index >= len(row):
                continue
            category = status_category(row[column_index])
            if category:
                commands.append((
                    "BACKGROUND",
                    (column_index, row_index),
                    (column_index, row_index),
                    STATUS_FILL_RL[category],
                ))
    return commands

def generate_report(
    data_path: Path,
    checklist_path: Path,
    pdf_path: Path,
    dut_filter: Optional[str] = None,
) -> Path:
    rows = load_csv(data_path) if data_path.exists() else []

    if dut_filter:
        rows = [
            row
            for row in rows
            if row.get("dut_id", "") == dut_filter
        ]

    checklist_rows = load_checklist_csv(checklist_path)
    if dut_filter:
        checklist_rows = [
            row
            for row in checklist_rows
            if row.get("dut_id", "") == dut_filter
        ]

    if not rows and not checklist_rows:
        raise RuntimeError(
            "No matching rail measurement data or system-test checklist records were found."
        )

    runs = run_records(rows)
    latest = latest_attempt_by_rail(
        runs,
        dut_filter,
    )

    latest_run_ids = {
        run_id
        for run_id, _ in latest.values()
    }

    report_rows = [
        row
        for row in rows
        if row.get("run_id", "") in latest_run_ids
    ]

    latest_checklist = latest_checklist_by_test(checklist_rows, dut_filter)
    latest_checklist_run_ids = {
        run_id for run_id, _ in latest_checklist.values()
    }
    report_checklist_rows = [
        row for row in checklist_rows
        if row.get("test_run_id", "") in latest_checklist_run_ids
    ]

    status_matrix = system_test_matrix_statuses(rows, checklist_rows, dut_filter)
    overall = overall_system_test_status(status_matrix)

    if not latest:
        rail_overall = "INCOMPLETE"
    elif any(key not in latest for key in RAIL_ORDER):
        rail_overall = "INCOMPLETE"
    else:
        latest_runs = [latest[key][1] for key in RAIL_ORDER]
        if any(run.get("status") != "COMPLETE" for run in latest_runs):
            rail_overall = "INCOMPLETE"
        elif all(bool(run.get("run_pass")) for run in latest_runs):
            rail_overall = "PASS"
        else:
            rail_overall = "FAIL"

    combined_rows = report_rows + report_checklist_rows

    dut_ids = sorted({
        row.get("dut_id", "")
        for row in combined_rows
        if row.get("dut_id", "")
    })

    operators = sorted({
        row.get("operator", "")
        for row in combined_rows
        if row.get("operator", "")
    })

    timestamps = sorted(
        row.get("timestamp", "")
        for row in combined_rows
        if row.get("timestamp", "")
    )

    rigol_ids = sorted({
        compact_instrument_id(row.get("rigol_idn", ""))
        for row in report_rows
        if row.get("rigol_idn", "")
    })

    prefixes = sorted({
        row.get("ioc_prefix", "")
        for row in report_rows
        if row.get("ioc_prefix", "")
    })

    output_pdf_path = timestamped_report_path(
        pdf_path
    )

    output_pdf_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    doc = SimpleDocTemplate(
        str(output_pdf_path),
        pagesize=letter,
        rightMargin=0.45 * inch,
        leftMargin=0.45 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
        title="Multi-Rail Power Supply Monitor Verification Report",
        author="Automated capstone rail test",
    )

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="CenterTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=18,
            leading=22,
        )
    )

    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["BodyText"],
            fontSize=7.5,
            leading=9,
        )
    )

    styles.add(
        ParagraphStyle(
            name="Tiny",
            parent=styles["BodyText"],
            fontSize=6.5,
            leading=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TableCell",
            parent=styles["BodyText"],
            fontSize=6.8,
            leading=8.0,
            spaceAfter=0,
            spaceBefore=0,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TableCellCenter",
            parent=styles["TableCell"],
            alignment=TA_CENTER,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TableHeader",
            parent=styles["TableCellCenter"],
            fontName="Helvetica-Bold",
        )
    )

    # Portrait letter with 0.45 in margins provides a 7.60 in text frame.
    # Keep objects slightly inside that width so borders and antialiasing
    # never touch the frame boundary.
    plot_width = min(doc.width, 7.25 * inch)

    def report_cell(value: object, style_name: str = "TableCell") -> Paragraph:
        """Wrap table text so portrait-oriented report cells cannot overflow."""
        return Paragraph(escape(str(value or "")), styles[style_name])

    story = []
    plot_buffers: List[BytesIO] = []

    story.append(
        Paragraph(
            "Multi-Rail Isolated Power Supply Monitor<br/>"
            "System Test Report",
            styles["CenterTitle"],
        )
    )

    story.append(
        Spacer(
            1,
            0.12 * inch,
        )
    )

    meta_data = [
        [
            report_cell("Overall system status", "TableHeader"),
            overall,
            report_cell("Checklist file", "TableHeader"),
            report_cell(checklist_path.name),
        ],
        [
            report_cell("Rail measurement status", "TableHeader"),
            rail_overall,
            report_cell("Raw measurement data", "TableHeader"),
            report_cell(data_path.name),
        ],
        [
            report_cell("DUT", "TableHeader"),
            report_cell(", ".join(dut_ids) or "Not specified"),
            report_cell("Operator(s)", "TableHeader"),
            report_cell(", ".join(operators) or "Not specified"),
        ],
        [
            report_cell("Latest-attempt date range", "TableHeader"),
            report_cell(
                f"{timestamps[0] if timestamps else ''} to "
                f"{timestamps[-1] if timestamps else ''}"
            ),
            report_cell("IOC prefix", "TableHeader"),
            report_cell(", ".join(prefixes) or "Not recorded"),
        ],
        [
            report_cell("Electronic load", "TableHeader"),
            report_cell(", ".join(rigol_ids) or "Not recorded"),
            report_cell("Report generated", "TableHeader"),
            report_cell(now_timestamp()),
        ],
    ]

    mt = Table(
        meta_data,
        colWidths=[1.20 * inch, 2.55 * inch, 1.20 * inch, 2.55 * inch],
        hAlign="LEFT",
    )

    mt.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ("BACKGROUND", (2, 0), (2, -1), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ] + status_background_commands(meta_data, [1], start_row=0))
    )

    story.append(mt)
    story.append(Spacer(1, 0.16 * inch))

    story.append(
        Paragraph(
            "Acceptance criteria used",
            styles["Heading2"],
        )
    )

    criteria_bullets = [
        "<b>Voltage accuracy:</b> IOC voltage must agree with the external reference "
        "within &plusmn;2% across the tested operating range.",

        "<b>Current accuracy:</b> IOC current must agree with the external reference "
        "within &plusmn;5%. At low current, the larger of the percentage tolerance or "
        "an absolute floor is used: 25 mA for 39 mOhm channels and 20 mA for 50 mOhm channels.",

        "<b>Polarity:</b> Positive and negative rail voltages must have the correct sign. "
        "Current follows the firmware convention for all rails.",

        "<b>Display / EPICS agreement:</b> Local-display and EPICS values must represent "
        "the same underlying measurement within displayed resolution or rounding.",

        "<b>Limits and persistence:</b> Programmed limits must assert and clear correctly, "
        "and persistent settings must survive a power cycle.",

        "<b>Network recovery:</b> EPICS communication must resume normally after Ethernet "
        "communication is interrupted and restored.",

        "<b>Automated verification:</b> Rail accuracy, Channel Access connectivity, PV updates, "
        "and other electronically observable checks are derived automatically from the latest "
        "rail-test results.",

        "<b>Operator verification:</b> During each rail test, the operator is prompted only for "
        "local-display observations that cannot be measured automatically. These observations "
        "are reused for the applicable system-test checklist items.",
    ]

    criteria_bullet_style = ParagraphStyle(
        "CriteriaBullet",
        parent=styles["Small"],
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=2,
    )
    for bullet in criteria_bullets:
        story.append(
            Paragraph(
                f"&bull;&nbsp;&nbsp;{bullet}",
                criteria_bullet_style,
            )
        )

    story.append(Spacer(1, 0.10 * inch))

    story.append(
        Paragraph(
            "System test matrix — latest result",
            styles["Heading2"],
        )
    )

    matrix_data = [[
        report_cell("ID", "TableHeader"),
        report_cell("Test", "TableHeader"),
        report_cell("Result", "TableHeader"),
        report_cell("Attempt", "TableHeader"),
        report_cell("Source / notes", "TableHeader"),
    ]]
    for test in SYSTEM_TESTS:
        status = status_matrix[test.test_id]
        note_text = status["notes"] or status["source"]
        if status["source"] and status["source"] not in note_text:
            note_text = f"{status['source']}: {note_text}" if note_text else status["source"]
        matrix_data.append([
            test.test_id,
            report_cell(test.name),
            status["display"],
            status["attempt"],
            Paragraph(escape(note_text), styles["Tiny"]),
        ])

    matrix_table = Table(
        matrix_data,
        repeatRows=1,
        colWidths=[0.45 * inch, 1.45 * inch, 0.75 * inch, 0.55 * inch, 4.35 * inch],
        hAlign="LEFT",
    )
    matrix_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (3, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ] + status_background_commands(matrix_data, [2])))
    story.append(matrix_table)
    story.append(Spacer(1, 0.14 * inch))
    story.append(PageBreak())

    story.append(
        Paragraph(
            "Disposition by rail (latest attempt only)",
            styles["Heading2"],
        )
    )

    summary_data = [[
        report_cell("Rail", "TableHeader"),
        report_cell("Attempt", "TableHeader"),
        report_cell("IOC channel", "TableHeader"),
        report_cell("Status", "TableHeader"),
        report_cell("Start", "TableHeader"),
        report_cell("End", "TableHeader"),
    ]]

    for key in RAIL_ORDER:
        rail = RAILS[key]

        if key not in latest:
            summary_data.append([
                rail.label,
                "—",
                "—",
                "NOT TESTED",
                "—",
                "—",
            ])
            continue

        _, run = latest[key]
        meta = run.get("meta", {})
        end = run.get("end", {})
        status = str(run.get("status", "INCOMPLETE"))
        run_pass = run.get("run_pass")

        if run_pass is True and status == "COMPLETE":
            disposition = "PASS"
        elif run_pass is False and status == "COMPLETE":
            disposition = "FAIL"
        else:
            disposition = status

        summary_data.append([
            rail.label,
            str(meta.get("attempt", "")) if isinstance(meta, dict) else "",
            str(meta.get("ioc_channel", "")) if isinstance(meta, dict) else "",
            disposition,
            report_cell(str(meta.get("timestamp", "")).replace("T", " "), "TableCellCenter") if isinstance(meta, dict) else "",
            report_cell(str(end.get("timestamp", "")).replace("T", " "), "TableCellCenter") if isinstance(end, dict) else "",
        ])

    st = Table(
        summary_data,
        repeatRows=1,
        colWidths=[
            0.55 * inch,
            0.50 * inch,
            0.80 * inch,
            0.65 * inch,
            2.525 * inch,
            2.525 * inch,
        ],
        hAlign="LEFT",
    )

    st.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 1), (3, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ] + status_background_commands(summary_data, [3]))
    )

    story.append(st)
    story.append(Spacer(1, 0.12 * inch))

    story.append(Paragraph("Local-display observations captured during rail testing", styles["Heading2"]))
    observation_rows = [[
        report_cell("Rail", "TableHeader"),
        report_cell("Identity / polarity", "TableHeader"),
        report_cell("Updates with load", "TableHeader"),
        report_cell("Agrees with EPICS", "TableHeader"),
        report_cell("Limits / status", "TableHeader"),
        report_cell("Network state", "TableHeader"),
    ]]
    rail_observations = latest_rail_observations(rows, checklist_rows, dut_filter)
    for key in RAIL_ORDER:
        values = [RAILS[key].label]
        for observation_index in range(1, 6):
            row = rail_observations.get(key, {}).get(observation_index)
            values.append(str(row.get("step_result", "NOT RECORDED")) if row else "NOT RECORDED")
        observation_rows.append(values)

    observation_table = Table(
        observation_rows,
        repeatRows=1,
        colWidths=[0.55 * inch, 1.40 * inch, 1.40 * inch, 1.40 * inch, 1.40 * inch, 1.40 * inch],
        hAlign="LEFT",
    )
    observation_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.30, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.0),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ] + status_background_commands(observation_rows, [1, 2, 3, 4, 5])))
    story.append(observation_table)

    # One detailed section per rail, using only that rail's latest attempt.
    for key in RAIL_ORDER:
        rail = RAILS[key]
        story.append(PageBreak())
        story.append(
            Paragraph(
                f"{rail.label} detailed results - latest attempt",
                styles["Heading1"],
            )
        )

        if key not in latest:
            story.append(
                Paragraph(
                    "No test data recorded for this rail.",
                    styles["BodyText"],
                )
            )
            continue

        _, run = latest[key]
        meta = run.get("meta", {})
        end = run.get("end", {})

        try:
            attempt = int(meta.get("attempt", "0") or 0) if isinstance(meta, dict) else 0
        except (TypeError, ValueError):
            attempt = 0

        status = str(run.get("status", "INCOMPLETE"))
        run_pass = run.get("run_pass")

        if run_pass is True and status == "COMPLETE":
            disposition = "PASS"
        elif run_pass is False and status == "COMPLETE":
            disposition = "FAIL"
        else:
            disposition = status

        start_ts = meta.get("timestamp", "") if isinstance(meta, dict) else ""
        end_ts = end.get("timestamp", "") if isinstance(end, dict) else ""
        channel = meta.get("ioc_channel", "") if isinstance(meta, dict) else ""

        story.append(
            Paragraph(
                f"<b>Attempt {attempt}</b> — {disposition} &nbsp;&nbsp; "
                f"IOC channel: {channel} &nbsp;&nbsp; "
                f"Start: {start_ts} &nbsp;&nbsp; End: {end_ts}",
                styles["Small"],
            )
        )

        story.append(Spacer(1, 0.05 * inch))

        points = run.get("points", {})

        if isinstance(points, dict) and points:
            try:
                voltage_plot_buffer = build_rail_voltage_plot(
                    rail,
                    run,
                )

                current_plot_buffer = build_rail_current_plot(
                    rail,
                    run,
                )

                current_error_plot_buffer = build_rail_current_error_plot(
                    rail,
                    run,
                )

                plot_buffers.extend([
                    voltage_plot_buffer,
                    current_plot_buffer,
                    current_error_plot_buffer,
                ])

                story.append(
                    Paragraph(
                        "Ideal versus measured response",
                        styles["Heading2"],
                    )
                )

                story.append(
                    Image(
                        voltage_plot_buffer,
                        width=plot_width,
                        height=plot_width * (3.4 / 9.0),
                    )
                )

                story.append(Spacer(1, 0.06 * inch))

                story.append(
                    Image(
                        current_plot_buffer,
                        width=plot_width,
                        height=plot_width * (4.4 / 9.0),
                    )
                )

                story.append(Spacer(1, 0.06 * inch))

                story.append(
                    KeepTogether([
                        Paragraph(
                            "Current error detail",
                            styles["Heading2"],
                        ),
                        Image(
                            current_error_plot_buffer,
                            width=plot_width,
                            height=plot_width * (4.2 / 9.0),
                        ),
                        Spacer(1, 0.10 * inch),
                    ])
                )

            except Exception as exc:
                story.append(
                    Paragraph(
                        f"Plot generation warning: {exc}",
                        styles["Small"],
                    )
                )
                story.append(Spacer(1, 0.10 * inch))
        else:
            story.append(
                Paragraph(
                    "This latest attempt contains no recorded sample points.",
                    styles["Small"],
                )
            )
            story.append(Spacer(1, 0.10 * inch))

        point_data = [[
            "Set I\n(A)",
            "Rigol V\n(V)",
            "V ref\n(V)",
            "IOC V\n(V)",
            "V err\n(V)",
            "V tol\n(V)",
            "Rigol I\n(A)",
            "IOC I\n(A)",
            "I err\n(A)",
            "I tol\n(A)",
            "Result",
        ]]

        if isinstance(points, dict):
            for setpoint in sorted(points.keys()):
                samples_at_point = points[setpoint]

                if (
                    not isinstance(samples_at_point, list)
                    or not samples_at_point
                ):
                    continue

                rigol_voltage = mean_field(
                    samples_at_point,
                    "rigol_voltage_v",
                )

                voltage_reference = mean_field(
                    samples_at_point,
                    "voltage_reference_v",
                )

                ioc_voltage = mean_field(
                    samples_at_point,
                    "ioc_voltage_v",
                )

                voltage_error = mean_field(
                    samples_at_point,
                    "voltage_error_v",
                )

                voltage_tolerance = mean_field(
                    samples_at_point,
                    "voltage_tolerance_v",
                )

                rigol_current = mean_field(
                    samples_at_point,
                    "rigol_current_a",
                )

                ioc_current_ma = mean_field(
                    samples_at_point,
                    "ioc_current_ma",
                )

                current_error = mean_field(
                    samples_at_point,
                    "current_error_a",
                )

                current_tolerance = mean_field(
                    samples_at_point,
                    "current_tolerance_a",
                )

                point_pass = all(
                    as_bool(sample.get("sample_pass"))
                    for sample in samples_at_point
                )

                point_data.append([
                    f"{setpoint:.4f}",
                    f"{rigol_voltage:.4f}",
                    f"{voltage_reference:+.4f}",
                    f"{ioc_voltage:+.4f}",
                    f"{voltage_error:+.4f}",
                    f"{voltage_tolerance:.4f}",
                    f"{rigol_current:.4f}",
                    f"{ioc_current_ma/1000.0:.4f}",
                    f"{current_error:+.4f}",
                    f"{current_tolerance:.4f}",
                    "PASS" if point_pass else "FAIL",
                ])

        pt = Table(
            point_data,
            repeatRows=1,
            colWidths=[0.60 * inch] * 10 + [0.65 * inch],
            hAlign="LEFT",
        )

        pt.setStyle(
            TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.2),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ] + status_background_commands(point_data, [10]))
        )

        story.append(pt)
        story.append(Spacer(1, 0.10 * inch))

    story.append(PageBreak())
    story.append(Paragraph("System test checklist — merged automatic/manual evidence", styles["Heading1"]))
    story.append(Paragraph(
        "Each checklist step is filled from automatic rail-test evidence whenever the software can prove it. "
        "Only items that require visual/operator judgment remain manual. The source column identifies whether "
        "the current result came from automatic evidence, the latest checklist entry, or is still pending.",
        styles["Small"],
    ))
    story.append(Spacer(1, 0.10 * inch))

    for test in SYSTEM_TESTS:
        status = status_matrix[test.test_id]
        story.append(Paragraph(
            f"{test.test_id}: {escape(test.name)} — {escape(status['display'])}",
            styles["Heading2"],
        ))
        story.append(Paragraph(
            f"<b>Method:</b> {escape(test.method)}<br/><b>Pass criterion:</b> {escape(test.pass_criterion)}",
            styles["Small"],
        ))
        story.append(Spacer(1, 0.04 * inch))

        merged_steps = merged_test_step_results(test, rows, checklist_rows, dut_filter)
        step_table_data = [[
            report_cell("#", "TableHeader"),
            report_cell("Checklist item", "TableHeader"),
            report_cell("Result", "TableHeader"),
            report_cell("Source / evidence", "TableHeader"),
        ]]
        for step in merged_steps:
            step_table_data.append([
                step["step_index"],
                Paragraph(escape(step["step_text"]), styles["Tiny"]),
                step["step_result"],
                Paragraph(escape(step["source"] + (": " + step["notes"] if step["notes"] else "")), styles["Tiny"]),
            ])

        step_table = Table(
            step_table_data,
            repeatRows=1,
            colWidths=[0.30 * inch, 3.45 * inch, 0.70 * inch, 3.10 * inch],
            hAlign="LEFT",
        )
        step_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 6.8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 1), (2, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ] + status_background_commands(step_table_data, [2])))
        story.append(step_table)
        story.append(Spacer(1, 0.08 * inch))

    story.append(PageBreak())
    story.append(Paragraph("Test completion criteria", styles["Heading1"]))

    all_tests_executed = all(
        status_matrix[test.test_id]["display"] != "NOT TESTED"
        for test in SYSTEM_TESTS
    )
    all_rails_verified = (
        status_matrix["ST-03"]["effective"] == "PASS"
        and status_matrix["ST-04"]["effective"] == "PASS"
    )
    all_tests_pass = all(
        status_matrix[test.test_id]["effective"] == "PASS"
        for test in SYSTEM_TESTS
    )
    raw_preserved = data_path.exists() and data_path.stat().st_size > 0

    completion_rows = [
        [report_cell("Completion criterion", "TableHeader"), report_cell("Status", "TableHeader")],
        [report_cell("Every test identified in the system test matrix has been executed."), "YES" if all_tests_executed else "NO"],
        [report_cell("All six rail channels have completed voltage and current verification."), "YES" if all_rails_verified else "NO"],
        [report_cell("All system-test items have an effective PASS result."), "YES" if all_tests_pass else "NO"],
        [report_cell("Failed/incomplete tests are retained in the append-only checklist history for correction/retest or documentation as limitations."), "RECORDED" if checklist_path.exists() else "NO CHECKLIST DATA"],
        [report_cell("Raw measurement data has been preserved."), "YES" if raw_preserved else "NO"],
        [report_cell("Final test report has been generated."), "YES"],
    ]
    completion_table = Table(
        completion_rows,
        repeatRows=1,
        colWidths=[6.65 * inch, 0.90 * inch],
        hAlign="LEFT",
    )
    completion_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
    ] + status_background_commands(completion_rows, [1])))
    story.append(completion_table)

    story.append(PageBreak())
    story.append(Paragraph("Engineering basis for tolerances", styles["Heading1"]))
    ltc_v_err = ltc2945_voltage_datasheet_error_v()
    basis = (
        f"The LTC2945 uses a 12-bit VIN converter with 25 mV/LSB and a 102.4 V full-scale. "
        f"Its guaranteed total unadjusted error is ±0.75% of full-scale, "
        f"approximately ±{ltc_v_err:.3f} V for VIN.The report uses a "
        "tighter characterization/acceptance limit of 2% with a 100 mV floor, as this is a more reasonable limit at the used range."
    )
    story.append(Paragraph(basis, styles["Small"]))
    story.append(Spacer(1, 0.10 * inch))

    current_basis_rows = [[
        report_cell("Rail", "TableHeader"),
        report_cell("Shunt", "TableHeader"),
        report_cell("LTC2945 ADC TUE equivalent", "TableHeader"),
        report_cell("1% shunt at test max", "TableHeader"),
        report_cell("Recommended acceptance", "TableHeader"),
    ]]
    for key in RAIL_ORDER:
        rail = RAILS[key]
        adc_a = (LTC2945_TUE_FS * LTC2945_SENSE_FULL_SCALE_V) / rail.shunt_ohms
        shunt_a = SHUNT_TOLERANCE * rail.test_max_a
        current_basis_rows.append([
            rail.label,
            f"{rail.shunt_ohms*1000:.1f} mΩ",
            f"{adc_a*1000:.1f} mA",
            f"{shunt_a*1000:.1f} mA",
            f"±max({CURRENT_PERCENT_TOL*100:.0f}% reading, {rail.current_floor_a*1000:.0f} mA)",
        ])
    bt = Table(
        current_basis_rows,
        repeatRows=1,
        colWidths=[0.65*inch, 0.75*inch, 1.55*inch, 1.55*inch, 3.05*inch],
        hAlign="LEFT",
    )
    bt.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.35, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7.5),
        ("ALIGN", (1,1), (-1,-1), "CENTER"),
    ]))
    story.append(bt)
    story.append(Spacer(1, 0.12 * inch))
    story.append(Paragraph(
        "The current system-test criterion is ±5% of the reference value. At low current, where a "
        "percentage-only limit approaches zero and instrument/ADC resolution becomes significant, the "
        "script uses the larger of the 5% window and the configured absolute floor. The floor also covers "
        "the LTC2945 delta-sense full-scale TUE, shunt tolerance, and a small reference/rounding margin. ",
        styles["Small"],
    ))



    doc.build(story)
    print(f"Report written: {output_pdf_path}")
    return output_pdf_path
