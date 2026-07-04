# 初次使用操作流程（非程序用户版）

这份文档给第一次使用的人看，尽量不讲程序概念。你只需要会打开文件夹、双击文件、拖拽视频。

## 适用情况

- 电脑系统是 Windows。
- 你要把本地视频转成文字稿、整理稿、脚本复盘材料。
- 你使用 Codex Desktop，或者有人已经把这个 skill 文件夹发给你。

## 使用前准备

准备好这几样东西：

- 一个视频文件，常见格式如 `.mp4`、`.mov`、`.mkv`。
- 本 skill 文件夹：`local-video-script-reconstructor`。
- 64 位 Python，推荐 Python 3.10、3.11 或 3.12。
- 能访问网络。第一次使用时需要下载 Python 依赖和 Whisper 模型。

不用准备本地 API Key。最终整理稿由 Codex Desktop 当前配置的模型完成。

## 第一步：确认 skill 文件夹放对位置

如果别人发给你的是压缩包，先解压。

推荐放到这个位置：

```text
C:\Users\你的用户名\.codex\skills\local-video-script-reconstructor
```

不会找这个目录时，可以这样做：

1. 打开“文件资源管理器”。
2. 点击顶部地址栏。
3. 输入 `%USERPROFILE%\.codex\skills`，按回车。
4. 如果没有 `skills` 文件夹，就新建一个。
5. 把 `local-video-script-reconstructor` 文件夹放进去。

放好后，打开这个文件夹，应该能看到：

```text
SKILL.md
README.md
scripts
requirements.txt
```

如果看到的是“文件夹里面又套了一层同名文件夹”，需要进入最里面那层，确保 `SKILL.md` 和 `scripts` 在同一级。

## 第二步：安装 Python

如果电脑已经安装了 64 位 Python 3.10、3.11 或 3.12，可以跳过这一步。

如果没有安装：

1. 安装 64 位 Python。
2. 安装时勾选 `Add python.exe to PATH`，如果看到这个选项的话。
3. 安装完成后，重新打开 Codex Desktop 或重新打开文件夹窗口。

如果你不确定有没有装 Python，也可以先继续下一步。脚本会自动检查，缺少时会提示。

## 第三步：首次安装运行环境

进入 `local-video-script-reconstructor` 文件夹，打开里面的 `scripts` 文件夹。

双击：

```text
setup_windows.bat
```

看到黑色窗口后，不要关闭，等待它自动执行。

正常情况下会发生这些事：

- 自动寻找可用的 Python。
- 创建这个工具专用的本地环境。
- 通过默认 pip 镜像 `https://pypi.tuna.tsinghua.edu.cn/simple` 安装 `av`、`faster-whisper`、`Pillow` 等依赖。
- 设置 Whisper 模型下载镜像 `https://hf-mirror.com`，降低中国网络首次下载失败概率。
- 检查环境是否可用。

看到类似下面的结果，就表示准备好了：

```text
[SUCCESS] Setup complete.
```

如果 Windows 弹出安全提示，只在你确认这个文件来源可信时点击“更多信息”或“仍要运行”。

## 第四步：处理一个视频

最简单的方法是拖拽：

1. 打开 `local-video-script-reconstructor\scripts` 文件夹。
2. 找到 `run_windows.bat`。
3. 把你的视频文件直接拖到 `run_windows.bat` 上。
4. 松开鼠标。
5. 等黑色窗口执行完成。

也可以处理整个文件夹：

1. 把装有视频的文件夹拖到 `run_windows.bat` 上。
2. 脚本会自动扫描里面的视频。
3. 如果里面还有子文件夹，子文件夹里的视频也会一起处理。

第一次运行会比较慢，因为可能要下载 Whisper 模型。后面再次处理会快一些。

## 第五步：找到生成结果

处理完成后，脚本会在视频旁边创建一个同名文件夹。

例如原视频是：

```text
D:\视频素材\产品演示.mp4
```

生成结果通常在：

```text
D:\视频素材\产品演示\
```

里面会有：

```text
产品演示_转写稿.md
frame_samples
```

`产品演示_转写稿.md` 是语音转写稿。`frame_samples` 是自动抽取的画面截图，用来辅助分析画面信息。

## 第六步：让 Codex 生成整理稿

如果你是在 Codex Desktop 里使用，把生成的 `_转写稿.md` 文件路径发给 Codex，然后说：

```text
请读取这个转写稿，生成整理稿和可复用脚本结构。
```

Codex 会读取转写稿和截图信息，整理出：

- 核心总结
- 关键内容或卖点
- 分时间段内容拆解
- 可复用视频脚本结构
- 不确定信息提醒
- 剪辑、标题或发布建议

整理稿建议保存到同一个视频输出文件夹里，文件名类似：

```text
产品演示_整理稿.md
```

## 常见问题

### 提示找不到 Python

安装 64 位 Python 3.10、3.11 或 3.12，然后重新双击 `setup_windows.bat`。

### 安装依赖失败

多数是网络问题。脚本已经默认使用 `https://pypi.tuna.tsinghua.edu.cn/simple`。如果仍然失败，可以把黑色窗口里的错误截图发给维护者，或让懂技术的人帮你设置其他 Python 包下载源，也就是 pip 镜像。

### 第一次运行很久

这是正常的。第一次可能要下载语音识别模型。只要窗口还在输出内容，就先等它完成。

### 找不到输出文件

到原视频所在文件夹旁边找同名文件夹。比如 `产品演示.mp4` 的结果通常在 `产品演示\` 文件夹里。

### 中文显示乱码

生成的 Markdown 文件是 UTF-8 编码。优先用 Codex Desktop、VS Code、Typora 或其他支持 UTF-8 的编辑器打开。

### 公司电脑无法安装

可能是权限、代理或网络限制。把错误截图给维护者，通常需要配置网络代理或 Python 包下载源。

## 换一台电脑使用

换电脑时，只需要复制这些核心文件：

```text
local-video-script-reconstructor
```

不需要复制：

```text
outputs
__pycache__
```

到新电脑后重新执行：

```text
scripts\setup_windows.bat
```

每台电脑都会创建自己的本地运行环境，互不影响。
