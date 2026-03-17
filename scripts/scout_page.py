#!/usr/bin/env python3
"""Scout a job application page — detect ATS, extract form fields, capture screenshots.

Navigates to the job listing URL, follows through to the application page,
detects the ATS platform, checks for auth walls and SSO-only flows,
extracts form fields with multiple selector strategies, and writes
scout_report.json to the task directory.

This script handles raw field extraction. Profile key mapping and auto_fill
determination are done by the scout subagent LLM after this script runs.

Usage:
    python scripts/scout_page.py --task-dir tasks/2026-03-16_company_role --config config.json
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

# Add scripts dir to path for launch_browser import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from launch_browser import load_config, launch_persistent_context


# --- ATS Detection ---

ATS_PATTERNS = {
    "workday": ["myworkdayjobs.com", "wd1.myworkdayjobs.com", "wd5.myworkdayjobs.com", "workday.com"],
    "greenhouse": ["boards.greenhouse.io", "greenhouse.io"],
    "indeed_smart_apply": ["smartapply.indeed.com"],
    "lever": ["lever.co", "jobs.lever.co"],
    "icims": ["icims.com", "careers-", ".icims."],
    "taleo": ["taleo.net", "oracle.com/taleo"],
    "workable": ["workable.com", "apply.workable.com"],
    "paycom": ["paycomonline.net"],
    "bamboohr": ["bamboohr.com"],
    "jazz": ["applytojob.com"],
    "ashby": ["ashbyhq.com"],
    "smartrecruiters": ["smartrecruiters.com"],
    "jobvite": ["jobvite.com"],
}

# Patterns indicating an expired/closed listing
EXPIRED_INDICATORS = [
    "no longer accepting applications",
    "this job is no longer available",
    "this position has been filled",
    "this job has been closed",
    "this posting has expired",
    "job not found",
    "this position is no longer open",
    "application deadline has passed",
    "requisition is no longer active",
    "sorry, but we can't find that page",
    "this job posting is no longer active",
    "page not found",
    "the job you are looking for is no longer open",
    "is no longer open",
    "is no longer available",
]

# Patterns indicating auth wall
AUTH_WALL_INDICATORS = [
    "sign in to apply",
    "log in to apply",
    "create an account to apply",
    "sign in to continue",
    "please log in",
    "login required",
    "additional verification required",
    "verify you are human",
    "please verify you are a human",
    "complete the security check",
    "performing security verification",
    "verifies you are not a bot",
    "protect against malicious bots",
    "sign up or log in",
    "create or log in to",
    "you must create or log in",
    "sign in to your account to apply",
]

# Patterns indicating SSO-only apply
SSO_ONLY_INDICATORS = [
    "apply with linkedin",
    "apply with indeed",
    "sign in with linkedin to apply",
    "easy apply",
]


def detect_ats_platform(url: str) -> str | None:
    """Detect ATS platform from URL patterns."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    full_url = url.lower()

    for platform, patterns in ATS_PATTERNS.items():
        for pattern in patterns:
            if pattern in hostname or pattern in full_url:
                return platform
    return None


