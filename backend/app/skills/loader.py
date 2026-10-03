from functools import lru_cache
from pathlib import Path


SKILLS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=16)
def load_skill(name: str) -> str:
    """Load one skill only when the router selects it."""
    path = SKILLS_DIR / name / "SKILL.md"

    if not path.is_file():
        raise ValueError(f"Unknown skill: {name}")

    return path.read_text(encoding="utf-8")
