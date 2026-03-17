#!/usr/bin/env python3
"""Fill application forms using scout report field mappings and user answers.

Populates form fields using the selector fallback chain (primary -> by_label -> by_aria),
uploads resume with verification, handles multi-page navigation, and supports dry-run mode.

Usage:
    # Full submission:
    python scripts/fill_application.py \
        --task-dir tasks/2026-03-16_company_role \
        --answers '{"f1":"Dave","f2":"Fimek",...}' \
        --config config.json

    # Dry-run mode (stop before submit):
    python scripts/fill_application.py \
        --task-dir tasks/2026-03-16_company_role \
        --answers '{"f1":"Dave","f2":"Fimek",...}' \
        --config config.json \
        --dry-run

    # Resume from blocked state:
    python scripts/fill_application.py \
        --task-dir tasks/2026-03-16_company_role \
        --answers '{"f1":"Dave","f2":"Fimek",...}' \
        --config config.json \
        --resume-from '{"page_url":"...","page_number":2}'
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# Add scripts dir to path for launch_browser import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from launch_browser import load_config, launch_persistent_context


# Sensitive field patterns — pause and block if encountered
SENSITIVE_PATTERNS = [
    "social security", "ssn", "ss#", "social sec",
    "bank account", "routing number", "account number",
    "credit card", "card number", "cvv", "cvc",
    "government id", "passport number", "driver.?s? license number",
    "national id", "tax id", "ein", "itin",
]

# CAPTCHA indicators
CAPTCHA_INDICATORS = [
    "captcha", "recaptcha", "hcaptcha", "i'm not a robot",
    "verify you are human", "human verification", "security check",
    "bot detection", "challenge-platform",
]

# Submit button selectors (ordered by specificity)
SUBMIT_SELECTORS = [
    "button[type='submit']:has-text('Submit')",
    "button:has-text('Submit Application')",
    "button:has-text('Submit')",
    "input[type='submit']",
    "button:has-text('Apply')",
    "button:has-text('Send Application')",
    "button:has-text('Complete')",
    "button:has-text('Finish')",
]

# Next/Continue button selectors for multi-page forms
NEXT_PAGE_SELECTORS = [
    "button:has-text('Next')",
    "button:has-text('Continue')",
    "button:has-text('Save and Continue')",
    "button:has-text('Save & Continue')",
    "button:has-text('Proceed')",
    "button[type='submit']:not(:has-text('Submit'))",
]


class ApplicationResult:
    """Result of a form filling attempt."""

    def __init__(self):
        self.outcome = "unknown"  # submitted | dry_run | blocked | failed
        self.fields_filled = []
        self.pages_completed = 0
        self.screenshots = []
        self.block_reason = None
        self.block_screenshot = None
        self.error = None
        self.page_url = None
        self.unexpected_fields = []

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "fields_filled": self.fields_filled,
            "pages_completed": self.pages_completed,
            "screenshots": self.screenshots,
            "block_reason": self.block_reason,
            "block_screenshot": self.block_screenshot,
            "error": self.error,
            "page_url": self.page_url,
            "unexpected_fields": self.unexpected_fields,
        }


def fill_application(
    task_dir: str,
    answers: dict[str, str],
    config_path: str,
    dry_run: bool = False,
    resume_from: dict | None = None,
) -> ApplicationResult:
    """Fill and optionally submit a job application.

    Args:
        task_dir: Path to the task directory containing scout_report.json and resume
        answers: Dict mapping field_id -> answer string
        config_path: Path to config.json
        dry_run: If True, stop before clicking final submit
        resume_from: Progress dict from a previous blocked attempt

    Returns:
        ApplicationResult with outcome details.
    """
    task_path = Path(task_dir)
    config = load_config(config_path)
    result = ApplicationResult()

    # Load scout report
    report_file = task_path / "scout_report.json"
    if not report_file.exists():
        result.outcome = "failed"
        result.error = f"scout_report.json not found in {task_dir}"
        return result

    with open(report_file, "r", encoding="utf-8") as f:
        scout_report = json.load(f)

    # Load task.json for resume path
    task_file = task_path / "task.json"
    if not task_file.exists():
        result.outcome = "failed"
        result.error = f"task.json not found in {task_dir}"
        return result

    with open(task_file, "r", encoding="utf-8") as f:
        task_data = json.load(f)

    resume_path = task_data.get("resume_path")
    if resume_path:
        resume_full = Path(resume_path)
        if not resume_full.is_absolute():
            resume_full = Path(task_dir).parent.parent / resume_path

    screenshots_dir = task_path / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    application_url = scout_report.get("application_url", "")
    pages = scout_report.get("pages", [])

    with sync_playwright() as pw:
        context = launch_persistent_context(config, pw)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            # Navigate to application URL (or resume URL)
            start_url = application_url
            start_page = 1
            if resume_from and resume_from.get("page_url"):
                start_url = resume_from["page_url"]
                start_page = resume_from.get("page_number", 1)

            print(f"Navigating to: {start_url}")
            page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            result.page_url = page.url

            # Check for CAPTCHA/auth wall before filling
            block = check_for_blockers(page)
            if block:
                screenshot_name = "blocked-before-fill"
                ss = capture_screenshot(page, screenshots_dir, screenshot_name)
                result.outcome = "blocked"
                result.block_reason = block
                result.block_screenshot = ss
                result.screenshots.append(ss)
                return result

            # Process each page of the application
            for page_idx, page_data in enumerate(pages):
                page_num = page_data.get("page_number", page_idx + 1)

                # Skip pages before our resume point
                if page_num < start_page:
                    continue

                # If not first page and not resuming, try to navigate to this page
                if page_num > 1 and not (resume_from and page_num == start_page):
                    # The previous page's next button should have brought us here
                    page.wait_for_timeout(2000)

                result.page_url = page.url

                # Check for blockers on each page
                block = check_for_blockers(page)
                if block:
                    ss = capture_screenshot(page, screenshots_dir, f"blocked-page{page_num}")
                    result.outcome = "blocked"
                    result.block_reason = block
                    result.block_screenshot = ss
                    result.screenshots.append(ss)
                    result.pages_completed = page_num - 1
                    return result

                # Fill fields on this page
                fields = page_data.get("fields", [])
                for field in fields:
                    field_id = field.get("field_id")
                    if not field_id:
                        continue

                    answer = answers.get(field_id)
                    if answer is None or answer == "":
                        # Skip fields with no answer (optional fields left blank)
                        continue

                    field_type = field.get("type", "text")

                    # Check for sensitive fields
                    label = field.get("label", "")
                    if is_sensitive_field(label):
                        ss = capture_screenshot(page, screenshots_dir, f"blocked-sensitive-{field_id}")
                        result.outcome = "blocked"
                        result.block_reason = f"Sensitive field detected: '{label}' (field {field_id})"
                        result.block_screenshot = ss
                        result.screenshots.append(ss)
                        result.pages_completed = page_num - 1
                        return result

                    # Fill the field
                    success = fill_field(page, field, answer, resume_full if field_type == "file" else None)
                    if success:
                        result.fields_filled.append(field_id)
                    else:
                        print(f"  Warning: could not fill field {field_id} ({label})", file=sys.stderr)

                # Capture page screenshot after filling
                ss = capture_screenshot(page, screenshots_dir, f"filled-page{page_num}")
                result.screenshots.append(ss)
                result.pages_completed = page_num

                # If this is not the last page, click Next
                is_last_page = (page_idx == len(pages) - 1)
                if not is_last_page:
                    if not click_next_page(page):
                        print(f"  Warning: could not find Next button on page {page_num}", file=sys.stderr)
                        # Try to continue anyway

            # All pages filled — handle submission
            if dry_run:
                ss = capture_screenshot(page, screenshots_dir, "pre-submit-dry-run")
                result.screenshots.append(ss)
                result.outcome = "dry_run"
                print("Dry run complete — stopping before submit.")
                return result

            # Click submit
            submitted = click_submit(page)
            if submitted:
                page.wait_for_timeout(3000)
                ss = capture_screenshot(page, screenshots_dir, "post-submit")
                result.screenshots.append(ss)
                result.outcome = "submitted"
                result.page_url = page.url
                print("Application submitted.")
            else:
                ss = capture_screenshot(page, screenshots_dir, "submit-button-not-found")
                result.screenshots.append(ss)
                result.outcome = "blocked"
                result.block_reason = "Could not find or click the submit button"
                result.block_screenshot = ss

        except PwTimeout as e:
            result.outcome = "failed"
            result.error = f"Timeout: {e}"
            try:
                ss = capture_screenshot(page, screenshots_dir, "timeout-error")
                result.screenshots.append(ss)
            except Exception:
                pass
        except Exception as e:
            result.outcome = "failed"
            result.error = str(e)
            try:
                ss = capture_screenshot(page, screenshots_dir, "error")
                result.screenshots.append(ss)
            except Exception:
                pass
        finally:
            context.close()

    return result


def fill_field(page, field: dict, answer: str, resume_path: Path | None = None) -> bool:
    """Fill a single form field using the selector fallback chain.

    Args:
        page: Playwright page object
        field: Field dict from scout report with selectors
        answer: The answer text to fill
        resume_path: Path to resume file (for file upload fields)

    Returns:
        True if field was successfully filled.
    """
    field_type = field.get("type", "text")
    selectors = field.get("selectors", {})
    label = field.get("label", "")

    # Build selector list in fallback order
    selector_chain = []
    if "primary" in selectors:
        selector_chain.append(selectors["primary"])
    if "by_label" in selectors:
        selector_chain.append(selectors["by_label"])
    if "by_aria" in selectors:
        selector_chain.append(selectors["by_aria"])

    if not selector_chain:
        print(f"  No selectors for field '{label}'", file=sys.stderr)
        return False

    for selector in selector_chain:
        try:
            el = page.query_selector(selector)
            if not el or not el.is_visible():
                continue

            if field_type == "file":
                return fill_file_field(page, el, resume_path, label)
            elif field_type in ("select",):
                return fill_select_field(el, answer)
            elif field_type == "radio":
                return fill_radio_field(page, field, answer)
            elif field_type == "checkbox":
                return fill_checkbox_field(el, answer)
            elif field_type in ("text", "email", "tel", "number", "url", "textarea", "password"):
                return fill_text_field(el, answer)
            else:
                # Default to text fill
                return fill_text_field(el, answer)

        except Exception as e:
            print(f"  Selector '{selector}' failed for '{label}': {e}", file=sys.stderr)
            continue

    print(f"  All selectors failed for field '{label}'", file=sys.stderr)
    return False


def fill_text_field(element, answer: str) -> bool:
    """Fill a text/textarea field."""
    try:
        element.click()
        element.fill("")  # Clear first
        element.fill(answer)
        return True
    except Exception as e:
        print(f"  Text fill error: {e}", file=sys.stderr)
        return False


def fill_select_field(element, answer: str) -> bool:
    """Fill a select dropdown by matching option text."""
    try:
        # Try exact value match first
        options = element.query_selector_all("option")
        for opt in options:
            text = opt.inner_text().strip()
            value = opt.get_attribute("value") or ""
            if text.lower() == answer.lower() or value.lower() == answer.lower():
                element.select_option(value=value)
                return True

        # Try partial match
        for opt in options:
            text = opt.inner_text().strip()
            if answer.lower() in text.lower() or text.lower() in answer.lower():
                value = opt.get_attribute("value") or ""
                element.select_option(value=value)
                return True

        print(f"  No matching option for '{answer}'", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  Select fill error: {e}", file=sys.stderr)
        return False


def fill_radio_field(page, field: dict, answer: str) -> bool:
    """Select a radio button by matching answer text."""
    selectors = field.get("selectors", {})
    name_selector = selectors.get("primary", "")

    if not name_selector:
        return False

    try:
        radios = page.query_selector_all(name_selector)
        for radio in radios:
            value = radio.get_attribute("value") or ""
            # Also check the label
            label = radio.evaluate(
                "el => { let l = el.closest('label'); return l ? l.innerText.trim() : ''; }"
            )

            if (value.lower() == answer.lower() or
                label.lower() == answer.lower() or
                answer.lower() in label.lower()):
                radio.click()
                return True

        print(f"  No matching radio for '{answer}'", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  Radio fill error: {e}", file=sys.stderr)
        return False


def fill_checkbox_field(element, answer: str) -> bool:
    """Check or uncheck a checkbox based on answer."""
    try:
        should_check = answer.lower() in ("yes", "true", "1", "checked", "on")
        is_checked = element.is_checked()

        if should_check and not is_checked:
            element.click()
        elif not should_check and is_checked:
            element.click()

        return True
    except Exception as e:
        print(f"  Checkbox fill error: {e}", file=sys.stderr)
        return False


def fill_file_field(page, element, resume_path: Path | None, label: str) -> bool:
    """Upload a file using set_input_files with verification.

    Args:
        page: Playwright page
        element: The file input element
        resume_path: Path to the file to upload
        label: Field label for error messages

    Returns:
        True if upload succeeded and was verified.
    """
    if not resume_path or not resume_path.exists():
        print(f"  Resume file not found: {resume_path}", file=sys.stderr)
        return False

    try:
        element.set_input_files(str(resume_path))
        # Wait for upload processing
        page.wait_for_timeout(2000)

        # Verify upload: check if filename appears on page
        filename = resume_path.name
        body_text = page.inner_text("body")
        if filename.lower() in body_text.lower():
            print(f"  Resume uploaded and verified: {filename}")
            return True

        # Retry once
        print(f"  Upload verification failed, retrying...")
        element.set_input_files(str(resume_path))
        page.wait_for_timeout(2000)

        body_text = page.inner_text("body")
        if filename.lower() in body_text.lower():
            print(f"  Resume uploaded and verified on retry: {filename}")
            return True

        print(f"  Resume upload could not be verified (filename not found on page)", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  File upload error: {e}", file=sys.stderr)
        return False


def check_for_blockers(page) -> str | None:
    """Check the current page for CAPTCHA or other blockers.

    Returns a reason string if blocked, None if clear.
    """
    try:
        body_text = page.inner_text("body").lower()
    except Exception:
        return None

    for indicator in CAPTCHA_INDICATORS:
        if indicator in body_text:
            return f"CAPTCHA detected: '{indicator}'"

    return None


def is_sensitive_field(label: str) -> bool:
    """Check if a field label indicates a sensitive data request."""
    import re
    label_lower = label.lower()
    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, label_lower):
            return True
    return False


def click_next_page(page) -> bool:
    """Try to click a Next/Continue button for multi-page forms."""
    for selector in NEXT_PAGE_SELECTORS:
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                el.click()
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)
                return True
        except (PwTimeout, Exception):
            continue
    return False


def click_submit(page) -> bool:
    """Try to click the submit button."""
    for selector in SUBMIT_SELECTORS:
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                el.click()
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                return True
        except (PwTimeout, Exception):
            continue
    return False


def capture_screenshot(page, screenshots_dir: Path, name: str) -> str:
    """Capture a screenshot and return the relative path."""
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{name}.png"
    filepath = screenshots_dir / filename
    page.screenshot(path=str(filepath), full_page=True)
    return f"screenshots/{filename}"


def main():
    parser = argparse.ArgumentParser(
        description="Fill application forms using scout report field mappings"
    )
    parser.add_argument(
        "--task-dir", required=True,
        help="Path to task directory containing scout_report.json"
    )
    parser.add_argument(
        "--answers", required=True,
        help="JSON dict mapping field_id to answer string"
    )
    parser.add_argument(
        "--config", default="config.json",
        help="Path to config.json"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Stop before clicking the final submit button"
    )
    parser.add_argument(
        "--resume-from",
        help="JSON progress dict from a previous blocked attempt"
    )

    args = parser.parse_args()

    answers = json.loads(args.answers)
    resume_from = json.loads(args.resume_from) if args.resume_from else None

    result = fill_application(
        task_dir=args.task_dir,
        answers=answers,
        config_path=args.config,
        dry_run=args.dry_run,
        resume_from=resume_from,
    )

    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
