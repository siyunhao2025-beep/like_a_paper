#!/usr/bin/env python3
"""Create a durable project workspace for the like-a-paper workflow."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


DIRECTORIES = (
    "00_intake",
    "01_corpus/journal",
    "01_corpus/author",
    "01_corpus/controls",
    "01_corpus/text",
    "02_distillation",
    "03_contract",
    "04_blueprint",
    "05_sentence_ledger",
    "06_manuscript",
    "07_audit",
)

DEFAULT_SECTIONS = (
    "Abstract",
    "Introduction",
    "Data and methods",
    "Results",
    "Discussion",
    "Conclusions",
)


INTAKE_TEMPLATE = """# Intake checklist

## Scientific scope

- [ ] Research question
- [ ] Intended contribution
- [ ] Target population, period, region, and scale
- [ ] Target journal and article type

## Evidence

- [ ] Dataset names and versions
- [ ] Inclusion, exclusion, and quality-control rules
- [ ] Method and parameter record
- [ ] Code/configuration location
- [ ] Figures and tables
- [ ] Underlying numerical/statistical outputs
- [ ] Uncertainty estimates
- [ ] Known limitations
- [ ] Existing manuscript and bibliography

## Freeze review

- Conflicting numbers:
- Missing provenance:
- Figure/text mismatches:
- Unresolved analysis choices:
- Claims that may exceed the evidence:
- Evidence state: open
"""


CONTRACT_TEMPLATE = """# Writing contract

Status: drafted

## Corpus mode

## Target journal and article type

## Evidence and claim ceiling

## Global rules

## Title

## Abstract

## Introduction

## Data and methods

## Results

## Discussion

## Limitations

## Conclusions

## Captions and tables

## Prohibited claims and practices

## Unresolved items
"""


APPROVAL_TEMPLATE = """# Approval record

Record the user's exact approval text, scope, artifact version/hash when available, and timestamp.

| Gate or batch | Status | Scope | User wording | Timestamp | Notes |
|---|---|---|---|---|---|
| Gate 1: writing contract | pending |  |  |  |  |
| Gate 2: paragraph blueprint | pending |  |  |  |  |
"""


BLUEPRINT_TEMPLATE = """# Paragraph blueprint

Status: drafted

## Paragraph record template

- Paragraph ID:
- Section:
- Scientific question:
- Rhetorical function:
- Topic-sentence purpose:
- Study evidence:
- External evidence:
- Claim ceiling:
- Previous-paragraph link:
- Next-paragraph bridge:
- Prohibited conclusion:
- Open issue:
"""


AUDIT_TEMPLATE = """# Final reverse audit

