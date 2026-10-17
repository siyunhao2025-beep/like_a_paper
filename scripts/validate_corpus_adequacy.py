#!/usr/bin/env python3
"""Validate the mandatory corpus-adequacy gate for like-a-paper."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


MIN_SECTION_EXAMPLES = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate journal/author corpus adequacy before corpus-derived writing."
    )
    parser.add_argument("assessment", help="Path to corpus-adequacy.json")
    parser.add_argument("--output", help="Optional JSON verdict path")
    return parser.parse_args()


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def require_keys(model: dict[str, Any], keys: set[str], label: str) -> list[str]:
    return [f"{label}: missing field {key}" for key in sorted(keys - model.keys())]


def validate_section_map(
    value: Any, requested_sections: list[str], label: str
) -> tuple[list[str], list[str], list[str]]:
    schema_errors: list[str] = []
    eligible: list[str] = []
    ineligible: list[str] = []
    if not isinstance(value, dict):
        return [f"{label}: section_examples must be an object"], eligible, requested_sections

    for section in requested_sections:
        count = value.get(section)
        if not is_int(count) or count < 0:
            schema_errors.append(f"{label}: section_examples[{section!r}] must be a non-negative integer")
        elif count >= MIN_SECTION_EXAMPLES:
            eligible.append(section)
        else:
            ineligible.append(section)
    return schema_errors, eligible, ineligible


def add_numeric_floor(
    failures: list[str], model: dict[str, Any], field: str, minimum: int, label: str
) -> None:
    value = model.get(field)
    if is_int(value) and value < minimum:
        failures.append(f"{label}: {field}={value}, requires at least {minimum}")


def add_true_requirement(
    failures: list[str], model: dict[str, Any], field: str, label: str
) -> None:
    if model.get(field) is False:
        failures.append(f"{label}: {field} must be true")


def add_false_requirement(
    failures: list[str], model: dict[str, Any], field: str, label: str
) -> None:
    if model.get(field) is True:
        failures.append(f"{label}: {field} must be false")


def separate_blocked_checks(
    failures: list[str], downstream_fields: tuple[str, ...]
) -> tuple[list[str], list[str]]:
    """Separate prerequisite failures from stability checks that could not be reached."""
    downstream = [
        failure
        for failure in failures
        if any(field in failure for field in downstream_fields)
    ]
    primary = [failure for failure in failures if failure not in downstream]
    if not primary:
        return failures, []
    blocked = [
        failure.replace(" must be true", " is not established because a prerequisite failed")
        for failure in downstream
    ]
    return primary, blocked


JOURNAL_FIELDS = {
    "enabled",
    "usable_full_texts",
    "directly_relevant_full_texts",
    "verified_current_author_guide",
    "independent_author_teams",
    "publication_periods",
    "discovery_papers",
    "validation_papers",
    "section_examples",
    "article_type_matched",
    "holdout_rules_confirmed",
    "major_rule_invalidated",
    "new_high_confidence_rules_last_batch",
    "counterexample_search_documented",
    "phrase_level_traits_excluded",
    "critical_extraction_gaps",
}


AUTHOR_FIELDS = {
    "enabled",
    "usable_full_texts",
    "author_led_full_texts",
    "journals",
    "coauthor_or_lab_clusters",
    "independent_contexts_beyond_journal",
    "matched_controls",
    "control_contexts",
    "role_metadata_fraction",
    "discovery_papers",
    "validation_papers",
    "section_examples",
    "holdout_rules_confirmed",
    "leave_largest_cluster_out_confirmed",
    "major_rule_invalidated",
    "new_high_confidence_rules_last_batch",
    "counterexample_search_documented",
    "phrase_level_traits_excluded",
    "critical_extraction_gaps",
}


def common_schema_checks(
    model: dict[str, Any], required: set[str], label: str
) -> list[str]:
    errors = require_keys(model, required, label)
    boolean_fields = {
        key
        for key in required
        if key
        in {
            "enabled",
            "verified_current_author_guide",
            "article_type_matched",
            "holdout_rules_confirmed",
            "leave_largest_cluster_out_confirmed",
            "major_rule_invalidated",
            "counterexample_search_documented",
            "phrase_level_traits_excluded",
            "critical_extraction_gaps",
        }
    }
    integer_fields = required - boolean_fields - {"section_examples", "role_metadata_fraction"}

    for field in boolean_fields:
        if field in model and not isinstance(model[field], bool):
            errors.append(f"{label}: {field} must be boolean")
    for field in integer_fields:
        if field in model and (not is_int(model[field]) or model[field] < 0):
            errors.append(f"{label}: {field} must be a non-negative integer")
    return errors


def assess_journal(
    model: Any, requested_sections: list[str]
) -> dict[str, Any]:
    label = "journal_model"
    if not isinstance(model, dict):
        return {
            "model": label,
            "schema_errors": [f"{label} must be an object"],
            "failures": [],
            "primary_failures": [],
            "blocked_checks": [],
            "eligible_sections": [],
            "ineligible_sections": requested_sections,
            "global_pass": False,
        }

    schema_errors = common_schema_checks(model, JOURNAL_FIELDS, label)
    section_errors, eligible, ineligible = validate_section_map(
        model.get("section_examples"), requested_sections, label
    )
    schema_errors.extend(section_errors)
    failures: list[str] = []

    add_numeric_floor(failures, model, "usable_full_texts", 8, label)
    add_numeric_floor(failures, model, "directly_relevant_full_texts", 5, label)
    add_numeric_floor(failures, model, "independent_author_teams", 3, label)
    add_numeric_floor(failures, model, "publication_periods", 2, label)
    add_numeric_floor(failures, model, "discovery_papers", 6, label)
    add_numeric_floor(failures, model, "validation_papers", 2, label)

    for field in (
        "enabled",
        "verified_current_author_guide",
        "article_type_matched",
        "holdout_rules_confirmed",
        "counterexample_search_documented",
        "phrase_level_traits_excluded",
    ):
        add_true_requirement(failures, model, field, label)
    for field in ("major_rule_invalidated", "critical_extraction_gaps"):
        add_false_requirement(failures, model, field, label)

    if model.get("new_high_confidence_rules_last_batch") not in (None, 0):
        failures.append(f"{label}: final validation batch introduced a new high-confidence rule")

    usable = model.get("usable_full_texts")
    direct = model.get("directly_relevant_full_texts")
    discovery = model.get("discovery_papers")
    validation = model.get("validation_papers")
    if is_int(usable) and is_int(direct) and direct > usable:
        schema_errors.append(f"{label}: directly_relevant_full_texts cannot exceed usable_full_texts")
    if is_int(usable) and is_int(discovery) and is_int(validation) and discovery + validation != usable:
        schema_errors.append(f"{label}: discovery_papers + validation_papers must equal usable_full_texts")

    failures, blocked_checks = separate_blocked_checks(
        failures, ("holdout_rules_confirmed",)
    )

    return {
        "model": label,
        "schema_errors": schema_errors,
        "failures": failures,
        "primary_failures": failures,
        "blocked_checks": blocked_checks,
        "eligible_sections": eligible,
        "ineligible_sections": ineligible,
        "global_pass": not schema_errors and not failures,
    }


def assess_author(
    model: Any, requested_sections: list[str]
) -> dict[str, Any]:
    label = "author_model"
    if not isinstance(model, dict):
        return {
            "model": label,
            "schema_errors": [f"{label} must be an object"],
            "failures": [],
            "primary_failures": [],
            "blocked_checks": [],
            "eligible_sections": [],
            "ineligible_sections": requested_sections,
            "global_pass": False,
        }

    schema_errors = common_schema_checks(model, AUTHOR_FIELDS, label)
    fraction = model.get("role_metadata_fraction")
    if "role_metadata_fraction" in model and (
        not isinstance(fraction, (int, float))
        or isinstance(fraction, bool)
        or not 0 <= float(fraction) <= 1
    ):
        schema_errors.append(f"{label}: role_metadata_fraction must be a number from 0 to 1")

    section_errors, eligible, ineligible = validate_section_map(
        model.get("section_examples"), requested_sections, label
    )
    schema_errors.extend(section_errors)
    failures: list[str] = []

    add_numeric_floor(failures, model, "usable_full_texts", 10, label)
    add_numeric_floor(failures, model, "author_led_full_texts", 6, label)
    add_numeric_floor(failures, model, "journals", 2, label)
    add_numeric_floor(failures, model, "coauthor_or_lab_clusters", 2, label)
    add_numeric_floor(failures, model, "independent_contexts_beyond_journal", 2, label)
    add_numeric_floor(failures, model, "matched_controls", 4, label)
    add_numeric_floor(failures, model, "control_contexts", 2, label)
    add_numeric_floor(failures, model, "discovery_papers", 8, label)
    add_numeric_floor(failures, model, "validation_papers", 2, label)

    if isinstance(fraction, (int, float)) and not isinstance(fraction, bool) and fraction < 0.60:
        failures.append(f"{label}: role_metadata_fraction={fraction}, requires at least 0.60")

    for field in (
        "enabled",
        "holdout_rules_confirmed",
        "leave_largest_cluster_out_confirmed",
        "counterexample_search_documented",
        "phrase_level_traits_excluded",
    ):
        add_true_requirement(failures, model, field, label)
    for field in ("major_rule_invalidated", "critical_extraction_gaps"):
        add_false_requirement(failures, model, field, label)

    if model.get("new_high_confidence_rules_last_batch") not in (None, 0):
        failures.append(f"{label}: final validation batch introduced a new high-confidence rule")

    usable = model.get("usable_full_texts")
    led = model.get("author_led_full_texts")
    discovery = model.get("discovery_papers")
    validation = model.get("validation_papers")
    if is_int(usable) and is_int(led) and led > usable:
        schema_errors.append(f"{label}: author_led_full_texts cannot exceed usable_full_texts")
    if is_int(usable) and is_int(discovery) and is_int(validation) and discovery + validation != usable:
        schema_errors.append(f"{label}: discovery_papers + validation_papers must equal usable_full_texts")

    failures, blocked_checks = separate_blocked_checks(
        failures,
        ("holdout_rules_confirmed", "leave_largest_cluster_out_confirmed"),
    )

    return {
        "model": label,
        "schema_errors": schema_errors,
        "failures": failures,
        "primary_failures": failures,
        "blocked_checks": blocked_checks,
        "eligible_sections": eligible,
        "ineligible_sections": ineligible,
        "global_pass": not schema_errors and not failures,
    }


def print_model(result: dict[str, Any]) -> None:
    print(f"\n{result['model']}")
    print(f"  Global requirements: {'PASS' if result['global_pass'] else 'FAIL'}")
    print(f"  Eligible sections: {', '.join(result['eligible_sections']) or 'none'}")
    print(f"  Ineligible sections: {', '.join(result['ineligible_sections']) or 'none'}")
    for error in result["schema_errors"]:
        print(f"  SCHEMA ERROR: {error}")
    for failure in result["failures"]:
        print(f"  REQUIREMENT FAIL: {failure}")
    for blocked in result.get("blocked_checks", []):
        print(f"  NOT ESTABLISHED: {blocked}")


def diagnostic_labels(
    mode: str, results: dict[str, dict[str, Any]], data: dict[str, Any]
) -> list[str]:
    """Return non-verdict routing labels. Labels never change eligibility."""
    labels: list[str] = []
    if mode == "hybrid":
        if results.get("journal", {}).get("global_pass") and not results.get(
            "author", {}
        ).get("global_pass"):
            labels.append("JOURNAL_ONLY_ELIGIBLE")
        if results.get("author", {}).get("global_pass") and not results.get(
            "journal", {}
        ).get("global_pass"):
            labels.append("AUTHOR_ONLY_ELIGIBLE")

    author = data.get("author_model")
    if isinstance(author, dict) and not results.get("author", {}).get("global_pass", True):
        def author_floor(field: str, minimum: int) -> bool:
            value = author.get(field)
            return is_int(value) and value >= minimum

        exploratory_floors = (
            author_floor("usable_full_texts", 8)
            and author_floor("author_led_full_texts", 2)
            and author_floor("journals", 2)
            and author_floor("coauthor_or_lab_clusters", 2)
            and author_floor("matched_controls", 4)
            and author_floor("control_contexts", 2)
        )
        if exploratory_floors:
            labels.append("EXPLORATORY_AUTHOR_PROFILE_ONLY")

    journal = data.get("journal_model")
    if (
        isinstance(journal, dict)
        and not results.get("journal", {}).get("global_pass", True)
        and journal.get("verified_current_author_guide") is True
    ):
        labels.append("FORMAL_REQUIREMENTS_ONLY")
    return labels


def main() -> int:
    args = parse_args()
    path = Path(args.assessment).expanduser().resolve()
    if not path.is_file():
        print(f"Assessment not found: {path}", file=sys.stderr)
        return 2

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read assessment: {exc}", file=sys.stderr)
        return 2

    if not isinstance(data, dict):
        print("Assessment root must be an object.", file=sys.stderr)
        return 2

    mode = data.get("mode")
    requested_sections = data.get("requested_sections")
    if mode not in {"journal", "author", "hybrid"}:
        print("mode must be journal, author, or hybrid.", file=sys.stderr)
        return 2
    if (
        not isinstance(requested_sections, list)
        or not requested_sections
        or not all(isinstance(section, str) and section.strip() for section in requested_sections)
        or len(set(requested_sections)) != len(requested_sections)
    ):
        print("requested_sections must be a non-empty list of unique strings.", file=sys.stderr)
        return 2

    results: dict[str, dict[str, Any]] = {}
    if mode in {"journal", "hybrid"}:
        results["journal"] = assess_journal(data.get("journal_model"), requested_sections)
    if mode in {"author", "hybrid"}:
        results["author"] = assess_author(data.get("author_model"), requested_sections)

    schema_errors = [
        error
        for result in results.values()
        for error in result["schema_errors"]
    ]
    global_pass = all(result["global_pass"] for result in results.values())
    eligible_intersection = [
        section
        for section in requested_sections
        if all(section in result["eligible_sections"] for result in results.values())
    ]
    downgrade_labels = diagnostic_labels(mode, results, data)

    if schema_errors:
        verdict = "FAIL"
        exit_code = 2
        next_action = "Fix assessment schema errors before interpreting adequacy."
    elif not global_pass:
        verdict = "FAIL"
        exit_code = 1
        if mode == "hybrid":
            passing = [name for name, result in results.items() if result["global_pass"]]
            next_action = (
                "Hybrid mode is not eligible. Add evidence or explicitly downgrade to: "
                + (", ".join(passing) if passing else "a non-corpus-derived workflow")
                + "."
            )
        else:
            next_action = "Add or replace corpus material; do not start corpus-derived manuscript writing."
    elif len(eligible_intersection) < len(requested_sections):
        verdict = "SECTION_LIMITED"
        exit_code = 3
        next_action = (
            "Narrow the authorized writing scope to the eligible sections or add corpus material "
            "for the missing sections."
        )
    else:
        verdict = "PASS"
        exit_code = 0
        next_action = "Proceed to the writing contract; manuscript drafting still requires Gate 1 approval."

    report = {
        "assessment": str(path),
        "mode": mode,
        "requested_sections": requested_sections,
        "verdict": verdict,
        "eligible_sections": eligible_intersection,
        "models": results,
        "diagnostic_labels": downgrade_labels,
        "next_action": next_action,
    }

    print(f"Corpus adequacy verdict: {verdict}")
    print(f"Mode: {mode}")
    print(f"Requested sections: {', '.join(requested_sections)}")
    for result in results.values():
        print_model(result)
    print(f"\nEligible intersection: {', '.join(eligible_intersection) or 'none'}")
    print(f"Diagnostic labels: {', '.join(downgrade_labels) or 'none'}")
    print(f"Next action: {next_action}")

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Path.write_text gained a newline argument only in Python 3.10.
        with output_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(f"Verdict JSON: {output_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
