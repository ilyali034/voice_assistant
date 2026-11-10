"""Run the local microphone-based voice assistant from the project root."""

import argparse
import asyncio

from .main_engine.engine import AssistentEngine


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local voice assistant")
    parser.add_argument(
        "--mode",
        choices=("hybrid", "llm", "actions"),
        default="hybrid",
        help="hybrid uses actions for known commands and Ollama for other questions",
    )
    parser.add_argument("--lang", default="ru", help="Assistant and speech language")
    parser.add_argument("--model", default="llama3.2", help="Local Ollama model")
    parser.add_argument("--wake-word", default="ассистент")
    parser.add_argument("--volume", type=float, default=1.0)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    assistant = AssistentEngine(
        lang=args.lang,
        volume=args.volume,
        assistant_mode=args.mode,
        llm_model=args.model,
    )
    try:
        await assistant.start()
        print(
            f"Ассистент запущен в режиме {args.mode}. "
            f"Скажите «{args.wake_word}», затем произнесите команду. "
            "Во время озвучивания нажмите Esc, чтобы прервать ответ. "
            "Для выхода нажмите Ctrl+C."
        )
        await assistant.start_assistent(wake_word=args.wake_word)
    finally:
        await assistant.stop()


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\nРабота ассистента остановлена.")


if __name__ == "__main__":
    main()