- [ ] Every final sentence has an approved ledger entry
- [ ] Final wording matches approved wording
- [ ] Numbers, units, signs, and denominators match source artifacts
- [ ] Citations support the exact nearby propositions
- [ ] Comparison conditions are explicit
- [ ] Observation, interpretation, and speculation remain distinct
- [ ] Causal language stays within the design
- [ ] Abstract and conclusion remain within the body evidence
- [ ] Paragraph transitions follow the approved blueprint
- [ ] Phrase-overlap warnings were reviewed manually
- [ ] Unresolved items are closed or explicitly accepted
"""


CORPUS_COLUMNS = (
    "source_id",
    "citation",
    "identifier",
    "local_path_or_url",
    "journal",
    "year",
    "article_type",
    "topic_method_scale",
    "relevance_level",
    "full_text_usable",
    "extraction_quality",
    "target_author_role",
    "author_led",
    "contribution_statement",
    "coauthor_lab_cluster",
    "context_id",
    "time_band",
    "corpus_role",
    "discovery_or_validation",
    "matched_control_for",
    "sections_available",
    "sections_informed",
    "inclusion_reason",
    "cannot_support",
    "extraction_limitations",
    "status",
)


def empty_section_map() -> dict[str, int]:
    return {section: 0 for section in DEFAULT_SECTIONS}


def adequacy_template(mode: str) -> dict[str, object]:
    return {
        "mode": mode,
        "requested_sections": list(DEFAULT_SECTIONS),
        "journal_model": {
            "enabled": mode in {"journal", "hybrid"},
            "usable_full_texts": 0,
            "directly_relevant_full_texts": 0,
            "verified_current_author_guide": False,
            "independent_author_teams": 0,
            "publication_periods": 0,
            "discovery_papers": 0,
            "validation_papers": 0,
            "section_examples": empty_section_map(),
            "article_type_matched": False,
            "holdout_rules_confirmed": False,
            "major_rule_invalidated": False,
            "new_high_confidence_rules_last_batch": 0,
            "counterexample_search_documented": False,
            "phrase_level_traits_excluded": False,
            "critical_extraction_gaps": False,
        },
        "author_model": {
            "enabled": mode in {"author", "hybrid"},
            "usable_full_texts": 0,
            "author_led_full_texts": 0,
            "journals": 0,
            "coauthor_or_lab_clusters": 0,
            "independent_contexts_beyond_journal": 0,
            "matched_controls": 0,
            "control_contexts": 0,
            "role_metadata_fraction": 0.0,
            "discovery_papers": 0,
            "validation_papers": 0,
            "section_examples": empty_section_map(),
            "holdout_rules_confirmed": False,
            "leave_largest_cluster_out_confirmed": False,
            "major_rule_invalidated": False,
            "new_high_confidence_rules_last_batch": 0,
            "counterexample_search_documented": False,
            "phrase_level_traits_excluded": False,
            "critical_extraction_gaps": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an empty like-a-paper project workspace."
    )
    parser.add_argument("project_directory", help="New or empty project directory")
    parser.add_argument(
        "--mode",
        choices=("journal", "author", "hybrid"),
        default="hybrid",
        help="Corpus distillation mode (default: hybrid)",
    )
    return parser.parse_args()


def write_text(path: Path, content: str) -> None:
    # Path.write_text gained a newline argument only in Python 3.10.
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def cleanup_partial_init(root: Path) -> None:
    # Best effort: remove everything written during the failed initialization
    # so the non-empty-directory guard does not block a retry.
    for child in root.iterdir():
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink()
        except OSError:
            pass


def main() -> int:
    args = parse_args()
    root = Path(args.project_directory).expanduser().resolve()

    if root.exists() and any(root.iterdir()):
        print(
            f"Refusing to initialize a non-empty directory: {root}",
            file=sys.stderr,
        )
        return 2

    root.mkdir(parents=True, exist_ok=True)
    try:
        for relative in DIRECTORIES:
            (root / relative).mkdir(parents=True, exist_ok=True)

        created_at = datetime.now(timezone.utc).isoformat()
        state = {
            "skill": "like-a-paper",
            "mode": args.mode,
            "created_at": created_at,
            "evidence_state": "open",
            "corpus_adequacy_state": "not_assessed",
            "contract_state": "not_started",
            "blueprint_state": "not_started",
            "section_states": {},
            "manuscript_state": "not_started",
            "last_user_approval": None,
        }
        write_text(root / "project.json", json.dumps(state, indent=2, ensure_ascii=False) + "\n")
        write_text(root / "00_intake" / "intake-checklist.md", INTAKE_TEMPLATE)
        write_text(root / "00_intake" / "evidence-register.md", "# Evidence register\n\n")
        write_text(root / "00_intake" / "unresolved-items.md", "# Unresolved items\n\n")
        write_text(root / "02_distillation" / "distillation-report.md", "# Corpus distillation report\n\n")
        write_text(
            root / "02_distillation" / "corpus-adequacy.json",
            json.dumps(adequacy_template(args.mode), indent=2, ensure_ascii=False) + "\n",
        )
        write_text(
            root / "02_distillation" / "corpus-adequacy-report.md",
            "# Corpus adequacy report\n\nVerdict: not assessed\n",
        )
        write_text(root / "03_contract" / "writing-contract.md", CONTRACT_TEMPLATE)
        write_text(root / "03_contract" / "approval-record.md", APPROVAL_TEMPLATE)
        write_text(root / "04_blueprint" / "paragraph-blueprint.md", BLUEPRINT_TEMPLATE)
        write_text(root / "05_sentence_ledger" / "sentence_ledger.jsonl", "")
        write_text(root / "06_manuscript" / "manuscript.md", "# Manuscript\n\n")
        write_text(root / "07_audit" / "final-audit.md", AUDIT_TEMPLATE)

        corpus_path = root / "01_corpus" / "corpus-register.csv"
        with corpus_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(CORPUS_COLUMNS)
    except BaseException:
        # A failed initialization must not leave a half-built workspace
        # behind the non-empty-directory guard.
        cleanup_partial_init(root)
        raise

    print(f"Initialized like-a-paper workspace: {root}")
    print(f"Mode: {args.mode}")
    print("Next: complete 00_intake/intake-checklist.md and register the corpus.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
