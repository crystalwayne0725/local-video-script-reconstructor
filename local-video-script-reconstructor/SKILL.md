---
name: local-video-script-reconstructor
description: Use when Codex should process local video files or folders into transcripts, summaries, script reconstructions, report-generator-ready analysis blocks, batch notes, subtitle OCR, or speech/subtitle verification. Trigger for local video organizing, one-click video organizing, batch video folder organizing, recording summaries, subtitle recognition, subtitle OCR, subtitle verification, speech/subtitle comparison, organize this local video, summarize a recording, reconstruct a video script, turn backend videos into notes, or prepare video inputs for report-generator. For normal video/folder transcription, run scripts/run_windows.bat first because it handles Python discovery, dependency checks, model endpoint setup, and fallback; do not manually search for Python or run organize.py directly unless the runner fails. Then read generated Markdown and produce final notes using the currently configured Codex Desktop model provider.
---

# Local Video Script Reconstructor

Use this skill to turn local videos into Markdown transcripts, then produce organized notes, script outlines, and report-generator-ready structured analysis. Prefer the one-command Windows runner for normal use.

## Default Flow

1. If the user provides a local video path or folder path, run exactly this one-command entry from this skill folder:

   ```powershell
   .\scripts\run_windows.bat "<video_or_folder_path>"
   ```

2. Use a long integer timeout for the transcription command when the tool supports timeouts, such as `1800000` milliseconds. Do not use float timeout values.
3. Read the generated `*_转写稿.md` file or files with UTF-8 encoding on Windows PowerShell.
4. If the transcript contains `## Visual Frame Samples`, inspect the referenced frame image files before producing the final organized result. Use those frames for scene, shot, product, subtitle, and on-screen selling-point observations.
5. Use the currently configured Codex Desktop model provider to produce the final organized result.
6. Save the organized notes beside the transcript as `*_整理稿.md`.
7. The organized notes must include the report-generator intake contract described below.
8. Return the final notes and mention the generated Markdown file paths.

The runner automatically:

- finds Python,
- reuses the cached Python path after a successful run,
- checks or installs required dependencies,
- sets the China-friendly model endpoint `https://hf-mirror.com`,
- uses `small` as the default Whisper model,
- falls back to `tiny` when the primary model cannot load,
- lets `scripts/organize.py` reuse local model-cache markers after the first successful model load,
- detects whether the input is a file or folder,
- runs `scripts/organize.py`,
- prints generated output paths.

## Final Output

After reading each transcript, produce concise Markdown in the user's preferred language with:

- Core summary
- Key points
- Detailed content outline
- Reusable video script outline
- Confirmed facts vs uncertain or inferred points when transcription quality is limited
- Editing, title, or publishing suggestions when useful
- Visual observations from frame samples when available
- Report Generator Intake, using the exact contract below

## Report Generator Intake Contract

Every `*_整理稿.md` must include a section named exactly `## Report Generator Intake`.

Inside that section, include two subsections named exactly `### breakdown_json` and `### hook_analysis_json`. Each subsection must contain one fenced `json` block.

The JSON must be valid JSON, with no comments, trailing commas, or Markdown inside the JSON blocks.

### `breakdown_json` schema

Use this shape so `report-generator` can consume it directly:

```json
{
  "duration": 0.0,
  "segment_count": 0,
  "resolution": "N/A",
  "segments": [
    {
      "segment_index": 1,
      "start_time": 0.0,
      "end_time": 0.0,
      "shot_type": "N/A or inferred description",
      "camera_movement": "N/A or inferred description",
      "function_tag": "hook / selling point / proof / CTA / transition / other",
      "visual_content": "Brief content description. Mark inferred visual details clearly."
    }
  ],
  "bgm_analysis": {
    "music_style": {"primary": "N/A or inferred"},
    "emotion": {"primary": "N/A or inferred"},
    "tempo": {"bpm_estimate": "N/A", "pace": "N/A or inferred"}
  },
  "scene_analysis": {
    "primary_scene": "N/A or inferred",
    "video_style": {
      "overall": "N/A or inferred",
      "target_audience": []
    },
    "platform_recommendations": [
      {"platform": "platform name", "suitability": "high / medium / low", "reason": "short reason"}
    ]
  }
}
```

### `hook_analysis_json` schema

Use this shape when the transcript contains enough first-3-seconds context. If not, still output the object with conservative scores and explain uncertainty in the comments:

```json
{
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
}
```

### Intake Rules

