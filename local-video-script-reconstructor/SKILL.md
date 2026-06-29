---
name: local-video-script-reconstructor
description: Process local video files or folders into transcripts, summaries, script outlines, batch notes, subtitle OCR, or speech/subtitle verification. Trigger for local video organizing, recording summaries, subtitle recognition/OCR, speech-subtitle comparison, script reconstruction, backend-video notes, or report-generator intake only when the user explicitly asks for a video-analysis report or report input. For normal video/folder transcription, run scripts/run_windows.bat first because it handles Python discovery, dependency checks, model endpoint setup, and fallback; do not manually search for Python or run organize.py directly unless the runner fails.
---

# Local Video Script Reconstructor

Use this skill to turn local videos into Markdown transcripts, then produce organized notes and script outlines. Prefer the one-command Windows runner for normal use.

## Default Flow

1. If the user provides a local video path or folder path, run exactly this one-command entry from this skill folder:

   ```powershell
   .\scripts\run_windows.bat "<video_or_folder_path>"
   ```

2. Use a long integer timeout for the transcription command when the tool supports timeouts, such as `1800000` milliseconds. Do not use float timeout values.
3. Read the generated `*_转写稿.md` file or files with UTF-8 encoding on Windows PowerShell.
4. If no complete organized notes already exist, use transcript metadata, frame OCR text, and the Segment Evidence Map before producing the final organized result. Inspect referenced frame image files only when the user explicitly asks for visual verification, or when text evidence is insufficient for the requested report. Preserve confidence/source/evidence notes for scene, shot, product, subtitle, and on-screen selling-point observations.
5. Use the currently configured Codex Desktop model provider to produce the final organized result.
6. Save the organized notes beside the transcript inside that video's output folder as `*_整理稿.md`.
7. Return the final notes and mention the generated Markdown file paths.

The runner automatically:

- finds Python,
- reuses the cached Python path after a successful run,
- checks or installs required dependencies,
- sets the China-friendly model endpoint `https://hf-mirror.com`,
- uses `small` as the default Whisper model,
- falls back to `tiny` when the primary model cannot load,
- lets `scripts/organize.py` reuse local model-cache markers after the first successful model load,
- detects whether the input is a file or folder,
- creates one output folder per source video so transcripts, frame samples, organized notes, and optional reports stay together,
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

## Optional Report Path

Use this branch only when the user explicitly asks for a video-analysis report, report-generator input, or report-ready organized notes.

1. Read `references/report-generator-intake.md`.
2. Add the required `## Report Generator Intake` section to the organized notes.
3. Generate the report with the bridge script from this skill folder:

   ```powershell
   .\scripts\generate_report_from_notes.bat "<organized_notes.md>"
   ```

4. Mention both the organized notes path and generated report path.

Do not load the `report-generator` skill just to complete this branch; the bridge script calls its report script through the file contract. Use `python scripts\generate_report_from_notes.py` only when a non-Windows shell cannot run the batch file.

For batch jobs, include:

- Overall summary
- Per-video summary table
- Paths to generated transcript files
- Failed files and reasons, if any
- Optional report paths when the user asks for reports

## Advanced Commands

Use `scripts/organize.py` directly only when the user needs advanced control.

Representative visual frame sampling is enabled by default and saves frame images inside the video's output folder under `frame_samples/`. Disable it only when the user explicitly wants audio-only processing:

```powershell
python scripts\organize.py --video "<video_path>" --frame-samples 0 --language zh
```

Increase the sample count for visually dense videos:

```powershell
python scripts\organize.py --video "<video_path>" --frame-samples 12 --language zh
```

Disable frame OCR when only image samples are needed:

```powershell
python scripts\organize.py --video "<video_path>" --no-frame-ocr --language zh
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

## Rate-Limit Guard Rules

These rules prevent 429 Too Many Requests errors caused by rapid successive model API calls.

- If a complete `*_整理稿.md` already exists and the user did not explicitly ask to regenerate, revise, or visually verify it, read that file and return its path plus a concise status. Do not inspect frame samples or regenerate the notes.
- Produce the final organized result in **sequential stages** instead of one monolithic request: first generate the core summary, then the key points, then the content outline, then the script outline. Wait for each stage to complete before starting the next.
- Prefer transcript text, frame OCR text, and the Segment Evidence Map over image inspection. Open frame image files only on explicit visual-verification requests, and inspect at most 2 representative frames per model request.
- Never generate more than **2 major sections** (summary, key points, outline, script, etc.) in a single model request. Split longer tasks across multiple requests.
- After receiving a 429 error, **stop and wait** before retrying. Do not immediately resend the same request. Prefer reducing the scope of the next request rather than retrying the original one.
- When processing multiple videos in a batch, finish one video's organized notes completely before starting the next. Do not interleave or parallelize model requests across videos.
- Avoid re-reading or re-analyzing the same transcript content across multiple requests. Read the transcript once, produce the organized notes, then move on.
- If the transcript is very long (over 3000 characters), generate the organized notes in two passes: first the top half, then the bottom half, then merge.
- Do not spawn sub-agents or parallel workers for organized-note generation. One agent, one video, sequential output only.

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

