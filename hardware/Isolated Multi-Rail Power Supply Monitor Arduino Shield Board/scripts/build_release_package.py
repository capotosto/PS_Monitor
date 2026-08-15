"""
build_release_package.py
Launcher script for building documentation packages from KiCAD.
Tested on KiCAD Ver 9, Windows.
"""
from common import load_context, KICAD_CLI
from build_schematic_package import build_schematic
from build_assembly_package import build_assembly
from build_fabrication_package import build_fab
from build_step_package import build_step_package


def get_build_options():
    """Launch a menu to choose what CAM jobs to run"""
    schematic = assembly = fabrication = step = False

    if KICAD_CLI.is_file():
        pass
    else:
        print("kicad-cli not found, check the KICAD_BIN_PATH variable in "
              "common.py, it needs to be set to the path of the kicad-cli"
              " executable for your workstation.")

    while True:
        print("\nSelect package(s) to build:")
        print("  1) Schematic")
        print("  2) Assembly")
        print("  3) Fabrication")
        print("  4) STEP")
        print("  5) All")
        print("  q) Quit")

        choice = input("\nChoice: ").strip().lower()

        try:
            if choice == "1":
                schematic = True
                break

            elif choice == "2":
                assembly = True
                break

            elif choice == "3":
                fabrication = True
                break
            elif choice == "4":
                step = True
                break
            elif choice == "5":
                schematic = assembly = fabrication = step = True
                break

            elif choice == "q":
                raise SystemExit(0)

            else:
                raise ValueError("Invalid selection")

        except ValueError as e:
            print(f"\nError: {e}")

    return schematic, assembly, fabrication, step


def main():
    """Main function"""
    schematic, assembly, fabrication, step = get_build_options()
    ctx = load_context()

    if schematic:
        build_schematic(ctx)
    if assembly:
        build_assembly(ctx)
    if fabrication:
        build_fab(ctx)
    if step:
        build_step_package(ctx)


if __name__ == "__main__":
    main()
