"""
build_fabrication_package.py
Fab Drawing + Gerbers plotting script for plotting schematics from KiCAD.
Tested on KiCAD Ver 9, Windows.
"""
from pathlib import Path
import subprocess
import shutil
from datetime import datetime
from common import load_context, KICAD_CLI, KiCadProjectContext
from common import cleanup_temp_dir, zip_directory, combine_pdfs


def build_fab(ctx: KiCadProjectContext) -> None:
    """foo"""
    build_drill(ctx)  # Excellon Drill File
    build_ipc_d356(ctx)  # IPC D356 Netlist File
    build_fab_gerbers(ctx)  # Build all gerbers
    build_fab_pdf(ctx)  # Build Fab PDF binder
    cleanup_temp_dir(ctx.fab_output_dir_temp)  # Delete temp files


    timestamp = datetime.now().strftime("%m-%d-%Y_%H-%M")
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.fab_suffix
    rev_num = ctx.variables.revision_num

    zip_filename_out = f"{prefix}-{suffix}_Rev-{rev_num}_{timestamp}.zip"
    zip_source_dir = Path(ctx.fab_output_dir)
    zip_out_path = Path(ctx.fab_output_dir / zip_filename_out)

    zip_directory(zip_source_dir, zip_out_path)


def build_drill(ctx: KiCadProjectContext) -> None:
    """Build Drill file Excellon format"""
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.fab_suffix
    revision_num = ctx.variables.revision_num

    filename_drl = f"{prefix}-{suffix}_Rev-{revision_num}.drl"
    final_output_file = ctx.fab_output_dir / filename_drl

    output_path_temp = ctx.fab_output_dir_temp
    generated_drl_file = output_path_temp / f"{ctx.pcb_file.stem}.drl"

    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "drill",
        "--output",
        str(output_path_temp),
        "--format",
        "excellon",
        "--drill-origin",
        "absolute",
        "--excellon-zeros-format",
        "decimal",
        "--excellon-oval-format",
        "alternate",
        "--excellon-units",
        "mm",
        "--gerber-precision",
        "6",
        str(ctx.pcb_file),
    ]
    print("------------------------------------------------------------------")
    print("Creating Excellon Drill Files")
    print(f"Running: {cmd}")

    subprocess.run(cmd, check=True)

    print("Generated DRILL_FILE_EXCELLON output:", str(output_path_temp))
    print("Moving file....")

    if not generated_drl_file.is_file():
        raise FileNotFoundError(
            f"Expected drill file was not generated: {generated_drl_file}"
        )

    shutil.move(generated_drl_file, final_output_file)

    print(f"Move done, moved to: {final_output_file}")
    print("------------------------------------------------------------------")


def build_ipc_d356(ctx: KiCadProjectContext) -> None:
    """Build IPC-D-356 Netlist file"""
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.fab_suffix
    revision_num = ctx.variables.revision_num

    filename_d356 = f"{prefix}-{suffix}_Rev-{revision_num}.d356"

    output_path_temp = ctx.fab_output_dir_temp
    output_path_temp.mkdir(parents=True, exist_ok=True)

    generated_d356_file = output_path_temp / filename_d356
    final_output_file = ctx.fab_output_dir / filename_d356

    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "ipcd356",
        "--output",
        str(generated_d356_file),
        str(ctx.pcb_file),
    ]

    print("------------------------------------------------------------------")
    print("Creating IPC-D-356 Netlist File")
    print(f"Running: {cmd}")

    subprocess.run(cmd, check=True)

    print(f"Generated IPC-D-356 output: {generated_d356_file}")

    if not generated_d356_file.is_file():
        raise FileNotFoundError(
            f"Expected d356 file was not generated: {generated_d356_file}"
        )

    if final_output_file.exists():
        final_output_file.unlink()

    shutil.move(generated_d356_file, final_output_file)

    print(f"Move done, moved to: {final_output_file}")
    print("------------------------------------------------------------------")


def build_fab_gerbers(ctx: KiCadProjectContext) -> None:
    """Build All Fab Gerbers"""
    build_drill_dwg_layer_gerbers(ctx)  # Build Drill.Drawing Layer Gerbers (With Titleblock)
    build_other_gerbers(ctx)  # Build non-Drill.Drawing Layer Gerbers (No Titleblock)


def build_drill_dwg_layer_gerbers(ctx: KiCadProjectContext) -> None:
    """Build Fab Gerbers Drill.Drawing layer, **NOT** the Excellon file!"""
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.fab_suffix
    revision_num = ctx.variables.revision_num

    filename = f"{prefix}-{suffix}_Rev-{revision_num}.gbr"
    final_output_file = ctx.fab_output_dir / filename

    output_path_temp = ctx.fab_output_dir_temp
    generated_file = output_path_temp / f"{ctx.pcb_file.stem}-Drill_Drawing.gbr"

    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "gerbers",
        "--output",
        str(output_path_temp),
        "--drawing-sheet",
        str(ctx.fab_titleblock),
        "--layers",
        "Drill.Drawing",
        "--include-border-title",
        "--subtract-soldermask",
        "--common-layers",
        "Edge.Cuts",
        "--no-protel-ext",
        str(ctx.pcb_file),
    ]
    print("------------------------------------------------------------------")
    print("Creating Drill Drawing Files")
    print(f"Running: {cmd}")
    subprocess.run(cmd, check=True)

    print("Generated DRILL_DRAWING_FILE output:", str(output_path_temp))
    print("Moving file....")
    if not generated_file.is_file():
        raise FileNotFoundError(
            f"Expected drill file was not generated: {generated_file}"
        )

    shutil.move(generated_file, final_output_file)

    print(f"Move done, moved to: {final_output_file}")
    print("------------------------------------------------------------------")


