[README.md](https://github.com/user-attachments/files/29363617/README.md)
# Local Video Script Reconstructor

本项目用于将本地视频或视频文件夹转换为可读的 Markdown 转写稿、整理稿和视频分析输入材料。它面向短视频复盘、直播切片整理、课程/会议录像总结、字幕核对、脚本重建和后续报告生成等场景。

核心定位：先把本地视频变成结构化 Markdown，再交给 Codex 或下游报告工具做进一步分析。

## 功能特性

- 本地视频语音转写，输出 `*_转写稿.md`
- 支持单视频和文件夹批量处理
- 自动发现 Python、检查依赖、设置模型下载端点
- 默认使用 `faster-whisper` 的 `small` 模型，加载失败时回退到 `tiny`
- 默认使用 `https://hf-mirror.com`，更适合中国大陆网络环境
- 支持外部字幕文件、同名字幕自动发现、硬字幕 OCR
- 支持语音与字幕双向核对，输出字幕核对报告
- 默认抽取代表帧，辅助分析画面、产品、场景、景别和屏幕文字
- 可生成适配 `report-generator` 的结构化 JSON intake 区块

## 适用场景

- 短视频口播内容整理
- 直播切片脚本复盘
- 商品种草/引流素材拆解
- 后台录屏、会议录像、课程视频总结
- 字幕识别与字幕质量核对
- 批量视频归档和内容摘要
- 为视频分析报告生成器准备输入材料

## 项目结构

```text
local-video-script-reconstructor/
├─ SKILL.md                    # Codex skill 使用说明
├─ README.md                   # 项目说明
├─ requirements.txt            # 基础依赖
├─ requirements-ocr.txt        # OCR 相关依赖
├─ agents/
│  └─ openai.yaml              # 可选 agent 配置
├─ outputs/                    # 示例或生成输出
└─ scripts/
   ├─ run_windows.bat          # 推荐入口：Windows 一键运行
   ├─ organize.py              # 核心处理脚本
   ├─ subtitle_tools.py        # 字幕解析、OCR、核对工具
   ├─ bootstrap_windows.py     # 非交互依赖安装辅助
   ├─ setup_windows.bat        # 人工双击安装入口
   └─ check_env.py             # 环境检查脚本
```

## 环境要求

- Windows
- Python 3.10+
- 可访问 Hugging Face 或镜像站点，用于首次下载 Whisper 模型
- 推荐使用 Codex Desktop 配合本 skill 完成最终整理稿生成

基础依赖：

```text
av
faster-whisper
Pillow
```

OCR 相关依赖位于 `requirements-ocr.txt`：

```text
numpy
Pillow
rapidocr-onnxruntime
```

## 快速开始

推荐使用 Windows 一键入口。进入项目目录后运行：

```powershell
.\scripts\run_windows.bat "D:\path\to\video.mp4"
```

脚本会自动完成：

- 查找可用 Python
- 检查或安装依赖
- 设置 `HF_ENDPOINT=https://hf-mirror.com`
- 加载或下载 Whisper 模型
- 转写视频语音
- 抽取代表帧
- 生成 Markdown 转写稿

输出文件通常位于视频同目录：

```text
视频名_转写稿.md
视频名_frame_samples/
```

随后 Codex 会读取转写稿和代表帧，生成：

```text
视频名_整理稿.md
```

## 单视频高级用法

直接调用核心脚本：

```powershell
python scripts\organize.py --video "D:\path\to\video.mp4" --language zh
```

使用更快的测试模型：

```powershell
python scripts\organize.py --video "D:\path\to\video.mp4" --whisper-model tiny --language zh
```

指定输出目录：

```powershell
python scripts\organize.py --video "D:\path\to\video.mp4" --output-dir "D:\path\to\outputs" --language zh
```

使用本地 faster-whisper 模型目录：

```powershell
python scripts\organize.py --video "D:\path\to\video.mp4" --whisper-model "D:\models\faster-whisper-small" --language zh
```

指定模型下载端点：

```powershell
python scripts\organize.py --video "D:\path\to\video.mp4" --hf-endpoint "https://hf-mirror.com" --language zh
```

## 批量处理

处理文件夹中的视频：

```powershell
python scripts\organize.py --folder "D:\path\to\videos" --language zh
```

递归处理子文件夹：

```powershell
python scripts\organize.py --folder "D:\path\to\videos" --recursive --language zh
```

指定批量输出目录：

```powershell
python scripts\organize.py --folder "D:\path\to\videos" --recursive --output-dir "D:\path\to\outputs" --language zh
```

## 代表帧采样

默认会抽取 8 张代表帧，并写入转写稿的 `## Visual Frame Samples` 区块。整理稿生成时，应先查看这些图片，再描述：

- 产品和人物
- 场景和背景
- 屏幕字幕或价格信息
- 景别和运镜
- 画面卖点与视觉钩子

关闭抽帧：

```powershell
python scripts\organize.py --video "D:\path\to\video.mp4" --frame-samples 0 --language zh
```

增加抽帧数量：

```powershell
python scripts\organize.py --video "D:\path\to\video.mp4" --frame-samples 12 --language zh
```

## 字幕识别与核对

### 使用外部字幕文件

```powershell
python scripts\organize.py --video "D:\path\to\video.mp4" --subtitle "D:\path\to\subtitle.srt" --language zh
```

### 自动发现同名字幕

```powershell
python scripts\organize.py --video "D:\path\to\video.mp4" --check-subtitles --language zh
```

### 识别硬字幕 OCR

首次使用 OCR 前安装依赖：

```powershell
python scripts\bootstrap_windows.py --ocr
```

然后运行：

```powershell
python scripts\organize.py --video "D:\path\to\video.mp4" --check-subtitles --ocr-subtitles --language zh
```

可调整 OCR 区域：

```powershell
python scripts\organize.py --video "D:\path\to\video.mp4" --check-subtitles --ocr-subtitles --subtitle-area full --language zh
```

可调整采样间隔：

```powershell
python scripts\organize.py --video "D:\path\to\video.mp4" --check-subtitles --ocr-subtitles --ocr-sample-interval 0.5 --language zh
```

## 生成内容格式

`*_转写稿.md` 通常包含：

- Source video
- Whisper 模型信息
- Visual Frame Samples
- Required Final Output
- Transcript
- Timestamped Segments

Codex 读取后生成的 `*_整理稿.md` 应包含：

- 核心总结
- 关键卖点/关键内容
- 详细内容拆解
- 可复用视频脚本结构
- 已确认事实与不确定点
- 剪辑、标题、发布建议
- Report Generator Intake

## 与 report-generator 配合

本项目可以作为 `report-generator` 的上游。

`*_整理稿.md` 中应包含一个 `## Report Generator Intake` 章节，并在里面提供两个小节：`### breakdown_json` 和 `### hook_analysis_json`。每个小节下放一个合法的 `json` 代码块。

`breakdown_json` 示例：

```json
{ ... }
```

`hook_analysis_json` 示例：

```json
{ ... }
```

之后可直接运行：

```powershell
python scripts\generate_report.py "D:\path\to\视频名_整理稿.md" > report.md
```

`breakdown_json` 用于描述视频时长、分镜、BGM、场景和平台建议；`hook_analysis_json` 用于描述前三秒钩子评分、优势、不足和优化建议。

## 常见问题

### 首次运行很慢

首次运行可能需要下载 faster-whisper 模型。下载完成后会写入本地缓存标记，后续运行会优先使用本地缓存。

### 模型下载失败

可尝试：

```powershell
python scripts\organize.py --video "video.mp4" --whisper-model tiny --language zh
```

或指定其他镜像：

```powershell
python scripts\organize.py --video "video.mp4" --hf-endpoint "https://hf-mirror.com" --language zh
```

### 输出 Markdown 中文乱码

请用 UTF-8 读取文件。在 PowerShell 中可使用：

```powershell
Get-Content -Encoding UTF8 -Raw "视频名_转写稿.md"
```

### 没有画面细节

请确认：

- 没有使用 `--frame-samples 0`
- 已安装 `Pillow`
- 转写稿中存在 `## Visual Frame Samples`
- 整理稿生成时已经查看代表帧图片

### OCR 没识别到硬字幕

可尝试：

- 使用 `--subtitle-area full`
- 降低 `--ocr-sample-interval`
- 提供外部 `.srt` 字幕文件

## 注意事项

- 本项目不会删除、移动或覆盖源视频。
- 语音转写可能误识别品牌名、产品名、价格和成分名，发布前需要人工核对。
- 代表帧采样只能提供视觉证据，不等同于完整视觉理解模型。
- 如果用于商业投放报告，建议结合原视频画面、商品页和真实活动规则做最终确认。

## License

MIT

