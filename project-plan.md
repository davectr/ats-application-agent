# ATS Application Agent — Project Plan

## Overview

An autonomous Claude Code agent team that processes curated job listing emails, scouts application pages, collects human input via Obsidian, and submits applications. The system learns and improves with each application cycle through human-reviewed skill updates and answer rule accumulation.

---

## Architectural Constraints

- **Pure Claude Code architecture.** The orchestrator and all subagents are Claude Code instances. There is no Python pipeline, no wrapper script, no external orchestration framework. The orchestrator agent itself handles all decision-making and dispatch.
- **Subagent invocation.** The orchestrator spawns subagents by reading the agent definition file (e.g., `agents/intake.md`) and passing it as the prompt to `claude -p`. The call is synchronous and blocking — the orchestrator waits for the subagent to complete before proceeding. All subagents run from the project root (`D:\GitProjects\ats-application-agent`) as working directory so all relative paths in config.json resolve correctly. Example invocation:
  ```
  claude -p "$(cat agents/intake.md) TASK_DIR=tasks/2026-03-16_snap-finance_sr-dir-marketing-analytics EMAIL_PDF=path/to/email.pdf"
  ```
  The orchestrator constructs the prompt by combining the agent definition with task-specific parameters. The subagent executes, writes its outputs to the task directory, and exits. The orchestrator reads the outputs and determines the next step.
- **No autonomous skill mutation.** Subagents never modify skill files, answer rules, or profile data during execution. All skill and rule updates happen only through the orchestrator's `/skill` command, initiated by the user after reviewing a debrief.
- **Subagent timeout.** Browser-driving subagents (scout, application) should be given a maximum execution duration. If a subagent has not completed within 10 minutes, the orchestrator should kill it and write a `failed` status with a timeout error. This prevents hung Playwright sessions (network timeouts, infinite redirect loops) from blocking the orchestrator indefinitely.

---

## Project Specifics

| Item | Value |
|---|---|
| Remote repo | https://github.com/davectr/ats-application-agent |
| Local repo | `D:\GitProjects\ats-application-agent` |
| Build agent location | `D:\GitProjects\platform-build-agents\ats-build-agent` |
| Chrome profile | `D:\GitProjects\ats-application-agent\.chrome-profile` |
| Obsidian output folder | `D:\Obsidian Notes\Notes\Job Seeking\Auto App` |
| Git workflow | Feature branches → PR → user merges to main |
| Browser mode | Headed Chrome (installed), minimized, `channel="chrome"` |
| Browser profile | Persistent context via `.chrome-profile` (default profile, not a named user) |

---

## User Commands

| Command | Description |
|---|---|
| `/apply <path>` | Process an email PDF — runs intake and scout, produces Obsidian questionnaire |
| `/submit` | Read completed questionnaire, run application agents sequentially |
| `/submit --dry-run` | Run the full application flow but stop before clicking the final submit button. Captures a pre-submission screenshot for review. |
| `/status` | Display current state of all tasks in the active batch |
| `/continue` | Resume a blocked agent after manual intervention |
| `/debrief` | Review post-application findings and suggested learnings |
| `/skill <update instructions>` | Update an ATS skill or answer rule based on debrief findings |

### Submission Readiness

When `/submit` is invoked, the orchestrator parses the Obsidian questionnaire and determines which jobs are ready. A job is ready to submit when:
- Its task status is `awaiting_answers`
- All required questions (where `Required: yes`) in the questionnaire have a non-empty `Answer:` field
- The job section has not been marked as skipped by the user

Jobs that are not ready are skipped with a status message. The orchestrator reports which jobs will be submitted and which were skipped before proceeding.

### `/skill` Interaction Model

The `/skill` command supports two modes:

- **Freeform instruction:** The user provides a natural language update instruction. Example: `/skill Add a rule for "years of experience" questions: answer with "18+ years"`. The orchestrator interprets the instruction and updates the appropriate file (answer rule in profile.json, or an ATS skill file).
- **Debrief-guided:** The user runs `/debrief`, reviews the suggested skill updates, then uses `/skill` to approve or modify specific suggestions. Example: `/skill Apply suggestion 2 from the Snap Finance debrief`.

### Batch Scope

A "batch" is the set of task directories created by a single `/apply` invocation. Each `/apply` creates tasks with the same date prefix (e.g., `2026-03-16_*`). Commands scope as follows:

