"""Common Files module for building release package documentation
for KiCAD Projects"""

from dataclasses import dataclass
from pathlib import Path
import shutil
import json
from zipfile import ZipFile, ZIP_DEFLATED
from pypdf import PdfWriter

# Set this to the path of the Kicad bin folder of the version of Kicad
# you wish to use.
KICAD_BIN_PATH = Path(r"C:\Program Files\KiCad\9.0\bin")
KICAD_CLI = KICAD_BIN_PATH / "kicad-cli.exe"


# ----------------------------------------------------------------------------
# If you're not using default filenames, you'll have to specify them here;
# defaults are assuming the root-level schematic sheet and the PCB filename
# match the project filename, e.g. if the project is "EVR.kicad_pro", if
# you have "EVR.kicad_sch" and "EVR.kicad_pcb", none of the
# below need to be changed.
#
# Do the same for the drawing borders, setting the format names.
# If the names are unchanged, They will resolve with the default settings.
#
# If they differ, change only the FALLBACK filename below.

SCHEMATIC_FILE_FALLBACK = None
SCHEMATIC_TITLEBLOCK_FALLBACK = None

PCB_FILE_FALLBACK = None
FAB_TITLEBLOCK_FALLBACK = None
ASSY_TITLEBLOCK_TOP_FALLBACK = None
ASSY_TITLEBLOCK_BOT_FALLBACK = None

@dataclass(frozen=True)
class KiCadVariables:
    """Text Variables pulled from within KiCad PROJECT Definition File"""
    drawing_number_prefix: str
    assy_suffix: str
    fab_suffix: str
    schema_suffix: str
    revision_num: str

    @classmethod
    def from_project_file(cls, project_file: Path) -> "KiCadVariables":
        """JSON File parser"""
        with open(project_file, encoding="utf-8") as f:
            data = json.load(f)

        text_variables = data.get("text_variables", {})

        required_keys = [
            "DRAWING_NUMBER-PREFIX",
            "DRAWING-ASSY_SUFFIX",
            "DRAWING-FAB_SUFFIX",
            "DRAWING-SCHEMA_SUFFIX",
            "REVISION_NUM",
        ]

        missing_keys = [
            key for key in required_keys
            if key not in text_variables
        ]

        if missing_keys:
            raise KeyError(
                "Missing required KiCad text variable(s): "
                + ", ".join(missing_keys)
            )

        return cls(
            drawing_number_prefix=text_variables["DRAWING_NUMBER-PREFIX"],
            assy_suffix=text_variables["DRAWING-ASSY_SUFFIX"],
            fab_suffix=text_variables["DRAWING-FAB_SUFFIX"],
            schema_suffix=text_variables["DRAWING-SCHEMA_SUFFIX"],
            revision_num=text_variables["REVISION_NUM"],
        )


@dataclass(frozen=True)
class KiCadProjectContext:
    """Project Context"""
    project_file: Path
    project_root: Path
    variables: KiCadVariables

    schematic_file: Path
    schematic_titleblock: Path
    pcb_file: Path
    fab_titleblock: Path
    assy_titleblock_top: Path
    assy_titleblock_bot: Path

    output_root: Path
    schematic_output_dir: Path
    fab_output_dir: Path
    fab_output_dir_temp: Path
    assy_output_dir: Path
    assy_output_dir_temp: Path
    step_output_dir: Path


