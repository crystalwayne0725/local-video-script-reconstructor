import os
import argparse
import re
import sys
from datetime import datetime
from math import ceil, gcd
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
DEFAULT_FRAME_SAMPLE_INTERVAL_SECONDS = 1.0
DEFAULT_SHOT_DETECTION_INTERVAL_SECONDS = 0.35
DEFAULT_SHOT_CHANGE_THRESHOLD = 0.32
DEFAULT_MIN_SHOT_SECONDS = 0.8
DEFAULT_LONG_SHOT_SAMPLE_SECONDS = 7.0


def configure_hf_endpoint(hf_endpoint=None):
    endpoint = hf_endpoint or os.environ.get("HF_ENDPOINT") or DEFAULT_HF_ENDPOINT
    os.environ["HF_ENDPOINT"] = endpoint.rstrip("/")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    print(f"[INFO] Model download endpoint: {os.environ['HF_ENDPOINT']}")


def app_state_dir():
    base_dir = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or str(Path.home())
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
   python scripts\\organize.py --video "<video_path>" --whisper-model tiny
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


def resolve_output_dir(output_dir=None, video_path=None, base_folder=None):
    if not output_dir:
        return None

    expanded = os.path.expandvars(os.path.expanduser(str(output_dir)))
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)

    if base_folder:
        anchor = os.path.abspath(base_folder)
    elif video_path:
        anchor = os.path.dirname(os.path.abspath(video_path))
    else:
        anchor = os.getcwd()
    return os.path.abspath(os.path.join(anchor, expanded))


def resolve_output_file(output_file=None, video_path=None):
    if not output_file:
        return None

    expanded = os.path.expandvars(os.path.expanduser(str(output_file)))
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)

    anchor = os.path.dirname(os.path.abspath(video_path)) if video_path else os.getcwd()
    return os.path.abspath(os.path.join(anchor, expanded))


def video_output_root(video_path, output_dir=None, base_folder=None):
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    resolved_output_dir = resolve_output_dir(output_dir, video_path, base_folder)
    if output_dir and base_folder:
        relative_path = os.path.relpath(os.path.abspath(video_path), os.path.abspath(base_folder))
        relative_parent = os.path.dirname(relative_path)
        return os.path.join(resolved_output_dir, relative_parent, video_name)

    target_dir = resolved_output_dir if resolved_output_dir else os.path.dirname(os.path.abspath(video_path))
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


def resolve_auto_frame_sample_count(duration_seconds):
    duration_seconds = float(duration_seconds or 0.0)
    if duration_seconds <= 0:
        return 1
    return max(1, int(ceil(duration_seconds / DEFAULT_FRAME_SAMPLE_INTERVAL_SECONDS)))


def build_frame_sample_targets(duration_seconds, sample_count=None):
    duration_seconds = float(duration_seconds or 0.0)
    if duration_seconds <= 0:
        raise RuntimeError("Could not determine video duration for visual frame sampling.")

    if sample_count is not None:
        sample_count = int(sample_count)
        if sample_count < 0:
            raise ValueError("--frame-samples must be 0 or a positive integer.")
        if sample_count == 0:
            return []
        return [((index + 0.5) * duration_seconds / sample_count) for index in range(sample_count)]

    sample_count = resolve_auto_frame_sample_count(duration_seconds)
    max_target = max(duration_seconds - 0.001, 0.0)
    return [
        min(max_target, (index + 0.5) * DEFAULT_FRAME_SAMPLE_INTERVAL_SECONDS)
        for index in range(sample_count)
    ]