- **`/status`** — shows all tasks in the most recent batch by default. If tasks from multiple batches exist, shows the most recent. The user can specify a date to view older batches.
- **`/submit`** — operates on the most recent batch. Only submits jobs in `awaiting_answers` state with completed answers.
- **`/debrief`** — shows debriefs from the most recent batch. If multiple jobs have debriefs, presents a summary of all with the option to drill into a specific one.
- **`/continue`** — operates on the specific blocked task (there should only be one at a time since processing is sequential).

---

## Agent Team

All subagents are discrete Claude Code instances spawned by the orchestrator. Each gets its own context window, executes its task, writes outputs to the task directory, and exits. The orchestrator reads task state to determine what to dispatch next.

### Orchestrator
- The only agent the user interacts with
- Dispatches subagents by constructing a task prompt with file paths and instructions
- Manages task lifecycle, maintains skills and answer rules via `/skill`
- Processes jobs sequentially — one subagent in flight at a time
- Reads task.json to determine current state and next action

### Intake Subagent
- **Receives at spawn:** path to email PDF, path to task root directory
- Parses email PDF text + embedded URL annotations via `pypdf`
- Downloads tailored resumes via direct HTTP (no browser needed)
- Deduplicates URLs (PDFs contain duplicates)
- **Validation:** After parsing, the intake agent verifies: at least 1 job listing extracted, each listing has all 3 URL types (job listing, resume view, resume download), and text extraction produced non-empty content for each listing. If validation fails, the batch is marked as failed with a descriptive error identifying what was missing, rather than producing partial or corrupt task data.
- **Outputs:** `listing.json` + resume PDFs per job, creates task directories

### Scout Subagent
- **Receives at spawn:** path to task directory (containing listing.json), path to config.json
- Launches headed Chrome with persistent profile using `launch_persistent_context`
- Browser is ephemeral — opens when subagent starts, closes when subagent exits
- Navigates to job application page (may require multi-step: job board → ATS)
- Detects ATS platform from URL/DOM
- Verifies auth access — if blocked, reports `auth_required` and exits
- **Detects SSO-only apply flows** (e.g., "Apply with LinkedIn", "Sign in with Indeed to apply"). If the application page has no traditional form and only offers third-party SSO apply, the scout sets `listing_status: "sso_apply_only"` in the scout report. The task transitions to `sso_apply_only` and is skipped with a note to the user to apply manually.
- Maps all form fields: label, type, options, required/optional status
- Screenshot capture at each navigation step
- **Outputs:** `scout_report.json` per job
- Does not fill forms, does not submit anything

### Application Subagent
- **Receives at spawn:** path to task directory, path to profile.json, path to ATS skill file, path to user responses
- Loads platform-specific ATS skill (or `skills/ats/generic.md` as fallback)
- Browser is ephemeral — opens when subagent starts, closes when subagent exits
- Fills forms, uploads resume, handles multi-page flows
- **Unexpected fields:** The scout report is a map, not a contract. ATS forms may render fields dynamically based on earlier selections. When the application agent encounters a field not in the scout report, it applies the same logic as discovery mode: check answer rules, check profile data, and if neither resolves it, write a blocked state. The debrief captures what was unexpected.
- **Resume upload verification:** After uploading via `set_input_files()`, the application agent verifies the upload took by checking for the filename on the page. If the filename doesn't appear, or the upload field still shows empty, the agent retries once, then writes a blocked state if it still fails.
- On blocker: writes blocked state with screenshot to task directory, exits
- On completion: produces debrief with platform learnings and one-off observations
- One invocation per job
- **On unknown platforms (generic skill / discovery mode):** reads the page dynamically, identifies form fields by label and context, works through them methodically, screenshots every step, and is liberal about pausing for user input. The debrief from a discovery-mode run becomes the seed for a new platform-specific ATS skill.

---

## Task Lifecycle

```
queued
  → intake_complete
    → listing_expired (job posting closed — skipped)
    → sso_apply_only (no traditional form, only LinkedIn/Indeed SSO — skipped, user applies manually)
    → auth_required (if login needed — user logs in manually, restarts)
    → scouted
      → awaiting_answers (questionnaire in Obsidian)
        → ready_to_apply (user completed answers)
          → submitted
          → failed (with error details)
          → blocked (with screenshot, awaiting /continue)
```

