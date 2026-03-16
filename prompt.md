# Task: Create GitHub Issues from Project Plan

## Context

You are working in the repository `davectr/ats-application-agent` at `D:\GitProjects\ats-application-agent`. The file `project-plan.md` in this directory is the complete, reviewed project plan for an automated job application system built on Claude Code.

Your task is to create 5 GitHub issues in this repository, one per deployment phase. Each issue must contain everything a dev agent needs to execute that phase without asking questions. The dev agent will read the issue, read `project-plan.md` for reference, and build.

## Prerequisites

- Ensure you are in the correct directory: `D:\GitProjects\ats-application-agent`
- Ensure the GitHub CLI (`gh`) is authenticated and can access the repo
- Ensure `project-plan.md` exists in the root directory

## Issue Structure

Each issue must follow this exact format:

```markdown
## Phase Overview
[One paragraph summarizing what this phase accomplishes and what state the project should be in when complete]

## Depends On
[Which issues/phases must be merged before this one starts, or "None" for Phase 1]

## Deliverables
[Exact list of files to create or modify, pulled from the corresponding phase in project-plan.md]

## Acceptance Criteria
[Specific, testable conditions that confirm the phase is complete]

## Reference
All specifications, schemas, formats, and behavioral details are defined in `project-plan.md` in the repo root. Read it in full before starting work. Do not invent schemas, formats, or behaviors — everything you need is in the plan.
```

## Issues to Create

### Issue 1: Phase 1 — Foundation

**Title:** `Phase 1: Foundation — repo structure, config, task state, orchestrator skeleton`

**Phase Overview:** Establish the repo structure, configuration files, profile template, task state management, and the orchestrator skeleton. At the end of this phase, the orchestrator responds to `/status` and can create/read task directories. The profile template is ready for the user to populate.

**Depends On:** None

**Deliverables:**
- `.gitignore`
- `CLAUDE.md` — orchestrator agent definition with command routing for `/status`
- `config.json` — all paths, browser config, URL classification, pacing, timeout settings as specified in project-plan.md
- `profile.json` — empty template matching the schema in project-plan.md (contact, demographics, education, work_history, answer_rules, always_ask)
- `launch-browser.bat` — Chrome launch shortcut as specified in project-plan.md
- `agents/intake.md` — placeholder (empty file with a header comment noting it will be built in Phase 2a)
- `agents/scout.md` — placeholder
- `agents/application.md` — placeholder
- `skills/ats/generic.md` — placeholder
- `templates/questionnaire.md` — questionnaire template matching the format in project-plan.md
- `templates/debrief.md` — debrief template matching the format in project-plan.md
- `scripts/manage_task_state.py` — create task directories, read/write task.json, status transitions, batch status query. Must support all lifecycle states defined in project-plan.md including the `progress` field structure.
- `tasks/` directory (empty, gitignored)

**Acceptance Criteria:**
- All files listed above exist and match the schemas/formats in project-plan.md
- `scripts/manage_task_state.py` can: create a task directory with proper naming convention, write a valid task.json, transition between all lifecycle states, query batch status across multiple task directories
- `.gitignore` excludes `.chrome-profile/`, `tasks/`, `test-data/`, and `*.pdf`
- `config.json` contains all configuration fields specified in project-plan.md (chrome profile path, obsidian path, browser settings, URL classification, pacing, timeout)
- `profile.json` is valid JSON matching the full schema including answer_rules and always_ask arrays
- `launch-browser.bat` launches Chrome with the correct `--user-data-dir` flag pointing to `.chrome-profile`
- Running the orchestrator with `/status` when no tasks exist returns an empty status summary without errors

---

### Issue 2: Phase 2a — Intake

**Title:** `Phase 2a: Intake — email PDF parsing, URL extraction, resume download`

**Phase Overview:** Build the intake subagent and its supporting scripts. After this phase, the orchestrator's `/apply` command processes an email PDF through the intake subagent: parsing job listings, extracting and categorizing URLs, downloading tailored resumes, and creating task directories with `intake_complete` status. Scout functionality is not included — that is Phase 2b.

**Depends On:** Phase 1 merged

**Deliverables:**
- `agents/intake.md` — full intake subagent definition. Must specify: what the subagent receives at spawn (path to email PDF, path to task root), what scripts it calls, what outputs it produces, and validation rules.
- `scripts/parse_email_pdf.py` — extract text content and embedded URL annotations from a Proficiently career coach email PDF using `pypdf`. Deduplicate URLs. Categorize each URL as job_listing, resume_view, or resume_download using the domain patterns in config.json's `url_classification`. Output structured JSON array of job listings with all fields specified in project-plan.md.
- `scripts/download_resumes.py` — download resume PDFs from Google Docs export URLs via direct HTTP. Validate downloaded files are real PDFs (check header, verify non-zero size). Save to task directory with company-slug filename.
- Update `CLAUDE.md` — wire `/apply` command to dispatch the intake subagent. After intake completes, the orchestrator should report how many jobs were parsed and transition to Phase 2b processing (which will fail gracefully since scout isn't built yet — that's expected).

