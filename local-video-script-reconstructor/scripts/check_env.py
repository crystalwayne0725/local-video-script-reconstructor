import importlib.util
import argparse
import os
import sys


REQUIRED_PACKAGES = {
    "av": "av",
    "faster_whisper": "faster-whisper",
}
OCR_PACKAGES = {
    "numpy": "numpy",
    "PIL": "Pillow",
    "rapidocr_onnxruntime": "rapidocr-onnxruntime",
}
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"


def ok(message):
    print(f"[OK] {message}")


def warn(message):
    print(f"[WARN] {message}")


def fail(message):
    print(f"[ERROR] {message}")


def check_python():
    version = sys.version_info
    print(f"[INFO] Python: {sys.version.split()[0]}")
    if version < (3, 9):
        fail("Python 3.9 or newer is required.")
        return False
    ok("Python version is supported.")
    return True


def check_packages(package_map, required=True, install_hint=None):
    passed = True
    for module_name, package_name in package_map.items():
        if importlib.util.find_spec(module_name):
            ok(f"Python package installed: {package_name}")
        else:
            passed = False
            if required:
                fail(f"Missing Python package: {package_name}")
            else:
                warn(f"Optional Python package missing: {package_name}")
            if install_hint:
                print(f"       Fix: {install_hint}")
            else:
                print(f"       Fix: python -m pip install {package_name}")
    return passed


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
    parser.add_argument("--with-ocr", action="store_true", help="Require optional OCR packages for hard-subtitle recognition.")
    args = parser.parse_args()

    print("Local Video Script Reconstructor environment check")
    print("=" * 56)

    checks = [
        check_python(),
        check_packages(REQUIRED_PACKAGES, required=True),
        check_model_configuration(),
        check_model_download_endpoint(),
    ]
    ocr_check = check_packages(
        OCR_PACKAGES,
        required=args.with_ocr,
        install_hint="python scripts\\bootstrap_windows.py --ocr",
    )
    if args.with_ocr:
        checks.append(ocr_check)

    print("=" * 56)
    if all(checks):
        ok("Environment is ready.")
        return 0

    fail("Environment is not ready. Fix the items above, then run this check again.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
