#!/usr/bin/env python3
"""Render a like-a-paper JSONL ledger as a compact review or full audit Markdown file."""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a JSONL sentence ledger to Markdown.")
    parser.add_argument("ledger", help="Path to sentence_ledger.jsonl")
    parser.add_argument("--output", help="Output Markdown path; stdout when omitted")
    parser.add_argument(
        "--view",
        choices=("review", "audit"),
        default="review",
        help="Compact four-field user review (default) or complete audit view",
    )
    return parser.parse_args()


def text(value: Any, fallback: str = "—") -> str:
    if value is None:
        return fallback
    rendered = str(value).strip()
    return rendered or fallback


def load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_no}: invalid JSON: {exc.msg}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"line {line_no}: record must be an object")
            records.append(record)
    return records


def render_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, list) or not evidence:
        return ["- No evidence record (valid only for a justified rhetorical or objective sentence)."]

    lines: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            lines.append("- Invalid evidence item.")
            continue
        evidence_id = text(item.get("evidence_id"))
        evidence_type = text(item.get("evidence_type"))
        relation = text(item.get("support_relation"))
        citation = text(item.get("citation"), "")
        locator = text(item.get("locator"))
        source_text_type = text(item.get("source_text_type"))
        source_note = text(item.get("source_text"))
        label = f"- **{evidence_id}** — `{evidence_type}` / `{relation}`"
        if citation:
            label += f" — {citation}"
        lines.append(label)
        lines.append(f"  - Locator: {locator}")
        lines.append(f"  - {source_text_type}: {source_note}")
    return lines


def render_review_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, list) or not evidence:
        return ["- 未记录依据；仅在经过说明的修辞句或研究目标句中可以接受。"]

    labels = {
        "literature": "文献",
        "figure": "本研究图",
        "table": "本研究表",
        "analysis": "本研究分析",
        "dataset": "本研究数据",
        "method_record": "方法记录",
        "code": "代码记录",
        "journal_rule": "期刊规则",
        "user_decision": "已批准决定",
        "rhetorical": "段落逻辑",
    }
    relation_labels = {
        "direct": "直接支撑",
        "partial": "部分支撑",
        "analogous": "类比支撑",
        "contextual": "背景支撑",
        "methodological": "方法支撑",
        "contrasting": "对照关系",
        "rhetorical": "修辞衔接",
    }

    lines: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            lines.append("- 依据记录格式无效。")
            continue
        evidence_type = text(item.get("evidence_type"))
        relation = text(item.get("support_relation"))
        citation = text(item.get("citation"), "")
        locator = text(item.get("locator"))
        source_text_type = text(item.get("source_text_type"))
        source_note = text(item.get("source_text"))
        evidence_id = text(item.get("evidence_id"))
        label = labels.get(evidence_type, evidence_type)
        relation_label = relation_labels.get(relation, relation)

        if evidence_type == "literature":
            note_kind = "原文短摘录" if source_text_type == "excerpt" else "忠实来源说明（非逐字引文）"
            lines.append(
                f"- **{label}｜{relation_label}**：{citation or evidence_id}；{note_kind}：“{source_note}”；位置：{locator}"
            )
        elif evidence_type == "rhetorical":
            lines.append(
                f"- **{label}｜无需外部引用**：{source_note}；位置：{locator}"
            )
        else:
            lines.append(
                f"- **{label}｜{relation_label}**：{evidence_id}；{source_note}；位置：{locator}"
            )
    return lines


def group_records(
    records: list[dict[str, Any]],
) -> OrderedDict[str, OrderedDict[str, list[dict[str, Any]]]]:
    grouped: OrderedDict[str, OrderedDict[str, list[dict[str, Any]]]] = OrderedDict()
    for record in records:
        section = text(record.get("section"), "Unspecified section")
        paragraph = text(record.get("paragraph_id"), "Unspecified paragraph")
        grouped.setdefault(section, OrderedDict()).setdefault(paragraph, []).append(record)
    return grouped


