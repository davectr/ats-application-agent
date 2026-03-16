#!/usr/bin/env python3
"""Task state management for the ATS Application Agent.

Creates task directories, reads/writes task.json, validates status transitions,
and queries batch status.

Usage:
    python scripts/manage_task_state.py create --batch-date 2026-03-16 --company "Snap Finance" --title "Sr. Director, Marketing Analytics"
    python scripts/manage_task_state.py read --job-id 2026-03-16_snap-finance_sr-dir-marketing-analytics
    python scripts/manage_task_state.py transition --job-id 2026-03-16_snap-finance_sr-dir-marketing-analytics --status intake_complete
    python scripts/manage_task_state.py batch-status
    python scripts/manage_task_state.py batch-status --batch-date 2026-03-16
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Resolve project root relative to this script's location
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = PROJECT_ROOT / "tasks"

# All valid statuses in the task lifecycle
ALL_STATUSES = [
    "queued",
    "intake_complete",
    "listing_expired",
    "sso_apply_only",
    "auth_required",
    "scouted",
    "awaiting_answers",
    "ready_to_apply",
    "submitted",
    "failed",
    "blocked",
]

# Valid forward transitions: current_status -> [allowed_next_statuses]
VALID_TRANSITIONS = {
    "queued": ["intake_complete"],
    "intake_complete": ["listing_expired", "sso_apply_only", "auth_required", "scouted"],
    "auth_required": ["scouted"],
    "scouted": ["awaiting_answers"],
    "awaiting_answers": ["ready_to_apply"],
    "ready_to_apply": ["submitted", "failed", "blocked"],
    "blocked": ["submitted", "failed", "blocked"],
    # Terminal states — no outbound transitions
    "listing_expired": [],
    "sso_apply_only": [],
    "submitted": [],
    "failed": [],
}


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug.

    Lowercase, replace non-alphanumeric with hyphens, collapse multiples, strip edges.
    """
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def make_job_id(batch_date: str, company: str, title: str) -> str:
    """Build job_id from batch date, company slug, and title slug."""
    return f"{batch_date}_{slugify(company)}_{slugify(title)}"


def now_iso() -> str:
    """Current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def task_dir_path(job_id: str) -> Path:
    """Return the path to a task directory."""
    return TASKS_DIR / job_id


def read_task(job_id: str) -> dict:
    """Read and return task.json for a given job_id."""
    task_file = task_dir_path(job_id) / "task.json"
    if not task_file.exists():
        print(f"Error: task.json not found for job_id '{job_id}'", file=sys.stderr)
        sys.exit(1)
    with open(task_file, "r", encoding="utf-8") as f:
        return json.load(f)


def write_task(job_id: str, task_data: dict) -> None:
    """Write task data to task.json."""
    task_file = task_dir_path(job_id) / "task.json"
    with open(task_file, "w", encoding="utf-8") as f:
        json.dump(task_data, f, indent=2, ensure_ascii=False)
        f.write("\n")


# --- Subcommands ---


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new task directory with initial task.json."""
    job_id = make_job_id(args.batch_date, args.company, args.title)
    task_dir = task_dir_path(job_id)

    if task_dir.exists():
        print(f"Error: task directory already exists: {task_dir}", file=sys.stderr)
        sys.exit(1)

    # Create task directory and screenshots subdirectory
    task_dir.mkdir(parents=True, exist_ok=False)
    (task_dir / "screenshots").mkdir()

    timestamp = now_iso()

    # Parse URLs if provided
    urls = {}
    if args.urls:
        urls = json.loads(args.urls)

    task_data = {
        "job_id": job_id,
        "batch_date": args.batch_date,
        "company": args.company,
        "title": args.title,
        "status": "queued",
        "created_at": timestamp,
        "updated_at": timestamp,
        "status_history": [
            {"status": "queued", "timestamp": timestamp}
        ],
        "urls": urls,
        "ats_platform": None,
        "resume_path": None,
        "scout_report_path": None,
        "last_agent": None,
        "error": None,
        "progress": None,
    }

    write_task(job_id, task_data)
    print(json.dumps(task_data, indent=2))


def cmd_read(args: argparse.Namespace) -> None:
    """Read and display task.json for a given job_id."""
    task_data = read_task(args.job_id)
    print(json.dumps(task_data, indent=2))


