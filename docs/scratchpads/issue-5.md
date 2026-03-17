# Issue #5: Phase 4 — Learning Loop

**Link:** https://github.com/davectr/ats-application-agent/issues/5
**Branch:** `issue-5`
**Depends on:** Phase 3 (#4) — merged

---

## Deliverables

1. **`/skill` command** (CLAUDE.md) — freeform and debrief-guided modes
2. **`/debrief` triage** (CLAUDE.md) — categorize observations into 4 types
3. **Save Rule processing** (CLAUDE.md `/submit`) — post-submission rule extraction
4. **ATS skill file creation** — format per project-plan.md
5. **Answer rule management** — add/modify rules in profile.json

## What Already Exists

- `parse_questionnaire.py` already parses `Save Rule:` tags and has `get_save_rules()` function
- `/debrief` command has basic triage categories mentioned
- `/skill` has a "not yet implemented" placeholder

## Implementation Plan

### Step 1: Implement `/skill` command in CLAUDE.md
- Replace placeholder with full implementation
- **Freeform mode:** parse user instruction → determine target → apply change
  - Answer rules: read profile.json, construct rule JSON, add to `answer_rules` array, write back
  - ATS skills: create/append to `skills/ats/{platform}.md` with required format
- **Debrief-guided mode:** read debrief, find suggestion, determine type, apply
- Include ATS skill file template (Platform ID, Navigation, Known Fields, Common Issues, Revision History)

### Step 2: Enhance `/debrief` with explicit triage
- Add categorization logic to the `/debrief` command
- Four categories: skill updates, script updates, answer rules, one-offs
- Number each actionable item for easy `/skill Apply suggestion N` references

### Step 3: Add Save Rule processing to `/submit`
- After all submissions complete, re-parse questionnaire
- Extract fields with `save_rule` set
- For `always`: construct candidate answer rule, present to user, add on approval
- For `never`: add question pattern to `always_ask` list
- Update profile.json

### Step 4: Smoke test
- Validate CLAUDE.md markdown structure
- Validate all script references in CLAUDE.md point to existing files
- Test parse_questionnaire.py Save Rule extraction with test input
- Verify ATS skill file format matches project-plan.md spec

## Files Modified

| File | Change |
|------|--------|
| `CLAUDE.md` | `/skill` command, `/debrief` triage, `/submit` Save Rule processing |
| `docs/scratchpads/issue-5.md` | This planning document |

## No Script Changes Needed

The orchestrator (CLAUDE.md) handles all learning loop operations directly — it reads/writes JSON and markdown files. No new Python scripts required. `parse_questionnaire.py` already has the Save Rule extraction built in from Phase 3.
