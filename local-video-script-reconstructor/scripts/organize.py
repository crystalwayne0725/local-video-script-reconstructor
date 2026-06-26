import os
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from subtitle_tools import (
    TextSegment,
    build_subtitle_comparison_report,
    build_subtitle_markdown,
    find_sidecar_subtitle,
    format_time_range,
    format_timestamp,
    ocr_video_subtitles,
    parse_subtitle_file,
)

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"}
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"
APP_STATE_DIR_NAME = "LocalVideoScriptReconstructor"
DEFAULT_FRAME_SAMPLE_COUNT = 8


def configure_hf_endpoint(hf_endpoint=None):
    endpoint = hf_endpoint or os.environ.get("HF_ENDPOINT") or DEFAULT_HF_ENDPOINT
    os.environ["HF_ENDPOINT"] = endpoint.rstrip("/")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    print(f"[INFO] Model download endpoint: {os.environ['HF_ENDPOINT']}")


def app_state_dir():
    base_dir = os.environ.get("LOCALAPPDATA") or os.path.join(str(Path.home()), ".local", "share")
    return Path(base_dir) / APP_STATE_DIR_NAME


def model_uses_hf_cache(whisper_model):
    expanded = os.path.expandvars(os.path.expanduser(str(whisper_model)))
    if os.path.isdir(expanded):
        return False
    if os.path.isabs(expanded) or expanded.startswith(".") or "\\" in expanded:
        return False
    return True


def model_ready_marker(whisper_model):
    if not model_uses_hf_cache(whisper_model):
        return None
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(whisper_model)).strip("._-")
    if not safe_name:
        safe_name = "model"
    return app_state_dir() / "model-cache-state" / f"{safe_name[:120]}.ready"


def marker_exists(marker):
    if not marker:
        return False
    try:
        return marker.exists()
    except OSError as error:
        print(f"[WARN] Could not read local model cache marker: {error}")
        return False


