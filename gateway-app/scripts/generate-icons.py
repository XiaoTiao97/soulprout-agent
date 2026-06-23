"""Generate Tauri app icons from the Soulprout logo."""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path


def run_tauri_icon(app_dir: Path, source: Path) -> None:
    source_arg = str(source)

    if platform.system() == "Windows":
        # Python subprocess cannot resolve `npx` on Windows without shell/cmd.
        npx = shutil.which("npx.cmd") or shutil.which("npx")
        if npx:
            subprocess.check_call([npx, "tauri", "icon", source_arg], cwd=app_dir)
            return
        subprocess.check_call(
            f'npx tauri icon "{source_arg}"',
            cwd=app_dir,
            shell=True,
        )
        return

    npx = shutil.which("npx")
    if not npx:
        raise FileNotFoundError("npx not found in PATH")
    subprocess.check_call([npx, "tauri", "icon", source_arg], cwd=app_dir)


def main() -> None:
    app_dir = Path(__file__).resolve().parent.parent
    project_root = app_dir.parent
    source = project_root / "web" / "src" / "assets" / "images" / "soulprout_logo.png"

    if not source.exists():
        print(f"[FAIL] Logo not found: {source}", file=sys.stderr)
        sys.exit(1)

    run_tauri_icon(app_dir, source)
    print(f"icons generated from {source}")


if __name__ == "__main__":
    main()
