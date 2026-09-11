#!/usr/bin/env python3
"""
Shuriken — Send test notification to Teams (via Power Automate) + Outlook.

Usage:
  # Test message
  python scripts/ci/send-notification.py --test

  # Real notification with results
  python scripts/ci/send-notification.py \
    --title "Shuriken Smoke Report" \
    --status PASSED \
    --brand brand3 \
    --build-version 4.2.1 \
    --confluence-url "https://your-tenant.atlassian.net/wiki/..."

Environment variables required:
  TEAMS_WEBHOOK_URL  — Power Automate HTTP trigger URL
"""

import argparse
import json
import os
import sys
from datetime import datetime

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Run: pip install requests")
    sys.exit(1)


def build_adaptive_card(
    title: str,
    message: str,
    status: str,
    brand: str,
    build_version: str,
    confluence_url: str,
) -> dict:
    """Build Power Automate-compatible Adaptive Card payload."""

    status_emoji = "✅" if status == "PASSED" else "❌"
    status_color = "Good" if status == "PASSED" else "Attention"

    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": title,
                            "weight": "Bolder",
                            "size": "Large",
                            "color": status_color,
                        },
                        {
                            "type": "TextBlock",
                            "text": message,
                            "wrap": True,
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Status", "value": f"{status_emoji} {status}"},
                                {"title": "Brand", "value": brand.upper()},
                                {"title": "Build", "value": build_version},
                            ],
                        },
                    ],
                    "actions": [],
                },
            }
        ],
    }

    # Add Confluence link button if provided
    if confluence_url:
        card["attachments"][0]["content"]["actions"].append(
            {
                "type": "Action.OpenUrl",
                "title": "📄 View Confluence Report",
                "url": confluence_url,
            }
        )

    return card


def send_notification(
    webhook_url: str,
    title: str,
    message: str,
    status: str,
    brand: str,
    build_version: str,
    confluence_url: str,
) -> bool:
    """Send Adaptive Card notification to Power Automate webhook."""

    payload = build_adaptive_card(
        title=title,
        message=message,
        status=status,
        brand=brand,
        build_version=build_version,
        confluence_url=confluence_url,
    )

    print(f"\n📤 Sending Adaptive Card to Power Automate...")
    print(f"   URL: {webhook_url[:80]}...")
    print(f"   Title: {title}")
    print(f"   Status: {status} | Brand: {brand} | Build: {build_version}")

    try:
        resp = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        print(f"\n   HTTP {resp.status_code}")

        if resp.status_code in (200, 202):
            print("✅ Notification delivered to Teams!")
            return True
        else:
            print(f"❌ Notification failed — HTTP {resp.status_code}")
            print(f"   Body: {resp.text[:500] if resp.text else '(empty)'}")
            return False

    except requests.exceptions.Timeout:
        print("\n❌ Request timed out after 30s")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ Connection error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Shuriken — Send notification")
    parser.add_argument("--test", action="store_true", help="Send a test message")
    parser.add_argument("--title", default="Shuriken Smoke Report")
    parser.add_argument("--message", default="")
    parser.add_argument("--status", default="PASSED", choices=["PASSED", "FAILED"])
    parser.add_argument("--brand", default="brand3")
    parser.add_argument("--build-version", default="test-1.0.0")
    parser.add_argument("--confluence-url", default="")
    parser.add_argument("--webhook-url", default=None, help="Override TEAMS_WEBHOOK_URL env var")
    args = parser.parse_args()

    # Get webhook URL
    webhook_url = args.webhook_url or os.environ.get("TEAMS_WEBHOOK_URL", "")
    if not webhook_url:
        print("❌ No webhook URL. Set TEAMS_WEBHOOK_URL env var or pass --webhook-url")
        sys.exit(1)

    if args.test:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        title = "🍽️ Shuriken Test Notification"
        message = f"This is a test message from Shuriken pipeline.\nSent at {now}.\nBrand3 smoke suite: 4/4 passed (32.5s)"
        status = "PASSED"
        brand = "brand3"
        build_version = "test-1.0.0"
        confluence_url = "https://your-tenant.atlassian.net/wiki/spaces/~000000000000/pages/000000000000/Automation+Reports"
    else:
        title = args.title
        message = args.message or f"{args.brand.upper()} smoke suite completed."
        status = args.status
        brand = args.brand
        build_version = args.build_version
        confluence_url = args.confluence_url or "https://your-tenant.atlassian.net/wiki"

    success = send_notification(
        webhook_url=webhook_url,
        title=title,
        message=message,
        status=status,
        brand=brand,
        build_version=build_version,
        confluence_url=confluence_url,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
