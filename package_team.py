"""Build a clean team ZIP and upload directory without changing source checkouts."""
from pathlib import Path
import os
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "team-release"
DEST = OUTPUT / "AmazingHand"
SKIP_DIRS = {".git", "__pycache__", ".pio", "build", "dist", "team-release",
             ".pytest_cache", ".mypy_cache", ".aws", ".codex", ".agents", ".vscode"}


def main():
    if DEST.exists():
        raise SystemExit("team-release/AmazingHand already exists; use a fresh output directory.")
    files = []
    for directory, dirs, names in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                         and not d.startswith('.venv') and d != 'venv')
        for name in sorted(names):
            source = Path(directory) / name
            relative = source.relative_to(ROOT)
            if (name.startswith('.env') or source.suffix in {'.pyc', '.pyo', '.log', '.zip'}
                    or relative.as_posix() == 'data/config.yaml'):
                continue
            if source.stat().st_size >= 100 * 1024 * 1024:
                raise SystemExit(f"File exceeds GitHub size limit: {relative}")
            files.append((source, relative))
    DEST.mkdir(parents=True)
    with zipfile.ZipFile(OUTPUT / 'AmazingHand-team.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for source, relative in files:
            target = DEST / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            archive.write(target, Path('AmazingHand') / relative)
    print(f"Packaged {len(files)} files in {OUTPUT / 'AmazingHand-team.zip'}")


if __name__ == '__main__':
    main()
