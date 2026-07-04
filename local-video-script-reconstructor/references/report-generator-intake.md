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
      "shot_id": 1,
      "start_time": 0.0,
      "end_time": 0.0,
      "shot_start_time": 0.0,
      "shot_end_time": 0.0,
      "visual_evidence": "representative frame path, or N/A",
      "source_frame_count": 1,
      "merged_frame_count": 0,
      "source_frame_paths": ["all sampled frame paths merged into this shot, when available"],
      "shot_type": "N/A or inferred description",
      "camera_movement": "N/A or inferred description",
      "function_tag": "hook / selling point / proof / CTA / transition / other",
      "visual_content": "Brief content description. Mark inferred visual details clearly.",
      "speech_text": "Transcript text for this segment",
      "onscreen_text": "OCR text visible near this segment, or N/A",
      "script_text": "Report-facing script/copy text for this segment. Usually copied or cleaned from speech_text.",
      "script_method": "Reusable script method, such as audience hook, pain point, price anchor, trust proof, contrast, objection handling, or CTA.",
      "visual_method": "Reusable visual method, such as product close-up, price caption, before/after comparison, hand demo, scene proof, or live-stream cut.",
      "replication_note": "Concrete shooting/copy note that explains how to recreate this segment without copying brand-specific claims blindly.",
      "confidence": "high / medium / low",
      "source": ["transcript", "shot_frame", "frame_ocr"],
      "evidence": {"shot_id": 1, "frame_index": 1, "frame_time": 0.0, "frame_path": "relative path from the notes file, or N/A"}
    }
  ],
  "commerce_script_structure": {
    "target_audience": ["audience group 1", "audience group 2"],
    "framework": "Overall conversion framework, such as audience hook + pain scene + product proof + offer + CTA.",
    "key_conversion_points": [
      "Conversion point 1 based on transcript, OCR, or visual evidence.",
      "Conversion point 2 based on transcript, OCR, or visual evidence."
    ],
    "modules": [
      {
        "order": 1,
        "name": "module name, such as opening hook / pain point / product proof / offer / CTA",
        "conversion_role": "What this module makes the viewer do or believe.",
        "script_pattern": "Reusable script formula abstracted from source segments.",
        "source_segments": [1, 2],
        "replication_note": "How to adapt this module to another product/category."
      }
    ],
    "risk_notes": [
      "Claim, compliance, evidence, or adaptation risk to avoid."
    ]
  },
  "replication_suggestions": {
    "script_formula": [
      "Audience + pain + product solution + proof + offer + CTA"
    ],
    "narrative_structure": {
      "开场钩子": "time span / percentage / one-line content summary",
      "核心卖点": "time span / percentage / one-line content summary",
      "产品价值": "time span / percentage / one-line content summary",
      "场景延伸": "time span / percentage / one-line content summary, or 0s / 0% / N/A",
      "行动号召": "time span / percentage / one-line content summary"
    },
    "content_analysis": {
      "叙事声音": "Narrative voice, persona, tone, and speaking rhythm.",
      "修辞手法": ["contrast", "repetition", "numbers", "question hook", "social proof"],
      "词库": {
        "核心词": ["product/category words"],
        "场景词": ["scene words"],
        "情绪词": ["emotion words"],
        "转化词": ["offer/CTA words"]
      },
      "内容亮点": ["why viewers stop, understand, believe, or act"],
      "可优化点": ["what should be improved when recreating"]
    },
    "viral_5d_initial": {
      "Hook": "0-10 or star rating",
      "Emotion": "0-10 or star rating",
      "爆点结构": "0-10 or star rating",
      "CTA": "0-10 or star rating",
      "社交货币": "0-10 or star rating"
    },
    "copy_variants": [
      "方向1：copy recreation direction with hook type and angle",
      "方向2：copy recreation direction with hook type and angle",
      "方向3：copy recreation direction with hook type and angle"
    ],
    "voiceover_directions": [
      "版本1：voiceover script direction, including target user, hook, proof, and CTA.",
      "版本2：voiceover script direction, including target user, hook, proof, and CTA.",
      "版本3：voiceover script direction, including target user, hook, proof, and CTA."
    ],
    "minidrama_directions": [
      "版本1：mini-drama scene direction with pain, turn, product value, and CTA.",
      "版本2：mini-drama scene direction with pain, turn, product value, and CTA.",
      "版本3：mini-drama scene direction with pain, turn, product value, and CTA."
    ],
    "viral_5d_overall": {
      "Hook": "0-10 or star rating",
      "Hook_comment": "Why the hook score is justified.",
      "Emotion": "0-10 or star rating",
      "Emotion_comment": "Why the emotion score is justified.",
      "爆点结构": "0-10 or star rating",
      "爆点结构_comment": "Why the structure score is justified.",
      "CTA": "0-10 or star rating",
      "CTA_comment": "Why the CTA score is justified.",
      "社交货币": "0-10 or star rating",
      "社交货币_comment": "Why the social-currency score is justified.",
      "total_score": 0,
      "recommend": "Recommended voiceover or mini-drama direction to shoot first, with one reason."
    },
    "shot_plan": [
      "Must-shoot shot 1 with framing, action, evidence, or prop requirement.",
      "Must-shoot shot 2 with framing, action, evidence, or prop requirement."
    ],
    "production_checklist": [
      "Script, prop, lighting, subtitle, proof-shot, compliance, and CTA checks before filming."
    ],
    "risks_to_avoid": [
      "Avoid copying unverifiable claims, missing proof shots, generic AI-like copy, or offer wording that does not fit the new product."
    ]
  },
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

