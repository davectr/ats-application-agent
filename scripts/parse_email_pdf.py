#!/usr/bin/env python3
"""Parse a Proficiently career coach email PDF into structured job listings.

Extracts text content and embedded URL annotations using pypdf. Deduplicates
URLs, classifies them using config.json patterns, and outputs a JSON array
of structured job listings.

Usage:
    python scripts/parse_email_pdf.py <email.pdf>
    python scripts/parse_email_pdf.py <email.pdf> --config config.json

Output:
    JSON array of listing objects to stdout. Each listing has:
    job_number, company, title, description, pay, job_type, location,
    match_rationale, urls (job_listing, resume_view, resume_download)

Exit codes:
    0 = success
    1 = validation failure or error
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from pypdf import PdfReader


def extract_urls_from_pdf(reader: PdfReader) -> list[str]:
    """Extract all URL annotations from PDF pages, deduplicated, preserving order."""
    seen = set()
    urls = []
    for page in reader.pages:
        annotations = page.get("/Annots")
        if not annotations:
            continue
        annots = annotations if isinstance(annotations, list) else [annotations]
        for annot in annots:
            obj = annot.get_object() if hasattr(annot, "get_object") else annot
            if obj.get("/Subtype") == "/Link":
                action = obj.get("/A")
                if action:
                    action_obj = (
                        action.get_object()
                        if hasattr(action, "get_object")
                        else action
                    )
                    uri = action_obj.get("/URI")
                    if uri:
                        uri_str = str(uri)
                        if uri_str not in seen:
                            seen.add(uri_str)
                            urls.append(uri_str)
    return urls


def extract_text_from_pdf(reader: PdfReader) -> str:
    """Extract and concatenate text from all PDF pages."""
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n".join(parts)


def classify_url(url: str, url_config: dict) -> str | None:
    """Classify a URL as job_listing, resume_view, resume_download, or None."""
    # Check resume_download first (more specific than resume_view)
    if url_config["resume_download_pattern"] in url:
        return "resume_download"
    if url_config["resume_view_pattern"] in url:
        return "resume_view"
    # Check job listing domains
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    for domain in url_config["job_listing_domains"]:
        if hostname == domain or hostname.endswith("." + domain):
            return "job_listing"
    return None


def associate_urls_with_listings(
    urls: list[str], url_config: dict, listing_count: int
) -> list[dict]:
    """Classify URLs and group into per-listing URL sets.

    URLs appear in PDF annotation order: for each listing, the job_listing URL
    comes first, then resume_view, then resume_download. This function collects
    classified URLs in order and groups them into sets of 3.
    """
    job_listings = []
    resume_views = []
    resume_downloads = []

    for url in urls:
        category = classify_url(url, url_config)
        if category == "job_listing":
            job_listings.append(url)
        elif category == "resume_view":
            resume_views.append(url)
        elif category == "resume_download":
            resume_downloads.append(url)

    # Build per-listing URL dicts
    url_sets = []
    for i in range(listing_count):
        url_set = {
            "job_listing": job_listings[i] if i < len(job_listings) else None,
            "resume_view": resume_views[i] if i < len(resume_views) else None,
            "resume_download": resume_downloads[i] if i < len(resume_downloads) else None,
        }
        url_sets.append(url_set)

    return url_sets


def parse_listing_block(block: str, job_number: int) -> dict:
    """Parse a single listing text block into structured fields."""
    lines = block.strip().split("\n")
    if not lines:
        return {}

    # First line: "Company - Title" or "Company Name - Job Title"
    first_line = lines[0].strip()
    # Split on " - " (with spaces around dash) for company/title
    parts = first_line.split(" - ", 1)
    if len(parts) == 2:
        company = parts[0].strip()
        title = parts[1].strip()
    else:
        company = first_line
        title = ""

    # Join remaining lines for field extraction
    body = "\n".join(lines[1:])

    # Extract description: text between title line and first field marker
    # Field markers: "Company:", "Pay:", "Job Type:", "Location:", "Why we like it:"
    desc_match = re.search(
        r"^(.*?)(?=\n\s*(?:Company:|Pay:|Job Type:|Location:|Why we like it))",
        body,
        re.DOTALL,
    )
    description = desc_match.group(1).strip() if desc_match else ""

    # Extract named fields
    pay = _extract_field(body, r"Pay:\s*(.+?)(?=\n\s*(?:Job Type:|Location:|Why we like it)|$)")
    job_type = _extract_field(body, r"Job Type:\s*(.+?)(?=\n\s*(?:Location:|Why we like it)|$)")
    location = _extract_field(body, r"Location:\s*(.+?)(?=\n\s*(?:Why we like it|View Job|View Resume)|$)")
    match_rationale = _extract_field(
        body, r"Why we like it:?\s*(.+?)(?=\n\s*(?:View Job|View Resume|Download Resume)|$)"
    )

    # Clean up multi-line fields (collapse line breaks into spaces)
    description = _clean_multiline(description)
    match_rationale = _clean_multiline(match_rationale)

    return {
        "job_number": job_number,
        "company": company,
        "title": title,
        "description": description,
        "pay": pay.strip() if pay else "Not listed",
        "job_type": job_type.strip() if job_type else "",
        "location": location.strip() if location else "",
        "match_rationale": match_rationale,
    }


def _extract_field(text: str, pattern: str) -> str:
    """Extract a field value using a regex pattern."""
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _clean_multiline(text: str) -> str:
    """Collapse multi-line text into a single line, normalizing whitespace."""
    if not text:
        return ""
    # Replace newlines with spaces, collapse multiple spaces
    return re.sub(r"\s+", " ", text).strip()


def parse_email_pdf(pdf_path: str, config_path: str) -> list[dict]:
    """Parse an email PDF and return structured job listings."""
    # Load config
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    url_config = config["url_classification"]

    # Read PDF
    reader = PdfReader(pdf_path)

    # Extract text and URLs
    full_text = extract_text_from_pdf(reader)
    unique_urls = extract_urls_from_pdf(reader)

    if not full_text.strip():
        print("Error: PDF text extraction produced no content", file=sys.stderr)
        sys.exit(1)

    # Split text into listing blocks at "#N" markers
    # Pattern matches "#1", "#2", etc. at start of line
    blocks = re.split(r"(?:^|\n)#(\d+)\s*\n?", full_text)
    # blocks alternates: [preamble, "1", block1_text, "2", block2_text, ...]

    listings = []
    i = 1  # Skip preamble (index 0)
    while i < len(blocks) - 1:
        job_number = int(blocks[i])
        block_text = blocks[i + 1]
        listing = parse_listing_block(block_text, job_number)
        if listing and listing.get("company"):
            listings.append(listing)
        i += 2

    if not listings:
        print("Error: no job listings found in PDF text", file=sys.stderr)
        sys.exit(1)

    # Associate URLs with listings
    url_sets = associate_urls_with_listings(unique_urls, url_config, len(listings))

    # Merge URLs into listings
    for idx, listing in enumerate(listings):
        listing["urls"] = url_sets[idx] if idx < len(url_sets) else {}

    # Validate: each listing must have all 3 URL types
    errors = []
    for listing in listings:
        urls = listing.get("urls", {})
        missing = [k for k in ("job_listing", "resume_view", "resume_download") if not urls.get(k)]
        if missing:
            errors.append(
                f"Listing #{listing['job_number']} ({listing['company']}): "
                f"missing URL types: {', '.join(missing)}"
            )

    if errors:
        print("Error: URL validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        sys.exit(1)

    return listings


def main():
    parser = argparse.ArgumentParser(
        description="Parse a Proficiently email PDF into structured job listings"
    )
    parser.add_argument("pdf_path", help="Path to the email PDF file")
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config.json (default: config.json in project root)",
    )
    args = parser.parse_args()

    if not Path(args.pdf_path).exists():
        print(f"Error: PDF file not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    if not Path(args.config).exists():
        print(f"Error: config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    listings = parse_email_pdf(args.pdf_path, args.config)
    print(json.dumps(listings, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
