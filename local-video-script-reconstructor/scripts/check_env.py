import argparse
import importlib.metadata as importlib_metadata
import importlib.util
import os
import platform
import subprocess
import sys
from pathlib import Path


REQUIRED_PACKAGES = {
    "av": ("av", ">=11.0.0,<18.0.0"),
    "faster_whisper": ("faster-whisper", ">=1.0.0,<2.0.0"),
    "PIL": ("Pillow", ">=10.0.0,<13.0.0"),
}
OCR_PACKAGES = {
    "numpy": ("numpy", ">=1.24.0,<3.0.0"),
    "PIL": ("Pillow", ">=10.0.0,<13.0.0"),
    "rapidocr_onnxruntime": ("rapidocr-onnxruntime", ">=1.2.3,<1.3.0"),
}
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"
DEFAULT_PIP_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
APP_STATE_DIR_NAME = "LocalVideoScriptReconstructor"


def ok(message):
    print(f"[OK] {message}")


def warn(message):
    print(f"[WARN] {message}")


def fail(message):
    print(f"[ERROR] {message}")


def state_dir():
    base_dir = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or str(Path.home())
    return Path(base_dir) / APP_STATE_DIR_NAME


def check_python():
    version = sys.version_info
    print(f"[INFO] Python: {sys.version.split()[0]}")
    print(f"[INFO] Python executable: {sys.executable}")
    if version < (3, 9):
        fail("Python 3.9 or newer is required.")
        return False
    if version < (3, 10):
        warn("Python 3.10 or newer is recommended for current media/ML wheels.")
    if version >= (3, 13):
        warn("If pip cannot find compatible media/ML wheels, install 64-bit Python 3.10-3.12 and rerun setup.")
    ok("Python version is supported.")
    return True


def check_platform():
    system = platform.system() or "unknown"
    machine = platform.machine() or "unknown"
    print(f"[INFO] Platform: {system} {machine}")
    if os.name != "nt":
        warn("Windows batch runners are the supported first-run path for this skill.")
    return True


def check_python_architecture():
    architecture = platform.architecture()[0] or "unknown"
    if "64" not in architecture:
        fail(f"64-bit Python is required for the bundled media/ML wheels. Detected: {architecture}")
        return False
    ok(f"Python architecture is supported: {architecture}")
    return True


def check_virtual_environment():
    base_prefix = getattr(sys, "base_prefix", sys.prefix)
    if sys.prefix != base_prefix:
        ok(f"Running inside a Python virtual environment: {sys.prefix}")
    else:
        warn("Not running inside a Python virtual environment. bootstrap_windows.py creates a per-user venv by default.")
    return True


def check_pip():
    result = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        ok(f"pip is available: {result.stdout.strip()}")
        return True
    fail("pip is not available for this Python.")
    print("       Fix: python -m ensurepip --upgrade")
    return False


def check_project_files():
    root = Path(__file__).resolve().parents[1]
    required_files = [
        root / "SKILL.md",
        root / "requirements.txt",
        root / "scripts" / "organize.py",
        root / "scripts" / "bootstrap_windows.py",
        root / "scripts" / "find_python_windows.bat",
    ]
    passed = True
    for path in required_files:
        if path.exists():
            ok(f"Required file found: {path.relative_to(root)}")
        else:
            fail(f"Required file missing: {path}")
            passed = False
    return passed


def load_packaging_helpers():
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version

        return SpecifierSet, Version
    except ImportError:
        try:
            from pip._vendor.packaging.specifiers import SpecifierSet
            from pip._vendor.packaging.version import Version

            return SpecifierSet, Version
        except ImportError:
            return None, None


def package_version_satisfies(distribution_name, version_spec):
    SpecifierSet, Version = load_packaging_helpers()
    if not SpecifierSet or not Version:
        warn("Cannot verify package versions because packaging is unavailable.")
        return True, "version not checked"

    try:
        installed_version = importlib_metadata.version(distribution_name)
    except importlib_metadata.PackageNotFoundError:
        return False, "not installed"

    try:
        satisfies = Version(installed_version) in SpecifierSet(version_spec)
    except Exception as error:
        return False, f"{installed_version} (could not parse version: {error})"
    return satisfies, installed_version


def check_state_directory():
    state_directory = state_dir()
    try:
        state_directory.mkdir(parents=True, exist_ok=True)
        probe = state_directory / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as error:
        fail(f"State directory is not writable: {state_directory} ({error})")
        return False
    ok(f"State directory is writable: {state_directory}")
    return True


def check_packages(package_map, required=True, install_hint=None):
    passed = True
    for module_name, package_info in package_map.items():
        package_name, version_spec = package_info
        if importlib.util.find_spec(module_name):
            version_ok, version_detail = package_version_satisfies(package_name, version_spec)
            if version_ok is True:
                ok(f"Python package installed: {package_name} {version_detail} ({version_spec})")
            else:
                passed = False
                if required:
                    fail(f"Python package version is not supported: {package_name} {version_detail}; required {version_spec}")
                else:
                    warn(f"Optional Python package version is not supported: {package_name} {version_detail}; required {version_spec}")
                fix = install_hint or "python scripts\\bootstrap_windows.py"
                print(f"       Fix: {fix}")
        else:
            passed = False
            if required:
                fail(f"Missing Python package: {package_name}")
            else:
                warn(f"Optional Python package missing: {package_name}")
            if install_hint:
                print(f"       Fix: {install_hint}")
            else:
                print("       Fix: python scripts\\bootstrap_windows.py")
    return passed


def check_python_package_download_index():
    index_url = os.environ.get("PIP_INDEX_URL") or DEFAULT_PIP_INDEX_URL
    if os.environ.get("PIP_INDEX_URL"):
        ok(f"PIP_INDEX_URL is set: {index_url}")
    else:
        ok(f"PIP_INDEX_URL is not set. bootstrap_windows.py will default to {DEFAULT_PIP_INDEX_URL}.")
    return True


def check_model_configuration():
    ok("Model API credentials are handled by Codex Desktop, not by this local script.")
    ok("No DEEPSEEK_API_KEY environment variable is required for this skill mode.")
    ok("System ffmpeg is not required; media decoding is handled by faster-whisper/PyAV.")
    return True


def check_model_download_endpoint():
    endpoint = os.environ.get("HF_ENDPOINT")
    if endpoint:
        ok(f"HF_ENDPOINT is set: {endpoint}")
    else:
        ok(f"HF_ENDPOINT is not set. organize.py will default to {DEFAULT_HF_ENDPOINT}.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Check local video skill dependencies.")
    parser.add_argument("--with-ocr", action="store_true", help="Also check OCR packages used by frame and hard-subtitle OCR.")
    args = parser.parse_args()

    print("Local Video Script Reconstructor environment check")
    print("=" * 56)

    checks = [
        check_python(),
        check_platform(),
        check_python_architecture(),
        check_virtual_environment(),
        check_pip(),
        check_project_files(),
        check_state_directory(),
        check_python_package_download_index(),
        check_packages(REQUIRED_PACKAGES, required=True),
        check_model_configuration(),
        check_model_download_endpoint(),
    ]
    if args.with_ocr:
        checks.append(
            check_packages(
                OCR_PACKAGES,
                required=True,
                install_hint="python scripts\\bootstrap_windows.py --ocr",
            )
        )

    print("=" * 56)
    if all(checks):
        ok("Environment is ready.")
        return 0

    fail("Environment is not ready. Fix the items above, then run this check again.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


