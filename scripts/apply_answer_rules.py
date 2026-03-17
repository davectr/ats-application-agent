#!/usr/bin/env python3
"""Apply answer rules to scout report fields.

Matches question labels against answer rules in profile.json using
case-insensitive regex. Implements full precedence order:
  1. always_ask checked first
  2. Answer rules in array order (first match wins)
  3. skip_if_optional evaluated after rule match
  4. No match → surface to user

Usage:
    python scripts/apply_answer_rules.py --scout-report tasks/.../scout_report.json --profile profile.json
    python scripts/apply_answer_rules.py --fields '[...]' --profile profile.json
"""

import argparse
import json
import re
import sys
from pathlib import Path


def load_profile(profile_path: str) -> dict:
    """Load and return profile.json."""
    path = Path(profile_path)
    if not path.exists():
        print(f"Error: profile not found: {profile_path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_scout_report(report_path: str) -> dict:
    """Load and return scout_report.json."""
    path = Path(report_path)
    if not path.exists():
        print(f"Error: scout report not found: {report_path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def matches_pattern(text: str, pattern: str) -> bool:
    """Case-insensitive regex match of pattern against text."""
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        # Fall back to literal substring match if regex is invalid
        return pattern.lower() in text.lower()


def check_always_ask(label: str, always_ask: list[str]) -> bool:
    """Check if a question label matches any always_ask pattern."""
    for pattern in always_ask:
        if matches_pattern(label, pattern):
            return True
    return False


def evaluate_rule(rule: dict, field: dict) -> dict:
    """Evaluate an answer rule against a field.

    Returns a resolution dict with:
        category: "auto_answered" | "skipped" | "needs_input"
        answer: str | None
        rule_matched: bool
    """
    # Handle skip_if_optional behavior
    if rule.get("behavior") == "skip_if_optional":
        if not field.get("required", False):
            return {
                "category": "skipped",
                "answer": None,
                "rule_matched": True,
            }
        # Field is required and has skip_if_optional — fall through to fallback
        fallback = rule.get("fallback", "ASK_USER")
        if fallback == "ASK_USER":
            return {
                "category": "needs_input",
                "answer": None,
                "rule_matched": True,
            }
        return {
            "category": "auto_answered",
            "answer": fallback,
            "rule_matched": True,
        }

    # Handle conditional logic (logic array)
    if "logic" in rule:
        field_options = field.get("options", [])
        options_text = " ".join(str(o).lower() for o in field_options)

        for condition in rule["logic"]:
            cond_type = condition.get("condition")

            if cond_type == "options_contain":
                # Check if any option matches the condition value pattern
                value_pattern = condition.get("value", "")
                if matches_pattern(options_text, value_pattern):
                    return {
                        "category": "auto_answered",
                        "answer": condition["answer"],
                        "rule_matched": True,
                    }

            elif cond_type == "default":
                return {
                    "category": "auto_answered",
                    "answer": condition["answer"],
                    "rule_matched": True,
                }

        # No condition matched
        return {
            "category": "needs_input",
            "answer": None,
            "rule_matched": True,
        }

    # Simple answer rule
    if "answer" in rule:
        return {
            "category": "auto_answered",
            "answer": rule["answer"],
            "rule_matched": True,
        }

    # Rule matched but has no actionable resolution
    return {
        "category": "needs_input",
        "answer": None,
        "rule_matched": True,
    }


def apply_rules(fields: list[dict], profile: dict) -> list[dict]:
    """Apply answer rules to a list of fields.

    Args:
        fields: List of field dicts from scout_report.json
        profile: Parsed profile.json dict

    Returns:
        List of annotated field dicts with resolution info added:
            resolution_category: "auto_filled" | "auto_answered" | "skipped" | "needs_input"
            resolution_answer: str | None (the resolved answer text)
    """
    answer_rules = profile.get("answer_rules", [])
    always_ask = profile.get("always_ask", [])

    annotated = []
    for field in fields:
        result = resolve_field(field, answer_rules, always_ask, profile)
        annotated_field = {**field, **result}
        annotated.append(annotated_field)

    return annotated


def resolve_field(field: dict, answer_rules: list, always_ask: list, profile: dict) -> dict:
    """Resolve a single field against the rules engine.

    Returns:
        resolution_category: str
        resolution_answer: str | None
    """
    label = field.get("label", "")

    # Fields already marked as auto_fill by the scout subagent
    if field.get("auto_fill"):
        profile_key = field.get("profile_key", "")
        value = resolve_profile_value(profile_key, profile)
        return {
            "resolution_category": "auto_filled",
            "resolution_answer": value,
        }

    # --- Precedence 1: always_ask ---
    if check_always_ask(label, always_ask):
        return {
            "resolution_category": "needs_input",
            "resolution_answer": None,
        }

    # --- Precedence 2: answer rules (first match wins) ---
    for rule in answer_rules:
        pattern = rule.get("pattern", "")
        if matches_pattern(label, pattern):
            result = evaluate_rule(rule, field)
            return {
                "resolution_category": result["category"],
                "resolution_answer": result["answer"],
            }

    # --- Precedence 3: no match → needs input ---
    return {
        "resolution_category": "needs_input",
        "resolution_answer": None,
    }


def resolve_profile_value(profile_key: str, profile: dict) -> str:
    """Resolve a dotted profile key to its value.

    Examples:
        "contact.first_name" → profile["contact"]["first_name"]
        "demographics.work_authorization" → profile["demographics"]["work_authorization"]
        "education[0].degree" → profile["education"][0]["degree"]
        "work_history[0].company" → profile["work_history"][0]["company"]
        "_resume_file" → "(resume file)"
    """
    if profile_key == "_resume_file":
        return "(resume file)"

    if not profile_key:
        return ""

    parts = profile_key.replace("[", ".[").split(".")
    current = profile

    for part in parts:
        if not part:
            continue
        if part.startswith("[") and part.endswith("]"):
            # Array index
            try:
                idx = int(part[1:-1])
                current = current[idx]
            except (ValueError, IndexError, TypeError):
                return ""
        else:
            if isinstance(current, dict):
                current = current.get(part, "")
            else:
                return ""

    return str(current) if current else ""


def main():
    parser = argparse.ArgumentParser(
        description="Apply answer rules to scout report fields"
    )
    parser.add_argument(
        "--scout-report",
        help="Path to scout_report.json"
    )
    parser.add_argument(
        "--fields",
        help="JSON array of fields (alternative to --scout-report)"
    )
    parser.add_argument(
        "--profile", default="profile.json",
        help="Path to profile.json"
    )

    args = parser.parse_args()

    profile = load_profile(args.profile)

    if args.scout_report:
        report = load_scout_report(args.scout_report)
        # Flatten all fields from all pages
        all_fields = []
        for page in report.get("pages", []):
            all_fields.extend(page.get("fields", []))
    elif args.fields:
        all_fields = json.loads(args.fields)
    else:
        print("Error: provide --scout-report or --fields", file=sys.stderr)
        sys.exit(1)

    annotated = apply_rules(all_fields, profile)
    print(json.dumps(annotated, indent=2))


if __name__ == "__main__":
    main()