def load_context() -> KiCadProjectContext:
    """Load the Project Context"""
    project_file = find_kicad_project_file()
    project_root = project_file.parent
    project_stem = project_file.stem

    variables = KiCadVariables.from_project_file(project_file)

    schematic_file = resolve_project_file(
        project_root=project_root,
        default_filename=f"{project_stem}.kicad_sch",
        fallback_filename=SCHEMATIC_FILE_FALLBACK,
    )

    schematic_titleblock = resolve_project_file(
        project_root=project_root,
        default_filename="KiCAD_PLDF_Schematic.kicad_wks",
        fallback_filename=SCHEMATIC_TITLEBLOCK_FALLBACK,
    )

    pcb_file = resolve_project_file(
        project_root=project_root,
        default_filename=f"{project_stem}.kicad_pcb",
        fallback_filename=PCB_FILE_FALLBACK,
    )

    fab_titleblock = resolve_project_file(
        project_root=project_root,
        default_filename="KiCAD_PLDF_FAB_DRAWING.kicad_wks",
        fallback_filename=FAB_TITLEBLOCK_FALLBACK,
    )

    assy_titleblock_top = resolve_project_file(
        project_root=project_root,
        default_filename="KiCAD_PLDF_ASSY_DRAWING_TOP.kicad_wks",
        fallback_filename=ASSY_TITLEBLOCK_TOP_FALLBACK,
    )

    assy_titleblock_bot = resolve_project_file(
        project_root=project_root,
        default_filename="KiCAD_PLDF_ASSY_DRAWING_BOT.kicad_wks",
        fallback_filename=ASSY_TITLEBLOCK_BOT_FALLBACK,
    )

    output_root = project_root / "Outputs"

    schematic_output_dir = output_root / "SCH"
    fab_output_dir = output_root / "FAB"
    fab_output_dir_temp = fab_output_dir / "TEMP"
    assy_output_dir = output_root / "ASSY"
    assy_output_dir_temp = assy_output_dir / "TEMP"
    step_output_dir = output_root / "STEP"

    return KiCadProjectContext(
        project_file=project_file,
        project_root=project_root,
        variables=variables,

        schematic_file=schematic_file,
        schematic_titleblock=schematic_titleblock,
        pcb_file=pcb_file,
        fab_titleblock=fab_titleblock,
        assy_titleblock_top=assy_titleblock_top,
        assy_titleblock_bot=assy_titleblock_bot,

        output_root=output_root,
        schematic_output_dir=schematic_output_dir,
        fab_output_dir=fab_output_dir,
        fab_output_dir_temp=fab_output_dir_temp,
        assy_output_dir=assy_output_dir,
        assy_output_dir_temp=assy_output_dir_temp,
        step_output_dir=step_output_dir,
    )


def resolve_project_file(
    project_root: Path,
    default_filename: str,
    fallback_filename: str | None = None,
) -> Path:
    """
    Checks for a default filename in the KiCad project root first.
    If it is not found, checks an optional fallback filename.

    Raises FileNotFoundError if neither file exists.
    """
    default_path = project_root / default_filename

    if default_path.is_file():
        return default_path

    if fallback_filename is not None:
        fallback_path = project_root / fallback_filename

        if fallback_path.is_file():
            return fallback_path

    raise FileNotFoundError(
        f"Could not find '{default_filename}'"
        + (f" or fallback '{fallback_filename}'" if fallback_filename else "")
        + f" in {project_root}"
    )


def find_file_upward(pattern: str, start: Path | None = None) -> Path:
    """
    Searches upward from start, or from this script folder, until it finds
    a file matching the given glob pattern.
    """
    here = start.resolve() if start is not None else Path(__file__).resolve()

    if here.is_file():
        here = here.parent

    for parent in [here, *here.parents]:
        matches = list(parent.glob(pattern))
        if matches:
            return matches[0]

    raise FileNotFoundError(
        f"No file matching '{pattern}' found in parent directories."
    )


def find_kicad_project_file() -> Path:
    """Search the directory tree for the KiCad Project file"""
    return find_file_upward("*.kicad_pro")


def cleanup_temp_dir(temp_dir: Path) -> None:
    """Delete TEMP directory, but do not stop the build if cleanup fails."""
    temp_dir = Path(temp_dir)

    if not temp_dir.exists():
        return

    try:
        shutil.rmtree(temp_dir)
        print("Deleted temp folder:", temp_dir)

    except PermissionError as exc:
        print(f"WARNING: Could not delete temp folder: {temp_dir}")
        print(f"         {exc}")
        print("         Continuing build...")


def combine_pdfs(output_pdf: Path, input_pdfs: list[Path]) -> Path:
    """Combine multiple PDFs into one PDF using pypdf."""
    writer = PdfWriter()
    added_count = 0

    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    try:
        for input_pdf in input_pdfs:
            if not input_pdf.is_file():
                print(f"WARNING: PDF not found, skipping: {input_pdf}")
                continue

            print(f"Adding PDF: {input_pdf}")
            writer.append(str(input_pdf))
            added_count += 1

        if added_count == 0:
            raise FileNotFoundError(
                f"No input PDFs were found. Output PDF was not created: {output_pdf}"
            )

        if output_pdf.exists():
            output_pdf.unlink()

        with output_pdf.open("wb") as f:
            writer.write(f)

    finally:
        writer.close()

    print(f"Combined {added_count} PDF file(s) into: {output_pdf}")
    return output_pdf


def zip_directory(source_dir: Path, zip_file: Path) -> None:
    """Zip all the Fab files"""
    source_dir = source_dir.resolve()

    with ZipFile(zip_file, "w", compression=ZIP_DEFLATED) as zipf:
        for file_path in source_dir.rglob("*"):
            if not file_path.is_file():
                continue

            # Do not include zip files
            if file_path.suffix.lower() == ".zip":
                continue

            # Also avoid including the output zip itself
            if file_path.resolve() == zip_file:
                continue

            arcname = file_path.relative_to(source_dir)
            zipf.write(file_path, arcname)
