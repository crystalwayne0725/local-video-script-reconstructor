import argparse
import os
import struct
import subprocess
import sys
from pathlib import Path


APP_STATE_DIR_NAME = "LocalVideoScriptReconstructor"
DEFAULT_PIP_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"


def run_command(command, cwd):
    print("[CMD] " + " ".join(str(part) for part in command))
    return subprocess.run(command, cwd=str(cwd), check=False).returncode


def state_dir():
    base_dir = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or str(Path.home())
    return Path(base_dir) / APP_STATE_DIR_NAME


def validate_bootstrap_python():
    if sys.version_info < (3, 9):
        print("[ERROR] Python 3.9 or newer is required.", file=sys.stderr)
        return False
    if struct.calcsize("P") * 8 != 64:
        print("[ERROR] 64-bit Python is required for the bundled media/ML wheels.", file=sys.stderr)
        return False
    return True


def validate_runtime_python(python_executable):
    result = subprocess.run(
        [
            str(python_executable),
            "-c",
            "import struct, sys; raise SystemExit(0 if sys.version_info >= (3, 9) and struct.calcsize('P') * 8 == 64 else 1)",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0:
        return True
    print(f"[ERROR] Runtime Python is not supported: {python_executable}", file=sys.stderr)
    print("[HINT] Use 64-bit Python 3.9 or newer. Delete a stale venv if this path is outdated.", file=sys.stderr)
    return False


def venv_python_path(venv_dir):
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def same_executable(left, right):
    try:
        return Path(left).resolve() == Path(right).resolve()
    except OSError:
        return os.path.abspath(str(left)).lower() == os.path.abspath(str(right)).lower()


def ensure_virtualenv(root, args):
    if args.no_venv:
        print("[INFO] Using the current Python environment because --no-venv was provided.")
        return Path(sys.executable)

    venv_dir = Path(os.path.expandvars(args.venv_dir)).expanduser() if args.venv_dir else state_dir() / "venv"
    venv_dir = venv_dir.resolve()
    python_path = venv_python_path(venv_dir)

    if python_path.exists():
        print(f"[INFO] Reusing skill virtual environment: {venv_dir}")
        return python_path if validate_runtime_python(python_path) else None

    print(f"[INFO] Creating skill virtual environment: {venv_dir}")
    result = run_command([sys.executable, "-m", "venv", str(venv_dir)], root)
    if result != 0 or not python_path.exists():
        print("[ERROR] Could not create the skill virtual environment.", file=sys.stderr)
        print(
            "[HINT] Install a standard 64-bit Python with the venv module, or rerun "
            "with --no-venv if you intentionally want to install into the current Python.",
            file=sys.stderr,
        )
        return None

    return python_path if validate_runtime_python(python_path) else None


def ensure_pip(root, python_executable):
    result = subprocess.run(
        [str(python_executable), "-m", "pip", "--version"],
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0:
        return True

    print("[WARN] pip is not available for this Python. Trying ensurepip...")
    result = subprocess.run(
        [str(python_executable), "-m", "ensurepip", "--upgrade"],
        cwd=str(root),
        check=False,
    )
    if result.returncode != 0:
        print("[ERROR] Could not enable pip for this Python.", file=sys.stderr)
        print("[HINT] Reinstall Python with pip enabled, or install pip manually.", file=sys.stderr)
        return False
    return True


def effective_pip_index_url(args):
    return args.pip_index_url or os.environ.get("PIP_INDEX_URL") or DEFAULT_PIP_INDEX_URL


def append_pip_network_options(command, args):
    index_url = effective_pip_index_url(args)
    if index_url:
        command.extend(["--index-url", index_url])
    if args.pip_extra_index_url:
        command.extend(["--extra-index-url", args.pip_extra_index_url])
    if args.pip_timeout:
        command.extend(["--timeout", str(args.pip_timeout)])
    if args.pip_retries is not None:
        command.extend(["--retries", str(args.pip_retries)])
    return command


def build_pip_install_command(python_executable, requirements, args):
    command = [str(python_executable), "-m", "pip", "install", "-r", str(requirements)]
    return append_pip_network_options(command, args)


def install_requirements(root, python_executable, requirements, args, label):
    print(f"[INFO] Installing {label} dependencies...")
    print(f"[INFO] Python: {python_executable}")
    print(f"[INFO] Requirements: {requirements}")
    index_url = effective_pip_index_url(args)
    if args.pip_index_url:
        print(f"[INFO] pip index URL from --pip-index-url: {index_url}")
    elif os.environ.get("PIP_INDEX_URL"):
        print(f"[INFO] pip index URL from PIP_INDEX_URL: {index_url}")
    else:
        print(f"[INFO] pip index URL defaulting to China-friendly mirror: {index_url}")

    result = run_command(build_pip_install_command(python_executable, requirements, args), root)
    if result != 0:
        print(f"[ERROR] {label.capitalize()} dependency installation failed.", file=sys.stderr)
        print(
            "[HINT] If the network is restricted, set PIP_INDEX_URL or pass "
            "--pip-index-url to use an accessible Python package mirror.",
            file=sys.stderr,
        )
    return result


def main():
    parser = argparse.ArgumentParser(description="Install dependencies for the local video skill.")
    parser.add_argument("--ocr", action="store_true", help="Also install OCR dependencies for hard-subtitle verification.")
    parser.add_argument("--no-venv", action="store_true", help="Install into the current Python instead of the per-user skill virtual environment.")
    parser.add_argument("--venv-dir", help="Custom virtual environment directory. Defaults to the per-user skill state directory.")
    parser.add_argument("--upgrade-pip", action="store_true", help="Upgrade pip, setuptools, and wheel before installing dependencies.")
    parser.add_argument(
        "--pip-index-url",
        help="Custom Python package index URL for restricted networks. Default: PIP_INDEX_URL or https://pypi.tuna.tsinghua.edu.cn/simple.",
    )
    parser.add_argument("--pip-extra-index-url", help="Additional Python package index URL.")
    parser.add_argument("--pip-timeout", type=int, default=120, help="pip network timeout in seconds. Default: 120.")
    parser.add_argument("--pip-retries", type=int, default=3, help="pip network retry count. Default: 3.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    requirements = root / "requirements.txt"
    requirements_ocr = root / "requirements-ocr.txt"

    if not requirements.exists():
        print(f"[ERROR] requirements.txt not found: {requirements}", file=sys.stderr)
        return 1

    if not validate_bootstrap_python():
        return 1

    python_executable = ensure_virtualenv(root, args)
    if not python_executable:
        return 1

    if same_executable(python_executable, sys.executable):
        print(f"[INFO] Runtime Python: {python_executable}")
    else:
        print(f"[INFO] Bootstrap Python: {sys.executable}")
        print(f"[INFO] Runtime Python: {python_executable}")
        print("[INFO] Batch runners will reuse this virtual environment after setup.")

    if not ensure_pip(root, python_executable):
        return 1

    if args.upgrade_pip:
        command = [str(python_executable), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"]
        result = run_command(append_pip_network_options(command, args), root)
        if result != 0:
            print("[ERROR] pip upgrade failed.", file=sys.stderr)
            return result

    result = install_requirements(root, python_executable, requirements, args, "runtime")
    if result != 0:
        return result

    if args.ocr:
        if not requirements_ocr.exists():
            print(f"[ERROR] OCR requirements not found: {requirements_ocr}", file=sys.stderr)
            return 1
        result = install_requirements(root, python_executable, requirements_ocr, args, "OCR")
        if result != 0:
            return result

    print("[INFO] Running environment check...")
    check_command = [str(python_executable), str(root / "scripts" / "check_env.py")]
    if args.ocr:
        check_command.append("--with-ocr")
    result = subprocess.run(
        check_command,
        cwd=str(root),
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