def write_model_ready_marker(whisper_model):
    marker = model_ready_marker(whisper_model)
    if not marker:
        return
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            "\n".join(
                [
                    f"model={whisper_model}",
                    f"endpoint={os.environ.get('HF_ENDPOINT', '')}",
                    f"updated_at={datetime.now().isoformat(timespec='seconds')}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        print(f"[WARN] Could not write local model cache marker: {error}")


def clear_model_ready_marker(whisper_model):
    marker = model_ready_marker(whisper_model)
    if not marker:
        return
    try:
        if marker.exists():
            marker.unlink()
    except OSError as error:
        print(f"[WARN] Could not clear local model cache marker: {error}")


def restore_hf_offline(original_value):
    if original_value is None:
        os.environ.pop("HF_HUB_OFFLINE", None)
    else:
        os.environ["HF_HUB_OFFLINE"] = original_value


def env_value_is_truthy(value):
    if value is None:
        return False
    return str(value).strip().lower() not in {"", "0", "false", "no", "off", "none"}


def model_error_message(whisper_model, error):
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
    return f"""Failed to load or download the faster-whisper model.

Model: {whisper_model}
Endpoint: {endpoint}

Most likely cause: the first-run model download timed out.
Recommended fixes:
1. Retry with a smaller test model:
   python scripts\\organize.py --video "your_video.mp4" --whisper-model tiny
2. For China network environments, keep using the mirror endpoint:
   PowerShell: $env:HF_ENDPOINT="https://hf-mirror.com"
   CMD: set HF_ENDPOINT=https://hf-mirror.com
3. If your company has an internal model cache, pass it with:
   --hf-endpoint "<mirror_url>"
4. If you already have a local faster-whisper model folder, pass that folder path as --whisper-model.

Original error: {error}
"""


def load_whisper_model(whisper_model):
    print(f"[PROGRESS] Loading faster-whisper model: {whisper_model}")
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError(
            "Missing dependency: faster-whisper. Run scripts\\setup_windows.bat first."
        ) from error

    marker = model_ready_marker(whisper_model)
    original_offline = os.environ.get("HF_HUB_OFFLINE")
    has_marker = marker_exists(marker)

    offline_requested = env_value_is_truthy(original_offline)

    if has_marker and not offline_requested:
        print("[INFO] Cached model marker found. Loading from local cache without remote checks.")
        os.environ["HF_HUB_OFFLINE"] = "1"
        try:
            model = WhisperModel(whisper_model, device="cpu", compute_type="int8")
            write_model_ready_marker(whisper_model)
            return model
        except Exception as cache_error:
            print(f"[WARN] Cached model load failed: {cache_error}")
            print("[INFO] Retrying with the configured model endpoint.")
            clear_model_ready_marker(whisper_model)
        finally:
            restore_hf_offline(original_offline)
    else:
        if has_marker:
            print("[INFO] Cached model marker found. Using the current HF_HUB_OFFLINE setting.")
        else:
            print("[INFO] First successful load will create a local cache marker.")
        print("[INFO] First run may download model files and can take several minutes.")

    try:
        model = WhisperModel(whisper_model, device="cpu", compute_type="int8")
        write_model_ready_marker(whisper_model)
        return model
    except Exception as error:
        raise RuntimeError(model_error_message(whisper_model, error)) from error


def transcribe_media(media_path, whisper_model, language=None, fallback_whisper_model=None):
    model_attempts = [whisper_model]
    if fallback_whisper_model and fallback_whisper_model != whisper_model:
        model_attempts.append(fallback_whisper_model)

    model = None
    used_model = None
    fallback_used = False
    for index, model_name in enumerate(model_attempts):
        try:
            model = load_whisper_model(model_name)
            used_model = model_name
            fallback_used = index > 0
            break
        except RuntimeError:
            if index + 1 >= len(model_attempts):
                raise
            next_model = model_attempts[index + 1]
            print(f"[WARN] Model '{model_name}' failed to load. Trying fallback model '{next_model}'.")

    print("[PROGRESS] Transcribing audio locally...")

    transcribe_options = {"beam_size": 5}
    if language:
        transcribe_options["language"] = language

    raw_segments, _ = model.transcribe(media_path, **transcribe_options)
    speech_segments = []
    for segment in raw_segments:
        text = segment.text.strip()
        if text:
            speech_segments.append(TextSegment(float(segment.start), float(segment.end), text, "speech"))
        print(".", end="", flush=True)
    if speech_segments:
        print()
    metadata = {
        "requested_model": whisper_model,
        "used_model": used_model,
        "fallback_model": fallback_whisper_model or "",
        "fallback_used": "yes" if fallback_used else "no",
        "language": language or "auto",
        "hf_endpoint": os.environ.get("HF_ENDPOINT", ""),
        "quality_warning": (
            "Fallback Whisper model was used. Review product names, ingredient names, and claims before publishing."
            if fallback_used
            else ""
        ),
    }
    return speech_segments, metadata


def frame_sample_output_dir(video_path, output_dir=None, base_folder=None):
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    if output_dir and base_folder:
        relative_path = os.path.relpath(os.path.abspath(video_path), os.path.abspath(base_folder))
        relative_stem = os.path.splitext(relative_path)[0]
        return os.path.join(os.path.abspath(output_dir), f"{relative_stem}_frame_samples")

    target_dir = os.path.abspath(output_dir) if output_dir else os.path.dirname(os.path.abspath(video_path))
    return os.path.join(target_dir, f"{video_name}_frame_samples")


def media_duration_seconds(container, video_stream, av_module):
    if container.duration:
        return float(container.duration / av_module.time_base)
    if video_stream.duration and video_stream.time_base:
        return float(video_stream.duration * video_stream.time_base)
    return 0.0


def frame_sample_filename(index, seconds):
    safe_time = format_timestamp(seconds).replace(":", "-")
    return f"frame_{index:03d}_{safe_time}.jpg"


def extract_frame_samples(video_path, sample_count, output_dir=None, base_folder=None):
    sample_count = int(sample_count or 0)
    if sample_count <= 0:
        return []

    try:
        import av
    except ImportError as error:
        raise RuntimeError("Missing dependency: av. Run scripts\\setup_windows.bat first.") from error

    frame_dir = frame_sample_output_dir(video_path, output_dir, base_folder)
    os.makedirs(frame_dir, exist_ok=True)

    samples = []
    with av.open(video_path) as container:
        video_stream = next((stream for stream in container.streams if stream.type == "video"), None)
        if video_stream is None:
            raise RuntimeError("No video stream found for visual frame sampling.")

        duration = media_duration_seconds(container, video_stream, av)
        if duration <= 0:
            raise RuntimeError("Could not determine video duration for visual frame sampling.")

        targets = [((index + 0.5) * duration / sample_count) for index in range(sample_count)]
        target_index = 0

        for frame in container.decode(video_stream):
            if frame.pts is None:
                continue
            frame_time = float(frame.pts * frame.time_base)
            if frame_time + 0.001 < targets[target_index]:
                continue

            image = frame.to_image().convert("RGB")
            image.thumbnail((960, 960))
            output_path = os.path.abspath(
                os.path.join(frame_dir, frame_sample_filename(target_index + 1, frame_time))
            )
            image.save(output_path, quality=88)
            samples.append({"index": target_index + 1, "time": frame_time, "path": output_path})
            target_index += 1
            if target_index >= len(targets):
                break

    if not samples:
        raise RuntimeError("No frames were decoded for visual frame sampling.")
    return samples


def markdown_image_path(path):
    return os.path.abspath(path).replace("\\", "/")


def build_visual_frame_samples_markdown(frame_samples=None, frame_sample_error=None):
    if frame_samples:
        lines = [
            "## Visual Frame Samples",
            "",
            "Use these sampled frames to describe visible products, people, scenes, subtitles, shot type, camera movement, and on-screen selling points. Prefer direct visual observations over transcript-only inference.",
            "",
            "| # | Time | File | Preview |",
            "|---|------|------|---------|",
        ]
        for sample in frame_samples:
            image_path = markdown_image_path(sample["path"])
            timestamp = format_timestamp(sample["time"])
            lines.append(
                f"| {sample['index']} | {timestamp} | `{image_path}` | ![frame {sample['index']} at {timestamp}]({image_path}) |"
            )
        return "\n".join(lines) + "\n"

    if frame_sample_error:
        return f"## Visual Frame Samples\n\nFrame sampling failed: {frame_sample_error}\n"

    return "## Visual Frame Samples\n\nNo visual frame samples were generated.\n"

def build_transcript_markdown(video_path, speech_segments, transcription_metadata, frame_samples=None, frame_sample_error=None):
    if not speech_segments:
        raise RuntimeError("Speech recognition returned no text. Check whether the video contains clear speech.")

    text = "".join(segment.text for segment in speech_segments).strip()
    source = os.path.abspath(video_path)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamped_lines = "\n".join(
        f"- [{format_time_range(segment)}] {segment.text}" for segment in speech_segments
    )
    quality_warning = transcription_metadata.get("quality_warning")
    quality_line = f"- Quality warning: {quality_warning}\n" if quality_warning else ""
    visual_samples_section = build_visual_frame_samples_markdown(frame_samples, frame_sample_error)
    return f"""# Video Transcript

- Source video: `{source}`
- Generated at: {generated_at}
- Requested Whisper model: `{transcription_metadata.get("requested_model", "")}`
- Used Whisper model: `{transcription_metadata.get("used_model", "")}`
- Fallback used: `{transcription_metadata.get("fallback_used", "no")}`
- Language: `{transcription_metadata.get("language", "auto")}`
- HF endpoint: `{transcription_metadata.get("hf_endpoint", "")}`
{quality_line}- Agent task: Inspect the visual frame samples when available, then produce organized notes plus report-generator intake JSON blocks with the currently configured Codex Desktop model provider.

{visual_samples_section}
## Required Final Output

Produce concise Markdown in the user's preferred language. Include:

1. Core summary
2. Key points
3. Detailed content outline with timestamps and visual observations from frame samples when available
4. Reusable video script outline
5. Confirmed facts vs uncertain/inferred points when transcription quality is limited
6. Editing, title, or publishing suggestions when useful
7. A section named exactly `## Report Generator Intake`

Inside `## Report Generator Intake`, include two fenced JSON blocks named exactly:

### breakdown_json
```json
{{
  "duration": 0.0,
  "segment_count": 0,
  "resolution": "N/A",
  "segments": [
    {{
      "segment_index": 1,
      "start_time": 0.0,
      "end_time": 0.0,
      "shot_type": "N/A or inferred description",
      "camera_movement": "N/A or inferred description",
      "function_tag": "hook / selling point / proof / CTA / transition / other",
      "visual_content": "Brief content description. Mark inferred visual details clearly."
    }}
  ],
  "bgm_analysis": {{
    "music_style": {{"primary": "N/A or inferred"}},
    "emotion": {{"primary": "N/A or inferred"}},
    "tempo": {{"bpm_estimate": "N/A", "pace": "N/A or inferred"}}
  }},
  "scene_analysis": {{
    "primary_scene": "N/A or inferred",
    "video_style": {{
      "overall": "N/A or inferred",
      "target_audience": []
    }},
    "platform_recommendations": [
      {{"platform": "platform name", "suitability": "high / medium / low", "reason": "short reason"}}
    ]
  }}
}}
```

### hook_analysis_json
```json
{{
  "overall_score": 0.0,
  "visual_impact": 0.0,
  "visual_comment": "Mention when visual details are inferred or unavailable.",
  "language_hook": 0.0,
  "language_comment": "",
  "emotion_trigger": 0.0,
  "emotion_comment": "",
  "information_density": 0.0,
  "info_comment": "",
  "rhythm_control": 0.0,
  "rhythm_comment": "",
  "hook_type": "",
  "strengths": [],
  "weaknesses": [],
  "suggestions": [],
  "retention_prediction": ""
}}
```

The JSON must be valid JSON with no comments or trailing commas. Build `segments` from the timestamped transcript below, convert timecodes to seconds, and use the visual frame samples above to fill shot type, camera movement, scene, and visual_content when possible. Mark unavailable details as `N/A` or inferred.

## Transcript

{text}

## Timestamped Segments

{timestamped_lines}
"""


def default_output_path(video_path):
    video_dir = os.path.dirname(os.path.abspath(video_path))
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(video_dir, f"{video_name}_转写稿.md")


def derived_output_path(video_path, suffix, output_dir=None, base_folder=None):
    if output_dir and base_folder:
        relative_path = os.path.relpath(os.path.abspath(video_path), os.path.abspath(base_folder))
        relative_stem = os.path.splitext(relative_path)[0]
        return os.path.join(os.path.abspath(output_dir), f"{relative_stem}_{suffix}.md")

    target_dir = os.path.abspath(output_dir) if output_dir else os.path.dirname(os.path.abspath(video_path))
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(target_dir, f"{video_name}_{suffix}.md")


def output_path_for_video(video_path, output_dir=None, base_folder=None):
    if not output_dir:
        return default_output_path(video_path)

    if base_folder:
        relative_path = os.path.relpath(os.path.abspath(video_path), os.path.abspath(base_folder))
        relative_stem = os.path.splitext(relative_path)[0]
        return os.path.join(os.path.abspath(output_dir), f"{relative_stem}_转写稿.md")

    video_name = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(os.path.abspath(output_dir), f"{video_name}_转写稿.md")


def write_markdown_file(output_file, content):
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    with open(output_file, "w", encoding="utf-8-sig") as f:
        f.write(content)


def load_subtitle_segments(video_path, subtitle_path=None, ocr_subtitles=False, subtitle_area="bottom", ocr_sample_interval=1.0):
    if subtitle_path and ocr_subtitles:
        raise ValueError("Use either --subtitle or --ocr-subtitles, not both.")

    if subtitle_path:
        print(f"[PROGRESS] Loading subtitle file: {subtitle_path}")
        return parse_subtitle_file(subtitle_path), os.path.abspath(subtitle_path)

    if ocr_subtitles:
        return (
            ocr_video_subtitles(video_path, sample_interval=ocr_sample_interval, area=subtitle_area),
            f"hard-subtitle OCR ({subtitle_area}, every {ocr_sample_interval:.2f}s)",
        )

    sidecar = find_sidecar_subtitle(video_path)
    if sidecar:
        print(f"[PROGRESS] Found sidecar subtitle: {sidecar}")
        return parse_subtitle_file(sidecar), os.path.abspath(sidecar)

    raise RuntimeError("No subtitle source found. Provide --subtitle or use --ocr-subtitles for burned-in subtitles.")


def iter_video_files(folder_path, recursive=False):
    root = Path(folder_path)
    pattern = "**/*" if recursive else "*"
    for path in sorted(root.glob(pattern)):
        if path.is_file() and path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS:
            yield str(path)


def process_video(
    video_path,
    output_file,
    whisper_model,
    language=None,
    check_subtitles=False,
    subtitle_path=None,
    ocr_subtitles=False,
    subtitle_area="bottom",
    ocr_sample_interval=1.0,
    subtitle_threshold=0.72,
    fallback_whisper_model=None,
    output_dir=None,
    base_folder=None,
    frame_sample_count=DEFAULT_FRAME_SAMPLE_COUNT,
):
    print(f"\n[VIDEO] {video_path}")
    extension = os.path.splitext(video_path)[1].lower()
    if extension not in SUPPORTED_VIDEO_EXTENSIONS:
        raise ValueError(f"Unsupported video format: {extension}")

    speech_segments, transcription_metadata = transcribe_media(
        video_path,
        whisper_model,
        language,
        fallback_whisper_model=fallback_whisper_model,
    )

    frame_samples = []
    frame_sample_error = None
    if frame_sample_count and int(frame_sample_count) > 0:
        print(f"[PROGRESS] Extracting {int(frame_sample_count)} visual frame sample(s)...")
        try:
            frame_samples = extract_frame_samples(
                video_path,
                int(frame_sample_count),
                output_dir=output_dir,
                base_folder=base_folder,
            )
            print(f"[SUCCESS] Visual frame samples saved to: {os.path.dirname(frame_samples[0]['path'])}")
        except Exception as error:
            frame_sample_error = str(error)
            print(f"[WARN] Visual frame sampling failed: {frame_sample_error}")

    transcript_markdown = build_transcript_markdown(
        video_path,
        speech_segments,
        transcription_metadata,
        frame_samples=frame_samples,
        frame_sample_error=frame_sample_error,
    )
    write_markdown_file(output_file, transcript_markdown)

    print(f"[SUCCESS] Markdown saved to: {output_file}")
    generated_files = [output_file]
    if frame_samples:
        generated_files.append(os.path.dirname(frame_samples[0]["path"]))

    if check_subtitles:
        subtitle_segments, subtitle_source = load_subtitle_segments(
            video_path,
            subtitle_path=subtitle_path,
            ocr_subtitles=ocr_subtitles,
            subtitle_area=subtitle_area,
            ocr_sample_interval=ocr_sample_interval,
        )
        subtitle_output = derived_output_path(video_path, "字幕识别稿", output_dir, base_folder)
        subtitle_markdown = build_subtitle_markdown(video_path, subtitle_segments, subtitle_source)
        write_markdown_file(subtitle_output, subtitle_markdown)
        generated_files.append(subtitle_output)
        print(f"[SUCCESS] Subtitle Markdown saved to: {subtitle_output}")

        report_output = derived_output_path(video_path, "字幕核对报告", output_dir, base_folder)
        report_markdown = build_subtitle_comparison_report(
            video_path,
            speech_segments,
            subtitle_segments,
            output_file,
            subtitle_source,
            similarity_threshold=subtitle_threshold,
        )
        write_markdown_file(report_output, report_markdown)
        generated_files.append(report_output)
        print(f"[SUCCESS] Subtitle comparison report saved to: {report_output}")

    return generated_files


def run():
    parser = argparse.ArgumentParser(description="Transcribe a local video, optionally verify subtitles, and generate Markdown outputs for Codex.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video", help="Single local video path.")
    source.add_argument("--folder", help="Folder containing local videos.")
    parser.add_argument("--recursive", action="store_true", help="Scan subfolders when using --folder.")
    parser.add_argument("--output", help="Markdown output path for --video only.")
    parser.add_argument("--output-dir", help="Output folder for generated transcript Markdown files.")
    parser.add_argument("--frame-samples", type=int, default=DEFAULT_FRAME_SAMPLE_COUNT, help="Number of representative visual frames to extract for report generation. Use 0 to disable. Default: 8.")
    parser.add_argument("--whisper-model", default="small", help="faster-whisper model name. Default: small.")
    parser.add_argument("--fallback-whisper-model", default="tiny", help="Fallback model if the primary model cannot load. Default: tiny.")
    parser.add_argument("--language", help="Optional speech language code, such as zh or en.")
    parser.add_argument("--check-subtitles", action="store_true", help="Generate subtitle recognition and two-way comparison reports.")
    parser.add_argument("--subtitle", help="External subtitle file path (.srt, .vtt, .ass, .ssa). For --video only.")
    parser.add_argument("--ocr-subtitles", action="store_true", help="Use OCR to recognize hard subtitles burned into the video frames.")
    parser.add_argument(
        "--subtitle-area",
        default="bottom",
        choices=["bottom", "lower-third", "full"],
        help="Video area used for hard-subtitle OCR. Default: bottom.",
    )
    parser.add_argument(
        "--ocr-sample-interval",
        type=float,
        default=1.0,
        help="Seconds between OCR samples when using --ocr-subtitles. Default: 1.0.",
    )
    parser.add_argument(
        "--subtitle-threshold",
        type=float,
        default=0.72,
        help="Text similarity threshold for subtitle mismatch reporting. Default: 0.72.",
    )
    parser.add_argument(
        "--hf-endpoint",
        help=f"Model download endpoint. Default: existing HF_ENDPOINT or {DEFAULT_HF_ENDPOINT}.",
    )
    args = parser.parse_args()
    configure_hf_endpoint(args.hf_endpoint)
    check_subtitles = args.check_subtitles or bool(args.subtitle) or args.ocr_subtitles

    if args.folder and args.subtitle:
        raise ValueError("--subtitle can only be used with --video. Folder mode can auto-discover sidecar subtitles or use --ocr-subtitles.")

    if args.video:
        if not os.path.exists(args.video):
            raise FileNotFoundError(f"Video file not found: {args.video}")
        output_file = args.output or output_path_for_video(args.video, args.output_dir)
        generated_files = process_video(
            args.video,
            output_file,
            args.whisper_model,
            args.language,
            check_subtitles=check_subtitles,
            subtitle_path=args.subtitle,
            ocr_subtitles=args.ocr_subtitles,
            subtitle_area=args.subtitle_area,
            ocr_sample_interval=args.ocr_sample_interval,
            subtitle_threshold=args.subtitle_threshold,
            fallback_whisper_model=args.fallback_whisper_model,
            output_dir=args.output_dir,
            frame_sample_count=args.frame_samples,
        )
        print("\n[GENERATED FILES]")
        for generated_file in generated_files:
            print(f"- {generated_file}")
        print("\nAsk Codex to read the generated Markdown and produce final notes or subtitle verification conclusions.")
        return

    if args.output:
        raise ValueError("--output can only be used with --video. Use --output-dir for folder mode.")

    if not os.path.isdir(args.folder):
        raise NotADirectoryError(f"Video folder not found: {args.folder}")

    videos = list(iter_video_files(args.folder, args.recursive))
    if not videos:
        raise RuntimeError("No supported video files found.")

    print(f"[BATCH] Found {len(videos)} video(s). Starting batch transcription.")
    success = []
    failures = []

    for video_path in videos:
        try:
            output_file = output_path_for_video(video_path, args.output_dir, args.folder if args.output_dir else None)
            success.append(
                process_video(
                    video_path,
                    output_file,
                    args.whisper_model,
                    args.language,
                    check_subtitles=check_subtitles,
                    ocr_subtitles=args.ocr_subtitles,
                    subtitle_area=args.subtitle_area,
                    ocr_sample_interval=args.ocr_sample_interval,
                    subtitle_threshold=args.subtitle_threshold,
                    fallback_whisper_model=args.fallback_whisper_model,
                    output_dir=args.output_dir,
                    base_folder=args.folder if args.output_dir else None,
                    frame_sample_count=args.frame_samples,
                )
            )
        except Exception as exc:
            failures.append((video_path, str(exc)))
            print(f"[ERROR] {video_path}: {exc}")

    print("\n[BATCH SUMMARY]")
    print(f"Success: {len(success)}")
    print(f"Failed: {len(failures)}")
    if failures:
        for video_path, error in failures:
            print(f"- {video_path}: {error}")
        raise SystemExit(1)

    print("Ask Codex to read the generated Markdown and produce final notes or subtitle verification conclusions.")


def main():
    try:
        run()
        return 0
    except KeyboardInterrupt:
        print("\n[ERROR] Cancelled by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())




