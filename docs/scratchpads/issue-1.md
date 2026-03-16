# Issue #1: Phase 1 Foundation

**GitHub:** https://github.com/davectr/ats-application-agent/issues/1
**Branch:** `issue-1`
**Phase:** Foundation

## Scope

Establish repo structure, configuration files, profile template, task state management, and orchestrator skeleton.

## Deliverables

1. `config.json` — paths, browser config, URL classification, pacing, timeout
2. `profile.json` — empty template for user to populate
3. `launch-browser.bat` — Chrome shortcut with persistent profile
4. `agents/intake.md`, `agents/scout.md`, `agents/application.md` — placeholders
5. `skills/ats/generic.md` — placeholder
6. `templates/questionnaire.md` — Obsidian questionnaire template
7. `templates/debrief.md` — debrief template
8. `scripts/manage_task_state.py` — task directory CRUD, status transitions, batch query
9. `CLAUDE.md` — orchestrator with `/status` command

## Key Decisions

- **Slug generation:** lowercase, non-alphanumeric → hyphens, collapse multiples, strip edges
- **Valid transitions:** forward-only with defined map (see manage_task_state.py)
- **CLI output:** JSON to stdout, errors to stderr + exit code 1
- **CLAUDE.md:** only `/status` is functional; other commands are stubs for future phases
