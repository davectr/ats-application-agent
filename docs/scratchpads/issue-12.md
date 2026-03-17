# Issue #12: End-to-End Test Plan Execution

**Branch:** `issue-12`
**Depends on:** All phases (#1–#5) merged
**Full test plan:** `docs/scratchpads/issue-6.md`

---

## Objective

Execute the full E2E test plan from issue-6.md against live ATS platforms. Document failures in `test-output.md`, fix code, re-run until all tests pass.

## Execution Strategy

### Phase 1: Intake Pipeline (T1.1–T1.8) — No browser
- Parse 4 email PDFs (16 jobs total)
- Create task directories
- Download resumes
- Transition to intake_complete
- Verify batch status queries

### Phase 2: Browser Launch (T2.1) — User checkpoint
- Verify Playwright persistent context launch
- User must close Chrome beforehand

### Phase 3: Scout Pipeline (T3.1–T3.6) — Browser required
- Scout 4 jobs from batch 1
- Detect ATS platforms
- Handle auth/expired/SSO states
- Extract form fields with selectors

### Phase 4: Answer Rules (T4.1–T4.2)
- Validate rule matching with real scout data
- Test comprehensive rule coverage with test profile

### Phase 5–11: Remaining phases
- Questionnaire, parsing, dry-run, live submission, debrief, learning loop, multi-batch

## Test Cycle Protocol

1. Execute test plan phase by phase
2. At each checkpoint → stop, present results, wait for user
3. On failure → document in test-output.md
4. After full run → fix issues, re-run failed tests
5. Repeat until all pass

## Files Affected

- `test-output.md` (new, gitignored) — test results
- `scripts/*.py` — fixes for any failures found
- `agents/*.md` — fixes if agent definitions are incorrect
- `profile.json` — needs populated data (not committed)

## Notes

- profile.json must be populated (restored from stash, not committed)
- Chrome must be closed for browser tests
- Resume downloads may fail (Google Auth) — expected behavior