def check_page_status(page) -> dict:
    """Check page for expired, auth wall, or SSO-only indicators.

    Returns dict with:
        listing_status: "open" | "expired" | "requires_account" | "sso_apply_only"
        auth_required: bool
    """
    # Check for Cloudflare challenge (title-based detection)
    try:
        title = page.title().lower()
    except Exception:
        title = ""
    if "just a moment" in title or "attention required" in title:
        # Cloudflare Turnstile or similar challenge page
        return {"listing_status": "requires_account", "auth_required": True}

    # Also check for Cloudflare challenge iframe
    try:
        frames = page.frames
        for frame in frames:
            if "challenges.cloudflare.com" in frame.url:
                return {"listing_status": "requires_account", "auth_required": True}
    except Exception:
        pass

    try:
        body_text = page.inner_text("body").lower()
    except Exception:
        body_text = ""

    # Check for expired listing
    for indicator in EXPIRED_INDICATORS:
        if indicator in body_text:
            return {"listing_status": "expired", "auth_required": False}

    # Check for auth wall
    for indicator in AUTH_WALL_INDICATORS:
        if indicator in body_text:
            return {"listing_status": "requires_account", "auth_required": True}

    # Check for Workday sign-in page (shows "Sign In" prominently with no form)
    try:
        current_url = page.url.lower()
    except Exception:
        current_url = ""
    if "myworkdayjobs.com" in current_url:
        # Workday pages that show "Sign In" without any visible form fields
        # indicate the application requires account creation
        form_fields = page.query_selector_all(
            "input[type='text'], input[type='email'], textarea, select"
        )
        visible_fields = [f for f in form_fields if f.is_visible()]
        if not visible_fields and "sign in" in body_text:
            return {"listing_status": "requires_account", "auth_required": True}

    # Check for SSO-only apply (only if no traditional form is present)
    sso_found = any(indicator in body_text for indicator in SSO_ONLY_INDICATORS)
    if sso_found:
        # Check if there's also a traditional application form
        form_fields = page.query_selector_all(
            "input[type='text'], input[type='email'], textarea, select"
        )
        if not form_fields:
            return {"listing_status": "sso_apply_only", "auth_required": False}

    return {"listing_status": "open", "auth_required": False}


def extract_fields(page) -> list[dict]:
    """Extract all form fields from the current page.

    Returns a list of field dicts with: label, type, required, options, selectors.
    Profile key mapping and auto_fill are NOT set here — the scout subagent LLM
    handles that enrichment step.
    """
    fields = []
    field_counter = 0

    # --- Text inputs, email, tel, number, url ---
    inputs = page.query_selector_all(
        "input[type='text'], input[type='email'], input[type='tel'], "
        "input[type='number'], input[type='url'], input[type='password'], "
        "input:not([type])"
    )
    for el in inputs:
        field_counter += 1
        field = _extract_input_field(page, el, field_counter)
        if field:
            fields.append(field)

    # --- Textareas ---
    textareas = page.query_selector_all("textarea")
    for el in textareas:
        field_counter += 1
        field = _extract_textarea_field(page, el, field_counter)
        if field:
            fields.append(field)

    # --- Select dropdowns ---
    selects = page.query_selector_all("select")
    for el in selects:
        field_counter += 1
        field = _extract_select_field(page, el, field_counter)
        if field:
            fields.append(field)

    # --- File inputs ---
    file_inputs = page.query_selector_all("input[type='file']")
    for el in file_inputs:
        field_counter += 1
        field = _extract_file_field(page, el, field_counter)
        if field:
            fields.append(field)

    # --- Checkboxes (standalone, not part of a group) ---
    checkboxes = page.query_selector_all("input[type='checkbox']")
    for el in checkboxes:
        field_counter += 1
        field = _extract_checkbox_field(page, el, field_counter)
        if field:
            fields.append(field)

    # --- Radio button groups ---
    radio_groups = _extract_radio_groups(page)
    for group_name, group_els in radio_groups.items():
        field_counter += 1
        field = _extract_radio_field(page, group_els, field_counter, group_name)
        if field:
            fields.append(field)

    return fields


def _get_label(page, element) -> str:
    """Get the label text for a form element using multiple strategies."""
    # Strategy 1: Explicit <label for="id">
    el_id = element.get_attribute("id")
    if el_id:
        label_el = page.query_selector(f"label[for='{el_id}']")
        if label_el:
            text = label_el.inner_text().strip()
            if text:
                return text

    # Strategy 2: aria-label
    aria_label = element.get_attribute("aria-label")
    if aria_label:
        return aria_label.strip()

    # Strategy 3: aria-labelledby
    labelled_by = element.get_attribute("aria-labelledby")
    if labelled_by:
        label_el = page.query_selector(f"#{labelled_by}")
        if label_el:
            text = label_el.inner_text().strip()
            if text:
                return text

    # Strategy 4: Placeholder
    placeholder = element.get_attribute("placeholder")
    if placeholder:
        return placeholder.strip()

    # Strategy 5: Parent label element
    parent_label = element.evaluate(
        "el => { let p = el.closest('label'); return p ? p.innerText.trim() : null; }"
    )
    if parent_label:
        return parent_label

    # Strategy 6: Name attribute as fallback
    name = element.get_attribute("name")
    if name:
        return name

    return ""


