# Issue #6: End-to-End Test Plan — Full Scenario Coverage Across ATS Platforms

**Branch:** `issue-6`
**Depends on:** All phases (#1–#5) — merged

---

## Objective

Validate every code path in the ATS Application Agent through real execution against live ATS platforms. Every test must execute the actual code it is testing — no mocks, no simulated outputs. The user observes results at defined checkpoints and provides manual inputs where required (auth, CAPTCHAs, questionnaire answers).

---

## Test Cycle Protocol

This issue follows an iterative cycle:

```
1. Test agent executes the full test plan
2. At each checkpoint → agent stops, presents results, waits for user
3. On failure → agent documents the failure in test-output.md
4. After full run → dev agent reads test-output.md, makes fixes
5. Test agent re-runs the plan (updating this issue with results)
6. Repeat until all tests pass
```

### Failure Documentation Format (test-output.md)

Each failure entry in `test-output.md` must include:

```markdown
## FAIL: <Test ID> — <Test Name>

**Script:** `scripts/<script>.py`
**Command:** `<exact command that was run>`
**Expected:** <what should have happened>
**Actual:** <what actually happened>
**Error Output:**
\`\`\`
<stderr/stdout/traceback>
\`\`\`
**Likely Root Cause:** <analysis of why it failed>
**Suggested Fix:** <specific code changes with file and function references>
**Severity:** blocking | degraded | cosmetic
```

---

## Test Data Inventory

| PDF | Batch Date | Jobs | Companies |
|-----|-----------|------|-----------|
| `test-data/sample-email.pdf` | 2026-03-16 | 4 | Snap Finance, RKW Residential, Semrush, Exzeo Group |
| `test-data/sample-email-2.pdf` | 2026-03-12 | 3 | BoomPop, Roadpass Digital, Raytheon |
| `test-data/sample-email-3.pdf` | 2026-03-11 | 3 | DeepIntent, Calix, TextNow |
| `test-data/sample-email-4.pdf` | 2026-03-10 | 6 | Fleetio, Enzo Tech Group, Patriot Holdings, Fusable, Pearl Inc., FICO |

**Total: 16 jobs across 4 batches, covering Indeed and ZipRecruiter job boards with unknown ATS platforms behind them.**

---

## Pre-Test Setup

Before any test execution:

```bash
cd /d/GitProjects/ats-application-agent

# 1. Clean prior test runs
python -c "import shutil, os; [shutil.rmtree(os.path.join('tasks', d)) for d in os.listdir('tasks') if os.path.isdir(os.path.join('tasks', d))]" 2>/dev/null

# 2. Verify profile.json is populated
python -c "import json; p=json.load(open('profile.json')); assert p['contact']['first_name'], 'Profile not populated'; print('Profile OK:', p['contact']['first_name'], p['contact']['last_name'])"

# 3. Verify Chrome is NOT running with the project profile
# (User must close Chrome if open with .chrome-profile)

# 4. Verify scripts exist
python -c "
import os
scripts = ['parse_email_pdf.py','download_resumes.py','launch_browser.py','scout_page.py','fill_application.py','manage_task_state.py','generate_questionnaire.py','apply_answer_rules.py','parse_questionnaire.py']
missing = [s for s in scripts if not os.path.exists(f'scripts/{s}')]
print('All scripts present' if not missing else f'MISSING: {missing}')
"

# 5. Initialize test-output.md
echo "# End-to-End Test Results" > test-output.md
echo "" >> test-output.md
echo "**Run Date:** $(date +%Y-%m-%d)" >> test-output.md
echo "**Run Number:** 1" >> test-output.md
echo "" >> test-output.md
```

**CHECKPOINT: Setup** — Present setup verification results. User confirms Chrome is closed and ready to proceed.

---

## Phase 1: Intake Pipeline

Tests intake for all 4 sample emails. No browser needed.

### T1.1 — Parse sample-email.pdf (4 jobs)

```bash
python scripts/parse_email_pdf.py test-data/sample-email.pdf --config config.json
```

**Verify:**
- [ ] Exit code 0
- [ ] Output is valid JSON array with exactly 4 elements
- [ ] Each element has non-empty `company`, `title`, `description`
- [ ] Each element has all 3 URL types: `urls.job_listing`, `urls.resume_view`, `urls.resume_download`
- [ ] Companies match: Snap Finance, RKW Residential, Semrush, Exzeo Group
- [ ] Job listing URLs are Indeed or ZipRecruiter domains
- [ ] Resume download URLs are Google Docs export links

### T1.2 — Parse sample-email-2.pdf (3 jobs)

```bash
python scripts/parse_email_pdf.py test-data/sample-email-2.pdf --config config.json
```

**Verify:** Same structure checks. Expect 3 jobs: BoomPop, Roadpass Digital, Raytheon.

### T1.3 — Parse sample-email-3.pdf (3 jobs)

```bash
python scripts/parse_email_pdf.py test-data/sample-email-3.pdf --config config.json
```

**Verify:** Same structure checks. Expect 3 jobs: DeepIntent, Calix, TextNow.

### T1.4 — Parse sample-email-4.pdf (6 jobs)

```bash
python scripts/parse_email_pdf.py test-data/sample-email-4.pdf --config config.json
```

**Verify:** Same structure checks. Expect 6 jobs: Fleetio, Enzo Tech Group, Patriot Holdings, Fusable, Pearl Inc., FICO.

### T1.5 — Task Directory Creation (batch from sample-email.pdf)

For each of the 4 parsed listings from T1.1:

```bash
python scripts/manage_task_state.py create \
  --batch-date 2026-03-16 \
  --company "<company>" \
  --title "<title>" \
  --urls '<urls JSON>'
```

**Verify:**
- [ ] 4 task directories created under `tasks/`
- [ ] Each contains `task.json` with status `queued`
- [ ] `job_id` follows `YYYY-MM-DD_company-slug_title-slug` format
- [ ] `status_history` has one entry

### T1.6 — Resume Download

For each listing from T1.1:

```bash
python scripts/download_resumes.py --listing-json '[<listing>]' --output-dir "tasks/<job_id>"
```

**Verify:**
- [ ] Output JSON has `status` field per download
- [ ] Successful downloads produce valid PDF files (> 1KB)
- [ ] `auth_required` status is handled gracefully (Google Doc not shared publicly)
- [ ] Resume filename matches `<company-slug>-resume.pdf`

### T1.7 — Status Transition to intake_complete

For each task where listing.json was written:

```bash
python scripts/manage_task_state.py transition \
  --job-id "<job_id>" \
  --status intake_complete \
  --last-agent intake \
  --resume-path "tasks/<job_id>/<resume-filename>"
```

**Verify:**
- [ ] Task status is now `intake_complete`
- [ ] `status_history` has 2 entries (queued → intake_complete)
- [ ] `resume_path` is set (if download succeeded)

### T1.8 — Batch Status Query

```bash
python scripts/manage_task_state.py batch-status --batch-date 2026-03-16
```

**Verify:**
- [ ] Shows all 4 tasks
- [ ] All in `intake_complete` status
- [ ] Output is valid JSON

**CHECKPOINT: Intake** — Present summary table of all 4 parsed jobs (company, title, resume status, task status). User reviews before proceeding to scouting.

---

## Phase 2: Browser Launch Validation

### T2.1 — Playwright Browser Launch

```bash
python scripts/launch_browser.py --config config.json --test
```

**Verify:**
- [ ] Browser launches in headed mode
- [ ] Uses the Chrome profile from `.chrome-profile/`
- [ ] Test page loads (about:blank)
- [ ] Browser closes cleanly
- [ ] No errors in output

**USER ACTION:** If this fails with "Chrome profile locked," user must close all Chrome instances and retry.

**CHECKPOINT: Browser** — Report browser launch result. User confirms Chrome is working.

---

## Phase 3: Scout Pipeline

Scouts all 4 jobs from the sample-email.pdf batch. This is where ATS diversity appears — each job board link may redirect to a different ATS.

### T3.1 — Scout Job 1 (Snap Finance via Indeed)

```bash
python scripts/scout_page.py --task-dir "tasks/<snap-finance-job-id>" --config config.json
```

**Verify:**
- [ ] Browser opens and navigates to Indeed job listing
- [ ] Script finds and clicks "Apply" button (may redirect to company ATS)
- [ ] `scout_report.json` is written to task directory
- [ ] `listing_status` is one of: `open`, `expired`, `requires_account`, `sso_apply_only`
- [ ] If `open`: `ats_platform` is detected (or `null` for unknown)
- [ ] If `open`: `pages` array contains at least 1 page with fields
- [ ] Each field has `field_id`, `label`, `type`, `required`, `selectors`
- [ ] Screenshots captured in `tasks/<job_id>/screenshots/`

**Possible outcomes requiring user action:**
- `auth_required` → User logs in via `launch-browser.bat`, re-run scout
- `listing_expired` → Document and skip
- `sso_apply_only` → Document and skip

### T3.2 — Scout Job 2 (RKW Residential via Indeed)

Same verification as T3.1 against the RKW Residential task directory.

### T3.3 — Scout Job 3 (Semrush via ZipRecruiter)

Same verification as T3.1 against the Semrush task directory.

### T3.4 — Scout Job 4 (Exzeo Group via ZipRecruiter)

Same verification as T3.1 against the Exzeo Group task directory.

### T3.5 — Scout Report Enrichment

For each scouted job (status `open`), verify profile key enrichment:

```bash
python -c "
import json
report = json.load(open('tasks/<job_id>/scout_report.json'))
profile = json.load(open('profile.json'))
for page in report['pages']:
    for field in page['fields']:
        if field.get('auto_fill'):
            pk = field.get('profile_key','')
            print(f'  {field[\"label\"]} -> {pk} = auto_fill:{field[\"auto_fill\"]}')
"
```

**Verify:**
- [ ] Contact fields (First Name, Last Name, Email, Phone) map to `contact.*` profile keys
- [ ] Demographic fields map to `demographics.*` profile keys
- [ ] File upload field maps to `_resume_file`
- [ ] `auto_fill` is `true` only when the corresponding profile value is non-empty

### T3.6 — Status Transitions After Scouting

For each job that was successfully scouted:

```bash
python scripts/manage_task_state.py transition \
  --job-id "<job_id>" \
  --status scouted \
  --last-agent scout \
  --ats-platform "<detected_platform>" \
  --scout-report-path "tasks/<job_id>/scout_report.json"
```

**Verify:**
- [ ] Status transitions to `scouted`
- [ ] `ats_platform` is set in task.json
- [ ] `scout_report_path` is set

For expired/auth/SSO jobs, verify the correct terminal state was set.

**CHECKPOINT: Scout** — Present scout summary table (company, ATS platform, listing_status, field count, auto-fill count). Include screenshots from each scout. User reviews before questionnaire generation.

---

## Phase 4: Answer Rules Engine

### T4.1 — Answer Rule Matching (with test profile)

```bash
python scripts/apply_answer_rules.py \
  --scout-report "tasks/<scouted-job-id>/scout_report.json" \
  --profile profile.json
```

**Verify:**
- [ ] Output is valid JSON with `resolution_category` for each field
- [ ] `auto_filled` fields have non-empty `resolution_answer`
- [ ] Fields matching `always_ask` patterns (if any) resolve to `needs_input`
- [ ] Unmatched fields resolve to `needs_input`
- [ ] If answer_rules exist: matching fields resolve to `auto_answered` with correct answer

### T4.2 — Answer Rules with Test Profile (comprehensive rule coverage)

Use the test profile with pre-populated rules:

```bash
python scripts/apply_answer_rules.py \
  --scout-report test-data/sample_scout_report.json \
  --profile test-data/test_profile.json
```

**Verify:**
- [ ] `skip_if_optional` behavior works for optional fields
- [ ] Conditional logic (`options_contain`) selects correct answer based on available options
- [ ] `default` condition serves as fallback
- [ ] `always_ask` overrides matching answer rules
- [ ] First matching rule wins (precedence order)

**CHECKPOINT: Answer Rules** — Present resolution table (field label, category, answer). User reviews before questionnaire generation.

---

## Phase 5: Questionnaire Generation & Parsing

### T5.1 — Generate Questionnaire

Collect all scouted task directories and generate:

```bash
python scripts/generate_questionnaire.py \
  --task-dirs "tasks/<job_id_1>,tasks/<job_id_2>,..." \
  --profile profile.json \
  --config config.json
```

**Verify:**
- [ ] Questionnaire file created at Obsidian output path: `D:\Obsidian Notes\Notes\Job Seeking\Auto App\YYYY-MM-DD Applications.md`
- [ ] File contains sections for each scouted job
- [ ] Each section has `<!-- job_id: ... -->` comment
- [ ] Auto-Filled section lists profile-mapped fields with `<!-- field_id: ... -->` comments
- [ ] Auto-Answered section lists rule-matched fields
- [ ] Needs Your Input section lists remaining fields with `**Q` prefix, `Type:`, `Required:`, `Answer:`, `Save Rule:` fields
- [ ] All `<!-- field_id -->` comments are present and valid
- [ ] Warning header about not deleting structural elements is present

### T5.2 — Transition to awaiting_answers

For each scouted task:

```bash
python scripts/manage_task_state.py transition \
  --job-id "<job_id>" \
  --status awaiting_answers \
  --last-agent orchestrator
```

**Verify:**
- [ ] Status transitions to `awaiting_answers`
- [ ] `status_history` updated correctly

**CHECKPOINT: Questionnaire** — Present the generated questionnaire content. Open it in Obsidian for user to see. User fills in answers for at least 2 jobs (one fully, one partially to test "not ready" detection). User also adds `Save Rule: always` to at least one answer and `Save Rule: never` to another.

**USER ACTION REQUIRED:** Fill in the questionnaire in Obsidian:
1. Complete all required answers for at least 1 job
2. Leave at least 1 required answer empty on another job (to test skip behavior)
3. Add `Save Rule: always` tag on one answer
4. Add `Save Rule: never` tag on another answer
5. Save the file
6. Signal ready to continue

---

## Phase 6: Questionnaire Parsing

### T6.1 — Parse Completed Questionnaire

```bash
python scripts/parse_questionnaire.py --input "<path to questionnaire .md>"
```

**Verify:**
- [ ] Output is valid JSON
- [ ] Each job has `ready: true` or `ready: false` based on required answer completeness
- [ ] Job with all required answers filled → `ready: true`
- [ ] Job with missing required answers → `ready: false` with descriptive errors
- [ ] `fields` array includes all field_ids from the questionnaire
- [ ] User-input answers are captured correctly
- [ ] `save_rule` fields captured: `"always"` and `"never"` where tagged

### T6.2 — Parse with Job ID Filter

```bash
python scripts/parse_questionnaire.py --input "<path>" --job-id "<specific job_id>"
```

**Verify:**
- [ ] Output contains only the specified job
- [ ] All fields and answers for that job are present

### T6.3 — Structural Validation

Create a copy of the questionnaire with a deliberately broken structure (missing `<!-- field_id -->` comment):

```bash
# The test agent creates a corrupted copy and parses it
python scripts/parse_questionnaire.py --input "<corrupted copy>"
```

**Verify:**
- [ ] Parser detects the structural error
- [ ] Error message identifies the specific job section and missing element
- [ ] Job with broken structure has `ready: false`

### T6.4 — Save Rule Extraction

```bash
python -c "
import json, sys
sys.path.insert(0, 'scripts')
from parse_questionnaire import parse_questionnaire
result = parse_questionnaire('<path to questionnaire>')
rules = [f for j in result['jobs'] for f in j['fields'] if f.get('save_rule')]
for r in rules:
    print(f'{r[\"label\"]} -> save_rule: {r[\"save_rule\"]}')
"
```

**Verify:**
- [ ] `save_rule: "always"` entries found
- [ ] `save_rule: "never"` entries found
- [ ] Non-tagged fields have `save_rule: null`

**CHECKPOINT: Parse** — Present parse results table (job, ready status, field count, save rules found). User confirms accuracy matches what they entered.

---

## Phase 7: Application Submission (Dry Run)

### T7.1 — Transition Ready Jobs to ready_to_apply

For each job where `ready: true`:

```bash
python scripts/manage_task_state.py transition \
  --job-id "<job_id>" \
  --status ready_to_apply \
  --last-agent orchestrator
```

### T7.2 — Dry Run Application (first ready job)

Build the answers dict from the parsed questionnaire, then:

```bash
python scripts/fill_application.py \
  --task-dir "tasks/<job_id>" \
  --answers '<answers JSON mapping field_id to answer>' \
  --config config.json \
  --dry-run
```

**Verify:**
- [ ] Browser opens and navigates to the application URL
- [ ] Fields are filled in order (top to bottom)
- [ ] Selector fallback chain works (primary → by_label → by_aria)
- [ ] Text fields filled correctly (name, email, phone, etc.)
- [ ] Select dropdowns select the correct option
- [ ] Resume upload executes via `set_input_files()` and filename is verified on page
- [ ] Multi-page navigation works (if applicable)
- [ ] Sensitive field detection triggers on SSN/bank fields (if encountered)
- [ ] CAPTCHA detection works (if encountered)
- [ ] Pre-submission screenshot is captured
- [ ] Script stops before clicking submit (dry-run mode)
- [ ] Output JSON has `outcome: "dry_run"`
- [ ] `fields_filled` array lists all filled field_ids
- [ ] `screenshots` array lists all captured screenshots

**Possible outcomes requiring user action:**
- `blocked` with CAPTCHA → User solves CAPTCHA in manual Chrome, then re-run with `--resume-from`
- `blocked` with auth → User logs in, then re-run
- `blocked` with sensitive field → Expected safety behavior, document and proceed

**CHECKPOINT: Dry Run** — Present dry-run results: fields filled, screenshots captured, pre-submission state. User reviews the screenshots to verify form was filled correctly. User decides whether to proceed to live submission.

---

## Phase 8: Application Submission (Live)

**USER DECISION REQUIRED:** User chooses which jobs to submit live. Some jobs may have expired listings or require accounts not worth creating. The test can proceed with even 1 live submission.

### T8.1 — Live Submission

For each job the user approves for live submission:

```bash
python scripts/fill_application.py \
  --task-dir "tasks/<job_id>" \
  --answers '<answers JSON>' \
  --config config.json
```

**Verify:**
- [ ] All fields filled (same checks as dry-run)
- [ ] Submit button clicked
- [ ] Confirmation page/message detected
- [ ] Post-submission screenshot captured
- [ ] Output JSON has `outcome: "submitted"`
- [ ] No unexpected fields that couldn't be resolved

### T8.2 — Status Transition to submitted

```bash
python scripts/manage_task_state.py transition \
  --job-id "<job_id>" \
  --status submitted \
  --last-agent application
```

**Verify:**
- [ ] Status is `submitted`
- [ ] `status_history` reflects full lifecycle

### T8.3 — Blocked State Handling (if encountered)

If any application hits a blocker:

```bash
python scripts/manage_task_state.py transition \
  --job-id "<job_id>" \
  --status blocked \
  --last-agent application \
  --progress '{"page_url":"...","page_number":N,"fields_filled":[...],"block_reason":"...","screenshot":"..."}'
```

**Verify:**
- [ ] `progress` field is populated in task.json
- [ ] `block_reason` is descriptive
- [ ] Screenshot of blocked state exists

**USER ACTION:** If blocked, user resolves the blocker manually, then:

```bash
python scripts/fill_application.py \
  --task-dir "tasks/<job_id>" \
  --answers '<answers JSON>' \
  --config config.json \
  --resume-from '{"page_url":"...","page_number":N}'
```

**Verify:**
- [ ] Agent re-fills all fields from the beginning (ATS forms don't retain data)
- [ ] Agent navigates to the correct page
- [ ] Application completes past the previous block point

### T8.4 — Submission Pacing

If multiple jobs are submitted sequentially, verify pacing delay:

```bash
python -c "
import json
cfg = json.load(open('config.json'))
print(f'Default delay: {cfg[\"pacing\"][\"submission_delay_seconds\"]}s')
print(f'Domain overrides: {cfg[\"pacing\"][\"domain_overrides\"]}')
"
```

**Verify:**
- [ ] At least 60 seconds between submissions (or domain-specific override)
- [ ] Timestamps in task.json reflect the delay

**CHECKPOINT: Submission** — Present submission results table (company, outcome, fields filled, pages completed, screenshots). User reviews.

---

## Phase 9: Debrief Generation

### T9.1 — Verify Debrief Files

For each submitted/blocked/failed job, verify `debrief.md` exists:

```bash
cat tasks/<job_id>/debrief.md
```

**Verify:**
- [ ] Debrief file exists in each task directory that had an application attempt
- [ ] Contains required sections: Platform Learnings, One-Off Observations, Failures/Issues, Suggested Skill Updates, Suggested Script Updates, Screenshots
- [ ] `Outcome` matches task status
- [ ] `ATS Platform` matches scout report
- [ ] Screenshots section lists actual screenshot files that exist

### T9.2 — Batch Status Final

```bash
python scripts/manage_task_state.py batch-status --batch-date 2026-03-16
```

**Verify:**
- [ ] All tasks have reached a terminal or expected state
- [ ] Status distribution is accurate (submitted, blocked, failed, expired, sso_apply_only)

**CHECKPOINT: Debrief** — Present debrief content for each job. User reviews platform learnings and suggestions.

---

## Phase 10: Learning Loop

### T10.1 — Save Rule: always Processing

From the parsed questionnaire (Phase 6), take the field tagged `Save Rule: always`:

```bash
python -c "
import json
with open('profile.json', 'r') as f:
    profile = json.load(f)
new_rule = {
    'pattern': '<regex derived from the question label>',
    'answer': '<the user answer>',
    'type': '<field type>'
}
profile['answer_rules'].append(new_rule)
with open('profile.json', 'w') as f:
    json.dump(profile, f, indent=2, ensure_ascii=False)
    f.write('\n')
print('Rule added:', json.dumps(new_rule, indent=2))
"
```

**Verify:**
- [ ] Rule added to `profile.json` `answer_rules` array
- [ ] Pattern is a valid regex
- [ ] Answer matches what the user entered

### T10.2 — Save Rule: never Processing

From the parsed questionnaire, take the field tagged `Save Rule: never`:

```bash
python -c "
import json
with open('profile.json', 'r') as f:
    profile = json.load(f)
profile['always_ask'].append('<pattern from question label>')
with open('profile.json', 'w') as f:
    json.dump(profile, f, indent=2, ensure_ascii=False)
    f.write('\n')
print('Added to always_ask:', profile['always_ask'][-1])
"
```

**Verify:**
- [ ] Pattern added to `always_ask` array
- [ ] Pattern is a reasonable regex for the question

### T10.3 — Verify Rules Apply on Re-run

Re-run answer rules against a scout report to verify the new rules take effect:

```bash
python scripts/apply_answer_rules.py \
  --scout-report "tasks/<job_id>/scout_report.json" \
  --profile profile.json
```

**Verify:**
- [ ] The question that had `Save Rule: always` is now `auto_answered`
- [ ] The question that had `Save Rule: never` is now `needs_input` (forced by always_ask)

**CHECKPOINT: Learning Loop** — Present the updated profile.json rules and always_ask list. Verify rules would apply correctly on a future batch.

---

## Phase 11: Multi-Batch & Edge Cases

### T11.1 — Second Batch Intake (sample-email-2.pdf)

Run the full intake pipeline on a second email:

```bash
python scripts/parse_email_pdf.py test-data/sample-email-2.pdf --config config.json
```

Then create tasks, download resumes, transition to intake_complete.

**Verify:**
- [ ] Second batch creates separate task directories
- [ ] Batch-status correctly scopes to the requested date
- [ ] No interference with the first batch

### T11.2 — Batch Status Default (most recent)

```bash
python scripts/manage_task_state.py batch-status
```

**Verify:**
- [ ] Returns the most recent batch (not an older one)

### T11.3 — Batch Status with Date Filter

```bash
python scripts/manage_task_state.py batch-status --batch-date 2026-03-16
```

**Verify:**
- [ ] Returns only the specified batch

### T11.4 — Third Batch (sample-email-3.pdf) and Fourth Batch (sample-email-4.pdf)

Repeat intake parsing for remaining emails:

```bash
python scripts/parse_email_pdf.py test-data/sample-email-3.pdf --config config.json
python scripts/parse_email_pdf.py test-data/sample-email-4.pdf --config config.json
```

**Verify:**
- [ ] All 3 jobs from email-3 parse correctly
- [ ] All 6 jobs from email-4 parse correctly
- [ ] Total of 16 jobs across 4 batches when all are created

**CHECKPOINT: Multi-Batch** — Present summary of all batches and their status.

---

## Scenario Coverage Matrix

This matrix tracks which scenarios have been exercised during the test run. The test agent marks each as it is encountered:

| Scenario | Test ID | Status | Notes |
|----------|---------|--------|-------|
| **Intake** | | | |
| PDF with multiple jobs parsed | T1.1-T1.4 | | |
| Resume download success | T1.6 | | |
| Resume download auth_required | T1.6 | | |
| Task directory creation | T1.5 | | |
| Status transition queued→intake_complete | T1.7 | | |
| Batch status query | T1.8 | | |
| **Scout** | | | |
| Job listing open, form found | T3.1-T3.4 | | |
| ATS platform detected (Workday/Greenhouse/etc) | T3.1-T3.4 | | |
| Unknown ATS (null platform) | T3.1-T3.4 | | |
| Listing expired | T3.1-T3.4 | | |
| Auth required (login wall) | T3.1-T3.4 | | |
| SSO-only apply flow | T3.1-T3.4 | | |
| Multi-step navigation (job board → ATS) | T3.1-T3.4 | | |
| Profile key enrichment | T3.5 | | |
| Screenshot capture | T3.1-T3.4 | | |
| **Answer Rules** | | | |
| Auto-fill from profile | T4.1 | | |
| Auto-answer from rule match | T4.2 | | |
| Conditional logic (options_contain) | T4.2 | | |
| skip_if_optional behavior | T4.2 | | |
| always_ask override | T4.2 | | |
| No rule match → needs_input | T4.1 | | |
| **Questionnaire** | | | |
| Questionnaire generation with all 3 sections | T5.1 | | |
| Field_id comments present | T5.1 | | |
| Job_id comments present | T5.1 | | |
| Questionnaire parsing | T6.1 | | |
| Readiness check (ready vs. not ready) | T6.1 | | |
| Structural validation failure | T6.3 | | |
| Save Rule extraction | T6.4 | | |
| **Application** | | | |
| Dry-run mode (stop before submit) | T7.2 | | |
| Text field filling | T7.2 | | |
| Select dropdown filling | T7.2 | | |
| Radio button selection | T7.2 | | |
| Checkbox toggling | T7.2 | | |
| Resume upload + verification | T7.2 | | |
| Multi-page navigation | T7.2 | | |
| CAPTCHA detection | T7.2/T8.1 | | |
| Sensitive field detection | T7.2/T8.1 | | |
| Live submission | T8.1 | | |
| Blocked state with progress | T8.3 | | |
| Resume from blocked state (/continue) | T8.3 | | |
| Submission pacing delay | T8.4 | | |
| **Debrief** | | | |
| Debrief file generation | T9.1 | | |
| All sections present | T9.1 | | |
| Screenshots referenced and exist | T9.1 | | |
| **Learning Loop** | | | |
| Save Rule: always → answer rule | T10.1 | | |
| Save Rule: never → always_ask | T10.2 | | |
| New rule takes effect on next run | T10.3 | | |
| **Multi-Batch** | | | |
| Multiple batches coexist | T11.1 | | |
| Batch status scoping by date | T11.3 | | |
| Default batch = most recent | T11.2 | | |

---

## Completion Criteria

The test plan is **PASS** when:
1. All 16 jobs parse correctly across 4 sample emails
2. At least 3 different ATS platforms are encountered during scouting
3. At least 1 job completes the full lifecycle: queued → submitted
4. At least 1 dry-run completes successfully
5. At least 1 blocked state is handled and resumed
6. Questionnaire round-trip (generate → user fill → parse) is accurate
7. Save Rule processing adds rules that take effect on subsequent runs
8. All scenarios in the coverage matrix are marked pass or documented as not-encountered
9. `test-output.md` has no unresolved `blocking` severity failures

---

## Re-Run Protocol

After the dev agent makes fixes based on `test-output.md`:

1. Increment the "Run Number" in `test-output.md`
2. Add a new section: `## Run N Results`
3. Re-run only the failed tests (reference by Test ID)
4. If a fix introduces new failures, document those too
5. Update the scenario coverage matrix
6. Repeat until all tests pass or remaining failures are documented as known limitations