def build_other_gerbers(ctx: KiCadProjectContext) -> None:
    """Build All non-assembly and non-Drill.Drawing Gerbers"""
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.fab_suffix
    revision_num = ctx.variables.revision_num

    filename = f"{prefix}-{suffix}_Rev-{revision_num}.gbr"
    final_output_file = ctx.fab_output_dir / filename

    output_path_temp = ctx.fab_output_dir_temp
    ctx.fab_output_dir.mkdir(parents=True, exist_ok=True)

    layers = [
        "SST", "SMT",
        "LY01", "LY02", "LY03", "LY04",
        "LY05", "LY06", "LY07", "LY08",
        "LY09", "LY10", "LY11", "LY12",
        "LY13", "LY14", "LY15", "LY16",
        "SMB", "SSB"
    ]

    layer_arg = ",".join(layers)

    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "gerbers",
        "--output",
        str(output_path_temp),
        "--layers",
        str(layer_arg),
        "--subtract-soldermask",
        "--common-layers",
        "Edge.Cuts",
        "--no-protel-ext",
        str(ctx.pcb_file),
    ]

    print("------------------------------------------------------------------")
    print("Creating Non-Fab layer and Non-Assembly Gerbers...")
    print(f"Running: {cmd}")
    subprocess.run(cmd, check=True)

    print("Generated Gerber Output Directory:", str(output_path_temp))
    print("Moving files....")

    moved_count = 0
    missing_files = []

    for layer in layers:
        generated_file = output_path_temp / f"{ctx.pcb_file.stem}-{layer}.gbr"

        final_filename = f"{prefix}-{suffix}_Rev-{revision_num}_{layer}.gbr"
        final_output_file = ctx.fab_output_dir / final_filename

        if not generated_file.is_file():
            missing_files.append(generated_file)
            continue

        if final_output_file.exists():
            final_output_file.unlink()

        shutil.move(generated_file, final_output_file)
        moved_count += 1
        print(f"Moved: {generated_file.name} -> {final_output_file.name}")

    print(f"Moved {moved_count} Gerber file(s).")

    if missing_files:
        print("WARNING: Expected Gerber file was not generated...\n"
                  "The script is configured assuming maximum 16 layers. "
                  "\nIf layers do not exist, ignore the error.\n")
        for missing_file in missing_files:
            print(f"  - {missing_file}")

    print("Move done.")

    print("------------------------------------------------------------------")


def build_fab_pdf(ctx: KiCadProjectContext) -> None:
    """Build all the individual PDF pages...then combine them,
    and move them to the fab outputs directory"""

    drill_pdf = build_drill_dwg_layer_pdf(ctx)
    other_pdf = build_other_pdf(ctx)

    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.fab_suffix
    revision_num = ctx.variables.revision_num

    filename = f"{prefix}-{suffix}_Rev-{revision_num}.pdf"
    final_output_file = ctx.fab_output_dir / filename

    print("------------------------------------------------------------------")
    print("Combining Fab PDF Files")
    pdf_binder = combine_pdfs(
        output_pdf = final_output_file,
        input_pdfs=[
            drill_pdf,
            other_pdf,
        ]
    )
    print("------------------------------------------------------------------")
    _ = pdf_binder


def build_drill_dwg_layer_pdf(ctx: KiCadProjectContext) -> Path:
    """Build Fab Gerbers Drill.Drawing layer PDF, **NOT** the Excellon file!"""
    output_path_temp = ctx.fab_output_dir_temp
    generated_file = output_path_temp / f"{ctx.pcb_file.stem}-Drill_Drawing.pdf"
    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "pdf",
        "--output",
        str(generated_file),
        "--layers",
        "Drill.Drawing,Edge.Cuts",
        "--drawing-sheet",
        str(ctx.fab_titleblock),
        "--include-border-title",
        "--subtract-soldermask",
        "--theme",
        "Plotter",
        "--mode-single",
        str(ctx.pcb_file),
    ]
    print("------------------------------------------------------------------")
    print("Creating Drill Drawing Files")
    print(f"Running: {cmd}")
    subprocess.run(cmd, check=True)
    return generated_file


def build_other_pdf(ctx: KiCadProjectContext) -> None:
    """Build All non-assembly and non-Drill.Drawing PDF Sheets"""

    output_path_temp = ctx.fab_output_dir_temp
    generated_file = output_path_temp
    ctx.fab_output_dir.mkdir(parents=True, exist_ok=True)


    layers = [
        "SST", "SMT", 
        "LY01", "LY02", "LY03", "LY04",
        "LY05", "LY06", "LY07", "LY08",
        "LY09", "LY10", "LY11", "LY12",
        "LY13", "LY14", "LY15", "LY16",
        "SMB", "SSB",
    ]

    layer_arg = ",".join(layers)

    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "pdf",
        "--output",
        str(generated_file),
        "--layers",
        str(layer_arg),
        "--subtract-soldermask",
        "--black-and-white",
        "--common-layers",
        "Edge.Cuts",
        "--mode-multipage",
        str(ctx.pcb_file),
    ]

    print("------------------------------------------------------------------")
    print("Creating Non-Fab layer and Non-Assembly PDF Plots...")
    print(f"Running: {cmd}")
    subprocess.run(cmd, check=True)
    print("------------------------------------------------------------------")
    return generated_file / f"{ctx.pcb_file.stem}.pdf"

if __name__ == "__main__":
    local_ctx = load_context()
    build_fab(local_ctx)
