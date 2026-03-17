#!/usr/bin/env python3
"""Generate Obsidian markdown questionnaire from scout reports and answer rules.

Reads scout reports from task directories, applies answer rules via
apply_answer_rules.py module, and produces a single Obsidian markdown
note with all jobs in the batch.

Usage:
    python scripts/generate_questionnaire.py \
        --task-dirs tasks/2026-03-16_company1_role1,tasks/2026-03-16_company2_role2 \
        --profile profile.json \
        --config config.json

    # Output to custom path instead of Obsidian folder:
    python scripts/generate_questionnaire.py \
        --task-dirs tasks/2026-03-16_company1_role1 \
        --profile profile.json \
        --config config.json \
        --output test-data/test_questionnaire.md
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

# Add scripts dir to path for apply_answer_rules import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_answer_rules import apply_rules, load_profile


def load_config(config_path: str) -> dict:
    """Load and return config.json."""
    path = Path(config_path)
    if not path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_scout_report(task_dir: str) -> dict | None:
    """Load scout_report.json from a task directory."""
    report_file = Path(task_dir) / "scout_report.json"
    if not report_file.exists():
        print(f"Warning: scout_report.json not found in {task_dir}", file=sys.stderr)
        return None
    with open(report_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_task(task_dir: str) -> dict | None:
    """Load task.json from a task directory."""
    task_file = Path(task_dir) / "task.json"
    if not task_file.exists():
        print(f"Warning: task.json not found in {task_dir}", file=sys.stderr)
        return None
    with open(task_file, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_job_section(
    job_number: int,
    task: dict,
    report: dict,
    annotated_fields: list[dict],
) -> str:
    """Generate the markdown section for a single job.

    Returns the complete markdown string for this job's questionnaire section.
    """
    job_id = task["job_id"]
    company = task["company"]
    title = task["title"]
    ats_platform = report.get("ats_platform") or "unknown"
    app_url = report.get("application_url") or "N/A"

    # Get resume filename from task
    resume_path = task.get("resume_path", "")
    resume_filename = Path(resume_path).name if resume_path else "N/A"

    lines = []
    lines.append(f"## {job_number}. {company} — {title} <!-- job_id: {job_id} -->")
    lines.append(f"**ATS Platform:** {ats_platform}")
    lines.append(f"**Application URL:** {app_url}")
    lines.append(f"**Resume:** {resume_filename}")
    lines.append("**Status:** awaiting answers")
    lines.append("")

    # Categorize fields
    auto_filled = [f for f in annotated_fields if f["resolution_category"] == "auto_filled"]
    auto_answered = [f for f in annotated_fields if f["resolution_category"] == "auto_answered"]
    needs_input = [f for f in annotated_fields if f["resolution_category"] == "needs_input"]
    skipped = [f for f in annotated_fields if f["resolution_category"] == "skipped"]

    # --- Auto-Filled from Profile ---
    lines.append("### Auto-Filled from Profile")
    if auto_filled:
        for field in auto_filled:
            value = field.get("resolution_answer", "")
            lines.append(f"- {field['label']}: {value} <!-- field_id: {field['field_id']} -->")
    else:
        lines.append("- (none)")
    lines.append("(shown for transparency, no action needed)")
    lines.append("")

    # --- Auto-Answered from Rules ---
    lines.append("### Auto-Answered from Rules")
    if auto_answered:
        for field in auto_answered:
            value = field.get("resolution_answer", "")
            lines.append(f"- {field['label']}: {value} <!-- field_id: {field['field_id']} -->")
    else:
        lines.append("- (none)")
    lines.append("(review and override if incorrect)")
    lines.append("")

    # --- Needs Your Input ---
    lines.append("### Needs Your Input")
    lines.append("")
    if needs_input:
        for i, field in enumerate(needs_input, 1):
            field_type = field.get("type", "text")
            required = "yes" if field.get("required") else "no"
            lines.append(f"**Q{i}: {field['label']}** <!-- field_id: {field['field_id']} -->")
            lines.append(f"Type: {field_type}")

            # Show options for select/radio fields
            if field_type in ("select", "radio") and field.get("options"):
                options_str = ", ".join(field["options"])
                lines.append(f"Options: {options_str}")

            lines.append(f"Required: {required}")
            lines.append("Answer:")
            lines.append("Save Rule:")
            lines.append("")
    else:
        lines.append("(all fields auto-filled or auto-answered)")
        lines.append("")

    # --- Skipped Fields (informational) ---
    if skipped:
        lines.append("### Skipped (optional, auto-skipped by rules)")
        for field in skipped:
            lines.append(f"- {field['label']} <!-- field_id: {field['field_id']} -->")
        lines.append("")

    return "\n".join(lines)


def generate_questionnaire(
    task_dirs: list[str],
    profile_path: str,
    config_path: str,
    output_path: str | None = None,
) -> str:
    """Generate the full Obsidian questionnaire markdown.

    Args:
        task_dirs: List of task directory paths
        profile_path: Path to profile.json
        config_path: Path to config.json
        output_path: Override output path (default: config obsidian path)

    Returns:
        Path to the generated questionnaire file.
    """
    profile = load_profile(profile_path)
    config = load_config(config_path)

    # Determine output path
    if output_path:
        out_path = Path(output_path)
    else:
        obsidian_dir = Path(config["obsidian_output_path"])
        obsidian_dir.mkdir(parents=True, exist_ok=True)
        batch_date = date.today().isoformat()
        # Try to get batch date from first task
        for td in task_dirs:
            task = load_task(td)
            if task and task.get("batch_date"):
                batch_date = task["batch_date"]
                break
        out_path = obsidian_dir / f"{batch_date} Applications.md"

    # Header with structural warning
    sections = []
    sections.append(f"# Applications — {batch_date if 'batch_date' in dir() else date.today().isoformat()}")
    sections.append("")
    sections.append("> **Do not delete** `## N.` headers, `**Q` prefixes, `Answer:` labels, or `<!-- field_id -->` / `<!-- job_id -->` comments.")
    sections.append("> These are invisible in Obsidian's rendered view but required for the parser.")
    sections.append("> You may add blank lines, reorder lines within a section, or edit answer text freely.")
    sections.append("")
    sections.append("---")
    sections.append("")

    # Generate sections for each job
    job_number = 0
    for td in task_dirs:
        task = load_task(td)
        if not task:
            continue

        report = load_scout_report(td)
        if not report:
            continue

        # Skip non-open listings
        if report.get("listing_status") != "open":
            continue

        job_number += 1

        # Flatten all fields from all pages
        all_fields = []
        for page in report.get("pages", []):
            all_fields.extend(page.get("fields", []))

        # Apply answer rules
        annotated_fields = apply_rules(all_fields, profile)

        # Generate section
        section = generate_job_section(job_number, task, report, annotated_fields)
        sections.append(section)
        sections.append("---")
        sections.append("")

    if job_number == 0:
        sections.append("No jobs with open listings found in this batch.")
        sections.append("")

    content = "\n".join(sections)

    # Determine batch date for header
    batch_date_val = date.today().isoformat()
    for td in task_dirs:
        task = load_task(td)
        if task and task.get("batch_date"):
            batch_date_val = task["batch_date"]
            break

    # Fix the header with actual batch date
    content = content.replace(
        f"# Applications — {date.today().isoformat()}",
        f"# Applications — {batch_date_val}",
        1
    )

    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Questionnaire written: {out_path}")
    return str(out_path)


def main():
    parser = argparse.ArgumentParser(
        description="Generate Obsidian questionnaire from scout reports"
    )
    parser.add_argument(
        "--task-dirs", required=True,
        help="Comma-separated list of task directory paths"
    )
    parser.add_argument(
        "--profile", default="profile.json",
        help="Path to profile.json"
    )
    parser.add_argument(
        "--config", default="config.json",
        help="Path to config.json"
    )
    parser.add_argument(
        "--output",
        help="Override output path (default: Obsidian folder from config)"
    )

    args = parser.parse_args()
    task_dirs = [td.strip() for td in args.task_dirs.split(",")]

    output = generate_questionnaire(
        task_dirs=task_dirs,
        profile_path=args.profile,
        config_path=args.config,
        output_path=args.output,
    )
    print(f"Output: {output}")


if __name__ == "__main__":
    main()
