"""
build_step_package.py
Build STEP File from KiCAD. Tested on KiCAD Ver 9, Windows.
"""
import subprocess
from common import load_context, KICAD_CLI, KiCadProjectContext


def build_step_package(ctx: KiCadProjectContext):
    """Build the step file and render images"""
    build_step_file(ctx)
    build_render(ctx)


def build_step_file(ctx: KiCadProjectContext):
    """Generate STEP File of PCB"""
    # ---- Extract naming variables ----
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.fab_suffix
    revision_num = ctx.variables.revision_num

    filename = f"{prefix}-{suffix}_Rev-{revision_num}.step"

    ctx.step_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = ctx.step_output_dir / filename

    # ---- KiCad CLI export ----
    cmd = [
        str(KICAD_CLI),
        "pcb",
        "export",
        "step",
        "--output",
        str(output_path),
        "--force",
        "--no-dnp",
        "--subst-models",
        "--cut-vias-in-body",
        "--include-tracks",
        "--include-pads",
        "--include-zones",
        "--include-silkscreen",
        "--include-soldermask",
        str(ctx.pcb_file)
    ]

    print("Running:", " ".join(cmd))

    subprocess.run(cmd, check=True)

    print("Generated schematic:", output_path)


def build_render(ctx: KiCadProjectContext):
    """Generate PNG renders of PCB"""
    # ---- Extract naming variables ----
    prefix = ctx.variables.drawing_number_prefix
    suffix = ctx.variables.fab_suffix
    revision_num = ctx.variables.revision_num

    top_filename = f"{prefix}-{suffix}_Rev-{revision_num}_top.png"
    bottom_filename = f"{prefix}-{suffix}_Rev-{revision_num}_bottom.png"
    isometric_filename = f"{prefix}-{suffix}_Rev-{revision_num}_isometric.png"
    left_filename = f"{prefix}-{suffix}_Rev-{revision_num}_left.png"
    right_fileanme = f"{prefix}-{suffix}_Rev-{revision_num}_right.png"
    front_filename = f"{prefix}-{suffix}_Rev-{revision_num}_front.png"
    back_filename = f"{prefix}-{suffix}_Rev-{revision_num}_back.png"

    ctx.step_output_dir.mkdir(parents=True, exist_ok=True)

    top_output_path = ctx.step_output_dir / top_filename
    bottom_output_path = ctx.step_output_dir / bottom_filename
    isometric_output_path = ctx.step_output_dir / isometric_filename
    left_output_path = ctx.step_output_dir / left_filename
    right_output_path = ctx.step_output_dir / right_fileanme
    front_output_path = ctx.step_output_dir / front_filename
    back_output_path = ctx.step_output_dir / back_filename

    # ---- KiCad CLI export ----
    print("--------------------------------------------------\nTop")
    cmd = [
        str(KICAD_CLI),
        "pcb",
        "render",
        "--output",
        str(top_output_path),
        "--quality",
        "high",
        "--floor",
        "--rotate='0,0,0'",
        "--side",
        "top",
        "--zoom",
        "1",
        "--width",
        "6400",
        "--height",
        "3600",
        # "--preset",
        # "follow_pcb_editor",
        str(ctx.pcb_file)
    ]

    print("Running:", " ".join(cmd))

    subprocess.run(cmd, check=True)

    print("Generated image:", top_output_path)

    print("--------------------------------------------------\nBottom")
    cmd = [
        str(KICAD_CLI),
        "pcb",
        "render",
        "--output",
        str(bottom_output_path),
        "--quality",
        "high",
        "--floor",
        "--rotate='0,0,0'",
        "--side",
        "bottom",
        "--zoom",
        "1",
        "--width",
        "6400",
        "--height",
        "3600",
        # "--preset",
        # "follow_pcb_editor",
        str(ctx.pcb_file)
    ]

    print("Running:", " ".join(cmd))

    subprocess.run(cmd, check=True)

    print("Generated image:", bottom_output_path)

    print("--------------------------------------------------\nIsometric")
    cmd = [
        str(KICAD_CLI),
        "pcb",
        "render",
        "--output",
        str(isometric_output_path),
        "--quality",
        "high",
        "--floor",
        "--rotate='315,0,45'",
        "--side",
        "top",
        "--zoom",
        "1",
        "--width",
        "6400",
        "--height",
        "3600",
        # "--preset",
        # "follow_pcb_editor",
        str(ctx.pcb_file)
        ]

    print("Running:", " ".join(cmd))

    subprocess.run(cmd, check=True)

    print("Generated image:", isometric_output_path)

    print("--------------------------------------------------\nLeft")
    cmd = [
        str(KICAD_CLI),
        "pcb",
        "render",
        "--output",
        str(left_output_path),
        "--quality",
        "high",
        "--floor",
        "--rotate='0,0,0'",
        "--side",
        "left",
        "--zoom",
        "1",
        "--width",
        "6400",
        "--height",
        "3600",
        # "--preset",
        # "follow_pcb_editor",
        str(ctx.pcb_file)
    ]

    print("Running:", " ".join(cmd))

    subprocess.run(cmd, check=True)

    print("Generated image:", left_output_path)

    print("--------------------------------------------------\nRight")
    cmd = [
        str(KICAD_CLI),
        "pcb",
        "render",
        "--output",
        str(right_output_path),
        "--quality",
        "high",
        "--floor",
        "--rotate='0,0,0'",
        "--side",
        "right",
        "--zoom",
        "1",
        "--width",
        "6400",
        "--height",
        "3600",
        # "--preset",
        # "follow_pcb_editor",
        str(ctx.pcb_file)
    ]

    print("Running:", " ".join(cmd))

    subprocess.run(cmd, check=True)

    print("Generated image:", right_output_path)

    print("--------------------------------------------------\nFront")
    cmd = [
        str(KICAD_CLI),
        "pcb",
        "render",
        "--output",
        str(front_output_path),
        "--quality",
        "high",
        "--floor",
        "--rotate='0,0,0'",
        "--side",
        "front",
        "--zoom",
        "1",
        "--width",
        "6400",
        "--height",
        "3600",
        # "--preset",
        # "follow_pcb_editor",
        str(ctx.pcb_file)
    ]

    print("Running:", " ".join(cmd))

    subprocess.run(cmd, check=True)

    print("Generated image:", front_output_path)

    print("--------------------------------------------------\nBack")
    cmd = [
        str(KICAD_CLI),
        "pcb",
        "render",
        "--output",
        str(back_output_path),
        "--quality",
        "high",
        "--floor",
        "--rotate='0,0,0'",
        "--side",
        "back",
        "--zoom",
        "1",
        "--width",
        "6400",
        "--height",
        "3600",
        # "--preset",
        # "follow_pcb_editor",
        str(ctx.pcb_file)
    ]

    print("Running:", " ".join(cmd))

    subprocess.run(cmd, check=True)

    print("Generated image:", back_output_path)


if __name__ == "__main__":
    local_ctx = load_context()
    build_step_package(local_ctx)
    # build_render(local_ctx)
