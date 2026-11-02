from __future__ import annotations

import shutil
from pathlib import Path

from report_config import DATA_DIR, OUTPUT_DIR


def _relative(path: Path) -> str:
    return str(path.relative_to(DATA_DIR.parent))


def clear_runtime_cache() -> list[str]:
    removed: list[str] = []

    for path in sorted(DATA_DIR.glob("*.json")):
        path.unlink()
        removed.append(_relative(path))

    team_dump_dir = DATA_DIR / "linear_team_dumps"
    if team_dump_dir.exists():
        for path in sorted(team_dump_dir.rglob("*.json")):
            path.unlink()
            removed.append(_relative(path))
        for path in sorted(team_dump_dir.rglob("*"), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        team_dump_dir.mkdir(parents=True, exist_ok=True)

    if OUTPUT_DIR.exists():
        removed.extend(_relative(path) for path in sorted(OUTPUT_DIR.rglob("*")) if path.is_file())
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    return removed


def main() -> None:
    removed = clear_runtime_cache()
    print(f"Cleared {len(removed)} cached artifacts.")
    for path in removed:
        print(f"- {path}")


if __name__ == "__main__":
    main()
