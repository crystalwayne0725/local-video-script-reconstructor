"""Generate a video-analysis report from organized notes.

This bridge keeps the local-video workflow from loading the report-generator
skill. It calls the sibling report-generator script through the Markdown intake
contract.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def default_report_script() -> Path:
    skill_root = Path(__file__).resolve().parents[1]
    return skill_root.parent / "report-generator" / "scripts" / "generate_report.py"


def default_output_path(notes_path: Path) -> Path:
    stem = notes_path.stem
    if stem.endswith("_整理稿"):
        stem = stem[: -len("_整理稿")]
    return notes_path.with_name(f"{stem}_视频分析报告.md")


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
        "--report-script",
        default=str(default_report_script()),
        help="Path to report-generator/scripts/generate_report.py.",
    )
    args = parser.parse_args(argv)

    notes_path = Path(args.organized_notes).expanduser().resolve()
    report_script = Path(args.report_script).expanduser().resolve()
    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else default_output_path(notes_path)
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

    command = [
        sys.executable,
        str(report_script),
        str(notes_path),
        "--output",
        str(output_path),
    ]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
