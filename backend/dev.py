from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"


def venv_python() -> Path:
    """Return the Python executable inside the project virtual environment."""
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"

    return VENV / "bin" / "python"


def ensure_venv() -> Path:
    """
    Create the local virtual environment when it does not exist.

    We intentionally launch all later commands through the venv Python path
    instead of relying on shell activation. This prevents global pip/uvicorn
    from being used by accident.
    """
    python = venv_python()

    if not python.exists():
        print(f"[setup] Creating virtual environment at {VENV}")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])

    return python


def dependencies_available(python: Path) -> bool:
    """Check that the packages required to start the backend are installed."""
    result = subprocess.run(
        [
            str(python),
            "-c",
            "import fastapi, uvicorn, langchain, langgraph, langchain_openai",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def ensure_dependencies(python: Path) -> None:
    """Install dependencies into the same interpreter that will run Uvicorn."""
    if dependencies_available(python):
        return

    print("[setup] Installing backend dependencies into .venv")
    subprocess.check_call(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "-r",
            str(REQUIREMENTS),
        ],
        cwd=ROOT,
    )


def ensure_env_file() -> None:
    """Create a local .env from the example without overwriting an existing one."""
    if not ENV_FILE.exists() and ENV_EXAMPLE.exists():
        shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
        print("[setup] Created .env from .env.example")
        print("[setup] Add your OPENAI_API_KEY before using model-backed routes.")


def main() -> None:
    python = ensure_venv()
    ensure_dependencies(python)
    ensure_env_file()

    print(f"[dev] Python: {python}")
    print("[dev] Backend: http://localhost:8000")

    # Use "python -m uvicorn" with the venv Python explicitly.
    # This avoids accidentally executing a globally installed uvicorn binary.
    subprocess.call(
        [
            str(python),
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--port",
            "8000",
        ],
        cwd=ROOT,
    )


if __name__ == "__main__":
    main()
