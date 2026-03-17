#!/usr/bin/env python3
"""Download resume PDFs from Google Docs export URLs.

Downloads tailored resume PDFs for each job listing. Validates that
downloaded files are real PDFs (checks header and size). Saves with
company-slug filename.

Usage:
    python scripts/download_resumes.py <listings.json> <output_dir>
    python scripts/download_resumes.py --listing-json '...' --output-dir tasks/2026-03-16_company_role/

Input:
    JSON array of listing objects (from parse_email_pdf.py output),
    either as a file path or inline JSON via --listing-json.

Output:
    JSON summary to stdout with download results per resume.

Exit codes:
    0 = all downloads succeeded
    1 = one or more downloads failed
"""

import argparse
import json
import re
import sys
from pathlib import Path

import requests


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def download_resume(url: str, output_path: Path) -> dict:
    """Download a resume PDF and validate it.

    Returns a result dict with status, file_size_bytes, and valid_pdf.
    """
    try:
        resp = requests.get(url, allow_redirects=True, timeout=30)
    except requests.RequestException as e:
        return {
            "status": "error",
            "error": str(e),
            "file_size_bytes": 0,
            "valid_pdf": False,
        }

    # Check for auth redirect to Google login
    if "accounts.google.com" in resp.url:
        return {
            "status": "auth_required",
            "error": "Redirected to Google login — resume doc may not be publicly shared",
            "file_size_bytes": 0,
            "valid_pdf": False,
        }

    # Check for HTML response (login page masquerading as 200)
    content_type = resp.headers.get("Content-Type", "")
    if resp.status_code == 200 and "text/html" in content_type:
        return {
            "status": "auth_required",
            "error": "Got HTML instead of PDF — likely a login page",
            "file_size_bytes": len(resp.content),
            "valid_pdf": False,
        }

    if resp.status_code != 200:
        return {
            "status": f"http_{resp.status_code}",
            "error": f"HTTP {resp.status_code}",
            "file_size_bytes": 0,
            "valid_pdf": False,
        }

    content = resp.content

    # Validate PDF header
    if not content[:5] == b"%PDF-":
        return {
            "status": "invalid_pdf",
            "error": "Downloaded file does not have PDF header",
            "file_size_bytes": len(content),
            "valid_pdf": False,
        }

    # Validate non-trivial size (> 1KB suggests real content)
    if len(content) < 1024:
        return {
            "status": "suspicious_size",
            "error": f"File very small ({len(content)} bytes), may be an error page",
            "file_size_bytes": len(content),
            "valid_pdf": False,
        }

    # Write file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(content)

    return {
        "status": "success",
        "file_size_bytes": len(content),
        "valid_pdf": True,
    }


def download_resumes(listings: list[dict], output_dir: str) -> dict:
    """Download resumes for all listings. Returns summary."""
    output_path = Path(output_dir)
    results = []
    all_success = True

    for listing in listings:
        company = listing.get("company", "unknown")
        url = listing.get("urls", {}).get("resume_download")
        slug = slugify(company)
        filename = f"{slug}-resume.pdf"
        filepath = output_path / filename

        if not url:
            results.append({
                "company": company,
                "filename": filename,
                "status": "error",
                "error": "No resume_download URL in listing",
                "file_size_bytes": 0,
                "valid_pdf": False,
            })
            all_success = False
            continue

        result = download_resume(url, filepath)
        result["company"] = company
        result["filename"] = filename
        results.append(result)

        if result["status"] != "success":
            all_success = False

    return {
        "all_success": all_success,
        "downloads": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Download resume PDFs from Google Docs export URLs"
    )
    parser.add_argument(
        "listings_path",
        nargs="?",
        help="Path to JSON file with listing array (from parse_email_pdf.py)",
    )
    parser.add_argument(
        "--listing-json",
        help="Inline JSON array of listings (alternative to file path)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to save downloaded resume PDFs",
    )
    args = parser.parse_args()

    # Load listings from file or inline JSON
    if args.listing_json:
        listings = json.loads(args.listing_json)
    elif args.listings_path:
        with open(args.listings_path, "r", encoding="utf-8") as f:
            listings = json.load(f)
    else:
        print("Error: provide either a listings file path or --listing-json", file=sys.stderr)
        sys.exit(1)

    summary = download_resumes(listings, args.output_dir)
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if not summary["all_success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