def frame_image_signature(image, size=(24, 24)):
    small = image.convert("RGB").resize(size)
    signature = []
    for red, green, blue in small.getdata():
        signature.extend((red // 16, green // 16, blue // 16))
    return tuple(signature)


def image_difference_score(previous_signature, current_signature):
    if not previous_signature or not current_signature:
        return 0.0
    pair_count = min(len(previous_signature), len(current_signature))
    if pair_count <= 0:
        return 0.0
    total = sum(
        abs(int(previous_signature[index]) - int(current_signature[index]))
        for index in range(pair_count)
    )
    return total / float(pair_count * 15)


def image_sharpness_score(image):
    grayscale = image.convert("L").resize((64, 64))
    pixels = list(grayscale.getdata())
    width, height = grayscale.size
    if width < 2 or height < 2:
        return 0.0
    total = 0
    comparisons = 0
    for y in range(height - 1):
        row_offset = y * width
        next_row_offset = (y + 1) * width
        for x in range(width - 1):
            value = pixels[row_offset + x]
            total += abs(value - pixels[row_offset + x + 1])
            total += abs(value - pixels[next_row_offset + x])
            comparisons += 2
    return total / float(comparisons * 255) if comparisons else 0.0


def make_frame_candidate(frame_time, image):
    sample_image = image.copy()
    sample_image.thumbnail((960, 960))
    return {
        "time": float(frame_time),
        "image": sample_image,
        "width": sample_image.width,
        "height": sample_image.height,
        "sharpness": image_sharpness_score(sample_image),
    }


def start_detected_shot(shot_id, frame_time, image, change_score=0.0):
    candidate = make_frame_candidate(frame_time, image)
    return {
        "shot_id": shot_id,
        "start_time": float(frame_time),
        "end_time": float(frame_time),
        "change_score": float(change_score or 0.0),
        "source_times": [float(frame_time)],
        "representative": candidate,
    }


def maybe_update_shot_representative(shot, frame_time, image):
    candidate = make_frame_candidate(frame_time, image)
    representative = shot.get("representative")
    elapsed = float(frame_time) - float(shot.get("start_time", frame_time))
    if representative is None:
        shot["representative"] = candidate
        return
    current_score = float(representative.get("sharpness") or 0.0)
    candidate_score = float(candidate.get("sharpness") or 0.0)
    is_early_stable_frame = 0.25 <= elapsed <= 1.5
    is_much_clearer = candidate_score > current_score * 1.25
    if is_much_clearer or (is_early_stable_frame and candidate_score >= current_score * 0.9):
        shot["representative"] = candidate


def save_detected_shot_samples(shots, frame_dir, duration):
    samples = []
    for index, shot in enumerate(shots, start=1):
        representative = shot.get("representative")
        if not representative:
            continue

        start_time = float(shot.get("start_time", representative["time"]))
        end_time = float(shot.get("end_time", start_time))
        if duration and index == len(shots):
            end_time = max(end_time, float(duration))
        if end_time < start_time:
            end_time = start_time

        output_path = os.path.abspath(
            os.path.join(frame_dir, frame_sample_filename(index, representative["time"]))
        )
        representative["image"].save(output_path, quality=88)
        source_times = shot.get("source_times") or []
        samples.append(
            {
                "index": index,
                "time": representative["time"],
                "path": output_path,
                "width": representative["width"],
                "height": representative["height"],
                "ocr_text": "",
                "ocr_confidence": "N/A",
                "sample_mode": "shot",
                "shot_id": index,
                "shot_start_time": round(start_time, 3),
                "shot_end_time": round(end_time, 3),
                "shot_duration": round(max(0.0, end_time - start_time), 3),
                "shot_change_score": round(float(shot.get("change_score") or 0.0), 3),
                "source_frame_count": len(source_times),
                "merged_frame_count": max(0, len(source_times) - 1),
            }
        )
    return samples


def extract_shot_aware_frame_samples(
    video_path,
    output_dir=None,
    base_folder=None,
    detection_interval=DEFAULT_SHOT_DETECTION_INTERVAL_SECONDS,
    change_threshold=DEFAULT_SHOT_CHANGE_THRESHOLD,
    min_shot_seconds=DEFAULT_MIN_SHOT_SECONDS,
):
    try:
        import av
    except ImportError as error:
        raise RuntimeError("Missing dependency: av. Run scripts\\setup_windows.bat first.") from error

    frame_dir = frame_sample_output_dir(video_path, output_dir, base_folder)
    os.makedirs(frame_dir, exist_ok=True)

    shots = []
    current_shot = None
    previous_signature = None
    next_probe_time = 0.0

    with av.open(video_path) as container:
        video_stream = next((stream for stream in container.streams if stream.type == "video"), None)
        if video_stream is None:
            raise RuntimeError("No video stream found for visual frame sampling.")

        duration = media_duration_seconds(container, video_stream, av)
        if duration <= 0:
            raise RuntimeError("Could not determine video duration for visual frame sampling.")

        for frame in container.decode(video_stream):
            if frame.pts is None:
                continue
            frame_time = float(frame.pts * frame.time_base)
            if frame_time + 0.001 < next_probe_time:
                continue
            next_probe_time = frame_time + float(detection_interval)

            image = frame.to_image().convert("RGB")
            signature = frame_image_signature(image)
            difference = image_difference_score(previous_signature, signature)

            if current_shot is None:
                current_shot = start_detected_shot(1, frame_time, image, difference)
            else:
                shot_elapsed = frame_time - float(current_shot["start_time"])
                is_new_shot = (
                    difference >= float(change_threshold)
                    and shot_elapsed >= float(min_shot_seconds)
                )
                if is_new_shot:
                    current_shot["end_time"] = frame_time
                    shots.append(current_shot)
                    current_shot = start_detected_shot(len(shots) + 1, frame_time, image, difference)
                else:
                    current_shot["end_time"] = frame_time
                    current_shot.setdefault("source_times", []).append(frame_time)
                    maybe_update_shot_representative(current_shot, frame_time, image)

            previous_signature = signature

    if current_shot:
        shots.append(current_shot)

    samples = save_detected_shot_samples(shots, frame_dir, duration)
    if not samples:
        raise RuntimeError("No frames were decoded for visual frame sampling.")
    return samples


def extract_interval_frame_samples(video_path, sample_count, output_dir=None, base_folder=None):
    if sample_count is not None and int(sample_count) == 0:
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

        targets = build_frame_sample_targets(duration, sample_count)
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


def extract_frame_samples(video_path, sample_count, output_dir=None, base_folder=None, sample_mode="shot"):
    if sample_count is not None or sample_mode == "interval":
        return extract_interval_frame_samples(
            video_path,
            sample_count,
            output_dir=output_dir,
            base_folder=base_folder,
        )
    if sample_mode == "shot":
        return extract_shot_aware_frame_samples(
            video_path,
            output_dir=output_dir,
            base_folder=base_folder,
        )
    raise ValueError(f"Unsupported frame sample mode: {sample_mode}")


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


def portable_display_path(path, base_dir=None):
    if not path:
        return "N/A"

    path_text = str(path)
    expanded = os.path.expandvars(os.path.expanduser(path_text))
    if not os.path.isabs(expanded) and not os.path.exists(expanded):
        return path_text.replace("\\", "/")

    absolute_path = os.path.abspath(expanded)
    display_path = absolute_path
    if base_dir:
        try:
            display_path = os.path.relpath(absolute_path, os.path.abspath(base_dir))
        except ValueError:
            display_path = absolute_path
    return display_path.replace("\\", "/")


def markdown_image_path(path, base_dir=None):
    return portable_display_path(path, base_dir)


def markdown_table_cell(value, limit=None):
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("|", "\\|")
    if limit and len(text) > limit:
        text = text[: max(0, limit - 3)] + "..."
    return text or "N/A"


def has_shot_aware_samples(frame_samples):
    return any(sample.get("sample_mode") == "shot" or sample.get("shot_id") for sample in frame_samples or [])


def frame_sample_time_range(sample):
    start = sample.get("shot_start_time")
    end = sample.get("shot_end_time")
    if start is None and end is None:
        timestamp = format_timestamp(sample["time"])
        return timestamp, timestamp
    start_text = format_timestamp(float(start if start is not None else sample["time"]))
    end_text = format_timestamp(float(end if end is not None else sample["time"]))
    return start_text, end_text


def build_visual_frame_samples_markdown(frame_samples=None, frame_sample_error=None, frame_ocr_error=None, base_dir=None):
    if frame_samples:
        if has_shot_aware_samples(frame_samples):
            lines = [
                "## Visual Shot Samples",
                "",
                "Each row represents one detected shot and one representative frame. Repeated interval frames inside the same shot are merged so the report can show shot changes instead of duplicate stills.",
                "",
                "| Shot | Shot Range | Representative Time | File | OCR Text | OCR Confidence | Merged Frames | Preview |",
                "|------|------------|---------------------|------|----------|----------------|---------------|---------|",
            ]
            for sample in frame_samples:
                image_path = markdown_image_path(sample["path"], base_dir=base_dir)
                start_text, end_text = frame_sample_time_range(sample)
                timestamp = format_timestamp(sample["time"])
                ocr_text = markdown_table_cell(sample.get("ocr_text"), limit=60)
                ocr_confidence = sample.get("ocr_confidence_label") or sample.get("ocr_confidence") or "N/A"
                merged_count = sample.get("merged_frame_count", 0)
                lines.append(
                    f"| {sample.get('shot_id', sample['index'])} | {start_text}-{end_text} | {timestamp} | `{image_path}` | {ocr_text} | {ocr_confidence} | {merged_count} | ![shot {sample.get('shot_id', sample['index'])} at {timestamp}]({image_path}) |"
                )
            if frame_ocr_error:
                lines.extend(["", f"Frame OCR warning: {frame_ocr_error}"])
            return "\n".join(lines) + "\n"

        lines = [
            "## Visual Frame Samples",
            "",
            "Use these sampled frames to describe visible products, people, scenes, subtitles, shot type, camera movement, and on-screen selling points. Prefer direct visual observations over transcript-only inference.",
            "",
            "| # | Time | File | OCR Text | OCR Confidence | Preview |",
            "|---|------|------|----------|----------------|---------|",
        ]
        for sample in frame_samples:
            image_path = markdown_image_path(sample["path"], base_dir=base_dir)
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


def frame_sample_interval_seconds(sample):
    start = float(sample.get("shot_start_time", sample.get("time", 0.0)))
    end = float(sample.get("shot_end_time", sample.get("time", start)))
    if end < start:
        end = start
    return start, end


def interval_overlap_seconds(start_a, end_a, start_b, end_b):
    return max(0.0, min(float(end_a), float(end_b)) - max(float(start_a), float(start_b)))


def interval_distance_seconds(start_a, end_a, start_b, end_b):
    if interval_overlap_seconds(start_a, end_a, start_b, end_b) > 0:
        return 0.0
    return min(abs(float(start_a) - float(end_b)), abs(float(start_b) - float(end_a)))


def nearest_frame_sample(frame_samples, start, end):
    if not frame_samples:
        return None, "N/A", "transcript", "low"

    segment_start = float(start)
    segment_end = float(end)
    if segment_end < segment_start:
        segment_end = segment_start

    if has_shot_aware_samples(frame_samples):
        best_sample = None
        best_overlap = -1.0
        best_distance = None
        for sample in frame_samples:
            sample_start, sample_end = frame_sample_interval_seconds(sample)
            overlap = interval_overlap_seconds(segment_start, segment_end, sample_start, sample_end)
            distance = interval_distance_seconds(segment_start, segment_end, sample_start, sample_end)
            if overlap > best_overlap or (overlap == best_overlap and (best_distance is None or distance < best_distance)):
                best_sample = sample
                best_overlap = overlap
                best_distance = distance
        if best_sample:
            if best_overlap > 0:
                confidence = "high"
                distance = 0.0
            elif best_distance is not None and best_distance <= 2.0:
                confidence = "medium"
                distance = best_distance
            else:
                confidence = "low"
                distance = best_distance if best_distance is not None else "N/A"
            sources = ["transcript", "shot_frame"]
            if best_sample.get("ocr_text"):
                sources.append("frame_ocr")
            return best_sample, round(distance, 3) if isinstance(distance, float) else distance, "+".join(sources), confidence

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
        "Use this table to bind transcript segments to nearby visual evidence. Fill report-generator segment fields from both speech and shot/frame evidence, and keep confidence conservative when the nearest visual evidence is far from the segment.",
        "",
        "| # | Time | Speech | Nearest Shot/Frame | OCR Text | Evidence Source | Confidence |",
        "|---|------|--------|---------------|----------|-----------------|------------|",
    ]
    for index, segment in enumerate(speech_segments, start=1):
        nearest, distance, source, confidence = nearest_frame_sample(frame_samples, segment.start, segment.end)
        if nearest:
            if nearest.get("shot_id"):
                shot_start, shot_end = frame_sample_time_range(nearest)
                frame_ref = (
                    f"shot {nearest.get('shot_id')} {shot_start}-{shot_end}; "
                    f"rep frame {nearest['index']} @ {format_timestamp(nearest['time'])} "
                    f"(distance {distance}s)"
                )
            else:
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


def build_transcript_markdown(video_path, speech_segments, transcription_metadata, frame_samples=None, frame_sample_error=None, frame_ocr_error=None, video_metadata=None, video_metadata_error=None, output_base_dir=None):
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
    source = portable_display_path(video_path, base_dir=output_base_dir)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    quality_warning = transcription_metadata.get("quality_warning")
    quality_line = f"- Quality warning: {quality_warning}\n" if quality_warning else ""
    video_metadata_section = build_video_metadata_markdown(video_metadata, video_metadata_error)
    visual_samples_section = build_visual_frame_samples_markdown(
        frame_samples,
        frame_sample_error,
        frame_ocr_error,
        base_dir=output_base_dir,
    )
    segment_evidence_section = build_segment_evidence_markdown(speech_segments, frame_samples)
    return f"""# Video Transcript

- Source video: `{source}`
- Generated at: {generated_at}
- Requested Whisper model: `{transcription_metadata.get("requested_model", "")}`
- Used Whisper model: `{transcription_metadata.get("used_model", "")}`
- Fallback used: `{transcription_metadata.get("fallback_used", "no")}`
- Language: `{transcription_metadata.get("language", "auto")}`
- HF endpoint: `{transcription_metadata.get("hf_endpoint", "")}`
{quality_line}- Agent task: Inspect the video metadata, visual shot/frame samples, frame OCR, and segment evidence map when available, then produce organized notes with the currently configured Codex Desktop model provider. When visual shot samples are present, treat each detected shot as the primary report-generator segment and merge repeated frames inside the same shot. Add report-generator intake only when the user explicitly asks for a video-analysis report or report input. For report-ready notes, build the full intake in paced stages: evidence JSON first, then commerce structure and seven-step replication suggestions.

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
2. In `breakdown_json`, include report-facing segment fields (`script_text`, `script_method`, `visual_method`, `replication_note`), `commerce_script_structure`, and full `replication_suggestions` so report-generator can render the seven-step viral-replication section.
3. Generate the report with `scripts\\generate_report_from_notes.bat "<organized_notes.md>"` from the skill folder.
4. Mention both the organized notes path and generated report path.

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
    frame_sample_count=None,
    frame_sample_mode="shot",
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
    should_extract_frame_samples = frame_sample_count is None or int(frame_sample_count) > 0
    if should_extract_frame_samples:
        if frame_sample_count is None:
            duration_text = video_metadata.get("duration") or "unknown"
            if frame_sample_mode == "shot":
                print(
                    "[PROGRESS] Extracting visual frame sample(s) with shot-aware detection "
                    f"(video duration: {duration_text}s)..."
                )
            else:
                print(
                    "[PROGRESS] Extracting visual frame sample(s) automatically at 1 frame/second "
                    f"(video duration: {duration_text}s)..."
                )
        else:
            print(f"[PROGRESS] Extracting {int(frame_sample_count)} visual frame sample(s)...")
        try:
            frame_samples = extract_frame_samples(
                video_path,
                frame_sample_count,
                output_dir=output_dir,
                base_folder=base_folder,
                sample_mode=frame_sample_mode,
            )
            print(
                f"[SUCCESS] Extracted {len(frame_samples)} visual frame sample(s) to: "
                f"{os.path.dirname(frame_samples[0]['path'])}"
            )
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

    output_base_dir = os.path.dirname(os.path.abspath(output_file))
    transcript_markdown = build_transcript_markdown(
        video_path,
        speech_segments,
        transcription_metadata,
        frame_samples=frame_samples,
        frame_sample_error=frame_sample_error,
        frame_ocr_error=frame_ocr_error,
        video_metadata=video_metadata,
        video_metadata_error=video_metadata_error,
        output_base_dir=output_base_dir,
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
        subtitle_markdown = build_subtitle_markdown(
            video_path,
            subtitle_segments,
            subtitle_source,
            output_base_dir=os.path.dirname(os.path.abspath(subtitle_output)),
        )
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
            output_base_dir=os.path.dirname(os.path.abspath(report_output)),
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
    parser.add_argument(
        "--output",
        help="Markdown output path for --video only. Relative paths resolve beside the input video.",
    )
    parser.add_argument(
        "--output-dir",
        help="Output folder for generated transcript Markdown files. Relative paths resolve beside the input video or folder.",
    )
    parser.add_argument(
        "--frame-samples",
        type=int,
        help=(
            "Exact number of representative visual frames to extract. Use 0 to disable. "
            "When omitted, --frame-sample-mode controls automatic sampling."
        ),
    )
    parser.add_argument(
        "--frame-sample-mode",
        choices=["shot", "interval"],
        default="interval",
        help=(
            "Automatic visual sampling mode when --frame-samples is omitted. "
            "interval keeps the dense 1 frame/second behavior for detailed downstream analysis; "
            "shot detects scene changes and saves one representative frame per shot. Default: interval."
        ),
    )
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

    if args.frame_samples is not None and args.frame_samples < 0:
        raise ValueError("--frame-samples must be 0 or a positive integer.")

    if args.folder and args.subtitle:
        raise ValueError("--subtitle can only be used with --video. Folder mode can auto-discover sidecar subtitles or use --ocr-subtitles.")

    if args.video:
        if not os.path.exists(args.video):
            raise FileNotFoundError(f"Video file not found: {args.video}")
        output_file = resolve_output_file(args.output, args.video) or output_path_for_video(args.video, args.output_dir)
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
            frame_sample_mode=args.frame_sample_mode,
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
                    frame_sample_mode=args.frame_sample_mode,
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