- When `## Visual Shot Samples` is available, build `segments` from detected shots first. Merge transcript lines and OCR text that overlap the same shot into that shot segment.
- Use transcript timestamped segments as the primary fallback when visual shot samples are unavailable.
- Use actual shot start/end times when `## Visual Shot Samples` is available. Otherwise use transcript segment start/end times. Convert timecodes to seconds.
- Use `## Video Metadata`, `## Visual Shot Samples`, `## Visual Frame Samples`, frame OCR, and `## Segment Evidence Map` when available to fill duration, resolution, FPS, aspect ratio, shot type, camera movement, scene, product, subtitle, and visual content details.
- Put the representative shot frame in `segments[].visual_evidence` so report-generator can embed it in Markdown/Excel outputs. Preserve `source_frame_count` and `merged_frame_count` when the transcript says repeated interval frames were merged into a shot.
- For every report-ready segment, fill `script_text`, `script_method`, `visual_method`, and `replication_note`. `script_text` may be the cleaned `speech_text`; the other three fields should abstract the reusable method behind the source evidence.
- Add `commerce_script_structure` for selling or conversion-oriented videos. When the video is not commerce-oriented, still provide the closest structure and mark low-confidence or non-commerce assumptions clearly.
- Add the full `replication_suggestions` object as a separate paced model stage after basic `segments`, BGM, scene, and hook analysis are complete. Do not combine the full organized notes and full replication JSON in one request.
- `replication_suggestions` must support all seven report steps: narrative structure, TextContent analysis and initial Viral-5D diagnosis, copy variants, voiceover and mini-drama directions, overall Viral-5D scoring, shot plan and production checklist, and risks to avoid.
- Add conservative `confidence`, `source`, and `evidence` fields to segment objects when the evidence is useful.
- Prefer relative evidence paths from the organized notes or transcript location. Use absolute paths only when the evidence file is on a different drive or cannot be expressed relatively.
- Use `N/A` when a detail is unavailable. Mark inferred details clearly in values.
- Keep `visual_content` concise because report tables truncate long cells.
- Keep hook-analysis scores on a 0-10 scale. Viral-5D dimension scores may use 0-10 values or star strings; `viral_5d_overall.total_score` must be 0-100.
- Preserve product names and claims carefully. Put uncertain terms in confirmed/uncertain notes and mention uncertainty in JSON comment fields, not as JSON comments.
- Do not invent visual details, product claims, prices, discounts, or legal/medical efficacy claims. If a replication suggestion requires evidence that is not visible or transcribed, say so in risk notes.

For batch report requests, create a separate organized Markdown file per video when possible. If one batch file must contain all videos, use a clearly labeled subsection per video containing both JSON blocks.
