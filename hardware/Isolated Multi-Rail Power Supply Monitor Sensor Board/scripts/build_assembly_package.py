"""
build_assembly_package.py
Assembly Drawing + Gerbers plotting script for plotting schematics from KiCAD.
Tested on KiCAD Ver 9, Windows.
"""
from pathlib import Path
import subprocess
import shutil
from datetime import datetime
from common import load_context, KICAD_CLI, KiCadProjectContext
from common import cleanup_temp_dir, zip_directory, combine_pdfs


def build_assembly(ctx: KiCadProjectContext) -> None:
    """Build full Assembly Plot Job"""
    build_bom(ctx)
    build_assy_gerbers(ctx)
    build_assy_pdf(ctx)
    cleanup_temp_dir(ctx.assy_output_dir_temp)  # Delete temp files


    timestamp = datetime.now().strftime("%m-%d-%Y_%H-%M")
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.assy_suffix
    rev_num = ctx.variables.revision_num

    zip_filename_out = f"{prefix}-{suffix}_Rev-{rev_num}_{timestamp}.zip"
    zip_source_dir = Path(ctx.assy_output_dir)
    zip_out_path = Path(ctx.assy_output_dir / zip_filename_out)

    zip_directory(zip_source_dir, zip_out_path)




def build_bom(ctx: KiCadProjectContext) -> None:
    pass


def build_assy_gerbers(ctx: KiCadProjectContext) -> None:
    """Build all assembly gerber outputs"""
    # build_assy_top_grb(ctx)
    # build_assy_bot_grb(ctx)
    build_comp_place_top_ascii(ctx)
    build_comp_place_bot_ascii(ctx)
    build_comp_place_top_grb(ctx)
    build_comp_place_bot_grb(ctx)

def build_assy_top_grb(ctx: KiCadProjectContext) -> None:
    """Build Assy TOP Gerbers"""
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.assy_suffix
    revision_num = ctx.variables.revision_num

    filename = f"{prefix}-{suffix}_Rev-{revision_num}_TOP.gbr"
    final_output_file = ctx.assy_output_dir / filename

    output_path_temp = ctx.assy_output_dir_temp
    generated_file = output_path_temp / f"{ctx.pcb_file.stem}-Assembly_Top.gbr"

    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "gerbers",
        "--output",
        str(output_path_temp),
        "--drawing-sheet",
        str(ctx.assy_titleblock_top),
        "--layers",
        "Assembly.Top",
        "--include-border-title",
        "--subtract-soldermask",
        "--common-layers",
        "Edge.Cuts",
        "--no-protel-ext",
        str(ctx.pcb_file),
    ]
    print("------------------------------------------------------------------")
    print("Creating Assembly Gerber Files")
    print(f"Running: {cmd}")
    subprocess.run(cmd, check=True)

    print("Generated ASSY_TOP output:", str(output_path_temp))
    print("Moving file....")
    if not generated_file.is_file():
        raise FileNotFoundError(
            f"Expected assembly file was not generated: {generated_file}"
        )

    shutil.move(generated_file, final_output_file)

    print(f"Move done, moved to: {final_output_file}")
    print("------------------------------------------------------------------")


def build_assy_bot_grb(ctx: KiCadProjectContext) -> None:
    """Build Assy BOT Gerbers"""
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.assy_suffix
    revision_num = ctx.variables.revision_num

    filename = f"{prefix}-{suffix}_Rev-{revision_num}_BOT.gbr"
    final_output_file = ctx.assy_output_dir / filename

    output_path_temp = ctx.assy_output_dir_temp
    generated_file = output_path_temp / f"{ctx.pcb_file.stem}-Assembly_Bottom.gbr"

    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "gerbers",
        "--output",
        str(output_path_temp),
        "--drawing-sheet",
        str(ctx.assy_titleblock_bot),
        "--layers",
        "Assembly.Bottom",
        "--include-border-title",
        "--subtract-soldermask",
        "--common-layers",
        "Edge.Cuts",
        "--no-protel-ext",
        str(ctx.pcb_file),
    ]
    print("------------------------------------------------------------------")
    print("Creating Assembly Bottom Files")
    print(f"Running: {cmd}")
    subprocess.run(cmd, check=True)

    print("Generated ASSY_BOT output:", str(output_path_temp))
    print("Moving file....")
    if not generated_file.is_file():
        raise FileNotFoundError(
            f"Expected assembly file was not generated: {generated_file}"
        )

    shutil.move(generated_file, final_output_file)

    print(f"Move done, moved to: {final_output_file}")
    print("------------------------------------------------------------------")


