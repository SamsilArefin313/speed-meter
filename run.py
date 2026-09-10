"""IDE-friendly launcher for the Vehicle Speed Monitor.

Run this file directly. It prepares a local virtual environment when necessary
and then starts the desktop application.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import venv


PROJECT_DIR = Path(__file__).resolve().parent
VENV_DIR = PROJECT_DIR / ".venv"
REQUIREMENTS = PROJECT_DIR / "requirements.txt"
REQUIRED_IMPORTS = ("cv2", "PIL", "pygame", "torch", "torchvision", "ultralytics")


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def dependencies_available(python: Path | str) -> bool:
    check = "; ".join(f"import {module}" for module in REQUIRED_IMPORTS)
    result = subprocess.run(
        [str(python), "-c", check],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def prepare_environment() -> Path:
    python = venv_python()
    if not python.exists():
        print(f"Creating Python environment at {VENV_DIR} ...", flush=True)
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)

    if not dependencies_available(python):
        print("Installing application dependencies (the first run may take a while) ...", flush=True)
        subprocess.run(
            [str(python), "-m", "pip", "install", "--upgrade", "pip"],
            check=True,
        )
        subprocess.run(
            [str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)],
            check=True,
        )
    return python


def main() -> None:
    os.chdir(PROJECT_DIR)
    try:
        python = prepare_environment()
        subprocess.run([str(python), str(PROJECT_DIR / "app.py"), *sys.argv[1:]], check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Unable to start the application (exit code {exc.returncode}).") from exc
    except OSError as exc:
        raise SystemExit(f"Unable to prepare the Python environment: {exc}") from exc


if __name__ == "__main__":
    main()
