"""Exercise the Parallel tools without LiveKit, to check your key and latency.

uv run python scripts/try_parallel.py "who won the last formula one race"
uv run python scripts/try_parallel.py --research "best budget ANC headphones"
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from parallel_tools import ParallelTools  # noqa: E402

load_dotenv(".env.local")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--research", action="store_true", help="use deep_research")
    args = ap.parse_args()

    tools = ParallelTools()
    t0 = time.perf_counter()
    try:
        if args.research:
            out = await tools.research(args.question)
        else:
            out = await tools.search(args.question, [args.question[:80]])
    finally:
        await tools.aclose()
    print(out)
    print(f"\n--- {time.perf_counter() - t0:.2f}s ({tools.config.search_mode} mode)")


if __name__ == "__main__":
    asyncio.run(main())
