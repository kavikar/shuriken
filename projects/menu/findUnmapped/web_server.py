import json
import os
from typing import Dict, List, Tuple

import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS


MENU_API_BASE = "https://menu-api.example/api/v1/menu_events/data"


def _env(name: str, default: str = "") -> str:
	return os.environ.get(name, default).strip()

# B1 values are aligned to the working curl shared by QE.
BRAND_AUTH = {
	"B1": {
		"primary_token": _env("PLATE_B1_PRIMARY_TOKEN"),
		"fallback_token": _env("PLATE_B1_FALLBACK_TOKEN"),
		"primary_cookie": _env("PLATE_B1_PRIMARY_COOKIE"),
		"fallback_cookie": "",
	},
	"B2": {
		"primary_token": _env("PLATE_B2_PRIMARY_TOKEN"),
		"fallback_token": _env("PLATE_B2_FALLBACK_TOKEN"),
		"primary_cookie": _env("PLATE_B2_PRIMARY_COOKIE"),
		"fallback_cookie": "",
	},
	"B3": {
		"primary_token": _env("PLATE_B3_PRIMARY_TOKEN"),
		"fallback_token": "",
		"primary_cookie": "",
		"fallback_cookie": "",
	},
}


app = Flask(__name__, static_folder="web", static_url_path="")
CORS(app)


def _unique_non_empty(values: List[str]) -> List[str]:
	out: List[str] = []
	for value in values:
		value = (value or "").strip()
		if value and value not in out:
			out.append(value)
	return out


def _build_attempts(auth_cfg: Dict[str, str]) -> List[Tuple[str, str]]:
	tokens = _unique_non_empty([auth_cfg.get("primary_token", ""), auth_cfg.get("fallback_token", "")])
	cookies = [auth_cfg.get("primary_cookie", "").strip(), "", auth_cfg.get("fallback_cookie", "").strip()]
	attempts: List[Tuple[str, str]] = []
	for token in tokens:
		for cookie in cookies:
			pair = (token, cookie)
			if pair not in attempts:
				attempts.append(pair)
	return attempts


def fetch_unmapped_for_location(brand: str, location_id: str) -> Dict:
	auth_cfg = BRAND_AUTH.get(brand)
	if not auth_cfg:
		return {"ok": False, "status": "Unsupported brand", "http_status": 400, "items": []}

	params = {
		"location_id": str(location_id).strip(),
		"brand": brand,
		"event_type": "unavailable_products",
	}

	last_status = "Request failed"
	last_http_status = 500
	for token, cookie in _build_attempts(auth_cfg):
		headers = {
			"Authorization": f"Bearer {token}",
			"Accept": "application/json",
		}
		if cookie:
			headers["Cookie"] = cookie

		try:
			resp = requests.get(MENU_API_BASE, params=params, headers=headers, timeout=90, verify=False)
			last_http_status = resp.status_code

			if resp.status_code == 200:
				payload = resp.json()
				items = payload.get("unmapped_items") or []
				return {
					"ok": True,
					"status": "OK",
					"http_status": 200,
					"items": [str(x) for x in items],
				}

			last_status = f"HTTP {resp.status_code}"
		except requests.exceptions.Timeout:
			last_status = "Timeout"
			last_http_status = 504
		except Exception as exc:
			last_status = str(exc)
			last_http_status = 500

	return {"ok": False, "status": last_status, "http_status": last_http_status, "items": []}


@app.route("/")
def home():
	return send_from_directory("web", "index.html")


@app.route("/api/health")
def health():
	return jsonify({"status": "ok", "service": "findUnmapped"})


@app.route("/api/unmapped/location")
def check_location():
	brand = (request.args.get("brand") or "B1").upper().strip()
	location_id = (request.args.get("location_id") or "").strip()
	if not location_id:
		return jsonify({"status": "error", "message": "location_id is required"}), 400

	data = fetch_unmapped_for_location(brand, location_id)
	return jsonify({
		"status": "success" if data["ok"] else "error",
		"brand": brand,
		"location_id": location_id,
		"api_status": data["status"],
		"http_status": data["http_status"],
		"unmapped_items": data["items"],
		"count": len(data["items"]),
	})


@app.route("/api/unmapped/check", methods=["POST"])
def check_unmapped():
	body = request.get_json(silent=True) or {}
	brand = (body.get("brand") or "B1").upper().strip()
	locations = [str(x).strip() for x in (body.get("locations") or []) if str(x).strip()]
	products = [str(x).strip() for x in (body.get("products") or []) if str(x).strip()]

	if brand not in BRAND_AUTH:
		return jsonify({"status": "error", "message": f"Unsupported brand: {brand}"}), 400
	if not locations:
		return jsonify({"status": "error", "message": "At least one location is required"}), 400
	if not products:
		return jsonify({"status": "error", "message": "At least one product is required"}), 400

	cache: Dict[str, Dict] = {}
	for loc in locations:
		cache[loc] = fetch_unmapped_for_location(brand, loc)

	results = []
	for loc in locations:
		item_set = set(cache[loc]["items"])
		for prod in products:
			results.append({
				"location_id": loc,
				"product_id": prod,
				"is_unmapped": prod in item_set,
				"unmapped_count": len(item_set),
				"api_status": cache[loc]["status"],
				"http_status": cache[loc]["http_status"],
			})

	return jsonify({
		"status": "success",
		"summary": {
			"brand": brand,
			"locations_checked": len(locations),
			"products_checked": len(products),
			"total_checks": len(results),
			"unmapped": len([r for r in results if r["is_unmapped"]]),
		},
		"results": results,
	})


if __name__ == "__main__":
	print("findUnmapped web server starting on http://localhost:5100")
	app.run(host="0.0.0.0", port=5100, debug=True)