### Mid-Task Resume

When a subagent hits a blocker and exits, it must serialize enough state for the next invocation to pick up where it left off. The `task.json` includes a `progress` field that captures:

- Current page URL
- Which step in a multi-page flow was reached
- Which fields were filled (for logging/debrief purposes)
- The reason for the block

**Important:** ATS forms do not retain partially filled data across browser sessions. When the orchestrator re-spawns a subagent after `/continue`, the subagent navigates to the page indicated in `progress`, then **re-fills all fields from the beginning up to and past the point of the previous block.** The `progress` field's primary role is knowing which page to navigate to and what was already attempted, not skipping fields.

---

## Task State Schema (task.json)

```json
{
  "job_id": "2026-03-16_snap-finance_sr-dir-marketing-analytics",
  "batch_date": "2026-03-16",
  "company": "Snap Finance",
  "title": "Sr. Director, Marketing Analytics",
  "status": "scouted",
  "created_at": "2026-03-16T11:00:00Z",
  "updated_at": "2026-03-16T11:35:00Z",
  "status_history": [
    {"status": "queued", "timestamp": "2026-03-16T11:00:00Z"},
    {"status": "intake_complete", "timestamp": "2026-03-16T11:05:00Z"},
    {"status": "scouted", "timestamp": "2026-03-16T11:35:00Z"}
  ],
  "urls": {
    "job_listing": "https://www.indeed.com/viewjob?jk=b092a1131ce2385e",
    "resume_view": "https://docs.google.com/document/d/...",
    "resume_download": "https://docs.google.com/document/export?format=pdf&id=..."
  },
  "ats_platform": "workday",
  "resume_path": "tasks/2026-03-16_snap-finance_sr-dir-marketing-analytics/snap-finance-resume.pdf",
  "scout_report_path": "tasks/2026-03-16_snap-finance_sr-dir-marketing-analytics/scout_report.json",
  "last_agent": "scout",
  "error": null,
  "progress": null
}
```

**`progress` field (when blocked):**

```json
{
  "page_url": "https://snapfinance.wd1.myworkdayjobs.com/.../apply/step2",
  "page_number": 2,
  "fields_filled": ["f1", "f2", "f3", "f4", "f5"],
  "block_reason": "CAPTCHA detected on page 2",
  "screenshot": "screenshots/blocked-captcha-page2.png"
}
```

---

## Listing Schema (listing.json)

Created by the intake subagent, one per job. Consumed by the scout subagent and used to populate task.json.

```json
{
  "job_number": 1,
  "company": "Snap Finance",
  "title": "Sr. Director, Marketing Analytics",
  "description": "Lead analytics strategy and execution for digital acquisition and lifecycle marketing...",
  "pay": "Not listed",
  "job_type": "Full-time, Remote",
  "location": "US (Remote)",
  "match_rationale": "Closely matches your leadership experience in marketing analytics...",
  "urls": {
    "job_listing": "https://www.indeed.com/viewjob?jk=b092a1131ce2385e",
    "resume_view": "https://docs.google.com/document/d/1Wy9bgivjo7K3vfsExkCE7BmbmmtUK9EeBKKQhSjLKS8",
    "resume_download": "https://docs.google.com/document/export?format=pdf&id=1Wy9bgivjo7K3vfsExkCE7BmbmmtUK9EeBKKQhSjLKS8"
  }
}
```

---

## Scout Report Schema (scout_report.json)

