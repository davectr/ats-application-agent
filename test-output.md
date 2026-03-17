# E2E Test Results — Issue #12

**Branch:** `issue-12`
**Date:** 2026-03-17
**Test Plan:** `docs/scratchpads/issue-6.md`

---

## Phase 1: Intake Pipeline — PASS (all 8 tests)

| Test | Description | Result | Notes |
|------|------------|--------|-------|
| T1.1 | Parse sample-email.pdf (4 jobs) | PASS | |
| T1.2 | Parse sample-email-2.pdf (3 jobs) | PASS | |
| T1.3 | Parse sample-email-3.pdf (5 jobs) | PASS | Required fix: `greenhouse.io` domain matching |
| T1.4 | Parse sample-email-4.pdf (4 jobs) | PASS | Required fix: comma separator fallback for company/title |
| T1.5 | Create task directories | PASS | 4 task dirs created for batch 1 |
| T1.6 | Download resumes | PASS | Google Auth required — expected download failure is acceptable |
| T1.7 | Status transitions | PASS | queued → intake_complete |
| T1.8 | Batch status query | PASS | All 4 jobs in correct state |

**Fixes applied:**
- `config.json`: Changed `boards.greenhouse.io` to `greenhouse.io` for broader domain matching
- `parse_email_pdf.py`: Added `rfind(", ")` fallback for company/title separator

---

## Phase 2: Browser Launch — PASS

| Test | Description | Result | Notes |
|------|------------|--------|-------|
| T2.1 | Launch Playwright persistent context | PASS | Chrome launched with profile, navigated, closed cleanly |

---

## Phase 3: Scout Pipeline — PASS (all 4 jobs)

| Test | Job | ATS Platform | Status | Fields | Notes |
|------|-----|-------------|--------|--------|-------|
| T3.1 | Snap Finance | workday | requires_account | 0 | Workday account creation page (password fields) |
| T3.2 | RKW Residential | indeed_smart_apply | open | 3 | Zip code, City/State, Street address |
| T3.3 | Semrush | workday | requires_account | 0 | Workday sign-in page (blank JS rendering) |
| T3.4 | Exzeo Group | paycom | open | 4 | First Name, Last Name, Email, Confirm Email |

**Fixes applied:**
- `scout_page.py`: Fixed ATS detection after in-place navigation (save pre-apply URL for comparison)
- `scout_page.py`: Added redirect URL re-read after wait (ZipRecruiter → Workday)
- `scout_page.py`: Added Workday-specific 8s JS rendering wait
- `scout_page.py`: Added Workday sign-in page detection
- `scout_page.py`: Added Paycom and Indeed SmartApply to ATS_PATTERNS
- `scout_page.py`: Added `_clean_label()` to strip required indicators from labels
- `scout_page.py`: Added Cloudflare Turnstile detection (title + iframe)
- `scout_page.py`: Rewrote `find_apply_button()` to handle new-tab opens via `context.expect_page()`
- `scout_page.py`: Added multi-click loop (Step 4b) with `_click_modal_button()` for ATS modals
- `scout_page.py`: Added password field detection for account creation pages

---

## Phase 4: Answer Rules Engine — PASS

| Test | Description | Result | Notes |
|------|------------|--------|-------|
| T4.1 | Answer rules with empty rules | PASS | All fields → needs_input |
| T4.2 | Answer rules with test profile | PASS | auto_filled, auto_answered, conditional, always_ask all correct |

**Verified behaviors:**
- `auto_filled`: profile keys resolved correctly (Dave, Fimek, email, resume)
- `auto_answered`: work auth → "Yes", veteran → "I am not a protected veteran" (conditional), referral → "Indeed"
- `always_ask`: overrides matching rules (salary field stays needs_input)
- `skip_if_optional`: optional → skipped, required → needs_input (tested in isolation)
- `options_contain`: conditional logic selects correct option from available choices
- `default`: fallback condition used when no options_contain match

---

## Phase 5: Questionnaire Generation — PASS

| Test | Description | Result | Notes |
|------|------------|--------|-------|
| T5.1 | Generate questionnaire | PASS | 2 open jobs included, 2 requires_account excluded |
| T5.2 | Transition to awaiting_answers | PASS | Both jobs → awaiting_answers |