def build_comp_place_top_ascii(ctx: KiCadProjectContext) -> None:
    """Build TOP Component Placement/Position File for PnP"""
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.assy_suffix
    revision_num = ctx.variables.revision_num

    filename = f"{prefix}-{suffix}_Rev-{revision_num}_TOP.pos"
    final_output_file = ctx.assy_output_dir / filename

    output_path_temp = ctx.assy_output_dir_temp
    generated_file = output_path_temp / f"{ctx.pcb_file.stem}-Assembly_Top.pos"

    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "pos",
        "--output",
        str(generated_file),
        "--side",
        "front",
        "--format",
        "ascii",
        "--units",
        "in",
        str(ctx.pcb_file),
    ]
    print("------------------------------------------------------------------")
    print("Creating Assembly Top Files")
    print(f"Running: {cmd}")
    subprocess.run(cmd, check=True)

    print("Generated ASSY_TOP output:", str(output_path_temp))
    print("Moving file....")
    if not generated_file.is_file():
        raise FileNotFoundError(
            f"Expected assembly file was not generated: {generated_file}"
        )

    shutil.move(generated_file, final_output_file)

    print(f"Move done, moved to: {final_output_file}")
    print("------------------------------------------------------------------")


def build_comp_place_bot_ascii(ctx: KiCadProjectContext) -> None:
    """Build BOTTOM Component Placement/Position File for PnP"""
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.assy_suffix
    revision_num = ctx.variables.revision_num

    filename = f"{prefix}-{suffix}_Rev-{revision_num}_BOT.pos"
    final_output_file = ctx.assy_output_dir / filename

    output_path_temp = ctx.assy_output_dir_temp
    generated_file = output_path_temp / f"{ctx.pcb_file.stem}-Assembly_Bottom.pos"

    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "pos",
        "--output",
        str(generated_file),
        "--side",
        "back",
        "--format",
        "ascii",
        "--units",
        "in",
        str(ctx.pcb_file),
    ]
    print("------------------------------------------------------------------")
    print("Creating Assembly Bottom Files")
    print(f"Running: {cmd}")
    subprocess.run(cmd, check=True)

    print("Generated ASSY_BOT output:", str(output_path_temp))
    print("Moving file....")
    if not generated_file.is_file():
        raise FileNotFoundError(
            f"Expected assembly file was not generated: {generated_file}"
        )

    shutil.move(generated_file, final_output_file)

    print(f"Move done, moved to: {final_output_file}")
    print("------------------------------------------------------------------")


def build_comp_place_top_grb(ctx: KiCadProjectContext) -> None:
    """Build TOP Component Placement/Position File for PnP"""
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.assy_suffix
    revision_num = ctx.variables.revision_num

    filename = f"{prefix}-{suffix}_Rev-{revision_num}_TOP.gbr"
    final_output_file = ctx.assy_output_dir / filename

    output_path_temp = ctx.assy_output_dir_temp
    generated_file = output_path_temp / f"{ctx.pcb_file.stem}-Assembly_Top.gbr"

    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "pos",
        "--output",
        str(generated_file),
        "--side",
        "front",
        "--format",
        "gerber",
        "--units",
        "in",
        "--gerber-board-edge",
        str(ctx.pcb_file),
    ]
    print("------------------------------------------------------------------")
    print("Creating Assembly Top Files")
    print(f"Running: {cmd}")
    subprocess.run(cmd, check=True)

    print("Generated ASSY_TOP output:", str(output_path_temp))
    print("Moving file....")
    if not generated_file.is_file():
        raise FileNotFoundError(
            f"Expected assembly file was not generated: {generated_file}"
        )

    shutil.move(generated_file, final_output_file)

    print(f"Move done, moved to: {final_output_file}")
    print("------------------------------------------------------------------")


