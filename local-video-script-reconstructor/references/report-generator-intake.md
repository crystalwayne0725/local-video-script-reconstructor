# Report Generator Intake Contract

Read this reference only when the user explicitly asks for a video-analysis report, report-generator input, or report-ready organized notes.

The organized Markdown file must include one section named exactly:

```markdown
## Report Generator Intake
```

Inside that section, include two subsections named exactly `### breakdown_json` and `### hook_analysis_json`. Each subsection must contain one fenced `json` block. The JSON must be valid JSON with no comments, trailing commas, or Markdown inside the JSON blocks.

## `breakdown_json` schema

Use this shape so the report bridge can consume the notes directly:

```json
{
  "duration": 0.0,
  "segment_count": 0,
  "resolution": "N/A",
  "fps": "N/A",
  "aspect_ratio": "N/A",
  "segments": [
    {
      "segment_index": 1,
      "start_time": 0.0,
      "end_time": 0.0,
      "shot_type": "N/A or inferred description",
      "camera_movement": "N/A or inferred description",
      "function_tag": "hook / selling point / proof / CTA / transition / other",
      "visual_content": "Brief content description. Mark inferred visual details clearly.",
      "speech_text": "Transcript text for this segment",
      "onscreen_text": "OCR text visible near this segment, or N/A",
      "confidence": "high / medium / low",
      "source": ["transcript", "frame", "frame_ocr"],
      "evidence": {"frame_index": 1, "frame_time": 0.0, "frame_path": "absolute path or N/A"}
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

## `hook_analysis_json` schema

Use this shape when the transcript contains enough first-3-seconds context. If not, still output the object with conservative scores and explain uncertainty in the comment fields:

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

## Intake Rules

- Build `segments` from transcript timestamped segments when available.
- Use actual start and end times from the transcript. Convert timecodes to seconds.
- Use `## Video Metadata`, `## Visual Frame Samples`, frame OCR, and `## Segment Evidence Map` when available to fill duration, resolution, FPS, aspect ratio, shot type, camera movement, scene, product, subtitle, and visual content details.
- Add conservative `confidence`, `source`, and `evidence` fields to segment objects when the evidence is useful.
- Use `N/A` when a detail is unavailable. Mark inferred details clearly in values.
- Keep `visual_content` concise because report tables truncate long cells.
- Keep all scores on a 0-10 scale.
- Preserve product names and claims carefully. Put uncertain terms in confirmed/uncertain notes and mention uncertainty in JSON comment fields, not as JSON comments.

For batch report requests, create a separate organized Markdown file per video when possible. If one batch file must contain all videos, use a clearly labeled subsection per video containing both JSON blocks.
