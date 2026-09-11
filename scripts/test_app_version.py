import requests, json

AUTH = ("<browserstack-username>", "<browserstack-access-key>")

# Test 1: By custom_id
print("=== Test 1: By custom_id ===")
r = requests.get(
    "https://api-cloud.browserstack.com/app-automate/recent_apps/shuriken-brand3-android",
    auth=AUTH, timeout=30
)
print(f"Status: {r.status_code}")
print(f"Type: {type(r.json())}")
print(json.dumps(r.json(), indent=2)[:1000])

# Test 2: All recent apps
print("\n=== Test 2: All recent apps ===")
r2 = requests.get(
    "https://api-cloud.browserstack.com/app-automate/recent_apps",
    auth=AUTH, timeout=30
)
print(f"Status: {r2.status_code}")
data = r2.json()
if isinstance(data, list):
    for app in data[:3]:
        print(f"  {app.get('custom_id','?'):30s} {app.get('app_version','?'):10s} {app.get('app_url','?')}")
else:
    print(json.dumps(data, indent=2)[:500])

# Test 3: Maestro-specific recent apps
print("\n=== Test 3: Maestro API recent apps ===")
r3 = requests.get(
    "https://api-cloud.browserstack.com/app-automate/maestro/v2/apps",
    auth=AUTH, timeout=30
)
print(f"Status: {r3.status_code}")
print(json.dumps(r3.json(), indent=2)[:1000] if r3.status_code == 200 else r3.text[:500])
