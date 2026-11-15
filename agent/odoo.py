"""Minimal client for Odoo 19's JSON-2 external API (standard library only).

    odoo = Odoo.from_env()
    odoo.search_read("purchase.order", [["state", "=", "purchase"]], ["name", "partner_id"])

Every call is POST /json/2/<model>/<method> with named arguments, a bearer API key
and the database name in the X-Odoo-Database header.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import load_env


class OdooError(RuntimeError):
    pass


class Odoo:
    def __init__(self, url: str, db: str, api_key: str, timeout: float = 60):
        if not api_key:
            raise OdooError("ODOO_API_KEY is empty; run scripts/reset_sandbox.sh or set it in .env")
        self.url = url.rstrip("/")
        self.db = db
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "Odoo":
        env = load_env()
        return cls(env.get("ODOO_URL", "http://localhost:8069"), env.get("ODOO_DB", "lakan"), env.get("ODOO_API_KEY", ""))

    def call(self, model: str, method: str, **kwargs):
        req = urllib.request.Request(
            f"{self.url}/json/2/{model}/{method}",
            data=json.dumps(kwargs).encode(),
            headers={
                "Authorization": f"bearer {self.api_key}",
                "X-Odoo-Database": self.db,
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                body = json.loads(body).get("message", body)
            except (ValueError, AttributeError):
                pass
            raise OdooError(f"{model}.{method} failed ({e.code}): {str(body)[:300]}") from None

    def search_read(self, model: str, domain: list, fields: list, **kwargs) -> list[dict]:
        return self.call(model, "search_read", domain=domain, fields=fields, **kwargs)

    def read(self, model: str, ids: list[int], fields: list) -> list[dict]:
        return self.call(model, "read", ids=ids, fields=fields)
