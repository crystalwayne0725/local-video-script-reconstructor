"""Generate a video-analysis report from organized notes.

This bridge keeps the local-video workflow from loading the report-generator
skill directly. It calls the sibling report-generator script through the
Markdown intake contract and can optionally post-process the Excel workbook.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ORGANIZED_NOTES_SUFFIX = "_\u6574\u7406\u7a3f"
MARKDOWN_REPORT_SUFFIX = "_\u89c6\u9891\u5206\u6790\u62a5\u544a.md"
EXCEL_REPORT_SUFFIX = "_\u5185\u5bb9\u7cbe\u62c6\u8868.xlsx"
DEFAULT_STRIPPED_SHEET_NAME = "\u5185\u5bb9\u7cbe\u62c6\u8868"


def default_report_script() -> Path:
    skill_root = Path(__file__).resolve().parents[1]
    return skill_root.parent / "report-generator" / "scripts" / "generate_report.py"


def default_strip_script() -> Path:
    return Path(__file__).resolve().with_name("remove_excel_sheet.py")


def _stem_without_notes_suffix(notes_path: Path) -> str:
    stem = notes_path.stem
    if stem.endswith(ORGANIZED_NOTES_SUFFIX):
        stem = stem[: -len(ORGANIZED_NOTES_SUFFIX)]
    return stem


def default_output_path(notes_path: Path) -> Path:
    stem = _stem_without_notes_suffix(notes_path)
    return notes_path.with_name(f"{stem}{MARKDOWN_REPORT_SUFFIX}")


def default_excel_output_path(notes_path: Path) -> Path:
    stem = _stem_without_notes_suffix(notes_path)
    return notes_path.with_name(f"{stem}{EXCEL_REPORT_SUFFIX}")


def run_command(command: list[str]) -> int:
    return subprocess.run(command, check=False).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a video-analysis report from organized Markdown notes."
    )
    parser.add_argument("organized_notes", help="Organized Markdown with Report Generator Intake.")
    parser.add_argument(
        "-o",
        "--output",
        help="Output Markdown report path. Defaults beside the organized notes.",
    )
    parser.add_argument(
        "--excel-output",
        help=(
            "Optional Excel workbook path. When provided, the bridge removes the "
            "problematic breakdown worksheet by default."
        ),
    )
    parser.add_argument(
        "--keep-breakdown-sheet",
        action="store_true",
        help="Keep the Excel worksheet named 内容精拆表 instead of removing it.",
    )
    parser.add_argument(
        "--report-script",
        default=str(default_report_script()),
        help="Path to report-generator/scripts/generate_report.py.",
    )
    parser.add_argument(
        "--strip-script",
        default=str(default_strip_script()),
        help="Path to the helper that removes a named worksheet from an .xlsx file.",
    )
    args = parser.parse_args(argv)

    notes_path = Path(args.organized_notes).expanduser().resolve()
    report_script = Path(args.report_script).expanduser().resolve()
    strip_script = Path(args.strip_script).expanduser().resolve()
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else default_output_path(notes_path)
    )
    excel_output_path = (
        Path(args.excel_output).expanduser().resolve()
        if args.excel_output
        else None
    )

    if not notes_path.is_file():
        print(f"[ERROR] Organized notes not found: {notes_path}", file=sys.stderr)
        return 2
    if not report_script.is_file():
        print(f"[ERROR] Report generator script not found: {report_script}", file=sys.stderr)
        print(
            "[HINT] Install or enable the report-generator skill, or pass --report-script.",
            file=sys.stderr,
        )
        return 2
    if excel_output_path and not args.keep_breakdown_sheet and not strip_script.is_file():
        print(f"[ERROR] Excel strip helper not found: {strip_script}", file=sys.stderr)
        print(
            "[HINT] Restore scripts/remove_excel_sheet.py or pass --keep-breakdown-sheet.",
            file=sys.stderr,
        )
        return 2

    command = [
        sys.executable,
        str(report_script),
        str(notes_path),
        "--output",
        str(output_path),
    ]
    if excel_output_path:
        command.extend(["--excel-output", str(excel_output_path)])

    return_code = run_command(command)
    if return_code != 0 or not excel_output_path or args.keep_breakdown_sheet:
        return return_code

    strip_command = [
        sys.executable,
        str(strip_script),
        str(excel_output_path),
        "--sheet-name",
        DEFAULT_STRIPPED_SHEET_NAME,
    ]
    return run_command(strip_command)


if __name__ == "__main__":
    raise SystemExit(main())
