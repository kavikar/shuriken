#!/usr/bin/env python3
"""
Shuriken — Send notifications to Microsoft Teams and Outlook.
Posts an Adaptive Card to Teams webhook and sends email via Outlook/SMTP.

Usage:
  python3 notify.py \
    --confluence-url https://your-tenant.atlassian.net/wiki/... \
    --teams-webhook https://outlook.office.com/webhook/... \
    --brand brand3 \
    --build-version 4.2.1-rc.3 \
    --results-dir test-results/
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Run: pip install requests")
    sys.exit(1)


def load_summaries(results_dir: str) -> list:
    """Load all *-summary.json files."""
    summaries = []
    for f in sorted(Path(results_dir).glob("*-summary.json")):
        with open(f) as fh:
            summaries.append(json.load(fh))
    return summaries


def build_teams_card(
    summaries: list,
    confluence_url: str,
    build_version: str,
    pipeline_url: str,
    brand: str,
) -> dict:
    """Build an Adaptive Card payload for Power Automate webhook.
    
    Power Automate 'When a Teams webhook request is received' trigger
    expects the Adaptive Card directly in attachments format.
    """
    total = sum(s["total"] for s in summaries)
    passed = sum(s["passed"] for s in summaries)
    failed = sum(s["failed"] for s in summaries) + sum(s.get("errors", 0) for s in summaries)
    duration = sum(s.get("duration_s", 0) for s in summaries)
    overall = "✅ PASSED" if failed == 0 else "❌ FAILED"
    status_color = "Good" if failed == 0 else "Attention"

    # Resolve app version: prefer value from summary files, fall back to --build-version arg
    app_ver = ""
    for s in summaries:
        v = s.get("app_version", "")
        if v:
            app_ver = v
            break
    display_version = app_ver or build_version

    # Brand results lines
    brand_lines = []
    for s in summaries:
        icon = "✅" if s["status"] == "passed" else "❌"
        dur = s.get("duration_s", 0)
        display_brand = s.get("brand_name", s["brand"]).upper()
        brand_lines.append(f"{icon} **{display_brand}**: {s['passed']}/{s['total']} passed ({dur:.0f}s)")

    # Brand display name mapping
    brand_names = {"b3": "Brand Three", "b1": "Brand One", "b2": "B2", "b4": "Brand Four", "all": "ALL"}
    display_brand_name = brand_names.get(brand.lower(), brand.upper())

    facts = [
        {"title": "Status", "value": overall},
        {"title": "Total Tests", "value": str(total)},
        {"title": "Passed", "value": str(passed)},
        {"title": "Failed", "value": str(failed)},
        {"title": "Duration", "value": f"{duration:.0f}s"},
        {"title": "Brand(s)", "value": display_brand_name},
        {"title": "App Version", "value": display_version},
    ]

    actions = []
    if confluence_url and confluence_url != "N/A":
        actions.append({
            "type": "Action.OpenUrl",
            "title": "📝 View Confluence Report",
            "url": confluence_url,
        })
    if pipeline_url:
        actions.append({
            "type": "Action.OpenUrl",
            "title": "🔧 View GitLab Pipeline",
            "url": pipeline_url,
        })

    # Power Automate expects this exact structure for Adaptive Cards
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
                            "text": f"🍽️ Shuriken Smoke Report — {display_version}",
                            "weight": "Bolder",
                            "size": "Large",
                            "color": status_color,
                        },
                        {
                            "type": "TextBlock",
                            "text": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                            "isSubtle": True,
                            "spacing": "None",
                        },
                        {
                            "type": "FactSet",
                            "facts": facts,
                        },
                        {
                            "type": "TextBlock",
                            "text": "\n\n".join(brand_lines) if brand_lines else "No test details available.",
                            "wrap": True,
                        },
                    ],
                    "actions": actions,
                },
            }
        ],
    }
    return card


def send_teams_notification(webhook_url: str, card: dict) -> bool:
    """Post Adaptive Card to Power Automate webhook.
    
    Tries Adaptive Card format first. If it fails, falls back to
    a simple MessageCard (O365 connector format) as a safety net.
    """
    try:
        resp = requests.post(
            webhook_url,
            json=card,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        print(f"   Teams response: {resp.status_code} — {resp.text[:200] if resp.text else '(empty)'}")
        if resp.status_code in (200, 202) and "error" not in resp.text.lower():
            print("✅ Teams notification sent!")
            return True
        else:
            print(f"⚠️  Teams webhook returned {resp.status_code}: {resp.text[:300]}")
            # Fallback: try simple MessageCard format
            return send_teams_simple_fallback(webhook_url, card)
    except Exception as e:
        print(f"❌ Teams notification failed: {e}")
        return False


def send_teams_simple_fallback(webhook_url: str, card: dict) -> bool:
    """Fallback: Send a simple text message via MessageCard format."""
    try:
        # Extract text from the Adaptive Card for a plain fallback
        body_blocks = card.get("attachments", [{}])[0].get("content", {}).get("body", [])
        title = body_blocks[0].get("text", "Shuriken Report") if body_blocks else "Shuriken Report"
        facts_block = next((b for b in body_blocks if b.get("type") == "FactSet"), {})
        facts = facts_block.get("facts", [])
        facts_text = "\n".join(f"**{f['title']}**: {f['value']}" for f in facts)

        # O365 MessageCard format (legacy but widely supported)
        message_card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": title,
            "themeColor": "0076D7",
            "title": title,
            "sections": [
                {
                    "activityTitle": "Test Results",
                    "text": facts_text,
                    "markdown": True,
                }
            ],
        }

        resp = requests.post(
            webhook_url,
            json=message_card,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        print(f"   Fallback response: {resp.status_code} — {resp.text[:200] if resp.text else '(empty)'}")
        if resp.status_code in (200, 202):
            print("✅ Teams fallback notification sent!")
            return True
        else:
            print(f"⚠️  Fallback also failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ Teams fallback failed: {e}")
        return False


def send_outlook_notification(
    webhook_url: str,
    summaries: list,
    confluence_url: str,
    build_version: str,
    brand: str,
) -> bool:
    """Send email notification via Outlook Power Automate webhook or Logic App."""
    total = sum(s["total"] for s in summaries)
    passed = sum(s["passed"] for s in summaries)
    failed = sum(s["failed"] for s in summaries) + sum(s.get("errors", 0) for s in summaries)
    overall = "PASSED" if failed == 0 else "FAILED"

    # Resolve app version from summaries
    app_ver = ""
    for s in summaries:
        v = s.get("app_version", "")
        if v:
            app_ver = v
            break
    display_version = app_ver or build_version

    payload = {
        "subject": f"🍽️ Shuriken Smoke Report — {brand.upper()} {display_version} — {overall}",
        "body": f"""
