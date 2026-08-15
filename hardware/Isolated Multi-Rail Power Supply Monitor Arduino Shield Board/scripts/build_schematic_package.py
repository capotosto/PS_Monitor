"""
build_schematic_package.py
Schematic plotting script for plotting schematics from KiCAD.
Tested on KiCAD Ver 9, Windows.
"""

import subprocess
from common import load_context, KICAD_CLI, KiCadProjectContext


def build_schematic(ctx: KiCadProjectContext) -> None:
    """
    Generates schematic PDF package using KiCad CLI.
    Output name is driven by KiCad project variables:
    DRAWING_NUMBER-PREFIX + DRAWING-SCHEMA_SUFFIX
    """

    # ---- Extract naming variables ----
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.schema_suffix
    revision_num = ctx.variables.revision_num

    filename = f"{prefix}-{suffix}_Rev-{revision_num}.pdf"

    ctx.schematic_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = ctx.schematic_output_dir / filename

    # ---- KiCad CLI export ----
    cmd = [
        str(KICAD_CLI),
        "sch",
        "export",
        "pdf",
        "--output",
        str(output_path),
        "--theme",
        "Plotter",
        "--drawing-sheet",
        str(ctx.schematic_titleblock),
        str(ctx.schematic_file)
    ]

    print("Running:", " ".join(cmd))

    subprocess.run(cmd, check=True)

    print("Generated schematic:", output_path)


if __name__ == "__main__":
    local_ctx = load_context()
    build_schematic(local_ctx)
