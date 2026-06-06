# zhclip — 纯 CPU 中文视频转文字工具

> **项目状态：归档**  
> 这是一个学习项目。初衷是做一款本地运行的视频转文字工具，后经市场验证发现已有大量免费替代品（通义千问、飞书妙记、沉浸式翻译等），决定归档。代码保留作为技术作品集。

## 项目简介

纯 CPU 运行的中文/英文/粤语视频转文字工具。数据不上传云端，全部在本地处理。

灵感来自 HN 上的 [yapsnap](https://github.com/kouhxp/yapsnap)，目标是把同样的思路做成中文友好的版本。

## 功能

- 支持 YouTube 链接和本地文件上传
- 中文 / 英文 / 粤语语音识别（SenseVoice INT8）
- 双语对照显示：英文原文 + 中文翻译，带时间戳
- 双层缓存：音频 + 结果缓存，同一链接第二次秒出
- 纯前端 HTML+JS，零依赖部署

## 技术栈

| 模块 | 技术 | 说明 |
|------|------|------|
| 语音模型 | sherpa-onnx + SenseVoice INT8 | 229MB 量化模型，4GB 内存可跑 |
| 翻译 | deep-translator (Google) | 免费，国内需加超时保护 |
| 后端 | FastAPI + uvicorn | 轻量 Web 服务 |
| 下载 | yt-dlp | YouTube 链接解析 |
| 内存优化 | 30 秒分块处理 | 防止 4GB 内存 OOM |

## 项目结构

```
zhclip/
├── zhclip/
│   ├── cli.py          # 命令行入口
│   ├── transcribe.py   # 核心：转写 + 分段 + 翻译 + 缓存
│   └── download.py     # yt-dlp 下载模块
├── web/
│   ├── app.py          # FastAPI 服务
│   └── templates/
│       └── index.html  # 前端页面
├── data/
│   ├── models/         # SenseVoice 模型文件
│   ├── downloads/      # 音频缓存
│   └── uploads/        # 用户上传
├── 复盘笔记.md         # 完整踩坑记录
└── pyproject.toml
```

## 学到的东西

真正有价值的不是这个产品本身，而是做它的过程：

- **sherpa-onnx 本地语音模型部署** — 从下载、量化到推理全流程
- **内存敏感场景的性能优化** — 分块处理、INT8 量化、缓存策略
- **FastAPI 全栈 Web 开发** — 上传、后台任务、模板渲染
- **国内网络环境下的工程取舍** — Google 翻译超时保护、代理配置
- **独立项目从灵感到上线的全链路** — 技术实现只占 30%，其余是选型、踩坑、修 bug
- **最大的教训**：先找用户，再做产品。不要手里有锤子，看啥都是钉子。

## 启动方式

```bash
cd /e/Programs/zhclip
export ZHCLIP_DATA="E:/Programs/zhclip/data"
.venv/Scripts/python -m web.app
```

然后打开 http://127.0.0.1:8080

## License

MIT