<h2>Shuriken Smoke Test Results</h2>
<p><strong>App Version:</strong> {display_version} | <strong>Brand:</strong> {brand.upper()}</p>
<p><strong>Status:</strong> {'✅ PASSED' if failed == 0 else '❌ FAILED'}</p>
<p>Total: {total} | Passed: {passed} | Failed: {failed}</p>
<p><a href="{confluence_url}">📝 View Full Report on Confluence</a></p>
<hr/>
<p><em>Sent by Shuriken — Predictive Lifecycle Assurance & Testing Engine</em></p>
""",
        "confluence_url": confluence_url,
        "status": overall,
        "brand": brand,
        "build_version": display_version,
    }

    try:
        resp = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code in (200, 202):
            print("✅ Outlook notification sent!")
            return True
        else:
            print(f"⚠️  Outlook webhook returned {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Outlook notification failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Shuriken — Send Teams & Outlook notifications")
    parser.add_argument("--confluence-url", required=True)
    parser.add_argument("--teams-webhook", required=True)
    parser.add_argument("--outlook-webhook", default=None)
    parser.add_argument("--brand", default="all")
    parser.add_argument("--build-version", default="unknown")
    parser.add_argument("--pipeline-url", default="")
    parser.add_argument("--results-dir", default="test-results/")
    args = parser.parse_args()

    summaries = load_summaries(args.results_dir)
    if not summaries:
        print("⚠️  No test summaries found. Sending basic notification.")
        summaries = [{"brand": args.brand, "total": 0, "passed": 0, "failed": 0, "errors": 1, "duration_s": 0, "status": "error"}]

    # Send Teams notification
    card = build_teams_card(summaries, args.confluence_url, args.build_version, args.pipeline_url, args.brand)
    send_teams_notification(args.teams_webhook, card)

    # Send Outlook notification (optional)
    if args.outlook_webhook:
        send_outlook_notification(args.outlook_webhook, summaries, args.confluence_url, args.build_version, args.brand)
    else:
        print("ℹ️  No Outlook webhook configured — skipping email notification.")


if __name__ == "__main__":
    main()
