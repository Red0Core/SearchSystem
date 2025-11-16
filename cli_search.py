"""Terminal client for the product search API."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import httpx

API_URL = "http://localhost:8000/search"


def perform_query(query: str) -> dict:
    response = httpx.get(API_URL, params={"q": query}, timeout=20)
    response.raise_for_status()
    return response.json()


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
        try:
            response = perform_query(query)
        except httpx.HTTPError as exc:
            print(f"Request failed: {exc}")
            continue
        pretty_print_response(query, response)


def pretty_print_response(query: str, payload: dict) -> None:
    results = payload.get("results", [])
    took = payload.get("took_ms", 0)
    print(f"Query: {query} | results: {len(results)} | took: {took:.1f} ms")
    for item in results[:5]:
        score = item.get("score")
        score_repr = f"{score:.2f}" if isinstance(score, (int, float)) else "-"
        print(
            f"  - score={score_repr} | {item.get('manufacturer')} | "
            f"{item.get('product_code')} | {item.get('title')}"
        )


def batch_mode(file_path: Path) -> None:
    with file_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            query = line.strip()
            if not query:
                continue
            try:
                response = perform_query(query)
            except httpx.HTTPError as exc:
                print(f"{query}: FAILED ({exc})")
                continue
            pretty_print_response(query, response)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CLI client for the search API")
    parser.add_argument("query", nargs="?", help="Query string. If omitted, starts REPL mode.")
    parser.add_argument("--batch", type=Path, help="File with queries to execute line by line")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.batch:
        batch_mode(args.batch)
        return 0
    if args.query:
        response = perform_query(args.query)
        pretty_print_response(args.query, response)
        return 0
    interactive_shell()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