def _clean_label(label: str) -> str:
    """Clean label text: strip required indicators, extra whitespace, etc."""
    import re as _re
    # Remove trailing required indicators: *, \u2009*, \n\u2009*, etc.
    label = _re.sub(r"[\s\u2009\u00a0]*\*\s*$", "", label)
    # Collapse internal whitespace/newlines
    label = _re.sub(r"\s+", " ", label).strip()
    return label


def _is_required(element) -> bool:
    """Check if a form element is required."""
    if element.get_attribute("required") is not None:
        return True
    if element.get_attribute("aria-required") == "true":
        return True
    return False


def _build_selectors(element, label: str) -> dict:
    """Build multiple selector strategies for a form element."""
    selectors = {}

    # Primary: by name or id
    name = element.get_attribute("name")
    el_id = element.get_attribute("id")
    tag = element.evaluate("el => el.tagName.toLowerCase()")
    input_type = element.get_attribute("type") or ""

    if name:
        if tag == "input" and input_type:
            selectors["primary"] = f"{tag}[name='{name}']"
        elif tag in ("textarea", "select"):
            selectors["primary"] = f"{tag}[name='{name}']"
        else:
            selectors["primary"] = f"[name='{name}']"
    elif el_id:
        selectors["primary"] = f"#{el_id}"

    # By label
    if label:
        safe_label = label.replace("'", "\\'")
        if tag == "input" and input_type == "file":
            selectors["by_label"] = f"label:has-text('{safe_label}') input[type='file']"
        else:
            selectors["by_label"] = f"label:has-text('{safe_label}') + {tag}"

    # By aria
    aria_label = element.get_attribute("aria-label")
    if aria_label:
        safe_aria = aria_label.replace("'", "\\'")
        selectors["by_aria"] = f"[aria-label='{safe_aria}']"
    elif label:
        safe_label = label.replace("'", "\\'")
        selectors["by_aria"] = f"[aria-label*='{safe_label[:20]}']"

    return selectors


def _is_hidden(element) -> bool:
    """Check if an element is hidden/not visible."""
    try:
        return not element.is_visible()
    except Exception:
        return True


def _extract_input_field(page, element, counter: int) -> dict | None:
    """Extract field info from an input element."""
    if _is_hidden(element):
        return None

    label = _clean_label(_get_label(page, element))
    if not label:
        return None

    input_type = element.get_attribute("type") or "text"

    return {
        "field_id": f"f{counter}",
        "label": label,
        "type": input_type,
        "required": _is_required(element),
        "selectors": _build_selectors(element, label),
    }


def _extract_textarea_field(page, element, counter: int) -> dict | None:
    """Extract field info from a textarea element."""
    if _is_hidden(element):
        return None

    label = _clean_label(_get_label(page, element))
    if not label:
        return None

    return {
        "field_id": f"f{counter}",
        "label": label,
        "type": "textarea",
        "required": _is_required(element),
        "selectors": _build_selectors(element, label),
    }


def _extract_select_field(page, element, counter: int) -> dict | None:
    """Extract field info from a select element, including options."""
    if _is_hidden(element):
        return None

    label = _clean_label(_get_label(page, element))
    if not label:
        return None

    # Extract options
    option_els = element.query_selector_all("option")
    options = []
    for opt in option_els:
        text = opt.inner_text().strip()
        value = opt.get_attribute("value")
        # Skip placeholder options
        if text and value != "":
            options.append(text)

    return {
        "field_id": f"f{counter}",
        "label": label,
        "type": "select",
        "required": _is_required(element),
        "options": options,
        "selectors": _build_selectors(element, label),
    }