**Acceptance Criteria:**
- `parse_email_pdf.py` correctly extracts all job listings from the sample Proficiently email PDF format, including: job number, title, company, description, pay, job type, location, match rationale, and all 3 URL types per listing
- URL deduplication works (Proficiently PDFs contain duplicate annotations)
- URL categorization uses config.json patterns, not hardcoded domains
- `download_resumes.py` downloads valid PDFs from Google Docs export links
- Intake validation fires: if fewer than 3 URLs per listing or text extraction fails, the batch fails with a descriptive error
- After `/apply email.pdf`, task directories exist for each job with `listing.json`, downloaded resume PDF, and `task.json` in `intake_complete` status
- The intake subagent definition in `agents/intake.md` is complete and self-contained — a Claude Code instance receiving this definition and the task parameters can execute intake without additional context

---

### Issue 3: Phase 2b — Scout + Questionnaire

**Title:** `Phase 2b: Scout + Questionnaire — browser recon, field mapping, Obsidian note generation`

**Phase Overview:** Build the scout subagent, browser launch infrastructure, ATS detection, form field mapping, answer rules engine, and Obsidian questionnaire generation. After this phase, `/apply email.pdf` runs the full pipeline: intake parses the email, then the scout visits each application page, maps form fields, and produces a complete questionnaire in Obsidian with auto-filled fields, auto-answered rules, and human-input questions with field_id references.

**Depends On:** Phase 2a merged

**Deliverables:**
- `agents/scout.md` — full scout subagent definition. Must specify: what it receives at spawn, browser launch procedure using `launch_persistent_context`, ATS detection logic, auth wall detection, SSO-only apply detection, form field mapping with multiple selector strategies, and output format (scout_report.json).
- `scripts/launch_browser.py` — shared Playwright browser launch using `launch_persistent_context` with config.json settings (chrome profile path, channel, headed, minimized). Used by both scout and application agents.
- `scripts/scout_page.py` — navigate to job application URL, handle multi-step navigation (job board → ATS), detect ATS platform from URL/DOM, detect auth walls and SSO-only flows, extract all form fields with label, type, options, required status, and multiple selector strategies (primary, by_label, by_aria). Capture screenshots at each step. Output scout_report.json matching the schema in project-plan.md.
- `scripts/apply_answer_rules.py` — match question labels against answer rules in profile.json using case-insensitive regex. Implement full precedence order: always_ask checked first, then rules in array order (first match wins), then skip_if_optional evaluation, then surface to user. Handle conditional logic (options_contain) for select fields.
- `scripts/generate_questionnaire.py` — build Obsidian markdown note from scout reports + answer rules output. Three sections per job: auto-filled from profile, auto-answered from rules, needs user input. Include `<!-- field_id -->` HTML comments. Include structural warning note at top. Write to Obsidian output path from config.json. Filename convention: `YYYY-MM-DD Applications.md`.
- Update `CLAUDE.md` — wire `/apply` to dispatch scout subagents after intake, then generate the questionnaire. Wire `/continue` for auth_required recovery.

**Acceptance Criteria:**
- `launch_browser.py` opens headed Chrome using the persistent profile, minimized, and closes cleanly on exit
- `scout_page.py` can navigate to an Indeed job listing, follow through to the company ATS, detect the platform, and extract form fields with multiple selector strategies
- Scout correctly identifies and reports: `auth_required`, `sso_apply_only`, `listing_expired`, and `open` statuses
- `apply_answer_rules.py` correctly implements the full precedence chain: always_ask → rules (first match) → skip_if_optional → surface to user
- Generated Obsidian questionnaire matches the format in project-plan.md, including field_id comments, three sections per job, and structural warning note
- After `/apply email.pdf`, the Obsidian note exists at the configured path with all scouted jobs, and task.json files are in `scouted` or `awaiting_answers` status
- `/continue` successfully re-spawns the scout after manual auth resolution

---

### Issue 4: Phase 3 — Application + Debrief

**Title:** `Phase 3: Application + Debrief — form filling, submission, dry-run, debrief generation`

**Phase Overview:** Build the application subagent, questionnaire parser, form filling logic, resume upload with verification, submission pacing, dry-run mode, and debrief generation. After this phase, the full loop is operational: `/submit` reads the completed questionnaire, fills and submits applications sequentially with pacing delays, and produces a debrief for each attempt. `/submit --dry-run` does everything except click the final submit button.

**Depends On:** Phase 2b merged

**Deliverables:**
- `agents/application.md` — full application subagent definition. Must specify: what it receives at spawn (task directory, profile.json, ATS skill file, user responses), browser launch procedure, form filling from scout report field mappings, discovery mode for unexpected fields, resume upload with verification, blocked state handling, and debrief output.
- `skills/ats/generic.md` — generic ATS skill for unknown platforms. Describes discovery mode behavior: read page dynamically, identify fields by label/context, try multiple selector strategies, screenshot every step, pause liberally for user input.
- `scripts/parse_questionnaire.py` — read completed Obsidian note, extract answers per job mapped to field_ids. Validate structural integrity before proceeding: check for intact headers, field_id comments, Answer labels. Surface specific errors per job section if validation fails. Determine submission readiness: all required answers non-empty.
- `scripts/fill_application.py` — populate form fields using scout report selectors (try primary, then by_label, then by_aria). Upload resume via `set_input_files()` with post-upload filename verification. Handle multi-page navigation. Handle unexpected fields using discovery mode logic. Implement dry-run mode (stop before final submit click). Capture screenshots at key steps.
- Update `CLAUDE.md` — wire `/submit`, `/submit --dry-run`, and `/debrief` commands. Implement submission pacing from config.json between application agent invocations. `/debrief` shows batch summary with drill-down option.

