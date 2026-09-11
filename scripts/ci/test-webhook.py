import requests
import json
import os

url = os.environ.get("TEAMS_WEBHOOK_URL", "")
if not url:
    print("❌ TEAMS_WEBHOOK_URL not set. Run: . .\\scripts\\load-env.ps1")
    exit(1)

# Power Automate expects an "attachments" array with Adaptive Cards
payload = {
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
                        "text": "🍽️ Shuriken Test Notification",
                        "weight": "Bolder",
                        "size": "Large",
                        "color": "Good"
                    },
                    {
                        "type": "TextBlock",
                        "text": "Hello from Shuriken pipeline! This is a test message.",
                        "wrap": True
                    },
                    {
                        "type": "FactSet",
                        "facts": [
                            {"title": "Status", "value": "✅ PASSED"},
                            {"title": "Brand", "value": "Brand Three"},
                            {"title": "Build", "value": "test-1.0.0"},
                            {"title": "Tests", "value": "4/4 passed (32.5s)"}
                        ]
                    }
                ],
                "actions": [
                    {
                        "type": "Action.OpenUrl",
                        "title": "📄 View Confluence Report",
                        "url": "https://your-tenant.atlassian.net/wiki"
                    }
                ]
            }
        }
    ]
}

print("Sending Adaptive Card payload...")
print(json.dumps(payload, indent=2))

r = requests.post(url, json=payload, timeout=30)
print(f"\nStatus: {r.status_code}")
print(f"Headers: {dict(r.headers)}")
body = r.text[:500] if r.text else "(empty body)"
print(f"Body: {body}")

if r.status_code in (200, 202):
    print("\n✅ Webhook accepted the request.")
    print("Check Teams group chat for the Adaptive Card!")
else:
    print(f"\n❌ Webhook returned {r.status_code}")
