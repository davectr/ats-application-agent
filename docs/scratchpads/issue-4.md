# Issue #4: Phase 3 — Application + Debrief

**Link:** https://github.com/davectr/ats-application-agent/issues/4
**Branch:** `issue-4`
**Depends on:** Phase 2b merged (#3, PR #9)

---

## Deliverables

1. `scripts/parse_questionnaire.py` — Parse completed Obsidian note, extract answers per job mapped to field_ids. Structural integrity validation. Submission readiness check.
2. `scripts/fill_application.py` — Populate form fields using selector fallback chain. Resume upload with verification. Multi-page navigation. Dry-run mode. Screenshot capture.
3. `skills/ats/generic.md` — Generic ATS skill for unknown platforms. Discovery mode behavior.
4. `agents/application.md` — Full application subagent definition.
5. Update `CLAUDE.md` — Wire `/submit`, `/submit --dry-run`, `/debrief` commands.

---

## Implementation Plan

### Commit 1: parse_questionnaire.py
- Parse the Obsidian markdown questionnaire format
- Extract job sections by `<!-- job_id: XXX -->` headers
- Extract field answers by `<!-- field_id: XXX -->` comments
- Handle auto-filled, auto-answered, and user-input sections
- Structural integrity validation: check headers, field_id comments, Answer labels
- Submission readiness: all required answers non-empty
- Resilient to minor user edits: extra blank lines, whitespace, reordered lines
- Process `Save Rule:` tags for Phase 4 consumption
- Output: JSON with per-job answers mapped to field_ids

### Commit 2: fill_application.py
- Populate form fields using scout report selectors (primary → by_label → by_aria)
- Handle field types: text, email, tel, textarea, select, radio, checkbox, file
- Resume upload via `set_input_files()` with post-upload filename verification
- Multi-page navigation detection and handling
- Unexpected fields: discovery mode logic
- Dry-run mode: complete all filling, screenshot, stop before submit
- Screenshot capture at key steps (each page, pre-submit, post-submit)
- Blocked state handling: CAPTCHA, sensitive fields, upload failure
- Import from launch_browser.py for browser lifecycle

### Commit 3: skills/ats/generic.md
- Generic ATS skill for unknown platforms
- Discovery mode: dynamic field reading, multiple selector strategies
- Common form patterns, timing recommendations
- Sensitive field detection guidance
- Error handling patterns

### Commit 4: agents/application.md
- Full application subagent definition
- Receives: task directory, profile.json path, ATS skill file, user responses
- Browser launch procedure
- Form filling from scout report field mappings
- Discovery mode for unexpected fields
- Resume upload with verification
- Blocked state handling
- Debrief output generation
- Scope limits

### Commit 5: CLAUDE.md orchestrator updates
- `/submit` command: parse questionnaire, check readiness, dispatch application subagent per job with pacing
- `/submit --dry-run`: same flow but passes dry-run flag
- `/debrief` command: read debrief files, present batch summary
- `/continue` update: handle blocked tasks (re-spawn application subagent with progress)
- Submission pacing from config.json

---

## Key Design Decisions

- **Selector fallback chain:** primary → by_label → by_aria (matches scout report structure)
- **Pacing:** Orchestrator sleeps between application subagent invocations using config.json `pacing` settings
- **Debrief:** Written by the application subagent after each attempt, not by a separate script
- **Blocked state:** Application agent writes progress field to task.json and exits; orchestrator handles `/continue`
- **Re-fill on continue:** ATS forms don't retain data across sessions — must re-fill from beginning