def build_comp_place_bot_grb(ctx: KiCadProjectContext) -> None:
    """Build BOTTOM Component Placement/Position File for PnP"""
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.assy_suffix
    revision_num = ctx.variables.revision_num

    filename = f"{prefix}-{suffix}_Rev-{revision_num}_BOT.gbr"
    final_output_file = ctx.assy_output_dir / filename

    output_path_temp = ctx.assy_output_dir_temp
    generated_file = output_path_temp / f"{ctx.pcb_file.stem}-Assembly_Bottom.gbr"

    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "pos",
        "--output",
        str(generated_file),
        "--side",
        "back",
        "--format",
        "gerber",
        "--units",
        "in",
        "--gerber-board-edge",
        str(ctx.pcb_file),
    ]
    print("------------------------------------------------------------------")
    print("Creating Assembly Bottom Files")
    print(f"Running: {cmd}")
    subprocess.run(cmd, check=True)

    print("Generated ASSY_BOT output:", str(output_path_temp))
    print("Moving file....")
    if not generated_file.is_file():
        raise FileNotFoundError(
            f"Expected assembly file was not generated: {generated_file}"
        )

    shutil.move(generated_file, final_output_file)

    print(f"Move done, moved to: {final_output_file}")
    print("------------------------------------------------------------------")


def build_assy_pdf(ctx: KiCadProjectContext) -> None:
    """Build all the individual PDF pages...then combine them,
    and move them to the assy outputs directory"""

    assy_top_pdf = build_assy_top_pdf(ctx)
    assy_bot_pdf = build_assy_bot_pdf(ctx)

    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.assy_suffix
    revision_num = ctx.variables.revision_num

    filename = f"{prefix}-{suffix}_Rev-{revision_num}.pdf"
    final_output_file = ctx.assy_output_dir / filename

    print("------------------------------------------------------------------")
    print("Combining Assy PDF Files")
    pdf_binder = combine_pdfs(
        output_pdf = final_output_file,
        input_pdfs=[
            assy_top_pdf,
            assy_bot_pdf,
        ]
    )
    print("------------------------------------------------------------------")
    _ = pdf_binder


def build_assy_top_pdf(ctx: KiCadProjectContext) -> Path:
    """Build Top assembly PDF drawing"""
    output_path_temp = ctx.assy_output_dir_temp
    generated_file = output_path_temp / f"{ctx.pcb_file.stem}-Assy_TOP.pdf"
    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "pdf",
        "--output",
        str(generated_file),
        "--layers",
        "Assembly.Top,Edge.Cuts",
        "--drawing-sheet",
        str(ctx.assy_titleblock_top),
        "--include-border-title",
        "--subtract-soldermask",
        "--theme",
        "Plotter",
        "--mode-single",
        "--sketch-pads-on-fab-layers",
        str(ctx.pcb_file),
    ]
    print("------------------------------------------------------------------")
    print("Creating Top ASSY PDF")
    print(f"Running: {cmd}")
    subprocess.run(cmd, check=True)
    return generated_file

def build_assy_bot_pdf(ctx: KiCadProjectContext) -> Path:
    """Build Bottom assembly PDF drawing"""
    output_path_temp = ctx.assy_output_dir_temp
    generated_file = output_path_temp / f"{ctx.pcb_file.stem}-Assy_BOT.pdf"
    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "pdf",
        "--output",
        str(generated_file),
        "--layers",
        "Assembly.Bottom,Edge.Cuts",
        "--drawing-sheet",
        str(ctx.assy_titleblock_bot),
        "--include-border-title",
        "--subtract-soldermask",
        "--theme",
        "Plotter",
        "--mode-single",
        "--mirror",
        "--sketch-pads-on-fab-layers",
        str(ctx.pcb_file),
    ]
    print("------------------------------------------------------------------")
    print("Creating Bottom ASSY PDF")
    print(f"Running: {cmd}")
    subprocess.run(cmd, check=True)
    return generated_file


if __name__ == "__main__":
    local_ctx = load_context()
    build_assembly(local_ctx)
