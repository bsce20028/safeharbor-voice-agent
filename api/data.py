"""Simple JSON-style data store.

Seed data (customers + policies) lives in code. Quotes and claims created
during calls are kept in memory and mirrored to a JSON file in /tmp.

Note: on Vercel, /tmp is temporary, so saved quotes/claims reset when the
server restarts. That's fine for a portfolio demo. Swap this module for
Supabase later without touching the endpoints.
"""

import json
import os
import threading

# ---------------------------------------------------------------------------
# Seed data: fake customers and their policies (used to verify claim callers)
# ---------------------------------------------------------------------------
POLICIES = {
    "SH-1001": {
        "customer_name": "John Carter",
        "date_of_birth": "1988-04-12",
        "carrier": "Liberty Shield",
        "coverage": "full",
        "deductible": 500,
        "vehicle": "2021 Toyota Camry",
        "status": "active",
    },
    "SH-1002": {
        "customer_name": "Emily Davis",
        "date_of_birth": "1995-09-03",
        "carrier": "Summit Mutual",
        "coverage": "liability",
        "deductible": 1000,
        "vehicle": "2018 Honda Civic",
        "status": "active",
    },
    "SH-1003": {
        "customer_name": "Michael Brown",
        "date_of_birth": "1979-01-25",
        "carrier": "Harborline Insurance",
        "coverage": "full",
        "deductible": 250,
        "vehicle": "2023 Tesla Model 3",
        "status": "active",
    },
    "SH-1004": {
        "customer_name": "Sarah Wilson",
        "date_of_birth": "2001-06-30",
        "carrier": "Liberty Shield",
        "coverage": "full",
        "deductible": 1000,
        "vehicle": "2016 Ford F-150",
        "status": "lapsed",
    },
}

# ---------------------------------------------------------------------------
# Runtime store: quotes, claims, calls
# ---------------------------------------------------------------------------
_STORE_PATH = os.environ.get("STORE_PATH", "/tmp/safeharbor_store.json")
_lock = threading.Lock()


def _load() -> dict:
    try:
        with open(_STORE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"quote_requests": {}, "claims": {}, "calls": [], "counters": {"quote": 24800, "claim": 430}}


_store = _load()


def _save() -> None:
    try:
        with open(_STORE_PATH, "w") as f:
            json.dump(_store, f, indent=2)
    except OSError:
        pass  # read-only filesystem: keep data in memory only


def next_number(kind: str) -> int:
    with _lock:
        _store["counters"][kind] += 1
        _save()
        return _store["counters"][kind]


def save_quote_request(qid: str, record: dict) -> None:
    with _lock:
        _store["quote_requests"][qid] = record
        _save()


def get_quote_request(qid: str) -> dict | None:
    return _store["quote_requests"].get(qid)


def save_claim(claim_number: str, record: dict) -> None:
    with _lock:
        _store["claims"][claim_number] = record
        _save()


def save_call(record: dict) -> None:
    with _lock:
        _store["calls"].insert(0, record)
        _store["calls"] = _store["calls"][:100]
        _save()


def snapshot() -> dict:
    return {
        "quote_requests": list(_store["quote_requests"].values())[::-1],
        "claims": list(_store["claims"].values())[::-1],
        "calls": _store["calls"],
    }
