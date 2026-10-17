#!/usr/bin/env python3
"""Validate a like-a-paper JSONL sentence ledger using only the standard library."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SENTENCE_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d{2}-\d{2}[a-z]?$")
PARAGRAPH_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d{2}$")
WORD_RE = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")

REQUIRED_FIELDS = {
    "sentence_id",
    "section",
    "paragraph_id",
    "function",
    "english",
    "chinese",
    "claim_type",
    "evidence",
    "claim_ceiling",
    "previous_link",
    "next_link",
    "risk_flags",
    "status",
    "approved_by",
    "approved_at",
    "notes",
}

CLAIM_TYPES = {
    "external_fact",
    "study_result",
    "method",
    "author_inference",
    "limitation",
    "objective",
    "transition",
}

EVIDENCE_TYPES = {
    "literature",
    "figure",
    "table",
    "analysis",
    "dataset",
    "method_record",
    "code",
    "journal_rule",
    "user_decision",
    "rhetorical",
}

SUPPORT_RELATIONS = {
    "direct",
    "partial",
    "analogous",
    "contextual",
    "methodological",
    "contrasting",
    "rhetorical",
}

SOURCE_TEXT_TYPES = {"excerpt", "paraphrase", "artifact_note"}
STATUSES = {"drafted", "needs_revision", "approved", "rejected"}
STUDY_EVIDENCE = {"figure", "table", "analysis", "dataset", "code"}
METHOD_EVIDENCE = {"method_record", "literature", "dataset", "code"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a sentence ledger in JSONL format.")
    parser.add_argument("ledger", help="Path to sentence_ledger.jsonl")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero exit code when warnings are present",
    )
    return parser.parse_args()


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def add_issue(issues: list[str], line_no: int, sentence_id: str, message: str) -> None:
    label = sentence_id or "unknown-id"
    issues.append(f"line {line_no} [{label}]: {message}")


def validate_evidence(
    record: dict[str, Any],
    line_no: int,
    errors: list[str],
    warnings: list[str],
) -> set[str]:
    sentence_id = str(record.get("sentence_id", ""))
    evidence = record.get("evidence")
    observed_types: set[str] = set()

    if not isinstance(evidence, list):
        add_issue(errors, line_no, sentence_id, "evidence must be a list")
        return observed_types

    evidence_ids: set[str] = set()
    required = {
        "evidence_id",
        "evidence_type",
        "citation",
        "locator",
        "source_text_type",
        "source_text",
        "support_relation",
    }

    for index, item in enumerate(evidence, start=1):
        if not isinstance(item, dict):
            add_issue(errors, line_no, sentence_id, f"evidence item {index} must be an object")
            continue

        missing = required - item.keys()
        if missing:
            add_issue(
                errors,
                line_no,
                sentence_id,
                f"evidence item {index} is missing: {', '.join(sorted(missing))}",
            )

        evidence_id = item.get("evidence_id")
        if not is_nonempty_string(evidence_id):
            add_issue(errors, line_no, sentence_id, f"evidence item {index} has no evidence_id")
        elif evidence_id in evidence_ids:
            add_issue(errors, line_no, sentence_id, f"duplicate evidence_id {evidence_id}")
        else:
            evidence_ids.add(evidence_id)

        evidence_type = item.get("evidence_type")
        if evidence_type not in EVIDENCE_TYPES:
            add_issue(
                errors,
                line_no,
                sentence_id,
                f"evidence item {index} has invalid evidence_type {evidence_type!r}",
            )
        else:
            observed_types.add(evidence_type)

        if not is_nonempty_string(item.get("locator")):
            add_issue(errors, line_no, sentence_id, f"evidence item {index} needs a locator")

        source_text_type = item.get("source_text_type")
        if source_text_type not in SOURCE_TEXT_TYPES:
            add_issue(
                errors,
                line_no,
                sentence_id,
                f"evidence item {index} has invalid source_text_type {source_text_type!r}",
            )

        source_text = item.get("source_text")
        if not is_nonempty_string(source_text):
            add_issue(errors, line_no, sentence_id, f"evidence item {index} needs source_text")
        elif source_text_type == "excerpt":
            word_count = len(WORD_RE.findall(source_text))
            if word_count > 25:
                add_issue(
                    warnings,
                    line_no,
                    sentence_id,
                    f"evidence item {index} excerpt has {word_count} English words; shorten to 25 or fewer",
                )

        relation = item.get("support_relation")
        if relation not in SUPPORT_RELATIONS:
            add_issue(
                errors,
                line_no,
                sentence_id,
                f"evidence item {index} has invalid support_relation {relation!r}",
            )

        if evidence_type == "literature" and not is_nonempty_string(item.get("citation")):
            add_issue(errors, line_no, sentence_id, f"literature evidence item {index} needs a citation")

        if evidence_type != "literature" and item.get("citation") not in (None, ""):
            add_issue(
                warnings,
                line_no,
                sentence_id,
                f"non-literature evidence item {index} has a citation; confirm the evidence type",
            )

    return observed_types


def validate_record(
    record: Any,
    line_no: int,
    seen_ids: set[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    if not isinstance(record, dict):
        errors.append(f"line {line_no}: record must be a JSON object")
        return

    sentence_id = str(record.get("sentence_id", ""))
    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        add_issue(errors, line_no, sentence_id, f"missing fields: {', '.join(sorted(missing))}")

    if "change_note" not in record or not is_nonempty_string(record.get("change_note")):
        add_issue(
            warnings,
            line_no,
            sentence_id,
            "change_note is missing; the compact user review will not explain what changed or which drafting rule was applied",
        )

    if not SENTENCE_ID_RE.fullmatch(sentence_id):
        add_issue(errors, line_no, sentence_id, "sentence_id must match SECTION-PP-SS, e.g. DISC-02-04")
    elif sentence_id in seen_ids:
        add_issue(errors, line_no, sentence_id, "duplicate sentence_id")
    else:
        seen_ids.add(sentence_id)

    paragraph_id = record.get("paragraph_id")
    if not isinstance(paragraph_id, str) or not PARAGRAPH_ID_RE.fullmatch(paragraph_id):
        add_issue(errors, line_no, sentence_id, "paragraph_id must match SECTION-PP, e.g. DISC-02")
    elif not sentence_id.startswith(paragraph_id + "-"):
        add_issue(errors, line_no, sentence_id, "sentence_id must begin with paragraph_id")

    for field in (
        "section",
        "function",
        "english",
        "chinese",
        "claim_ceiling",
        "previous_link",
        "next_link",
    ):
        if not is_nonempty_string(record.get(field)):
            add_issue(errors, line_no, sentence_id, f"{field} must be a non-empty string")

    claim_type = record.get("claim_type")
    if claim_type not in CLAIM_TYPES:
        add_issue(errors, line_no, sentence_id, f"invalid claim_type {claim_type!r}")

    status = record.get("status")
    if status not in STATUSES:
        add_issue(errors, line_no, sentence_id, f"invalid status {status!r}")
    elif status == "approved":
        if not is_nonempty_string(record.get("approved_by")):
            add_issue(errors, line_no, sentence_id, "approved sentence needs approved_by")
        if not is_nonempty_string(record.get("approved_at")):
            add_issue(errors, line_no, sentence_id, "approved sentence needs approved_at")
    elif record.get("approved_by") not in (None, "") or record.get("approved_at") not in (None, ""):
        add_issue(
            warnings,
            line_no,
            sentence_id,
            "non-approved sentence contains approval metadata",
        )

    risk_flags = record.get("risk_flags")
    if not isinstance(risk_flags, list) or not all(isinstance(flag, str) for flag in risk_flags):
        add_issue(errors, line_no, sentence_id, "risk_flags must be a list of strings")

    evidence_types = validate_evidence(record, line_no, errors, warnings)
    evidence = record.get("evidence") if isinstance(record.get("evidence"), list) else []

    if claim_type == "external_fact" and "literature" not in evidence_types:
        add_issue(errors, line_no, sentence_id, "external_fact requires literature evidence")
    elif claim_type == "study_result" and not (evidence_types & STUDY_EVIDENCE):
        add_issue(errors, line_no, sentence_id, "study_result requires figure/table/analysis/dataset/code evidence")
    elif claim_type == "method" and not (evidence_types & METHOD_EVIDENCE):
        add_issue(errors, line_no, sentence_id, "method requires method_record/literature/dataset/code evidence")
    elif claim_type in {"author_inference", "limitation"} and not evidence:
        add_issue(errors, line_no, sentence_id, f"{claim_type} requires at least one evidence record")
    elif claim_type == "author_inference":
        if not (evidence_types & STUDY_EVIDENCE):
            add_issue(
                warnings,
                line_no,
                sentence_id,
                "author_inference has no current-study evidence; confirm it belongs in this manuscript",
            )
        if "literature" not in evidence_types:
            add_issue(
                warnings,
                line_no,
                sentence_id,
                "author_inference has no literature/theory evidence; confirm the claim ceiling",
            )
    elif claim_type == "objective" and not evidence:
        add_issue(
            warnings,
            line_no,
            sentence_id,
            "objective has no evidence record; link it to the approved blueprint or gap",
        )
    elif claim_type == "transition" and evidence and "rhetorical" not in evidence_types:
        add_issue(
            warnings,
            line_no,
            sentence_id,
            "transition evidence exists but is not labeled rhetorical",
        )


def main() -> int:
    args = parse_args()
    path = Path(args.ledger).expanduser().resolve()
    if not path.is_file():
        print(f"Ledger not found: {path}", file=sys.stderr)
        return 2

    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    record_count = 0

    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_no}: invalid JSON: {exc.msg}")
                continue
            record_count += 1
            validate_record(record, line_no, seen_ids, errors, warnings)

    print(f"Ledger: {path}")
    print(f"Records: {record_count}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")

    for issue in errors:
        print(f"ERROR: {issue}")
    for issue in warnings:
        print(f"WARNING: {issue}")

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
