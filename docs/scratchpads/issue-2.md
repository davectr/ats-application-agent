# Issue #2: Phase 2a — Intake

**Link:** https://github.com/davectr/ats-application-agent/issues/2
**Branch:** `issue-2`

## Deliverables

1. `scripts/parse_email_pdf.py` — PDF text + URL extraction, structured listing output
2. `scripts/download_resumes.py` — HTTP download of resume PDFs from Google Docs
3. `agents/intake.md` — full intake subagent definition
4. `CLAUDE.md` update — wire `/apply` command to dispatch intake subagent

## PDF Structure (from sample-email.pdf)

- 2 pages, 4 job listings
- Text format: `#N\nCompany - Title\nDescription\nCompany: ...\nPay: ...\nJob Type: ...\nLocation: ...\nWhy we like it: ...\nView Job\nView Resume\nDownload Resume`
- URL annotations: heavily duplicated (each URL appears 2-4 times per page)
- URL order per listing: job_listing (×4), resume_view (×2), resume_download (×2)
- URLs span page boundaries

## parse_email_pdf.py Design

1. Extract all text from all pages (concatenated)
2. Extract URL annotations from all pages, deduplicate preserving first-occurrence order
3. Load config.json for URL classification patterns
4. Classify each unique URL (job_listing, resume_view, resume_download)
5. Parse text: split on `#\d+` to find listing blocks
6. For each block: extract company, title, description, pay, job_type, location, match_rationale
7. Associate URLs: group classified URLs in order (3 per listing)
8. Validate: each listing has all 3 URL types, text extraction produced content
9. Output: JSON array of listing objects to stdout

## download_resumes.py Design

1. Accept: path to listings JSON + output directory
2. For each listing: HTTP GET the resume_download URL
3. Validate: check `%PDF-` header, non-zero size, not HTML error page
4. Save: `{company-slug}-resume.pdf` in output directory
5. Report: JSON summary of downloads

## Key Decisions

- Use `urllib.request` for downloads (stdlib, no extra dependency) — actually `requests` is available, use that for better error handling
- URL classification uses config.json patterns, not hardcoded
- Description field: text between title line and first field marker (Company:/Pay:)
- Company description paragraph without "Company:" prefix: included in description (minor edge case, acceptable)
