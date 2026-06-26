import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Install dependencies for the local video skill.")
    parser.add_argument("--ocr", action="store_true", help="Also install OCR dependencies for hard-subtitle verification.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    requirements = root / "requirements.txt"
    requirements_ocr = root / "requirements-ocr.txt"

    if not requirements.exists():
        print(f"[ERROR] requirements.txt not found: {requirements}", file=sys.stderr)
        return 1

    print("[INFO] Installing Python dependencies...")
    print(f"[INFO] Python: {sys.executable}")
    print(f"[INFO] Requirements: {requirements}")

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements)],
        cwd=str(root),
    )
    if result.returncode != 0:
        print("[ERROR] Dependency installation failed.", file=sys.stderr)
        return result.returncode

    if args.ocr:
        if not requirements_ocr.exists():
            print(f"[ERROR] OCR requirements not found: {requirements_ocr}", file=sys.stderr)
            return 1
        print("[INFO] Installing OCR dependencies...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements_ocr)],
            cwd=str(root),
        )
        if result.returncode != 0:
            print("[ERROR] OCR dependency installation failed.", file=sys.stderr)
            return result.returncode

    print("[INFO] Running environment check...")
    check_command = [sys.executable, str(root / "scripts" / "check_env.py")]
    if args.ocr:
        check_command.append("--with-ocr")
    result = subprocess.run(
        check_command,
        cwd=str(root),
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