- Build `segments` from the transcript timestamped segments when available.
- Use the actual start and end times from the transcript. Convert timecodes to seconds.
- Use `## Visual Frame Samples` when available to fill shot type, camera movement, scene, product, subtitle, and visual content details. If a detail is still unavailable, use `N/A` or mark it as inferred in the value.
- Keep `visual_content` concise because `report-generator` truncates long table cells.
- Keep all scores on a 0-10 scale.
- Preserve product names and claims carefully. Put uncertain terms in confirmed/uncertain notes and mention uncertainty in JSON comments fields, not as JSON comments.

For batch jobs, include:

- Overall summary
- Per-video summary table
- Paths to generated transcript files
- Failed files and reasons, if any
- A separate `Report Generator Intake` section for each video, or one clearly labeled subsection per video containing both JSON blocks

## Advanced Commands

Use `scripts/organize.py` directly only when the user needs advanced control.

Representative visual frame sampling is enabled by default and saves frame images beside the transcript in a `*_frame_samples` folder. Disable it only when the user explicitly wants audio-only processing:

```powershell
python scripts\organize.py --video "<video_path>" --frame-samples 0 --language zh
```

Increase the sample count for visually dense videos:

```powershell
python scripts\organize.py --video "<video_path>" --frame-samples 12 --language zh
```

Faster smoke test model:

```powershell
python scripts\organize.py --video "<video_path>" --whisper-model tiny --language zh
```

Custom output folder:

```powershell
python scripts\organize.py --folder "<folder_path>" --recursive --output-dir "<output_folder>" --language zh
```

Use a local faster-whisper model folder:

```powershell
python scripts\organize.py --video "<video_path>" --whisper-model "<local_model_folder>" --language zh
```

Use another model endpoint:

```powershell
python scripts\organize.py --video "<video_path>" --hf-endpoint "<mirror_url>" --language zh
```

## Subtitle Verification

Use this branch only when the user asks for subtitle recognition, subtitle OCR, or speech/subtitle comparison.

External subtitle file:

```powershell
python scripts\organize.py --video "<video_path>" --subtitle "<subtitle.srt>" --language zh
```

Same-name subtitle discovery:

```powershell
python scripts\organize.py --video "<video_path>" --check-subtitles --language zh
```

Hard-subtitle OCR:

```powershell
python scripts\bootstrap_windows.py --ocr
python scripts\organize.py --video "<video_path>" --check-subtitles --ocr-subtitles --language zh
```

When subtitle verification files exist, also summarize:

- Whether speech and subtitles are broadly consistent
- High-risk mismatches from `_字幕核对报告.md`
- Whether problems look like missing subtitle text, extra subtitle text, OCR noise, or timing offset

## Rules

- Act directly after receiving a valid local path.
- For normal video or folder tasks, do not search for Python, run `Get-Command`, run `check_env.py`, verify model installation, or call `organize.py` directly before trying `scripts/run_windows.bat`.
- Treat `scripts/run_windows.bat` as the default orchestrator; it handles Python discovery, dependency checks, model endpoint setup, model cache reuse, model fallback, and file/folder routing.
- Do not preflight or verify Whisper model installation separately. `scripts/organize.py` writes a per-user ready marker after a successful model load, then prefers the local Hugging Face cache on later runs.
- If a transcription command times out but the process was still loading or transcribing, rerun the same command with a longer integer timeout instead of changing the workflow.
- Do not ask for local script API credentials.
- Do not delete, rename, move, or overwrite source videos.
- Do not expose normal command steps to the user unless blocked.
- Use `scripts/setup_windows.bat` only as a human double-click fallback.
- Use `scripts/bootstrap_windows.py` when Codex needs non-interactive dependency installation.

## Troubleshooting

- If first-run model download fails, rerun the one-command runner or use `--whisper-model tiny`, the default `https://hf-mirror.com`, another `--hf-endpoint`, or a local model folder.
- If generated Markdown looks garbled in PowerShell, read it with `Get-Content -Encoding UTF8 -Raw` or reopen the file in an UTF-8-aware editor.
- If package installation fails because of network restrictions, request approval or report the dependency blocker clearly.
- If media decoding fails, reinstall dependencies or ask for a common mp4 file.
- If final-note generation fails, check Codex Desktop model/provider configuration instead of asking for a local API key.
- If hard-subtitle OCR finds no text, retry with `--subtitle-area full`, lower `--ocr-sample-interval`, or ask for an external subtitle file.

