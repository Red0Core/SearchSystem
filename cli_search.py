"""Terminal client that reuses the in-process search logic."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Iterable

from app.config import settings
from app.es_client import get_client
from app.search import search_products

MAX_RESULTS = 100
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"


async def perform_query(query: str) -> dict:
    es = get_client()
    return await search_products(es, settings.es_index, query, limit=MAX_RESULTS)


def interactive_shell() -> None:
    print("Interactive product search. Type 'exit' to quit.")
    while True:
        try:
            query = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            return
        response = asyncio.run(perform_query(query))
        pretty_print_response(query, response)


def pretty_print_response(query: str, payload: dict) -> None:
    results = payload.get("results", [])
    eta = float(payload.get("eta_ms", payload.get("took_ms", 0)))
    color = GREEN if eta < 200 else RED
    eta_label = f"{color}{eta:.1f} ms{RESET}"
    print(f"Query: {query} | results: {len(results)} | ETA: {eta_label}")
    for idx, item in enumerate(results[:MAX_RESULTS], start=1):
        score = item.get("score")
        score_repr = f"{score:.2f}" if isinstance(score, (int, float)) else "-"
        print(
            f"  {idx:02d}. score={score_repr} | {item.get('manufacturer')} | "
            f"{item.get('productCode')} | {item.get('title')}"
        )


def batch_mode(file_path: Path) -> None:
    with file_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            query = line.strip()
            if not query:
                continue
            response = asyncio.run(perform_query(query))
            pretty_print_response(query, response)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CLI client for the search service")
    parser.add_argument("query", nargs="?", help="Query string. If omitted, starts REPL mode.")
    parser.add_argument("--batch", type=Path, help="File with queries to execute line by line")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.batch:
        batch_mode(args.batch)
        return 0
    if args.query:
        response = asyncio.run(perform_query(args.query))
        pretty_print_response(args.query, response)
        return 0
    interactive_shell()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
