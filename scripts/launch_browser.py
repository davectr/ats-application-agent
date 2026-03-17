#!/usr/bin/env python3
"""Playwright browser launch with persistent Chrome profile.

Shared by scout and application subagents. Uses launch_persistent_context
with the Chrome profile path from config.json.

Usage:
    # As a module (imported by other scripts):
    from launch_browser import launch_persistent_context
    context = launch_persistent_context(config)
    page = context.pages[0]
    # ... do work ...
    context.close()

    # CLI test mode:
    python scripts/launch_browser.py --config config.json --test
"""

import argparse
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, BrowserContext


def load_config(config_path: str) -> dict:
    """Load and return config.json."""
    path = Path(config_path)
    if not path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def launch_persistent_context(config: dict, playwright_instance=None) -> BrowserContext:
    """Launch a persistent browser context using config settings.

    Args:
        config: Parsed config.json dict.
        playwright_instance: An existing Playwright instance. If None, caller
            must manage the Playwright lifecycle externally.

    Returns:
        BrowserContext with a persistent Chrome profile.
    """
    chrome_profile = config["chrome_profile_path"]
    browser_cfg = config.get("browser", {})

    # Ensure the Chrome profile directory exists
    Path(chrome_profile).mkdir(parents=True, exist_ok=True)

    launch_args = []
    if browser_cfg.get("start_minimized", True):
        launch_args.append("--start-minimized")

    context = playwright_instance.chromium.launch_persistent_context(
        user_data_dir=chrome_profile,
        channel=browser_cfg.get("channel", "chrome"),
        headless=browser_cfg.get("headless", False),
        args=launch_args,
    )

    return context


def run_test(config_path: str) -> None:
    """Test mode: launch browser, navigate to about:blank, close."""
    config = load_config(config_path)

    print("Launching browser with persistent profile...")
    print(f"  Chrome profile: {config['chrome_profile_path']}")
    print(f"  Channel: {config.get('browser', {}).get('channel', 'chrome')}")

    with sync_playwright() as pw:
        context = launch_persistent_context(config, pw)
        page = context.pages[0] if context.pages else context.new_page()

        page.goto("about:blank")
        print("  Navigated to about:blank")

        title = page.title()
        print(f"  Page title: '{title}'")

        context.close()
        print("Browser closed cleanly.")

    print("Test passed.")


def main():
    parser = argparse.ArgumentParser(
        description="Playwright browser launch with persistent Chrome profile"
    )
    parser.add_argument(
        "--config", default="config.json", help="Path to config.json"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Test mode: launch browser, navigate, close"
    )

    args = parser.parse_args()

    if args.test:
        run_test(args.config)
    else:
        print("Use --test for CLI testing, or import launch_persistent_context as a module.")


if __name__ == "__main__":
    main()