def cmd_transition(args: argparse.Namespace) -> None:
    """Transition a task to a new status with validation."""
    task_data = read_task(args.job_id)
    current_status = task_data["status"]
    new_status = args.status

    # Validate the new status is recognized
    if new_status not in ALL_STATUSES:
        print(f"Error: unknown status '{new_status}'", file=sys.stderr)
        print(f"Valid statuses: {', '.join(ALL_STATUSES)}", file=sys.stderr)
        sys.exit(1)

    # Validate the transition is allowed
    allowed = VALID_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        print(
            f"Error: invalid transition from '{current_status}' to '{new_status}'",
            file=sys.stderr,
        )
        if allowed:
            print(f"Allowed transitions from '{current_status}': {', '.join(allowed)}", file=sys.stderr)
        else:
            print(f"'{current_status}' is a terminal state with no outbound transitions", file=sys.stderr)
        sys.exit(1)

    timestamp = now_iso()

    # Update task data
    task_data["status"] = new_status
    task_data["updated_at"] = timestamp
    task_data["status_history"].append({"status": new_status, "timestamp": timestamp})

    # Optional fields that can be set during transition
    if args.error is not None:
        task_data["error"] = args.error
    if args.progress is not None:
        task_data["progress"] = json.loads(args.progress)
    if args.last_agent is not None:
        task_data["last_agent"] = args.last_agent
    if args.ats_platform is not None:
        task_data["ats_platform"] = args.ats_platform
    if args.resume_path is not None:
        task_data["resume_path"] = args.resume_path
    if args.scout_report_path is not None:
        task_data["scout_report_path"] = args.scout_report_path

    write_task(args.job_id, task_data)
    print(json.dumps(task_data, indent=2))


def cmd_batch_status(args: argparse.Namespace) -> None:
    """List status of all tasks in a batch."""
    if not TASKS_DIR.exists():
        print(json.dumps({"batch_date": None, "tasks": []}))
        return

    # Collect all task directories
    task_dirs = sorted(
        [d for d in TASKS_DIR.iterdir() if d.is_dir() and (d / "task.json").exists()]
    )

    if not task_dirs:
        print(json.dumps({"batch_date": None, "tasks": []}))
        return

    # Determine which batch to show
    if args.batch_date:
        target_date = args.batch_date
    else:
        # Find the most recent batch date
        dates = set()
        for d in task_dirs:
            parts = d.name.split("_", 1)
            if parts:
                dates.add(parts[0])
        target_date = max(dates) if dates else None

    if target_date is None:
        print(json.dumps({"batch_date": None, "tasks": []}))
        return

    # Filter to target batch and collect summaries
    batch_tasks = []
    for d in task_dirs:
        if not d.name.startswith(target_date + "_"):
            continue
        task_file = d / "task.json"
        with open(task_file, "r", encoding="utf-8") as f:
            task_data = json.load(f)
        batch_tasks.append({
            "job_id": task_data["job_id"],
            "company": task_data["company"],
            "title": task_data["title"],
            "status": task_data["status"],
            "updated_at": task_data["updated_at"],
        })

    result = {
        "batch_date": target_date,
        "tasks": batch_tasks,
    }
    print(json.dumps(result, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Task state management for the ATS Application Agent"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = subparsers.add_parser("create", help="Create a new task directory")
    p_create.add_argument("--batch-date", required=True, help="Batch date (YYYY-MM-DD)")
    p_create.add_argument("--company", required=True, help="Company name")
    p_create.add_argument("--title", required=True, help="Job title")
    p_create.add_argument("--urls", help="URLs as JSON string")

    # read
    p_read = subparsers.add_parser("read", help="Read task.json for a job")
    p_read.add_argument("--job-id", required=True, help="Job ID (task directory name)")

    # transition
    p_transition = subparsers.add_parser("transition", help="Transition task status")
    p_transition.add_argument("--job-id", required=True, help="Job ID")
    p_transition.add_argument("--status", required=True, help="New status")
    p_transition.add_argument("--error", help="Error message (for failed status)")
    p_transition.add_argument("--progress", help="Progress data as JSON string")
    p_transition.add_argument("--last-agent", help="Name of the last agent that ran")
    p_transition.add_argument("--ats-platform", help="ATS platform identifier")
    p_transition.add_argument("--resume-path", help="Path to resume file")
    p_transition.add_argument("--scout-report-path", help="Path to scout report")

    # batch-status
    p_batch = subparsers.add_parser("batch-status", help="Show status of all tasks in a batch")
    p_batch.add_argument("--batch-date", help="Batch date (defaults to most recent)")

    args = parser.parse_args()

    commands = {
        "create": cmd_create,
        "read": cmd_read,
        "transition": cmd_transition,
        "batch-status": cmd_batch_status,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
