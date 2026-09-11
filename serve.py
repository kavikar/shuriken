import hashlib
import json
import os
import random
import re
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8888"))
BASE_DIR = Path(__file__).resolve().parent
SITE_DIR = BASE_DIR / "site"


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=True).encode("utf-8")


def _deterministic_otp(phone: str, brand: str, env: str) -> str:
    seed = f"{phone}:{brand}:{env}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    return str(int(digest[:10], 16) % 900000 + 100000)


def _split_words(text: str) -> list[str]:
    return [part for part in re.split(r"[^a-zA-Z0-9.-]+", text.lower()) if part]


class VanillaHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE_DIR), **kwargs)

    def _send_json(self, status: int, payload: dict) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/health":
            self._send_json(200, {"status": "ok", "mode": "mock"})
            return

        if path.startswith("/api/") and path.endswith("/unmapped/live"):
            parts = [p for p in path.split("/") if p]
            brand = parts[1] if len(parts) > 1 else "brand-generic"
            location_id = (qs.get("location_id") or ["1000"])[0]
            base = ["item-alpha", "item-bravo", "item-charlie", "item-delta", "item-echo"]
            rnd = random.Random(f"{brand}:{location_id}")
            rnd.shuffle(base)
            unmapped = base[: rnd.randint(1, 3)]
            payload = {
                "status": "success",
                "http_status": 200,
                "body": {
                    "status": "OK",
                    "location_id": location_id,
                    "brand": brand,
                    "event_type": (qs.get("event_type") or ["unavailable_products"])[0],
                    "unmapped_items": unmapped,
                },
            }
            self._send_json(200, payload)
            return

        if path == "/api/version-compare/tree":
            repo = (qs.get("repo") or ["all"])[0]
            env = (qs.get("branch") or ["test"])[0]
            brands = ["brand1", "brand2", "brand3"] if repo == "all" else [repo.lower().replace(" ", "")]
            paths = [f"{brand}/{env}/gateway.yaml" for brand in brands]
            self._send_json(200, {"status": "success", "paths": paths})
            return

        if path == "/api/version-compare/file":
            rel_path = (qs.get("path") or ["brand1/test/gateway.yaml"])[0]
            parts = rel_path.split("/")
            brand = parts[0] if len(parts) > 0 else "brand1"
            env = parts[1] if len(parts) > 1 else "test"
            service = Path(parts[-1]).stem if parts else "gateway"
            version = f"v{1 + len(service)}.{2 + len(env)}.{3 + len(brand)}"
            self._send_json(
                200,
                {
                    "status": "success",
                    "brand": brand,
                    "environment": env,
                    "service": service,
                    "version": version,
                },
            )
            return

        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        if path == "/api/otp":
            phone = str(body.get("phone", "")).strip()
            brand = str(body.get("brand", "brand1")).strip().lower()
            env = str(body.get("env", "test")).strip().lower()
            if not re.fullmatch(r"\d{10}", phone):
                self._send_json(400, {"ok": False, "answer": "Phone must be 10 digits."})
                return
            otp = _deterministic_otp(phone, brand, env)
            self._send_json(200, {"ok": True, "phone": phone, "brand": brand, "env": env, "otp": otp})
            return

        if path == "/api/chat":
            query = str(body.get("query", "")).strip()
            words = _split_words(query)
            answer = "Mock assistant processed the request."
            payload = {"ok": True, "skill": "general", "answer": answer}

            if "otp" in words:
                phone_match = re.search(r"(\d{10})", query)
                phone = phone_match.group(1) if phone_match else "5550000000"
                brand = "brand1"
                env = "test"
                payload.update(
                    {
                        "skill": "otp-fetch-by-phone",
                        "answer": "Generated a deterministic OTP from mock service.",
                        "otp": _deterministic_otp(phone, brand, env),
                        "phone": phone,
                        "brand": brand,
                        "env": env,
                    }
                )
            elif "pending" in words or "tests" in words or "te" in words:
                payload.update(
                    {
                        "skill": "te-status-list",
                        "answer": "Here is the demo test execution snapshot.",
                        "columns": ["Test", "Status", "Owner"],
                        "rows": [
                            ["TE-1001-T01", "PASS", "qa-a"],
                            ["TE-1001-T02", "TODO", "qa-b"],
                            ["TE-1001-T03", "BLOCKED", "qa-c"],
                        ],
                        "summaryCards": [
                            {"label": "Total", "value": "3"},
                            {"label": "Pending", "value": "2"},
                        ],
                        "te": "TE-1001",
                    }
                )
            elif "scope" in words or "release" in words:
                payload.update(
                    {
                        "skill": "release-scope-fetch",
                        "answer": "Demo release scope resolved.",
                        "columns": ["Issue", "Type", "Status"],
                        "rows": [
                            ["REL-101", "Story", "In Progress"],
                            ["REL-102", "Bug", "Ready"],
                        ],
                        "summaryCards": [{"label": "Scope Size", "value": "2"}],
                        "release": "Release 1.0",
                    }
                )

            self._send_json(200, payload)
            return

        if path == "/api/offers":
            epics = str(body.get("epics", "")).strip()
            mode = str(body.get("mode", "preview")).strip()
            platforms = body.get("platforms", ["WEB", "APP"])
            output = (
                f"[MOCK] Offer flow mode={mode}\n"
                f"epics={epics or 'EPIC-1001'}\n"
                f"platforms={','.join(platforms)}\n"
                "generated_tests=12\nlinked_execution=TE-2001"
            )
            self._send_json(200, {"ok": True, "mode": mode, "exitCode": 0, "output": output})
            return

        if path == "/api/executioner":
            action = str(body.get("action", "dry-run")).strip()
            te = str(body.get("te", "TE-1001")).strip().upper() or "TE-1001"
            output = (
                f"[MOCK] executioner action={action}\n"
                f"te={te}\n"
                "updates: PASS=3 FAIL=1 TODO=2\n"
                "comment: simulated update complete"
            )
            self._send_json(200, {"ok": True, "action": action, "exitCode": 0, "output": output})
            return

        if path == "/api/loyalty":
            mode = str(body.get("mode", "dry-run")).strip()
            epics = str(body.get("epics", "")).strip() or "EPIC-2001"
            output = (
                f"[MOCK] loyalty mode={mode}\n"
                f"epics={epics}\n"
                "created_tests=6\n"
                "mapped_execution=TE-3001"
            )
            self._send_json(200, {"ok": True, "mode": mode, "exitCode": 0, "output": output})
            return

        self._send_json(404, {"ok": False, "answer": "Unknown endpoint."})


def main() -> None:
    os.chdir(SITE_DIR)
    print(f"Serving Vanilla Shuriken at http://{HOST}:{PORT}")
    print("Mock API enabled under /api/*")
    HTTPServer((HOST, PORT), VanillaHandler).serve_forever()


if __name__ == "__main__":
    main()