**Acceptance Criteria:**
- `parse_questionnaire.py` correctly extracts all answers mapped to field_ids from a completed Obsidian note
- Structural integrity validation catches missing field_id comments, broken headers, and missing Answer labels with specific error messages
- Submission readiness check correctly identifies jobs with incomplete required answers and skips them
- `fill_application.py` populates form fields using the selector fallback chain (primary → by_label → by_aria)
- Resume upload works via `set_input_files()` with post-upload verification (filename appears on page)
- Unexpected fields (not in scout report) are handled using discovery mode logic, not ignored
- Dry-run mode completes all filling and captures pre-submission screenshot without clicking submit
- Submission pacing respects config.json delay settings including domain overrides
- Debrief is generated after each application attempt, matching the format in project-plan.md, with separate sections for skill updates vs script updates
- All blocker types (CAPTCHA, sensitive field, unexpected element, upload failure) follow the manual intervention pattern defined in project-plan.md
- `/continue` successfully re-spawns the application agent after manual intervention

---

### Issue 5: Phase 4 — Learning Loop

**Title:** `Phase 4: Learning Loop — Save Rule processing, /skill command, ATS skill evolution`

**Phase Overview:** Build the system's ability to improve over time. `Save Rule:` tags in questionnaires automatically promote answers to rules or the always-ask list. The `/skill` command allows the user to update ATS skills and answer rules based on debrief findings. The orchestrator categorizes debrief observations by update type (orchestrator-updatable vs build-agent-needed). After this phase, the system gets measurably smarter with each application cycle.

**Depends On:** Phase 3 merged

**Deliverables:**
- Update `scripts/parse_questionnaire.py` — extract `Save Rule: always` and `Save Rule: never` tags from completed questionnaires
- Update `CLAUDE.md` — implement `/skill` command in both modes:
  - Freeform: orchestrator receives natural language instruction, determines target file (ATS skill or profile.json), makes the edit
  - Debrief-guided: orchestrator reads debrief suggestions, presents each to user, applies approved changes
- Update `CLAUDE.md` — implement debrief triage in `/debrief` output: categorize observations as skill updates (orchestrator), script updates (build agent), answer rules (orchestrator), or one-offs (no action)
- ATS skill file creation: when `/skill` creates a new platform skill, it follows the format specified in project-plan.md (Platform Identification, Navigation Flow, Known Field Patterns, Common Issues, Revision History)
- Answer rule management: `/skill` can add new rules to profile.json's `answer_rules` array and add patterns to `always_ask` list
- `Save Rule: always` processing: after `/submit` completes, the orchestrator scans answers for this tag and drafts new answer rules for user approval before adding to profile.json
- `Save Rule: never` processing: adds the question pattern to the `always_ask` list in profile.json

**Acceptance Criteria:**
- `Save Rule: always` on a questionnaire answer results in a new answer rule being proposed to the user and, on approval, added to profile.json
- `Save Rule: never` on a questionnaire answer adds the pattern to the always_ask list
- `/skill Add a rule for "years of experience": answer "18+ years"` correctly adds a new rule to profile.json
- `/skill Apply suggestion 2 from the Snap Finance debrief` correctly reads the debrief and applies the specified suggestion
- `/debrief` output categorizes observations into the four triage categories: skill updates, script updates, answer rules, one-offs
- New ATS skill files created by `/skill` follow the format in project-plan.md with all required sections
- Each skill update includes a revision history entry linking to the source debrief
- Previously unknown questions that received `Save Rule: always` are auto-answered on subsequent applications

## Execution Instructions

1. Verify `gh` CLI is authenticated: run `gh auth status`
2. Verify you are in the correct repo: run `gh repo view --json nameWithOwner`
3. Create each issue in order using `gh issue create` with the title, body, and label `phase-N` (create the labels first if they don't exist)
4. After creating all 5 issues, list them to confirm: `gh issue list`

Create the labels first:
```bash
gh label create "phase-1" --color "0E8A16" --description "Phase 1: Foundation"
gh label create "phase-2a" --color "1D76DB" --description "Phase 2a: Intake"
gh label create "phase-2b" --color "5319E7" --description "Phase 2b: Scout + Questionnaire"
gh label create "phase-3" --color "D93F0B" --description "Phase 3: Application + Debrief"
gh label create "phase-4" --color "FBCA04" --description "Phase 4: Learning Loop"
```

Then create each issue with its corresponding label. Use `gh issue create --title "..." --body "..." --label "phase-N"`.

Do not modify `project-plan.md`. Do not create branches. Do not write code. Only create the GitHub issues and labels.
