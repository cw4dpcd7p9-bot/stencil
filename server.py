#!/usr/bin/env python3
"""Stencil — a zero-dependency ad studio."""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
STORE = ROOT / "campaigns.json"
PUBLIC = ROOT / "public"
HOST = os.environ.get("STENCIL_HOST", "127.0.0.1")
PORT = int(os.environ.get("STENCIL_PORT", "8788"))

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,47}$")
RESERVED = {"api", "health", "static", "public", "favicon.ico", "index.html"}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_store() -> dict:
    if not STORE.exists():
        return {"campaigns": {}}
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"campaigns": {}}
    data.setdefault("campaigns", {})
    return data


def save_store(data: dict) -> None:
    tmp = STORE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(STORE)


def mint_id(existing: dict) -> str:
    for _ in range(48):
        token = "".join(secrets.choice("abcdefghijkmnopqrstuvwxyz23456789") for _ in range(6))
        if token not in existing and token not in RESERVED:
            return token
    raise RuntimeError("could not mint an id")


def json_bytes(payload: dict, status: int = 200) -> tuple[int, bytes, str]:
    body = json.dumps(payload).encode("utf-8")
    return status, body, "application/json; charset=utf-8"


def slim_campaign(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()[:80]
    brief = raw.get("brief") if isinstance(raw.get("brief"), dict) else {}
    ads = raw.get("ads") if isinstance(raw.get("ads"), list) else []
    style = raw.get("style") if isinstance(raw.get("style"), dict) else {}
    if not name and not brief and not ads:
        return None
    clean_brief = {}
    for key in ("product", "offer", "audience", "pain", "proof", "url", "tone"):
        val = str(brief.get(key) or "").strip()
        if len(val) > 280:
            val = val[:280]
        clean_brief[key] = val
    clean_ads = []
    for item in ads[:24]:
        if not isinstance(item, dict):
            continue
        clean_ads.append(
            {
                "angle": str(item.get("angle") or "")[:40],
                "platform": str(item.get("platform") or "")[:40],
                "headline": str(item.get("headline") or "")[:120],
                "primary": str(item.get("primary") or "")[:500],
                "support": str(item.get("support") or "")[:240],
                "cta": str(item.get("cta") or "")[:40],
            }
        )
    clean_style = {
        "bg": str(style.get("bg") or "#111114")[:16],
        "fg": str(style.get("fg") or "#f4f0e6")[:16],
        "accent": str(style.get("accent") or "#e8ff47")[:16],
        "size": str(style.get("size") or "square")[:24],
    }
    return {
        "name": name or clean_brief.get("product") or "untitled",
        "brief": clean_brief,
        "ads": clean_ads,
        "style": clean_style,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "Stencil/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 200_000:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path in {"/", "/index.html"}:
            return self._file(PUBLIC / "index.html", "text/html; charset=utf-8")
        if path == "/health":
            status, body, ctype = json_bytes({"ok": True})
            return self._send(status, body, ctype)
        if path == "/api/campaigns":
            return self._list()
        if path.startswith("/api/campaigns/"):
            cid = path.rsplit("/", 1)[-1]
            return self._get_one(cid)
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if path.startswith("/api/"):
            status, body, ctype = json_bytes({"error": "not found"}, 404)
            return self._send(status, body, ctype)
        status, body, ctype = json_bytes({"error": "not found"}, 404)
        self._send(status, body, ctype)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/campaigns":
            status, body, ctype = json_bytes({"error": "not found"}, 404)
            return self._send(status, body, ctype)
        self._create()

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "api" or parts[1] != "campaigns":
            status, body, ctype = json_bytes({"error": "not found"}, 404)
            return self._send(status, body, ctype)
        self._delete(parts[2])

    def _file(self, path: Path, content_type: str) -> None:
        if not path.exists() or not path.is_file():
            status, body, ctype = json_bytes({"error": "not found"}, 404)
            return self._send(status, body, ctype)
        data = path.read_bytes()
        self._send(200, data, content_type, {"Cache-Control": "no-cache"})

    def _list(self) -> None:
        data = load_store()
        items = []
        for cid, row in data["campaigns"].items():
            items.append({"id": cid, **row})
        items.sort(key=lambda row: row.get("updated") or row.get("created") or "", reverse=True)
        status, body, ctype = json_bytes({"campaigns": items})
        self._send(status, body, ctype)

    def _get_one(self, cid: str) -> None:
        data = load_store()
        row = data["campaigns"].get(cid)
        if not row:
            status, body, ctype = json_bytes({"error": "not found"}, 404)
            return self._send(status, body, ctype)
        status, body, ctype = json_bytes({"id": cid, **row})
        self._send(status, body, ctype)

    def _create(self) -> None:
        payload = self._read_json()
        clean = slim_campaign(payload)
        if not clean:
            status, body, ctype = json_bytes({"error": "need a brief or some ads"}, 400)
            return self._send(status, body, ctype)

        data = load_store()
        wanted = str(payload.get("id") or "").strip().lower()
        if wanted:
            if wanted in RESERVED or not ID_RE.match(wanted):
                status, body, ctype = json_bytes(
                    {"error": "id must be 2–48 letters, numbers, dashes"}, 400
                )
                return self._send(status, body, ctype)
            cid = wanted
        else:
            cid = mint_id(data["campaigns"])

        existing = data["campaigns"].get(cid)
        now = utc_now()
        row = {
            **clean,
            "created": (existing or {}).get("created") or now,
            "updated": now,
        }
        data["campaigns"][cid] = row
        save_store(data)
        status, body, ctype = json_bytes({"id": cid, **row}, 201 if not existing else 200)
        self._send(status, body, ctype)

    def _delete(self, cid: str) -> None:
        data = load_store()
        if cid not in data["campaigns"]:
            status, body, ctype = json_bytes({"error": "not found"}, 404)
            return self._send(status, body, ctype)
        del data["campaigns"][cid]
        save_store(data)
        status, body, ctype = json_bytes({"ok": True})
        self._send(status, body, ctype)


def main() -> int:
    PUBLIC.mkdir(exist_ok=True)
    if not STORE.exists():
        save_store({"campaigns": {}})
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"stencil on http://{HOST}:{PORT}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
