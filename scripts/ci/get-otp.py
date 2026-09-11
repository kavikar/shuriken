#!/usr/bin/env python3
"""
Shuriken — Retrieve OTP from Example Corp notifications service.

Calls the notifications-service API and writes the OTP to stdout + a file.
Based on: mobileAPPAutomation/src/utils/otp.util.ts

Usage:
  python scripts/ci/get-otp.py --phone 5555550100 --brand b3
  python scripts/ci/get-otp.py --phone 5555550100 --brand b3 --out otp.txt

Environment:
  OTP_ENV  — environment (default: uat)
"""

import argparse
import json
import re
import sys
import time

try:
    import requests
except ImportError:
    print("ERROR: 'requests' required. Run: pip install requests")
    sys.exit(1)

# Brand → API service prefix mapping
BRAND_API = {
    "b3":   "b3-api",
    "brand3": "b3-api",
    "b1":   "b1-api",
    "Brand One": "b1-api",
    "b2":   "b2-api",
    "b4":   "b4-api",
    "Brand Four": "b4-api",
}

# Brand → OTP brand code
BRAND_CODE = {
    "b3":   "B3",
    "brand3": "B3",
    "b1":   "ABI",
    "Brand One": "ABI",
    "b2":   "B2",
    "b4":   "B4",
    "Brand Four": "B4",
}


def _find_otp(value) -> str | None:
    if isinstance(value, dict):
        for key in ["otp", "code", "OTP", "Code", "verificationCode", "verification_code"]:
            if key in value and value[key] is not None:
                candidate = str(value[key]).strip()
                if candidate.isdigit() and 4 <= len(candidate) <= 8:
                    return candidate
        for nested in value.values():
            found = _find_otp(nested)
            if found:
                return found
        return None

    if isinstance(value, list):
        for item in value:
            found = _find_otp(item)
            if found:
                return found
        return None

    if isinstance(value, str):
        match = re.search(r"\b(\d{4,8})\b", value)
        return match.group(1) if match else None

    if value is None:
        return None

    text = str(value).strip()
    if text.isdigit() and 4 <= len(text) <= 8:
        return text
    return None


def retrieve_otp(phone: str, brand: str = "b3", env: str = "uat",
                 country_code: str = "1", retries: int = 5, delay: float = 3.0) -> str:
    """Retrieve OTP from the notifications service API."""
    api_prefix = BRAND_API.get(brand.lower(), "b3-api")
    brand_code = BRAND_CODE.get(brand.lower(), "B3")
    url = f"https://notifications-service-v0.{api_prefix}.{env}.staging.example/retrieveOTP/brand/{brand_code}/otp"

    body = {"countryCode": country_code, "number": phone}

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=body, headers={
                "accept": "application/json",
                "Content-Type": "application/json",
            }, timeout=15, verify=False)

            if resp.status_code != 200:
                print(f"  Attempt {attempt}: HTTP {resp.status_code}", file=sys.stderr)
                if attempt < retries:
                    time.sleep(delay)
                continue

            data = resp.json()
            otp = _find_otp(data)

            if otp:
                return str(otp)

            print(f"  Attempt {attempt}: No OTP in response: {json.dumps(data)}", file=sys.stderr)

        except Exception as e:
            print(f"  Attempt {attempt}: Error: {e}", file=sys.stderr)

        if attempt < retries:
            time.sleep(delay)

    raise RuntimeError(f"Failed to retrieve OTP after {retries} attempts for +{country_code}{phone}")


def main():
    parser = argparse.ArgumentParser(description="Retrieve OTP for Example Corp apps")
    parser.add_argument("--phone", required=True, help="10-digit phone number")
    parser.add_argument("--brand", default="b3", choices=["b3", "brand3", "b1", "Brand One", "b2", "b4", "Brand Four"])
    parser.add_argument("--env", default="uat", choices=["qa", "uat", "staging", "stg", "dem"])
    parser.add_argument("--country-code", default="1")
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--out", default=None, help="Write OTP to file (default: stdout only)")
    args = parser.parse_args()

    otp = retrieve_otp(
        phone=args.phone,
        brand=args.brand,
        env=args.env,
        country_code=args.country_code,
        retries=args.retries,
        delay=args.delay,
    )

    # Always print to stdout (Maestro runScript can capture this)
    print(otp)

    # Optionally write to file
    if args.out:
        with open(args.out, "w") as f:
            f.write(otp)
        print(f"OTP written to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
