# Applications — {{DATE}}

> **Do not delete** `## N.` headers, `**Q` prefixes, `Answer:` labels, or `<!-- field_id -->` / `<!-- job_id -->` comments.
> These are invisible in Obsidian's rendered view but required for the parser.
> You may add blank lines, reorder lines within a section, or edit answer text freely.

---

## {{N}}. {{COMPANY}} — {{TITLE}} <!-- job_id: {{JOB_ID}} -->
**ATS Platform:** {{ATS_PLATFORM}}
**Application URL:** {{APPLICATION_URL}}
**Resume:** {{RESUME_FILENAME}}
**Status:** awaiting answers

### Auto-Filled from Profile
{{#AUTO_FILLED}}
- {{LABEL}}: {{VALUE}} <!-- field_id: {{FIELD_ID}} -->
{{/AUTO_FILLED}}
(shown for transparency, no action needed)

### Auto-Answered from Rules
{{#AUTO_ANSWERED}}
- {{LABEL}}: {{VALUE}} <!-- field_id: {{FIELD_ID}} -->
{{/AUTO_ANSWERED}}
(review and override if incorrect)

### Needs Your Input

{{#NEEDS_INPUT}}
**Q{{Q_NUM}}: {{LABEL}}** <!-- field_id: {{FIELD_ID}} -->
Type: {{TYPE}}
Required: {{REQUIRED}}
Answer:
Save Rule:

{{/NEEDS_INPUT}}