```json
{
  "job_id": "2026-03-16_snap-finance_sr-dir-marketing-analytics",
  "ats_platform": "workday",
  "application_url": "https://snapfinance.wd1.myworkdayjobs.com/...",
  "listing_status": "open",
  "auth_required": false,
  "page_count": 3,
  "pages": [
    {
      "page_number": 1,
      "url": "https://snapfinance.wd1.myworkdayjobs.com/.../apply/step1",
      "screenshot": "screenshots/scout-page1.png",
      "fields": [
        {
          "field_id": "f1",
          "label": "First Name",
          "type": "text",
          "required": true,
          "auto_fill": true,
          "profile_key": "contact.first_name",
          "selectors": {
            "primary": "input[name='firstName']",
            "by_label": "label:has-text('First Name') + input",
            "by_aria": "[aria-label='First Name']"
          }
        },
        {
          "field_id": "f2",
          "label": "Why are you interested in this role?",
          "type": "textarea",
          "required": true,
          "auto_fill": false,
          "selectors": {
            "primary": "textarea[name='coverLetter']",
            "by_label": "label:has-text('Why are you interested') ~ textarea",
            "by_aria": "[aria-label*='interested']"
          }
        },
        {
          "field_id": "f3",
          "label": "How did you hear about us?",
          "type": "select",
          "required": false,
          "auto_fill": false,
          "options": ["LinkedIn", "Indeed", "Referral", "Other"],
          "selectors": {
            "primary": "select[name='source']",
            "by_label": "label:has-text('How did you hear') + select"
          }
        },
        {
          "field_id": "f4",
          "label": "Resume",
          "type": "file",
          "required": true,
          "auto_fill": true,
          "profile_key": "_resume_file",
          "selectors": {
            "primary": "input[type='file']",
            "by_label": "label:has-text('Resume') input[type='file']"
          },
          "note": "Application agent uses Playwright set_input_files() with the resume PDF path from the task directory."
        }
      ]
    }
  ]
}
```

**Key fields:**
- `field_id`: unique per field within the report — used to map questionnaire answers back to form fields
- `selectors`: multiple DOM selector strategies for resilience against dynamic rendering. The application agent tries `primary` first, falls back to `by_label`, then `by_aria`. ATS platforms with React-based rendering (Workday, Greenhouse) often generate non-deterministic IDs, so label-based and aria-based selectors are essential fallbacks.
- `profile_key`: for auto-fill fields, the dotted path into profile.json (e.g., `contact.email`, `demographics.work_authorization`). The special value `_resume_file` indicates the resume upload field. **The scout subagent assigns `profile_key` via heuristic label matching** — it is an LLM and uses the field label to reason about the correct mapping (e.g., "First Name" → `contact.first_name`, "Email" → `contact.email`). There is no static mapping table. **For array fields** (education, work_history): the scout maps to the first entry with `current: true` for work history, or index `[0]` for education. Example: "Most Recent Employer" → `work_history[0].company`, "Degree" → `education[0].degree`. If the ATS presents multi-entry work history forms (add multiple positions), this is a complex interaction best handled as a user-input question rather than auto-fill.
- `auto_fill`: determined by matching the field against profile data and answer rules
- `type: "file"`: identifies the resume upload field. The application agent uses Playwright's `set_input_files()` to upload the resume PDF from the task directory.
- `listing_status`: `open`, `expired`, or `requires_account`. If `expired`, the task transitions to `listing_expired` and is skipped.

### Additional Lifecycle State

`listing_expired` — the scout found the job posting is closed or no longer accepting applications. Task is skipped, no questionnaire generated.

---

## File Structure

```
ats-application-agent/
├── .gitignore
├── CLAUDE.md                    # Orchestrator agent definition + commands
├── config.json                  # Paths, Chrome profile, Obsidian folder
├── profile.json                 # Contact info, work history, answer rules
├── launch-browser.bat           # QoL shortcut to open Chrome profile manually
├── agents/
│   ├── intake.md                # Intake subagent definition (prompt + instructions)
│   ├── scout.md                 # Scout subagent definition
│   └── application.md           # Application subagent definition
├── scripts/
│   ├── parse_email_pdf.py       # Extract text, URLs, job listings from Proficiently PDF
│   ├── download_resumes.py      # HTTP download of resume PDFs from Google Docs export links
│   ├── launch_browser.py        # Playwright launch with persistent profile (shared by scout + application)
│   ├── scout_page.py            # Navigate to application page, detect ATS, extract form fields + selectors
│   ├── fill_application.py      # Populate form fields, upload resume, handle multi-page flows
│   ├── parse_questionnaire.py   # Read completed Obsidian note, extract answers mapped to field_ids
│   ├── generate_questionnaire.py # Build Obsidian markdown note from scout reports + answer rules
│   ├── manage_task_state.py     # Create task directories, read/write task.json, status transitions
│   └── apply_answer_rules.py    # Match questions against answer rules, resolve conditional logic
├── skills/
│   └── ats/
│       └── generic.md           # Seed ATS skill — others created through use
├── tasks/                       # Runtime data (gitignored)
│   └── YYYY-MM-DD_company-slug_role-slug/
│       ├── task.json
│       ├── listing.json
│       ├── resume.pdf
│       ├── scout_report.json
│       ├── debrief.md
│       └── screenshots/
└── templates/
    └── questionnaire.md         # Obsidian note template
```