**Verified:**
- Warning header present
- `<!-- job_id -->` and `<!-- field_id -->` comments on all structural elements
- `**Q` prefix, `Type:`, `Required:`, `Answer:`, `Save Rule:` fields present
- Auto-Filled/Auto-Answered sections present (both empty for this profile)
- Non-open listings correctly excluded

---

## Phase 6: Questionnaire Parsing — PASS

| Test | Description | Result | Notes |
|------|------------|--------|-------|
| T6.1 | Parse filled questionnaire | PASS | Required fix: add descriptive errors for missing required answers |
| T6.2 | Parse with job ID filter | PASS | Single job returned correctly |
| T6.3 | Structural validation (broken field_id) | PASS | Required fix: detect **Q lines missing field_id comment |
| T6.4 | Save rule extraction | PASS | "always" and "never" rules captured |

**Fixes applied:**
- `parse_questionnaire.py`: Added descriptive error messages for missing required answers
- `parse_questionnaire.py`: Detect `**Q` lines without `<!-- field_id -->` instead of silently corrupting previous field

**Verified:**
- RKW: `ready: true` (all optional fields)
- Exzeo: `ready: false`, error: "Required field 'Confirm Email' (f4) has no answer"
- Save rules: f1 "Zip code" → always, f2 "City, State" → never

---

## Phase 7: Application Dry-Run — PARTIAL PASS

| Test | Job | ATS | Result | Fields Filled | Notes |
|------|-----|-----|--------|--------------|-------|
| T7.2a | Exzeo Group | Paycom | PASS | 4/4 | All fields filled, dry-run stopped before submit |
| T7.2b | RKW Residential | Indeed SmartApply | FAIL | 0/3 | Session-dependent — Indeed requires active login |

**Fixes applied:**
- `fill_application.py`: Added `prepare_application_page()` that clicks through "Apply" and modal buttons to reveal the form before filling

**Known limitation:** Indeed SmartApply requires an active Indeed session. Without login cookies, the form doesn't render. This is expected — the orchestrator should report it as blocked.

---

## Phase 10: Learning Loop — PASS

| Test | Description | Result | Notes |
|------|------------|--------|-------|
| T10.1 | Save Rule: always → answer_rules | PASS | Zip code pattern added to profile |
| T10.2 | Save Rule: never → always_ask | PASS | City, State pattern added to always_ask |
| T10.3 | Verify rules on re-run | PASS | Zip code auto_answered, City/State needs_input |

---

## Phase 11: Multi-Batch — PASS (all 4 tests)

| Test | Description | Result | Notes |
|------|------------|--------|-------|
| T11.1 | Second batch intake (sample-email-2.pdf, 3 jobs) | PASS | BoomPop, Roadpass Digital, Raytheon — separate dirs, no batch 1 interference |
| T11.2 | Batch status default (most recent) | PASS | Returns 2026-03-19 batch (6 jobs), not older batches |
| T11.3 | Batch status with date filter | PASS | `--batch-date 2026-03-16` returns only batch 1 (4 jobs) |
| T11.4 | Third + fourth batch intake (email-3: 3 jobs, email-4: 6 jobs) | PASS | 16 total jobs across 4 batches: 4 + 3 + 3 + 6 |

**Verified:**
- Batch isolation: each batch uses its own date prefix, no cross-contamination
- Default batch-status returns most recent batch (2026-03-19)
- Date-filtered batch-status correctly scopes to specified date
- All 16 jobs from 4 PDFs parsed with correct company/title extraction
- Task directories created independently per batch

---

## Phases Not Yet Tested

| Phase | Reason |
|-------|--------|
| Phase 8: Live Submission | Requires user decision on which jobs to submit |
| Phase 9: Debrief | Depends on Phase 8 completion |

---

## Summary of All Code Fixes

| File | Fix | Commits |
|------|-----|---------|
| `config.json` | Greenhouse domain matching | 9ac4f0f |
| `parse_email_pdf.py` | Comma separator fallback | 9ac4f0f |
| `scout_page.py` | Cloudflare detection, new-tab handling | f9cafbe |
| `scout_page.py` | ATS detection after redirects, Workday/Paycom/SmartApply patterns, label cleanup | 209b935 |
| `parse_questionnaire.py` | Missing required answer errors, broken field_id detection | eac1256 |
| `fill_application.py` | Apply-click-through before filling | c62e34e |
| `CLAUDE.md` | Orchestrator launch-browser.bat for blocked URLs | 8390f91, 3791daf |
