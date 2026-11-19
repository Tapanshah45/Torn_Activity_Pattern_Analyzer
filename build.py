"""
Standalone binary packaging script.

Builds two targets:
  TornSleepAnalyzer.exe      — GUI  (windowed, no console)
  TornSleepAnalyzerCLI.exe   — CLI  (console)

Run from the project root:
    python build.py [--cli-only | --gui-only]
"""

import platform
import sys
import PyInstaller.__main__


_COMMON_HIDDEN = [
    "--hidden-import=ijson.backends.python",
    "--hidden-import=pydantic",
    "--hidden-import=rich",
    "--hidden-import=customtkinter",
    "--hidden-import=PIL",
    "--hidden-import=PIL._tkinter_finder",
    "--hidden-import=src.models",
    "--hidden-import=src.streamer",
    "--hidden-import=src.classifier",
    "--hidden-import=src.stats",
    "--hidden-import=src.engine",
]


def build_gui():
    sys_name = platform.system()
    ext = ".exe" if sys_name == "Windows" else ""
    print(f"\n[GUI] Building TornSleepAnalyzer{ext} for {sys_name}…")

    args = [
        "src/gui.py",
        "--onefile",
        "--windowed",               # no console window
        "--name=TornSleepAnalyzer",
        "--clean",
        *_COMMON_HIDDEN,
        # Bundle the entire CustomTkinter data folder (themes, fonts)
        "--collect-data=customtkinter",
    ]

    PyInstaller.__main__.run(args)
    print(f"[GUI] ✓  dist/TornSleepAnalyzer{ext}")


def build_cli():
    sys_name = platform.system()
    ext = ".exe" if sys_name == "Windows" else ""
    print(f"\n[CLI] Building TornSleepAnalyzerCLI{ext} for {sys_name}…")

    args = [
        "src/cli.py",
        "--onefile",
        "--console",
        "--name=TornSleepAnalyzerCLI",
        "--clean",
        *_COMMON_HIDDEN,
    ]

    PyInstaller.__main__.run(args)
    print(f"[CLI] ✓  dist/TornSleepAnalyzerCLI{ext}")


if __name__ == "__main__":
    cli_only = "--cli-only" in sys.argv
    gui_only = "--gui-only" in sys.argv

    if cli_only:
        build_cli()
    elif gui_only:
        build_gui()
    else:
        build_gui()
        build_cli()

    sys_name = platform.system()
    ext = ".exe" if sys_name == "Windows" else ""
    print("\n[SUCCESS] All builds complete!")
    print(f"  GUI → dist/TornSleepAnalyzer{ext}")
    print(f"  CLI → dist/TornSleepAnalyzerCLI{ext}")