def _extract_file_field(page, element, counter: int) -> dict | None:
    """Extract field info from a file input element."""
    if _is_hidden(element):
        return None

    label = _clean_label(_get_label(page, element))
    if not label:
        label = "Resume"  # Common default for file inputs

    return {
        "field_id": f"f{counter}",
        "label": label,
        "type": "file",
        "required": _is_required(element),
        "selectors": _build_selectors(element, label),
        "note": "Application agent uses Playwright set_input_files() with the resume PDF path from the task directory.",
    }


def _extract_checkbox_field(page, element, counter: int) -> dict | None:
    """Extract field info from a checkbox element."""
    if _is_hidden(element):
        return None

    label = _clean_label(_get_label(page, element))
    if not label:
        return None

    return {
        "field_id": f"f{counter}",
        "label": label,
        "type": "checkbox",
        "required": _is_required(element),
        "selectors": _build_selectors(element, label),
    }


def _extract_radio_groups(page) -> dict:
    """Group radio buttons by name attribute."""
    radios = page.query_selector_all("input[type='radio']")
    groups = {}
    for radio in radios:
        name = radio.get_attribute("name")
        if name:
            if name not in groups:
                groups[name] = []
            groups[name].append(radio)
    return groups


def _extract_radio_field(page, elements: list, counter: int, group_name: str) -> dict | None:
    """Extract field info from a radio button group."""
    visible_els = [el for el in elements if not _is_hidden(el)]
    if not visible_els:
        return None

    # Use the first element for label detection
    label = _clean_label(_get_label(page, visible_els[0]))
    if not label:
        label = group_name

    # Extract option labels
    options = []
    for el in visible_els:
        opt_label = _clean_label(_get_label(page, el))
        value = el.get_attribute("value")
        options.append(opt_label or value or "")

    return {
        "field_id": f"f{counter}",
        "label": label,
        "type": "radio",
        "required": _is_required(visible_els[0]),
        "options": [o for o in options if o],
        "selectors": {
            "primary": f"input[name='{group_name}']",
        },
    }


def capture_screenshot(page, screenshots_dir: Path, name: str) -> str:
    """Capture a screenshot and return the relative path."""
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{name}.png"
    filepath = screenshots_dir / filename
    page.screenshot(path=str(filepath), full_page=True)
    return f"screenshots/{filename}"


def _click_modal_button(page) -> bool:
    """Click common ATS modal buttons (Apply Manually, Continue, etc.).

    These appear as intermediate steps between the job listing and the
    actual application form — especially on Workday, Greenhouse, and iCIMS.

    Returns True if a modal button was found and clicked.
    """
    modal_selectors = [
        # Workday "Start Your Application" modal
        "a:has-text('Apply Manually')",
        "button:has-text('Apply Manually')",
        # Generic continue / proceed buttons
        "a:has-text('Continue')",
        "button:has-text('Continue')",
        "a:has-text('Start Application')",
        "button:has-text('Start Application')",
        "a:has-text('Start your application')",
        "button:has-text('Start your application')",
        # iCIMS / others
        "a:has-text('I Accept')",
        "button:has-text('I Accept')",
    ]

    for selector in modal_selectors:
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                el.click()
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                return True
        except (PwTimeout, Exception):
            continue

    return False