**Directory roles:**
- **agents/**: Subagent definitions — the full prompt and instructions the orchestrator passes when spawning each subagent. Agent definitions are stable.
- **scripts/**: Python tools that subagents call to perform their work. These are build-time deliverables created by the build agent during Phases 1-3. **Subagents must never write scripts from scratch at runtime — if a subagent needs a script that doesn't exist, that is a build failure, not a runtime behavior.** Scripts may evolve over time as new ATS patterns are encountered; script updates are flagged in debriefs and implemented by the build agent via PR.
- **skills/ats/**: Platform-specific knowledge loaded into the application subagent's context. Evolve over time via the orchestrator's `/skill` command.

### Updatable Components

| Component | Updated by | Mechanism |
|---|---|---|
| ATS skills (`skills/ats/`) | Orchestrator | `/skill` command after debrief review |
| Answer rules (`profile.json`) | Orchestrator | `/skill` command or `Save Rule:` tags |
| Python scripts (`scripts/`) | Build agent | Debrief flags needed changes → build agent creates PR → user merges |
| Agent definitions (`agents/`) | Build agent | Rarely — only if agent behavior needs restructuring |

### .gitignore

```
.chrome-profile/
tasks/
test-data/
*.pdf
```

Tracked: skills, config, profile, templates, CLAUDE.md, launch-browser.bat
Not tracked: Chrome profile, task runtime data, test artifacts, downloaded resumes

---

## Config (config.json)

```json
{
  "chrome_profile_path": "D:\\GitProjects\\ats-application-agent\\.chrome-profile",
  "obsidian_output_path": "D:\\Obsidian Notes\\Notes\\Job Seeking\\Auto App",
  "tasks_directory": "tasks",
  "profile_path": "profile.json",
  "agents_directory": "agents",
  "skills_directory": "skills",
  "browser": {
    "channel": "chrome",
    "headless": false,
    "start_minimized": true,
    "launch_method": "launch_persistent_context",
    "note": "Playwright must use launch_persistent_context with user_data_dir pointed at chrome_profile_path. Do not use browser.launch() or browser.new_context() — those create ephemeral profiles without saved cookies/sessions."
  },
  "url_classification": {
    "job_listing_domains": ["indeed.com", "ziprecruiter.com", "linkedin.com", "lever.co", "boards.greenhouse.io"],
    "resume_view_pattern": "docs.google.com/document/d/",
    "resume_download_pattern": "docs.google.com/document/export",
    "note": "Intake agent uses these patterns to classify URLs extracted from email PDFs. Add new job board domains here as they appear."
  },
  "pacing": {
    "submission_delay_seconds": 60,
    "domain_overrides": {
      "myworkdayjobs.com": 120
    },
    "note": "Minimum wait time between application agent invocations. Domain overrides apply when consecutive jobs target the same ATS domain."
  },
  "subagent_timeout_seconds": 600
}
```

---

## Profile & Answer Rules (profile.json)

### Structure

```json
{
  "contact": {
    "first_name": "",
    "last_name": "",
    "email": "",
    "phone": "",
    "linkedin_url": "",
    "city": "",
    "state": "",
    "zip": "",
    "country": "United States"
  },
  "demographics": {
    "work_authorization": "",
    "sponsorship_required": "",
    "veteran_status": "",
    "gender": "",
    "race_ethnicity": "",
    "disability": ""
  },
  "education": [
    {
      "institution": "",
      "degree": "",
      "field": "",
      "graduation_year": ""
    }
  ],
  "work_history": [
    {
      "company": "",
      "title": "",
      "start_date": "",
      "end_date": "",
      "current": false,
      "description": ""
    }
  ],
  "answer_rules": [],
  "always_ask": []
}
```

### Answer Rules

Rules match question text and resolve based on available options and field requirements.

```json
{
  "pattern": "veteran|military status",
  "logic": [
    {
      "condition": "options_contain",
      "value": "not a protected veteran|non-protected",
      "answer": "Veteran but not a protected veteran"
    },
    {
      "condition": "default",
      "answer": "Decline to answer"
    }
  ],
  "type": "select"
}
```

```json
{
  "pattern": "desired salary|salary expectation|compensation",
  "behavior": "skip_if_optional",
  "fallback": "ASK_USER"
}
```

Rules are added through the `/skill` command after reviewing debriefs, or via `Save Rule:` tags in the Obsidian questionnaire.

### Matching Algorithm & Precedence

Answer rule `pattern` fields are **case-insensitive regex** matched against the question label text. When evaluating a question against the rules:

1. **`always_ask` is checked first.** If the question matches any pattern in the `always_ask` list, it is always surfaced in the questionnaire regardless of any matching answer rules. `always_ask` has the highest precedence.
2. **Answer rules are evaluated in array order.** The first matching rule wins. More specific rules should be placed earlier in the array.
3. **`skip_if_optional` is evaluated after rule match.** If a matching rule has `behavior: "skip_if_optional"` and the field is not required, the field is left blank and excluded from the questionnaire.
4. **No matching rule.** If no rule matches and the field is not auto-fillable from profile data, it is surfaced in the questionnaire as needing user input.

### Always-Ask List

Question patterns that should never be auto-filled, always surfaced in the questionnaire:

```json
"always_ask": [
  "why are you interested",
  "tell us about yourself",
  "desired salary|salary|compensation"
]
```

---

## Obsidian Questionnaire Format

Filename: `YYYY-MM-DD Applications.md`
Location: `D:\Obsidian Notes\Notes\Job Seeking\Auto App\`

### Per-Job Section Structure

```markdown
## 1. Company Name — Job Title <!-- job_id: 2026-03-16_snap-finance_sr-dir-marketing-analytics -->
**ATS Platform:** workday
**Application URL:** https://...
**Resume:** company-resume.pdf
**Status:** awaiting answers

### Auto-Filled from Profile
- First Name: Dave <!-- field_id: f1 -->
- Last Name: Fimek <!-- field_id: f2 -->
- Email: davectr@gmail.com <!-- field_id: f3 -->
(shown for transparency, no action needed)

### Auto-Answered from Rules
- Authorized to work in US: Yes <!-- field_id: f7 -->
- Veteran status: Decline to answer <!-- field_id: f8 -->
- Gender: Male <!-- field_id: f9 -->
(review and override if incorrect)

### Needs Your Input

**Q1: Why are you interested in this role?** <!-- field_id: f5 -->
Type: textarea
Required: yes
Answer: 
Save Rule: 

**Q2: What is your desired salary?** <!-- field_id: f6 -->
Type: text
Required: no (skipped — field is optional)
```

The `<!-- job_id: XX -->` comment on each section header links the questionnaire section to the corresponding task directory. When `/submit` parses the questionnaire, it uses this `job_id` to match answers to the correct `tasks/` directory and scout report. The `<!-- field_id: XX -->` comments tie each question to the corresponding field in the scout report, which the application agent uses to locate the correct DOM element. Both are invisible in Obsidian's rendered view but machine-readable by the parser.

### Parser Resilience

The questionnaire parser should be resilient to minor user edits: extra blank lines, whitespace changes, and reordered lines within a section. The user must not delete structural elements (`## N.` headers, `**Q` prefixes, `Answer:` labels, or `<!-- field_id -->` comments). A note to this effect should appear at the top of each generated questionnaire.

**Structural integrity validation:** Before submission, the parser validates that all structural elements are intact for each job section. If a `<!-- field_id -->` comment is missing, a `## N.` header is malformed, or an `Answer:` label is absent, the parser surfaces a clear error naming the specific job section and element that's broken. It does not proceed with submission for that job. This prevents silent data loss — particularly important because `<!-- field_id -->` comments are invisible in Obsidian's rendered view and easy to accidentally delete.

### Save Rule Tags

When filling answers, the user can optionally tag:
- `Save Rule: always` — promote to answer rule in profile
- `Save Rule: never` — add to always-ask list
- No tag — one-off answer for this application only

---

## Debrief Format

Written by the application agent after each job submission attempt. Saved as `debrief.md` in the task directory.

```markdown
# Debrief: Company Name — Job Title

**Outcome:** submitted | failed | blocked
**ATS Platform:** workday
**Application URL:** https://...

## Platform Learnings
(Observations about how this ATS works that may apply to future applications)
- [learning with link to relevant page]

## One-Off Observations
(Things specific to this application that likely won't recur)
- [observation]

## Failures / Issues
- [what went wrong, if anything]

## Suggested Skill Updates (orchestrator — via `/skill`)
(ATS skill file changes and answer rule additions the orchestrator can apply)
- [recommendation]

## Suggested Script Updates (build agent — via PR)
(Python script changes needed for new form element types, ATS-specific logic, or parser improvements)
- [recommendation with details on what script and what change]

## Screenshots
- screenshots/step1-listing.png
- screenshots/step2-form.png
- screenshots/step3-submitted.png
```

---

## Browser Strategy

- Headed Chrome (installed, not bundled Chromium), minimized by default
- Playwright must use `launch_persistent_context` with `user_data_dir` pointed at `.chrome-profile` — retains cookies, login sessions, and browser fingerprint
- `channel="chrome"` ensures agents use installed Chrome, matching normal browsing fingerprint
- **Browser is ephemeral per subagent invocation.** Opens when a scout or application subagent starts, closes when that subagent exits. No persistent browser runs between tasks or during HITL phases.
- Chrome profile must not be open manually while agents are running (Chrome locks the profile directory)
- Agent can surface browser window when human intervention needed
- User solves blocker (CAPTCHA, login), signals `/continue`

---

## Auth Verification Flow

The scout agent may encounter login walls when navigating to application pages.

1. Scout attempts to reach the application form
2. If auth wall detected → writes `auth_required` status to task.json, exits
3. Orchestrator notifies user: "Auth required for [company]. Log in manually and run `/continue`."
4. User opens Chrome manually (via `launch-browser.bat`), navigates to the site, logs in, closes Chrome
5. User runs `/continue`
6. Orchestrator re-spawns scout for that job — now has authenticated session cookies

**Important:** CAPTCHAs are more aggressive during Playwright sessions. Login must happen in a manual Chrome session, not while Playwright is driving the browser. The persistent profile retains the session cookies for the agent to use afterward.

---

## Browser Launch Shortcut (launch-browser.bat)

```bat
@echo off
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="D:\GitProjects\ats-application-agent\.chrome-profile"
```

Placed in the project root for quick manual access to the Chrome profile.

---

## Security & Guardrails

- Domain allowlist: application agent only navigates to URLs from scout reports
- No credentials in repo: profile.json contains contact info only, no SSN/bank/passwords
- Sensitive field detection: agent pauses on requests for SSN, bank info, government ID
- Read-only profile data: agents read but never write to profile.json (only orchestrator writes via `/skill`)
- **No autonomous skill mutation:** subagents never modify skill files, answer rules, or profile data during execution. All updates go through the orchestrator's `/skill` command after user review.
- Subagent scope limits: scout cannot submit forms, intake cannot launch browser
- Audit trail: screenshots at every key step, debrief after every application attempt
- Chrome profile and runtime data gitignored — no sensitive data in version control

---

## Phase 1: Foundation

**Goal:** Repo structure, configuration, profile template, task state management, orchestrator skeleton.

### Deliverables
- Initialized repo with `.gitignore`, `CLAUDE.md`, `config.json`
- `profile.json` template (user fills in personal data)
- `launch-browser.bat`
- Task state management: directory creation, `task.json` read/write, status transitions, batch status query, `progress` field for mid-task resume
- Orchestrator agent definition (`CLAUDE.md`) with command routing for `/status`
- Questionnaire template (`templates/questionnaire.md`)
- Debrief template
- **Scripts:** `manage_task_state.py`

### Milestone
Orchestrator responds to `/status` and can create/read task directories. Profile template ready for user to populate.

---

## Phase 2a: Intake

**Goal:** Parse email PDFs and produce structured task data with downloaded resumes.

### Deliverables
- Intake subagent definition (`agents/intake.md`)
- Intake validation: verify URL count per listing, text extraction completeness, fail batch with descriptive error if thresholds not met
- Orchestrator wired up for `/apply` command (intake portion — creates task directories, downloads resumes, transitions tasks to `intake_complete`)
- **Scripts:** `parse_email_pdf.py`, `download_resumes.py`

### Milestone
User runs `/apply email.pdf`, task directories are created with `listing.json` and resume PDFs. All tasks in `intake_complete` state. Independently testable before any browser automation.

---

## Phase 2b: Scout + Questionnaire

**Goal:** Scout all application pages and produce the Obsidian questionnaire.

### Deliverables
- Scout subagent definition (`agents/scout.md`)
- Playwright browser launch with persistent Chrome profile via `launch_persistent_context`
- ATS platform detection from URL/DOM
- SSO-only apply flow detection (`sso_apply_only` state)
- Auth verification — detect login walls, report `auth_required`
- Form field mapping: labels, types, options, required/optional status, multiple selector strategies
- Multi-step navigation (job board → ATS "Apply" button)
- Screenshot capture at each step
- Obsidian questionnaire generation: auto-filled fields, auto-answered rules, human-input questions with field_id references
- Answer rules engine: pattern matching, conditional logic, `skip_if_optional`, `always_ask`, precedence order
- Orchestrator wired up for `/continue` command and scout dispatch
- **Scripts:** `launch_browser.py`, `scout_page.py`, `generate_questionnaire.py`, `apply_answer_rules.py`

### Milestone
User runs `/apply email.pdf`, receives a complete questionnaire in Obsidian with all jobs scouted, fields mapped, and known answers pre-filled.

---

## Phase 3: Application + Debrief

**Goal:** Full application submission loop with post-run reporting.

### Deliverables
- Application subagent definition (`agents/application.md`)
- Generic ATS skill (`skills/ats/generic.md`) — dynamic field reading, form filling, file upload, discovery mode behavior, unexpected field handling
- Submission readiness check: validate all required answers are present, questionnaire structural integrity validation
- Submission pacing: configurable delay between application agent invocations
- Form population from profile + answer rules + user responses, mapped via scout report `field_id` and `selectors`
- Resume upload with post-upload verification
- Multi-page form navigation
- Blocked state handling: screenshot, exit, await `/continue`
- Submission confirmation screenshot
- Dry-run mode (`/submit --dry-run`): completes all form filling but stops before final submit click, captures pre-submission screenshot
- Debrief generation after each application attempt
- Orchestrator wired up for `/submit` and `/debrief` commands
- **Scripts:** `fill_application.py`, `parse_questionnaire.py`

### Milestone
Full loop operational: email → questionnaire → answers → submission → debrief. User involved at two touchpoints plus debrief review.

---

## Phase 4: Learning Loop

**Goal:** System improves with each application cycle.

### Deliverables

**`Save Rule:` Processing**
- Parse `Save Rule: always` tags from completed questionnaires → add new answer rules to `profile.json`
- Parse `Save Rule: never` tags → add patterns to `always_ask` list in `profile.json`

**`/skill` Command Implementation**
- Freeform mode: orchestrator receives natural language instruction, determines which file to update (ATS skill or profile.json), makes the edit
- Debrief-guided mode: orchestrator reads debrief's "Suggested Skill Updates" section, presents each suggestion to the user, applies approved changes
- For ATS skill files: orchestrator creates or appends to the appropriate `skills/ats/{platform}.md` file
- For answer rules: orchestrator adds/modifies entries in `profile.json` `answer_rules` array

**ATS Skill File Format**
- Platform-specific skill files are markdown documents loaded into the application subagent's context at spawn time
- Structure:
  ```markdown
  # ATS Skill: Workday

  ## Platform Identification
  - URL pattern: `myworkdayjobs.com`

  ## Navigation Flow
  - [step-by-step description of how to reach the application form]

  ## Known Field Patterns
  - [field types and locations specific to this platform]

  ## Common Issues
  - [gotchas, failure modes, workarounds]

  ## Revision History
  - [date]: [what was added/changed and from which debrief]
  ```
- Skills start empty and accumulate content through debrief-reviewed updates
- Each update includes a revision history entry linking back to the debrief that prompted it

**Debrief Triage**
- The orchestrator categorizes debrief observations when presenting them via `/debrief`:
  - **Skill updates** (orchestrator can apply): ATS navigation patterns, field layout knowledge, timing/delay recommendations
  - **Script updates** (build agent needed): new form element types, parser improvements, new automation patterns
  - **Answer rules** (orchestrator can apply): new recurring questions with consistent answers
  - **One-offs** (no action): observations specific to a single application

### Milestone
After several application cycles, most questionnaires only surface genuinely new or role-specific questions. ATS skills cover the platforms encountered. The system is measurably faster and requires less human input per batch.
