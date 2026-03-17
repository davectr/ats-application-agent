# Issue #3: Phase 2b — Scout + Questionnaire

**Link:** https://github.com/davectr/ats-application-agent/issues/3
**Branch:** `issue-3`
**Depends on:** Phase 2a merged (#2)

## Deliverables

1. `scripts/launch_browser.py` — Playwright persistent context browser launch (shared by scout + application)
2. `scripts/scout_page.py` — Navigate to job URL, detect ATS, extract form fields, capture screenshots
3. `scripts/apply_answer_rules.py` — Answer rules engine with full precedence chain
4. `scripts/generate_questionnaire.py` — Obsidian markdown questionnaire from scout reports + rules
5. `agents/scout.md` — Full scout subagent definition
6. `CLAUDE.md` update — Wire `/apply` scout dispatch + `/continue` command

## Implementation Plan

### 1. launch_browser.py
- Read config.json for chrome_profile_path, browser settings
- Use `playwright.chromium.launch_persistent_context()`
- Settings: channel="chrome", headless=False, start_minimized=True
- Accept `--config` path argument
- Return context/page objects via function API (imported by scout_page.py)
- `--test` flag: launch, navigate about:blank, screenshot, close
- Clean close on exit (context.close())

### 2. scout_page.py
- Accept: `--task-dir`, `--config` arguments
- Read listing.json from task dir for job URL
- Call launch_browser.py to get browser context
- Multi-step navigation: job board page → find "Apply" button → follow to ATS
- ATS detection: URL pattern matching (workday, greenhouse, lever, etc.)
- Auth wall detection: look for login forms, redirect to login pages
- SSO-only detection: only LinkedIn/Indeed SSO buttons, no traditional form
- Expired listing detection: "no longer accepting", "closed", "expired" text
- Form field extraction: iterate all input/select/textarea elements
  - Label via associated <label>, aria-label, placeholder
  - Type from input type attribute
  - Options from <select> <option> elements
  - Required from required attribute, aria-required
  - Multiple selector strategies (primary, by_label, by_aria)
- Profile key mapping: heuristic (done by scout subagent LLM, not this script)
- Screenshot at each navigation step
- Output: scout_report.json to task dir

### 3. apply_answer_rules.py
- Accept: `--scout-report` or stdin, `--profile` path
- For each field in scout report:
  1. Skip if auto_fill=true (already handled by profile data)
  2. Check always_ask list — if match, category="needs_input"
  3. Check answer_rules in order — first match wins
     - If behavior="skip_if_optional" and not required: category="skipped"
     - If logic array: evaluate conditions (options_contain, default)
     - Simple answer: category="auto_answered"
  4. No match: category="needs_input"
- Output: annotated fields JSON with resolution category + resolved answer

### 4. generate_questionnaire.py
- Accept: `--task-dirs` (comma-separated), `--profile`, `--config`, `--output` (optional, defaults to config obsidian path)
- For each task dir:
  - Read scout_report.json
  - Run apply_answer_rules against fields
  - Build markdown sections
- Structural warning note at top
- Three sections per job: auto-filled, auto-answered, needs input
- field_id and job_id HTML comments
- Write to Obsidian output path

### 5. agents/scout.md
- Parameters: TASK_DIR, CONFIG_PATH
- Steps: launch browser → navigate → detect ATS → detect auth/SSO/expired → map fields → screenshot → write scout_report.json → transition task state
- Scope limits: no form filling, no submission, read-only profile

### 6. CLAUDE.md updates
- `/apply`: after intake, loop through intake_complete tasks, dispatch scout for each, then generate questionnaire
- `/continue`: find auth_required task, re-dispatch scout

## Key Design Decisions

- `scout_page.py` handles navigation and raw field extraction only. Profile key mapping (heuristic "First Name" → contact.first_name) is done by the scout subagent LLM reading the scout report fields.
- `apply_answer_rules.py` is a standalone script, not embedded in generate_questionnaire.py, for testability.
- `launch_browser.py` exposes a function API so other scripts can import it, plus a CLI `--test` mode.
- The scout subagent does two passes: first scout_page.py extracts raw fields, then the subagent enriches them with profile_key and auto_fill mappings.