def render_review(records: list[dict[str, Any]]) -> str:
    grouped = group_records(records)
    lines = [
        "# 逐句双语审阅稿",
        "",
        f"候选句总数：{len(records)}",
        "",
        "> 默认仅显示 English、中文、对应依据、修改说明。完整内部审计字段仍保存在 JSONL 台账中。",
        "",
    ]

    for section, paragraphs in grouped.items():
        lines.extend([f"## {section}", ""])
        # Number sentences within each review unit so "第 N 句" matches the
        # per-section approval interaction instead of drifting across sections.
        sentence_number = 0
        for paragraph_records in paragraphs.values():
            for record in paragraph_records:
                sentence_number += 1
                change_note = text(
                    record.get("change_note"),
                    text(record.get("notes"), "未记录修改说明。"),
                )
                lines.extend(
                    [
                        f"### 第 {sentence_number} 句",
                        "",
                        "**English**",
                        "",
                        text(record.get("english")),
                        "",
                        "**中文**",
                        "",
                        text(record.get("chinese")),
                        "",
                        "**对应依据**",
                        "",
                    ]
                )
                lines.extend(render_review_evidence(record.get("evidence")))
                lines.extend(
                    [
                        "",
                        "**修改说明**",
                        "",
                        change_note,
                        "",
                    ]
                )

        lines.extend(
            [
                "> 这一部分是否需要修改？如果不需要，请回复“无需修改，继续”。",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def render_audit(records: list[dict[str, Any]]) -> str:
    grouped = group_records(records)

    lines = [
        "# Bilingual sentence ledger",
        "",
        f"Total candidate sentences: {len(records)}",
        "",
        "> This document is an audit and approval surface, not the clean submission manuscript.",
        "",
    ]

    for section, paragraphs in grouped.items():
        lines.extend([f"## {section}", ""])
        for paragraph, paragraph_records in paragraphs.items():
            lines.extend([f"### {paragraph}", ""])
            for record in paragraph_records:
                sentence_id = text(record.get("sentence_id"))
                function = text(record.get("function"))
                status = text(record.get("status"))
                lines.extend(
                    [
                        f"#### {sentence_id} — {function} — `{status}`",
                        "",
                        "**English**",
                        "",
                        text(record.get("english")),
                        "",
                        "**中文**",
                        "",
                        text(record.get("chinese")),
                        "",
                        "**Claim type and ceiling**",
                        "",
                        f"- Type: `{text(record.get('claim_type'))}`",
                        f"- Ceiling: {text(record.get('claim_ceiling'))}",
                        "",
                        "**Evidence**",
                        "",
                    ]
                )
                lines.extend(render_evidence(record.get("evidence")))
                lines.extend(
                    [
                        "",
                        "**Logic**",
                        "",
                        f"- Previous: {text(record.get('previous_link'))}",
                        f"- Next: {text(record.get('next_link'))}",
                        "",
                        "**Change note**",
                        "",
                        text(record.get("change_note"), text(record.get("notes"), "—")),
                        "",
                        "**Risks and review**",
                        "",
                    ]
                )
                flags = record.get("risk_flags")
                if isinstance(flags, list) and flags:
                    lines.extend(f"- `{text(flag)}`" for flag in flags)
                else:
                    lines.append("- No active risk flag recorded.")

                approved_by = text(record.get("approved_by"), "")
                approved_at = text(record.get("approved_at"), "")
                if approved_by or approved_at:
                    lines.append(f"- Approval: {approved_by or 'unspecified'} at {approved_at or 'unspecified'}")
                notes = text(record.get("notes"), "")
                if notes:
                    lines.append(f"- Notes: {notes}")
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    input_path = Path(args.ledger).expanduser().resolve()
    if not input_path.is_file():
        print(f"Ledger not found: {input_path}", file=sys.stderr)
        return 2

    try:
        records = load_records(input_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    output = render_review(records) if args.view == "review" else render_audit(records)
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Path.write_text gained a newline argument only in Python 3.10.
        with output_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(output)
        print(f"Rendered {len(records)} sentences in {args.view} view to {output_path}")
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