def find_apply_button(page, context):
    """Look for an 'Apply' button on the page and click it.

    Returns the page to use for field extraction:
    - A new Page object if the click opened a new tab
    - The same page if it navigated in-place
    - None if no apply button was found

    Args:
        page: The current Playwright page.
        context: The browser context (to detect new tabs/popups).
    """
    apply_selectors = [
        # Indeed-specific patterns
        "a:has-text('Apply on company')",
        "button:has-text('Apply on company')",
        "a:has-text('Apply now')",
        "button:has-text('Apply now')",
        # Generic patterns
        "a:has-text('Apply')",
        "button:has-text('Apply')",
        "a:has-text('Apply for this job')",
        "button:has-text('Apply for this job')",
        # Data attribute patterns
        "[data-testid*='apply']",
        "[data-testid*='Apply']",
        "[id*='applyButton']",
        "[class*='apply-button']",
        # ZipRecruiter-specific
        "a:has-text('Apply on Company Site')",
        "button:has-text('Apply on Company Site')",
        # Greenhouse / Lever
        "a:has-text('Apply for this Job')",
        "#apply-now",
        ".postings-btn-wrapper a",
    ]

    for selector in apply_selectors:
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                pages_before = len(context.pages)
                # Try to catch a new tab opening
                try:
                    with context.expect_page(timeout=5000) as new_page_info:
                        el.click()
                    new_page = new_page_info.value
                    new_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    return new_page
                except PwTimeout:
                    # No new tab — click navigated in-place
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    return page
        except (PwTimeout, Exception):
            continue

    return None


