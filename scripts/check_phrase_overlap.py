#!/usr/bin/env python3
"""Flag exact contiguous word overlap between a draft and a local text corpus.

This is a screening aid, not a plagiarism detector or authorship classifier.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


WORD_RE = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flag exact word-sequence overlap with local corpus text files."
    )
    parser.add_argument("--draft", required=True, help="Plain-text or Markdown manuscript draft")
    parser.add_argument("--corpus-dir", required=True, help="Directory containing extracted source text")
    parser.add_argument("--n", type=int, default=8, help="Minimum contiguous words (default: 8)")
    parser.add_argument(
        "--extensions",
        default=".txt,.md",
        help="Comma-separated corpus extensions (default: .txt,.md)",
    )
    parser.add_argument("--max-matches", type=int, default=200, help="Maximum matches reported")
    parser.add_argument("--output", help="Optional JSON output path; otherwise print to stdout")
    return parser.parse_args()


def tokenize(value: str) -> list[str]:
    return [match.group(0).lower() for match in WORD_RE.finditer(value)]


def build_index(tokens: list[str], n: int) -> dict[tuple[str, ...], list[int]]:
    index: dict[tuple[str, ...], list[int]] = {}
    for position in range(0, len(tokens) - n + 1):
        gram = tuple(tokens[position : position + n])
        index.setdefault(gram, []).append(position)
    return index


def maximal_match(
    draft: list[str],
    source: list[str],
    draft_start: int,
    source_start: int,
    n: int,
) -> tuple[int, int, int, int]:
    d_left = draft_start
    s_left = source_start
    while d_left > 0 and s_left > 0 and draft[d_left - 1] == source[s_left - 1]:
        d_left -= 1
        s_left -= 1

    d_right = draft_start + n
    s_right = source_start + n
    while d_right < len(draft) and s_right < len(source) and draft[d_right] == source[s_right]:
        d_right += 1
        s_right += 1
    return d_left, d_right, s_left, s_right


def main() -> int:
    args = parse_args()
    if args.n < 4:
        print("Refusing n < 4 because it produces unmanageable false positives.", file=sys.stderr)
        return 2
    if args.max_matches < 1:
        print("--max-matches must be positive.", file=sys.stderr)
        return 2

    draft_path = Path(args.draft).expanduser().resolve()
    corpus_dir = Path(args.corpus_dir).expanduser().resolve()
    if not draft_path.is_file():
        print(f"Draft not found: {draft_path}", file=sys.stderr)
        return 2
    if not corpus_dir.is_dir():
        print(f"Corpus directory not found: {corpus_dir}", file=sys.stderr)
        return 2

    extensions = {
        extension.strip().lower() if extension.strip().startswith(".") else "." + extension.strip().lower()
        for extension in args.extensions.split(",")
        if extension.strip()
    }
    draft_tokens = tokenize(draft_path.read_text(encoding="utf-8-sig", errors="replace"))
    if len(draft_tokens) < args.n:
        print("Draft has fewer tokens than the requested overlap threshold.", file=sys.stderr)
        return 2

    draft_index = build_index(draft_tokens, args.n)
    raw_matches: dict[tuple[str, int, int, int, int], dict[str, object]] = {}
    files_scanned = 0

    for source_path in sorted(corpus_dir.rglob("*")):
        if not source_path.is_file() or source_path.suffix.lower() not in extensions:
            continue
        files_scanned += 1
        source_tokens = tokenize(source_path.read_text(encoding="utf-8-sig", errors="replace"))
        if len(source_tokens) < args.n:
            continue

        for source_position in range(0, len(source_tokens) - args.n + 1):
            gram = tuple(source_tokens[source_position : source_position + args.n])
            draft_positions = draft_index.get(gram)
            if not draft_positions:
                continue
            for draft_position in draft_positions[:10]:
                d_left, d_right, s_left, s_right = maximal_match(
                    draft_tokens,
                    source_tokens,
                    draft_position,
                    source_position,
                    args.n,
                )
                relative = source_path.relative_to(corpus_dir).as_posix()
                key = (relative, d_left, d_right, s_left, s_right)
                if key in raw_matches:
                    continue
                words = draft_tokens[d_left:d_right]
                preview_words = words[:25]
                preview = " ".join(preview_words)
                if len(words) > 25:
                    preview += " …"
                raw_matches[key] = {
                    "source": relative,
                    "word_count": len(words),
                    "phrase_preview_max_25_words": preview,
                    "draft_word_start": d_left + 1,
                    "draft_word_end": d_right,
                    "source_word_start": s_left + 1,
                    "source_word_end": s_right,
                }

    # Remove matches fully contained in a longer match from the same source and positions.
    ordered = sorted(
        raw_matches.values(),
        key=lambda item: (-int(item["word_count"]), str(item["source"]), int(item["draft_word_start"])),
    )
    retained: list[dict[str, object]] = []
    for match in ordered:
        contained = False
        for larger in retained:
            if match["source"] != larger["source"]:
                continue
            if (
                int(larger["draft_word_start"]) <= int(match["draft_word_start"])
                and int(larger["draft_word_end"]) >= int(match["draft_word_end"])
                and int(larger["source_word_start"]) <= int(match["source_word_start"])
                and int(larger["source_word_end"]) >= int(match["source_word_end"])
            ):
                contained = True
                break
        if not contained:
            retained.append(match)
        if len(retained) >= args.max_matches:
            break

    report = {
        "warning": "Screening aid only; matches require human review and are not a plagiarism verdict.",
        "draft": str(draft_path),
        "corpus_directory": str(corpus_dir),
        "minimum_words": args.n,
        "files_scanned": files_scanned,
        "matches_reported": len(retained),
        "matches": retained,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Path.write_text gained a newline argument only in Python 3.10.
        with output_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
        print(f"Wrote {len(retained)} review matches to {output_path}")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
