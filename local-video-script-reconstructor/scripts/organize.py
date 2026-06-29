import os
import argparse
import re
import sys
from datetime import datetime
from math import gcd
from pathlib import Path

from subtitle_tools import (
    TextSegment,
    clean_subtitle_text,
    build_subtitle_comparison_report,
    build_subtitle_markdown,
    extract_text_from_ocr_result,
    find_sidecar_subtitle,
    format_time_range,
    format_timestamp,
    load_rapid_ocr,
    ocr_video_subtitles,
    parse_subtitle_file,
    upscale_image,
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


def transcribe_media(media_path, whisper_model, language=None, fallback_whisper_model=None, model_cache=None):
    model_attempts = [whisper_model]
    if fallback_whisper_model and fallback_whisper_model != whisper_model:
        model_attempts.append(fallback_whisper_model)

    model = None
    used_model = None
    fallback_used = False
    for index, model_name in enumerate(model_attempts):
        try:
            if model_cache is not None and model_name in model_cache:
                print(f"[INFO] Reusing loaded faster-whisper model: {model_name}")
                model = model_cache[model_name]
            else:
                model = load_whisper_model(model_name)
                if model_cache is not None:
                    model_cache[model_name] = model
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


def aspect_ratio_text(width, height):
    if not width or not height:
        return "N/A"
    divisor = gcd(int(width), int(height))
    if divisor <= 0:
        return "N/A"
    return f"{int(width / divisor)}:{int(height / divisor)}"


def read_video_metadata(video_path):
    try:
        import av
    except ImportError as error:
        raise RuntimeError("Missing dependency: av. Run scripts\\setup_windows.bat first.") from error

    metadata = {
        "source_video": os.path.abspath(video_path),
        "duration": 0.0,
        "resolution": "N/A",
  "fps": "N/A",
  "aspect_ratio": "N/A",
        "width": None,
        "height": None,
        "aspect_ratio": "N/A",
        "fps": "N/A",
        "frame_count": "N/A",
        "video_codec": "N/A",
        "audio_streams": 0,
    }

    with av.open(video_path) as container:
        video_stream = next((stream for stream in container.streams if stream.type == "video"), None)
        audio_streams = [stream for stream in container.streams if stream.type == "audio"]
        metadata["audio_streams"] = len(audio_streams)
        if video_stream is None:
            return metadata

        duration = media_duration_seconds(container, video_stream, av)
        width = int(video_stream.codec_context.width or 0)
        height = int(video_stream.codec_context.height or 0)
        fps = video_stream.average_rate

        metadata.update(
            {
                "duration": round(duration, 3) if duration else 0.0,
                "resolution": f"{width}x{height}" if width and height else "N/A",
                "width": width or None,
                "height": height or None,
                "aspect_ratio": aspect_ratio_text(width, height),
                "fps": round(float(fps), 3) if fps else "N/A",
                "frame_count": int(video_stream.frames) if video_stream.frames else "N/A",
                "video_codec": video_stream.codec_context.name or "N/A",
            }
        )
    return metadata


def build_video_metadata_markdown(video_metadata=None, video_metadata_error=None):
    lines = ["## Video Metadata", ""]
    if video_metadata:
        lines.extend(
            [
                f"- Duration: `{video_metadata.get('duration', 'N/A')}` seconds",
                f"- Resolution: `{video_metadata.get('resolution', 'N/A')}`",
                f"- Aspect ratio: `{video_metadata.get('aspect_ratio', 'N/A')}`",
                f"- FPS: `{video_metadata.get('fps', 'N/A')}`",
                f"- Frame count: `{video_metadata.get('frame_count', 'N/A')}`",
                f"- Video codec: `{video_metadata.get('video_codec', 'N/A')}`",
                f"- Audio streams: `{video_metadata.get('audio_streams', 'N/A')}`",
            ]
        )
    else:
        lines.append("- Metadata unavailable.")
    if video_metadata_error:
        lines.append(f"- Metadata warning: {video_metadata_error}")
    return "\n".join(lines) + "\n"


def video_output_root(video_path, output_dir=None, base_folder=None):
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    if output_dir and base_folder:
        relative_path = os.path.relpath(os.path.abspath(video_path), os.path.abspath(base_folder))
        relative_parent = os.path.dirname(relative_path)
        return os.path.join(os.path.abspath(output_dir), relative_parent, video_name)

    target_dir = os.path.abspath(output_dir) if output_dir else os.path.dirname(os.path.abspath(video_path))
    return os.path.join(target_dir, video_name)


def frame_sample_output_dir(video_path, output_dir=None, base_folder=None):
    return os.path.join(video_output_root(video_path, output_dir, base_folder), "frame_samples")


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
            samples.append({"index": target_index + 1, "time": frame_time, "path": output_path, "width": image.width, "height": image.height, "ocr_text": "", "ocr_confidence": "N/A"})
            target_index += 1
            if target_index >= len(targets):
                break

    if not samples:
        raise RuntimeError("No frames were decoded for visual frame sampling.")
    return samples


def markdown_image_path(path):
    return os.path.abspath(path).replace("\\", "/")


def ocr_confidence_label(score):
    if score == "N/A" or score is None:
        return "N/A"
    try:
        score = float(score)
    except (TypeError, ValueError):
        return "N/A"
    if score >= 0.75:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def extract_ocr_text_and_score(result, min_confidence):
    if isinstance(result, tuple):
        result = result[0]
    if not result:
        return "", "N/A"

    text_parts = []
    scores = []
    for item in result:
        if len(item) < 3:
            continue
        text = str(item[1]).strip()
        try:
            score = float(item[2])
        except (TypeError, ValueError):
            score = 0.0
        if text and score >= min_confidence:
            text_parts.append(text)
            scores.append(score)

    if not text_parts:
        return "", "N/A"
    avg_score = sum(scores) / len(scores) if scores else 0.0
    return clean_subtitle_text(" ".join(text_parts)), round(avg_score, 3)


def ocr_frame_samples(frame_samples, min_confidence=0.45):
    if not frame_samples:
        return frame_samples
    try:
        import numpy as np
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("Missing frame OCR dependencies. Install numpy, Pillow, and rapidocr-onnxruntime.") from error

    engine = load_rapid_ocr()
    for sample in frame_samples:
        image = Image.open(sample["path"]).convert("RGB")
        image = upscale_image(image)
        result = engine(np.array(image))
        text = extract_text_from_ocr_result(result, min_confidence)
        _, score = extract_ocr_text_and_score(result, min_confidence)
        sample["ocr_text"] = text
        sample["ocr_confidence"] = score
        sample["ocr_confidence_label"] = ocr_confidence_label(score)
    return frame_samples


def markdown_image_path(path):
    return os.path.abspath(path).replace("\\", "/")


def markdown_table_cell(value, limit=None):
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("|", "\\|")
    if limit and len(text) > limit:
        text = text[: max(0, limit - 3)] + "..."
    return text or "N/A"


def build_visual_frame_samples_markdown(frame_samples=None, frame_sample_error=None, frame_ocr_error=None):
    if frame_samples:
        lines = [
            "## Visual Frame Samples",
            "",
            "Use these sampled frames to describe visible products, people, scenes, subtitles, shot type, camera movement, and on-screen selling points. Prefer direct visual observations over transcript-only inference.",
            "",
            "| # | Time | File | OCR Text | OCR Confidence | Preview |",
            "|---|------|------|----------|----------------|---------|",
        ]
        for sample in frame_samples:
            image_path = markdown_image_path(sample["path"])
            timestamp = format_timestamp(sample["time"])
            ocr_text = markdown_table_cell(sample.get("ocr_text"), limit=60)
            ocr_confidence = sample.get("ocr_confidence_label") or sample.get("ocr_confidence") or "N/A"
            lines.append(
                f"| {sample['index']} | {timestamp} | `{image_path}` | {ocr_text} | {ocr_confidence} | ![frame {sample['index']} at {timestamp}]({image_path}) |"
            )
        if frame_ocr_error:
            lines.extend(["", f"Frame OCR warning: {frame_ocr_error}"])
        return "\n".join(lines) + "\n"

    if frame_sample_error:
        return f"## Visual Frame Samples\n\nFrame sampling failed: {frame_sample_error}\n"

    return "## Visual Frame Samples\n\nNo visual frame samples were generated.\n"


def nearest_frame_sample(frame_samples, start, end):
    if not frame_samples:
        return None, "N/A", "transcript", "low"
    midpoint = (float(start) + float(end)) / 2.0
    nearest = min(frame_samples, key=lambda sample: abs(float(sample["time"]) - midpoint))
    distance = abs(float(nearest["time"]) - midpoint)
    if float(start) <= float(nearest["time"]) <= float(end):
        confidence = "high"
    elif distance <= 2.0:
        confidence = "medium"
    else:
        confidence = "low"
    sources = ["transcript", "frame"]
    if nearest.get("ocr_text"):
        sources.append("frame_ocr")
    return nearest, round(distance, 3), "+".join(sources), confidence


def build_segment_evidence_markdown(speech_segments, frame_samples=None):
    lines = [
        "## Segment Evidence Map",
        "",
        "Use this table to bind transcript segments to nearby visual evidence. Fill report-generator segment fields from both speech and frame evidence, and keep confidence conservative when the nearest frame is far from the segment.",
        "",
        "| # | Time | Speech | Nearest Frame | OCR Text | Evidence Source | Confidence |",
        "|---|------|--------|---------------|----------|-----------------|------------|",
    ]
    for index, segment in enumerate(speech_segments, start=1):
        nearest, distance, source, confidence = nearest_frame_sample(frame_samples, segment.start, segment.end)
        if nearest:
            frame_ref = f"frame {nearest['index']} @ {format_timestamp(nearest['time'])} (distance {distance}s)"
            ocr_text = markdown_table_cell(nearest.get("ocr_text"), limit=50)
        else:
            frame_ref = "N/A"
            ocr_text = "N/A"
        speech = markdown_table_cell(segment.text, limit=60)
        lines.append(
            f"| {index} | {format_time_range(segment)} | {speech} | {frame_ref} | {ocr_text} | {source} | {confidence} |"
        )
    return "\n".join(lines) + "\n"


def build_transcript_markdown(video_path, speech_segments, transcription_metadata, frame_samples=None, frame_sample_error=None, frame_ocr_error=None, video_metadata=None, video_metadata_error=None):
    if speech_segments:
        text = " ".join(segment.text.strip() for segment in speech_segments if segment.text.strip()).strip()
        timestamped_lines = "\n".join(
            f"- [{format_time_range(segment)}] {segment.text}" for segment in speech_segments
        )
    else:
        text = transcription_metadata.get(
            "empty_transcript_note",
            "No speech transcript was generated. Check whether the video contains clear speech.",
        )
        timestamped_lines = "- No speech segments were produced."
    source = os.path.abspath(video_path)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    quality_warning = transcription_metadata.get("quality_warning")
    quality_line = f"- Quality warning: {quality_warning}\n" if quality_warning else ""
    video_metadata_section = build_video_metadata_markdown(video_metadata, video_metadata_error)
    visual_samples_section = build_visual_frame_samples_markdown(frame_samples, frame_sample_error, frame_ocr_error)
    segment_evidence_section = build_segment_evidence_markdown(speech_segments, frame_samples)
    return f"""# Video Transcript

- Source video: `{source}`
- Generated at: {generated_at}
- Requested Whisper model: `{transcription_metadata.get("requested_model", "")}`
- Used Whisper model: `{transcription_metadata.get("used_model", "")}`
- Fallback used: `{transcription_metadata.get("fallback_used", "no")}`
- Language: `{transcription_metadata.get("language", "auto")}`
- HF endpoint: `{transcription_metadata.get("hf_endpoint", "")}`
{quality_line}- Agent task: Inspect the video metadata, visual frame samples, frame OCR, and segment evidence map when available, then produce organized notes with the currently configured Codex Desktop model provider. Add report-generator intake only when the user explicitly asks for a video-analysis report or report input.

{video_metadata_section}
{visual_samples_section}
{segment_evidence_section}
## Required Final Output

Produce concise Markdown in the user's preferred language. Include:

1. Core summary
2. Key points
3. Detailed content outline with timestamps, visual observations, OCR findings, and evidence confidence when available
4. Reusable video script outline
5. Confirmed facts vs uncertain/inferred points when transcription quality is limited
6. Editing, title, or publishing suggestions when useful

Optional report output, only when the user explicitly asks for a video-analysis report or report-generator input:

1. Add a `## Report Generator Intake` section to the organized notes using `references/report-generator-intake.md` from the local-video-script-reconstructor skill.
2. Generate the report with `scripts\\generate_report_from_notes.bat "<organized_notes.md>"` from the skill folder.
3. Mention both the organized notes path and generated report path.

## Transcript

{text}

## Timestamped Segments

{timestamped_lines}
"""


def default_output_path(video_path):
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(video_output_root(video_path), f"{video_name}_转写稿.md")


def derived_output_path(video_path, suffix, output_dir=None, base_folder=None):
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(video_output_root(video_path, output_dir, base_folder), f"{video_name}_{suffix}.md")


def output_path_for_video(video_path, output_dir=None, base_folder=None):
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(video_output_root(video_path, output_dir, base_folder), f"{video_name}_转写稿.md")


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
    model_cache=None,
    output_dir=None,
    base_folder=None,
    frame_sample_count=DEFAULT_FRAME_SAMPLE_COUNT,
    frame_ocr=True,
):
    print(f"\n[VIDEO] {video_path}")
    extension = os.path.splitext(video_path)[1].lower()
    if extension not in SUPPORTED_VIDEO_EXTENSIONS:
        raise ValueError(f"Unsupported video format: {extension}")

    video_metadata = {}
    video_metadata_error = None
    try:
        video_metadata = read_video_metadata(video_path)
    except Exception as error:
        video_metadata_error = str(error)
        print(f"[WARN] Video metadata extraction failed: {video_metadata_error}")

    if video_metadata.get("audio_streams") == 0:
        print("[WARN] No audio stream detected. Skipping speech transcription and continuing with visual evidence.")
        speech_segments = []
        transcription_metadata = {
            "requested_model": whisper_model,
            "used_model": "not run",
            "fallback_model": fallback_whisper_model or "",
            "fallback_used": "no",
            "language": language or "auto",
            "hf_endpoint": os.environ.get("HF_ENDPOINT", ""),
            "quality_warning": "No audio stream was detected, so the transcript and organized notes are based on visual frame samples and OCR only.",
            "empty_transcript_note": "No speech transcript was generated because the video does not contain a detectable audio stream.",
        }
    else:
        speech_segments, transcription_metadata = transcribe_media(
            video_path,
            whisper_model,
            language,
            fallback_whisper_model=fallback_whisper_model,
            model_cache=model_cache,
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

    frame_ocr_error = None
    if frame_samples and frame_ocr:
        print("[PROGRESS] Running OCR on visual frame sample(s)...")
        try:
            frame_samples = ocr_frame_samples(frame_samples)
            print("[SUCCESS] Visual frame OCR completed.")
        except Exception as error:
            frame_ocr_error = str(error)
            print(f"[WARN] Visual frame OCR failed: {frame_ocr_error}")

    transcript_markdown = build_transcript_markdown(
        video_path,
        speech_segments,
        transcription_metadata,
        frame_samples=frame_samples,
        frame_sample_error=frame_sample_error,
        frame_ocr_error=frame_ocr_error,
        video_metadata=video_metadata,
        video_metadata_error=video_metadata_error,
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
        if not speech_segments:
            subtitle_markdown = (
                subtitle_markdown.rstrip()
                + "\n\n## 语音对比\n\n无法做语音对比：语音转写结果为空或视频没有可检测音频。\n"
            )
        write_markdown_file(subtitle_output, subtitle_markdown)
        generated_files.append(subtitle_output)
        print(f"[SUCCESS] Subtitle Markdown saved to: {subtitle_output}")

        if not speech_segments:
            print("[WARN] Speech transcript is empty. Subtitle comparison report was skipped.")
            return generated_files

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
    parser.add_argument("--no-frame-ocr", action="store_true", help="Disable OCR on representative visual frame samples.")
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
            frame_ocr=not args.no_frame_ocr,
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
    model_cache = {}

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
                    model_cache=model_cache,
                    output_dir=args.output_dir,
                    base_folder=args.folder if args.output_dir else None,
                    frame_sample_count=args.frame_samples,
                    frame_ocr=not args.no_frame_ocr,
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





