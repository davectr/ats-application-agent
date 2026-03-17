# ATS Skill: Generic (Discovery Mode)

This skill is loaded when the ATS platform is unrecognized or `null`. It guides the application subagent through an unknown form using careful, methodical discovery.

---

## Platform Identification

- URL pattern: none (this is the fallback skill)
- Used when `ats_platform` is `null` or no platform-specific skill exists

---

## Discovery Mode Behavior

When operating in discovery mode, the application agent must:

1. **Read the page before acting.** Before filling any field, scan the full page structure. Identify all visible form fields, buttons, and navigation elements. Compare what you see against the scout report.
2. **Work top-to-bottom.** Fill fields in the order they appear on the page, matching against the scout report's field_id list. This ensures dependent fields (e.g., dropdowns that reveal sub-questions) trigger in the correct order.
3. **Try multiple selector strategies.** Use the selector fallback chain: `primary` → `by_label` → `by_aria`. If all three fail, try finding the element by visible label text on the page.
4. **Wait after each interaction.** After filling a field or clicking a button, wait 1–2 seconds for dynamic content to load. ATS forms often reveal additional fields based on previous answers.
5. **Screenshot every step.** Capture a screenshot after filling each page, after clicking navigation buttons, and before/after submission. These feed into the debrief.
6. **Be liberal about pausing.** If anything looks unexpected — new fields appeared, a confirmation dialog popped up, the page layout changed — pause and screenshot. Mark the task as blocked if the unexpected element can't be resolved from answers or profile data.

---

## Form Filling Strategy

### Text Fields (text, email, tel, number, url, textarea)
- Click the field first to ensure focus
- Clear any pre-filled value before typing
- Use Playwright's `fill()` method (not `type()`) for reliability

### Select Dropdowns
- Match answer text against option labels (case-insensitive)
- Fall back to partial match if exact match fails
- If no match found, screenshot and log the available options

### Radio Buttons
- Match answer against radio button labels or values
- Click the matching radio button directly

### Checkboxes
- Interpret "yes", "true", "1", "checked", "on" as checked
- Toggle if current state doesn't match desired state

### File Upload (Resume)
- Use `set_input_files()` with the absolute path to the resume PDF
- After upload, verify the filename appears on the page
- If verification fails, retry once
- If still failing, mark as blocked with screenshot

---

## Multi-Page Navigation

Many ATS forms span multiple pages (Workday commonly has 3-5 pages).

1. After filling all fields on the current page, look for a Next/Continue button
2. Click it and wait for the new page to load
3. Check for CAPTCHA or auth walls on the new page
4. Compare visible fields against the scout report's next page
5. If new fields appear that aren't in the scout report, treat them as unexpected fields

---

## Unexpected Fields

Fields not in the scout report may appear due to:
- Conditional fields triggered by earlier answers
- ATS updates since scouting
- Dynamic rendering differences

When an unexpected field is encountered:
1. Read the field label and type
2. Check answer rules from the profile — does a pattern match this question?
3. Check profile data — is there an obvious auto-fill mapping?
4. If neither resolves it, mark the task as **blocked** with:
   - Screenshot of the unexpected field
   - Field label and type
   - Current page URL
   - Which fields have been filled so far

---

## Sensitive Field Detection

Immediately block (do not fill) if a field requests:
- Social Security Number / SSN
- Bank account or routing numbers
- Credit card information
- Government ID / passport / driver's license numbers
- Tax ID / EIN / ITIN

Screenshot the field and exit with a blocked state.

---

## CAPTCHA Handling

If a CAPTCHA is detected at any point:
1. Screenshot the page
2. Mark the task as blocked with reason "CAPTCHA detected"
3. Exit — the user will solve it manually and run `/continue`

---

## Submission

1. After all pages are filled, look for a Submit/Apply button
2. In dry-run mode: screenshot the pre-submission state and stop
3. In normal mode: click Submit, wait for confirmation, screenshot the result
4. If no submit button is found, mark as blocked

---

## Timing Recommendations

- Wait 1-2 seconds after filling each field (dynamic forms)
- Wait 3 seconds after page navigation
- Wait 3 seconds after submission before capturing confirmation screenshot
- Do not rush — conservative timing avoids detection and dynamic rendering issues

---

## Common Issues on Unknown Platforms

- **React-based forms:** IDs may be non-deterministic. Rely on `by_label` and `by_aria` selectors.
- **Shadow DOM:** Some modern ATS forms use shadow DOM. Standard selectors won't penetrate it. If fields appear visible but selectors fail, note this in the debrief.
- **iframes:** The application form may be embedded in an iframe. Check for iframes if fields aren't found on the main page.
- **Auto-save:** Some forms auto-save as you type. Extra delays help ensure saves complete.
- **Required field validation:** The form may show validation errors after clicking Next/Submit. Screenshot these — they indicate fields that were missed or incorrectly filled.

---

## Debrief Notes

After completing (or failing) the application, the debrief should capture:
- Which platform this appeared to be (URL patterns, DOM structure clues)
- Any navigation quirks (multiple pages, back/forward behavior)
- Fields that were hard to fill (selector issues, dynamic behavior)
- Whether this platform should get its own skill file
- Timing issues (fields that loaded slowly, pages that needed longer waits)

---

## Revision History

- 2026-03-17: Initial generic skill created (Phase 3 build)
