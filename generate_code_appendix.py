
from pathlib import Path
import os
import re

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "documentation"

FW = ROOT / "firmware" / "Multi-Rail Isolated Power Supply Monitor"
IOC = ROOT / "epics-ioc"

OUTPUT = DOC / "TeX_files" / "Source-Code-Listings.tex"

CODE_EXTS = {".c", ".cc", ".cpp", ".h", ".hpp", ".ino"}
IOC_EXTS = {".db", ".dbd", ".substitutions", ".template", ".proto"}


def escape_tex(text):
    chars = {
        "\\": r"\textbackslash{}",
        "_": r"\_",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(chars.get(c, c) for c in text)


def listing(path, caption):
    relative = Path(os.path.relpath(path, DOC)).as_posix()

    label = "lst:" + re.sub(
        r"[^a-z0-9]+", "-",
        path.relative_to(ROOT).as_posix().lower()
    ).strip("-")

    language = (
        "language=C++,"
        if path.suffix.lower() in CODE_EXTS
        else ""
    )

    return (
        f"\\lstinputlisting[{language}"
        f"caption={{{escape_tex(caption)}}},"
        f"label={{{label}}}]"
        f"{{\\detokenize{{{relative}}}}}"
    )


lines = [
    "% Automatically generated source code listings",
    "% Regenerate when source files are added or removed.",
    "",
]

count = 0

# Arduino firmware: source and include
for directory, heading in [
    ("src", "Firmware Source Files"),
    ("include", "Firmware Header Files"),
]:
    folder = FW / directory

    if not folder.is_dir():
        raise FileNotFoundError(folder)

    files = sorted(
        (p for p in folder.rglob("*")
         if p.is_file() and p.suffix.lower() in CODE_EXTS),
        key=lambda p: (p.name != "main.cpp", str(p))
    )

    lines.append(f"\\subsection{{{heading}}}")
    lines.append("")

    for path in files:
        caption = "Firmware: " + path.relative_to(FW).as_posix()
        lines.append(listing(path, caption))
        lines.append("")
        count += 1


# EPICS IOC: startup and database/configuration files
if not IOC.is_dir():
    raise FileNotFoundError(IOC)

ioc_files = sorted(
    p for p in IOC.rglob("*")
    if p.is_file()
    and (
        p.name == "st.cmd"
        or p.suffix.lower() in IOC_EXTS
    )
    and not any(
        part.startswith("O.")
        for part in p.relative_to(IOC).parts
    )
)

lines.append("\\subsection{EPICS IOC}")
lines.append("")

for path in ioc_files:
    caption = "EPICS IOC: " + path.relative_to(IOC).as_posix()
    lines.append(listing(path, caption))
    lines.append("")
    count += 1


OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text("\n".join(lines), encoding="utf-8")

print(f"Generated {count} source listings: {OUTPUT}")
