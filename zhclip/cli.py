"""
zhclip.cli - 命令行入口
"""

import sys
import argparse
import logging
import json
from pathlib import Path

from zhclip.transcribe import transcribe_file, transcribe_url


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(message)s")


def main():
    parser = argparse.ArgumentParser(
        prog="zhclip",
        description="纯 CPU 中文视频/音频转文字工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  zhclip meeting.mp3
  zhclip https://www.youtube.com/watch?v=xxx
  zhclip video.mp4 --language en
  zhclip podcast.mp3 -o output.txt --timestamps
  zhclip interview.mp4 --json
        """,
    )

    parser.add_argument("input", help="音频/视频文件路径或 URL")
    parser.add_argument("-o", "--output", help="输出文件（默认打印到终端）")
    parser.add_argument(
        "--language",
        default="auto",
        choices=["auto", "zh", "en", "zh-en"],
        help="语言 (默认: auto 自动检测)",
    )
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    parser.add_argument(
        "--model",
        help="指定模型路径（不指定则自动下载 SenseVoice 模型）",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        # 判断输入是 URL 还是本地文件
        if args.input.startswith(("http://", "https://", "www.")):
            result = transcribe_url(
                url=args.input,
                language=args.language,
                model_path=args.model,
            )
        else:
            path = Path(args.input)
            if not path.exists():
                print(f"错误: 文件不存在: {path}")
                sys.exit(1)
            result = transcribe_file(
                input_path=str(path),
                language=args.language,
                model_path=args.model,
            )

        # 输出
        if args.json:
            output = json.dumps(result, ensure_ascii=False, indent=2)
        else:
            lines = []
            lines.append("─" * 50)
            lines.append("转写结果")
            lines.append("─" * 50)
            lines.append(result["text"])
            lines.append("")
            lines.append(
                f"音频: {result.get('duration', '?')}s"
                f" | 处理: {result.get('elapsed', '?')}s"
                f" | 语言: {result.get('language', args.language)}"
            )
            if "source_url" in result:
                lines.append(f"来源: {result['source_url']}")
            output = "\n".join(lines)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"已保存到: {args.output}")
        else:
            print(output)

    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()