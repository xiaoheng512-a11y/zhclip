# zhclip — 纯 CPU 中文视频转文字工具

## 项目位置
E:\Programs\zhclip\

## 项目状态（当前版本可用）
- Python + FastAPI Web 服务，port 8080
- sherpa-onnx + SenseVoice 模型（INT8 量化 229MB）
- 支持 YouTube 链接转写 + 文件上传转写
- **双语对照**：英文原文 + 中文翻译，带时间戳分段展示
- **缓存**：音频(.webm) + 结果(.json) 双层缓存，同链接秒出
- FFmpeg 在 C:\tools\bin\ffmpeg.exe（已加入 Windows 用户 PATH）
- Git 版本控制已初始化（3个提交 + original 分支）

## 目录结构
```
E:\Programs\zhclip\
├── zhclip/
│   ├── __init__.py
│   ├── cli.py          # 命令行入口
│   ├── transcribe.py   # 核心：转写+分段+翻译+缓存
│   └── download.py     # yt-dlp 下载模块
├── web/
│   ├── app.py          # FastAPI 服务
│   └── templates/
│       └── index.html  # 前端页面（双语分段展示）
├── data/
│   ├── models/         # 1.1GB SenseVoice 模型
│   ├── downloads/      # 缓存目录
│   ├── uploads/        # 上传文件
│   └── tmp/            # 临时文件
├── .venv/              # Python venv（依赖已装好）
├── run_web.bat         # Windows 启动脚本
├── run_cli.bat
├── pyproject.toml
└── .gitignore
```

## 启动方式
```bash
cd /e/Programs/zhclip
export ZHCLIP_DATA="E:/Programs/zhclip/data"
.venv/Scripts/python -m web.app
```
或双击 run_web.bat

## 已知问题
1. 系统只有 4GB RAM，长视频（20分钟+）转写较慢（~10分钟）
2. 翻译用 Google Translate API，在国内可能被墙，已加 8秒超时
3. Web 服务是单线程 uvicorn，转写时其他请求会排队

## CLAUDE_CODE_GIT_BASH_PATH
E:\Programs\Git\usr\bin\bash.exe