def scout_job(task_dir: str, config_path: str) -> dict:
    """Scout a single job application page.

    Args:
        task_dir: Path to the task directory containing listing.json
        config_path: Path to config.json

    Returns:
        Scout report dict.
    """
    task_path = Path(task_dir)
    config = load_config(config_path)

    # Read listing.json
    listing_file = task_path / "listing.json"
    if not listing_file.exists():
        print(f"Error: listing.json not found in {task_dir}", file=sys.stderr)
        sys.exit(1)

    with open(listing_file, "r", encoding="utf-8") as f:
        listing = json.load(f)

    # Read task.json for job_id
    task_file = task_path / "task.json"
    if not task_file.exists():
        print(f"Error: task.json not found in {task_dir}", file=sys.stderr)
        sys.exit(1)

    with open(task_file, "r", encoding="utf-8") as f:
        task_data = json.load(f)

    job_id = task_data["job_id"]
    job_url = listing["urls"]["job_listing"]
    screenshots_dir = task_path / "screenshots"

    report = {
        "job_id": job_id,
        "ats_platform": None,
        "application_url": None,
        "listing_status": "open",
        "auth_required": False,
        "page_count": 0,
        "pages": [],
    }

    with sync_playwright() as pw:
        context = launch_persistent_context(config, pw)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            # Step 1: Navigate to the job listing page
            print(f"Navigating to: {job_url}")
            page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            # Wait for JS rendering — dynamic sites (Indeed, Workday) need time
            page.wait_for_timeout(3000)
            screenshot_path = capture_screenshot(page, screenshots_dir, "scout-step1-listing")
            print(f"  Screenshot: {screenshot_path}")

            # Step 2: Check page status
            status = check_page_status(page)
            if status["listing_status"] != "open":
                report["listing_status"] = status["listing_status"]
                report["auth_required"] = status["auth_required"]
                report["application_url"] = page.url
                print(f"  Status: {status['listing_status']}")
                _write_report(report, task_path)
                return report

            # Step 3: Detect ATS from current URL
            ats = detect_ats_platform(page.url)
            if ats:
                report["ats_platform"] = ats

            # Step 4: Try to find and click "Apply" button
            # find_apply_button returns a Page (possibly new tab) or None
            pre_apply_url = page.url  # Save URL before click for comparison
            apply_result = find_apply_button(page, context)
            if apply_result is not None:
                # Switch to the page returned (may be a new tab or same page)
                active_page = apply_result
                new_url = active_page.url
                if new_url != pre_apply_url or active_page is not page:
                    print(f"  Followed apply link to: {new_url}")
                    # Wait for page to render (redirects may still be in flight)
                    active_page.wait_for_timeout(3000)
                    # Re-read URL after wait — redirects (e.g., ZipRecruiter → Workday) resolve here
                    final_url = active_page.url
                    if final_url != new_url:
                        print(f"  Redirected to: {final_url}")
                    # Extra wait for Workday's heavy JS rendering
                    if detect_ats_platform(final_url) == "workday":
                        active_page.wait_for_timeout(5000)
                    capture_screenshot(active_page, screenshots_dir, "scout-step2-apply-click")

                    # Detect ATS from final URL (after redirects)
                    new_ats = detect_ats_platform(final_url)
                    if new_ats:
                        report["ats_platform"] = new_ats

                    # Re-check status after navigation
                    status = check_page_status(active_page)
                    if status["listing_status"] != "open":
                        report["listing_status"] = status["listing_status"]
                        report["auth_required"] = status["auth_required"]
                        report["application_url"] = active_page.url
                        _write_report(report, task_path)
                        return report

                # Use the active page for field extraction
                page = active_page

            report["application_url"] = page.url

            # Step 4b: Multi-click navigation to reach the application form.
            # Job boards often require: listing → ATS page → modal → form.
            # Try up to 2 additional clicks to drill through to the form.
            for attempt in range(2):
                test_fields = extract_fields(page)
                if test_fields:
                    break  # Found form fields, stop clicking

                print(f"  No form fields found — trying click {attempt + 2}...")

                # Try ATS modal buttons first, then generic apply buttons
                clicked = _click_modal_button(page)
                if not clicked:
                    next_result = find_apply_button(page, context)
                    if next_result is not None:
                        page = next_result

                new_url_n = page.url
                if clicked or next_result:
                    print(f"  After click: {new_url_n[:80]}")
                    wait_ms = 8000 if detect_ats_platform(new_url_n) == "workday" else 3000
                    page.wait_for_timeout(wait_ms)
                    capture_screenshot(page, screenshots_dir, f"scout-step{attempt + 3}-click")
                    report["application_url"] = page.url

                    # Re-detect ATS
                    new_ats_n = detect_ats_platform(new_url_n)
                    if new_ats_n:
                        report["ats_platform"] = new_ats_n

                    # Re-check status
                    status = check_page_status(page)
                    if status["listing_status"] != "open":
                        report["listing_status"] = status["listing_status"]
                        report["auth_required"] = status["auth_required"]
                        report["application_url"] = page.url
                        _write_report(report, task_path)
                        return report
                else:
                    break  # No clickable elements found, stop

            # Step 5: Extract form fields from the current page
            fields = extract_fields(page)

            # Step 5b: Check if we landed on an account creation / login page
            # instead of the actual application form. Password fields are the
            # strongest signal — real application forms don't ask for passwords.
            password_fields = [f for f in fields if f["type"] == "password"]
            if password_fields:
                print("  Detected account creation/login page (password fields found)")
                page_screenshot = capture_screenshot(page, screenshots_dir, "scout-page1")
                report["listing_status"] = "requires_account"
                report["auth_required"] = True
                report["application_url"] = page.url
                report["pages"].append({
                    "page_number": 1,
                    "url": page.url,
                    "screenshot": page_screenshot,
                    "fields": [],  # Don't include auth fields in report
                })
                report["page_count"] = 1
                _write_report(report, task_path)
                return report

            page_screenshot = capture_screenshot(page, screenshots_dir, "scout-page1")

            page_data = {
                "page_number": 1,
                "url": page.url,
                "screenshot": page_screenshot,
                "fields": fields,
            }
            report["pages"].append(page_data)
            report["page_count"] = 1

            print(f"  Extracted {len(fields)} fields from page 1")

        except PwTimeout as e:
            print(f"  Timeout: {e}", file=sys.stderr)
            report["listing_status"] = "open"
            report["application_url"] = page.url
        except Exception as e:
            print(f"  Error during scouting: {e}", file=sys.stderr)
            report["application_url"] = page.url if page else job_url
        finally:
            context.close()

    _write_report(report, task_path)
    return report


def _write_report(report: dict, task_path: Path) -> None:
    """Write scout_report.json to the task directory."""
    report_file = task_path / "scout_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Scout report written: {report_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Scout a job application page"
    )
    parser.add_argument(
        "--task-dir", required=True,
        help="Path to task directory containing listing.json"
    )
    parser.add_argument(
        "--config", default="config.json",
        help="Path to config.json"
    )

    args = parser.parse_args()
    report = scout_job(args.task_dir, args.config)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
