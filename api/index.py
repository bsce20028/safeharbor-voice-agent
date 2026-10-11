"""SafeHarbor Insurance - AI voice agent backend (FastAPI).

ElevenLabs calls these endpoints as "server tools" during a call:
  POST /api/tools/get-quotes     -> quotes from 3 mock carriers
  POST /api/tools/select-quote   -> save the caller's chosen quote
  POST /api/tools/verify-policy  -> check policy number + date of birth
  POST /api/tools/file-claim     -> save a claim, return a claim number
And after each call:
  POST /api/webhooks/elevenlabs  -> post-call transcript + summary
Public, read-only for the landing page:
  GET  /api/health, GET /api/activity
"""

import hashlib
import hmac
import os
import sys
import time
import uuid
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))  # so sibling modules import on Vercel

from fastapi import Depends, FastAPI, Header, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import data  # noqa: E402
import retell  # noqa: E402
from carriers import get_all_quotes  # noqa: E402

TOOL_API_KEY = os.environ.get("TOOL_API_KEY", "dev-key-change-me")
WEBHOOK_SECRET = os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "")

app = FastAPI(title="SafeHarbor Voice Agent API", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


def require_api_key(x_api_key: str = Header(default=""), key: str = ""):
    """Accepts the key as an `x-api-key` header (tools) or `?key=` query param (admin)."""
    if not hmac.compare_digest(x_api_key or key, TOOL_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_policy_number(raw: str) -> str:
    """'sh 1001', 'SH1001', 'sh-1001' -> 'SH-1001'."""
    cleaned = "".join(ch for ch in raw.upper() if ch.isalnum())
    if cleaned.startswith("SH"):
        return f"SH-{cleaned[2:]}"
    return f"SH-{cleaned}" if cleaned.isdigit() else cleaned


def parse_date(raw: str) -> date | None:
    """Accepts 1988-04-12, 04/12/1988, April 12 1988, April 12, 1988, 12 April 1988."""
    text = raw.strip().replace(",", "")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Request models (field descriptions match what you enter in ElevenLabs)
# ---------------------------------------------------------------------------
class QuoteRequest(BaseModel):
    full_name: str
    email: str = ""
    zip: str = Field(min_length=3, max_length=10)
    age: int = Field(ge=16, le=100)
    car_year: int = Field(ge=1980, le=date.today().year + 1)
    car_make: str
    car_model: str
    accidents_last_3_years: int = Field(default=0, ge=0, le=10)
    coverage: str = "full"  # "full" or "liability"


class SelectQuoteRequest(BaseModel):
    quote_request_id: str
    carrier: str


class VerifyPolicyRequest(BaseModel):
    policy_number: str
    date_of_birth: str


class ClaimRequest(BaseModel):
    policy_number: str
    date_of_birth: str
    incident_date: str
    location: str
    description: str
    injuries: bool = False
    vehicle_drivable: bool = True
    police_report: bool = False
    other_party_name: str = ""
    other_party_insurer: str = ""


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "time": now_iso(), "voice_configured": bool(retell.API_KEY and retell.AGENT_ID)}


@app.get("/api/activity")
def activity():
    """Recent quotes and claims for the landing page (names shortened, no emails)."""
    snap = data.snapshot()

    def short(name: str) -> str:
        parts = name.split()
        return f"{parts[0]} {parts[-1][0]}." if len(parts) > 1 else (parts[0] if parts else "Caller")

    quotes = [
        {
            "reference": q.get("reference"),
            "name": short(q["driver"]["full_name"]),
            "car": f'{q["driver"]["car_year"]} {q["driver"]["car_make"]} {q["driver"]["car_model"]}',
            "quotes": q["quotes"],
            "selected": q.get("selected_carrier"),
            "created_at": q["created_at"],
        }
        for q in snap["quote_requests"][:10]
    ]
    claims = [
        {
            "claim_number": c["claim_number"],
            "policy_number": c["policy_number"],
            "priority": c["priority"],
            "location": c["location"],
            "created_at": c["created_at"],
        }
        for c in snap["claims"][:10]
    ]
    return {"quotes": quotes, "claims": claims}


# ---------------------------------------------------------------------------
# Tool endpoints (called by the ElevenLabs agent mid-call)
# ---------------------------------------------------------------------------
@app.post("/api/tools/get-quotes", dependencies=[Depends(require_api_key)])
async def get_quotes(req: QuoteRequest):
    driver = req.model_dump()
    driver["coverage"] = "liability" if "liab" in req.coverage.lower() else "full"
    driver["zip"] = req.zip.strip()

    quotes, failed = await get_all_quotes(driver)
    qid = f"QR-{uuid.uuid4().hex[:8].upper()}"
    data.save_quote_request(
        qid,
        {"id": qid, "driver": driver, "quotes": quotes, "failed_carriers": failed, "created_at": now_iso()},
    )

    if not quotes:
        return {
            "quote_request_id": qid,
            "quotes": [],
            "message": "No carriers responded right now. Apologize and offer a callback from a licensed agent.",
        }

    spoken = "; ".join(
        f'{q["carrier"]}: ${q["monthly_premium"]} per month with a ${q["deductible"]} deductible' for q in quotes
    )
    return {
        "quote_request_id": qid,
        "quotes": quotes,
        "message": f"Quotes, cheapest first: {spoken}. Ask which one the caller would like.",
    }


@app.post("/api/tools/select-quote", dependencies=[Depends(require_api_key)])
def select_quote(req: SelectQuoteRequest):
    record = data.get_quote_request(req.quote_request_id.strip().upper())
    if not record:
        raise HTTPException(status_code=404, detail="Quote request not found")

    chosen = next((q for q in record["quotes"] if req.carrier.lower() in q["carrier"].lower()), None)
    if not chosen:
        options = ", ".join(q["carrier"] for q in record["quotes"])
        return {"success": False, "message": f"That carrier isn't in the quotes. The options are: {options}."}

    reference = f"Q-{data.next_number('quote')}"
    record.update({"selected_carrier": chosen["carrier"], "reference": reference, "selected_at": now_iso()})
    data.save_quote_request(record["id"], record)
    return {
        "success": True,
        "reference": reference,
        "message": (
            f"Saved {chosen['carrier']} at ${chosen['monthly_premium']} per month. "
            f"Quote reference {reference}. A licensed agent will call within one business day to finalize the policy."
        ),
    }


def _check_policy(policy_number: str, date_of_birth: str) -> tuple[str, dict | None, str]:
    number = normalize_policy_number(policy_number)
    policy = data.POLICIES.get(number)
    dob = parse_date(date_of_birth)
    if not policy or not dob or policy["date_of_birth"] != dob.isoformat():
        return number, None, "We couldn't match that policy number and date of birth. Ask the caller to repeat them."
    if policy["status"] != "active":
        return number, None, "This policy is not active. Offer a callback from a licensed agent."
    return number, policy, ""


@app.post("/api/tools/verify-policy", dependencies=[Depends(require_api_key)])
def verify_policy(req: VerifyPolicyRequest):
    number, policy, error = _check_policy(req.policy_number, req.date_of_birth)
    if not policy:
        return {"verified": False, "message": error}
    first_name = policy["customer_name"].split()[0]
    return {
        "verified": True,
        "policy_number": number,
        "customer_first_name": first_name,
        "vehicle": policy["vehicle"],
        "carrier": policy["carrier"],
        "coverage": policy["coverage"],
        "message": f"Verified. Policyholder {first_name}, insured vehicle {policy['vehicle']} with {policy['carrier']}.",
    }


@app.post("/api/tools/file-claim", dependencies=[Depends(require_api_key)])
def file_claim(req: ClaimRequest):
    number, policy, error = _check_policy(req.policy_number, req.date_of_birth)
    if not policy:
        return {"success": False, "message": error}

    claim_number = f"CLM-{date.today().year}-{data.next_number('claim'):05d}"
    priority = "high" if req.injuries or not req.vehicle_drivable else "normal"
    data.save_claim(
        claim_number,
        {
            "claim_number": claim_number,
            "policy_number": number,
            "carrier": policy["carrier"],
            "vehicle": policy["vehicle"],
            **req.model_dump(exclude={"policy_number", "date_of_birth"}),
            "priority": priority,
            "status": "filed",
            "created_at": now_iso(),
        },
    )
    follow_up = "within 4 hours" if priority == "high" else "within 24 hours"
    return {
        "success": True,
        "claim_number": claim_number,
        "priority": priority,
        "message": (
            f"Claim filed. Claim number {claim_number}. An adjuster from {policy['carrier']} "
            f"will contact the caller {follow_up}."
        ),
    }


# ---------------------------------------------------------------------------
# Post-call webhook (ElevenLabs sends this after every call)
# ---------------------------------------------------------------------------
def _valid_signature(header: str, body: bytes) -> bool:
    """ElevenLabs header format: 't=<timestamp>,v0=<hmac_sha256_hex>'."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        timestamp, signature = parts["t"], parts["v0"]
    except (ValueError, KeyError):
        return False
    if abs(time.time() - int(timestamp)) > 30 * 60:
        return False
    expected = hmac.new(WEBHOOK_SECRET.encode(), f"{timestamp}.{body.decode()}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/api/webhooks/elevenlabs")
async def elevenlabs_webhook(request: Request):
    body = await request.body()
    if WEBHOOK_SECRET and not _valid_signature(request.headers.get("elevenlabs-signature", ""), body):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    d = payload.get("data", {})
    data.save_call(
        {
            "type": payload.get("type"),
            "conversation_id": d.get("conversation_id"),
            "duration_secs": (d.get("metadata") or {}).get("call_duration_secs"),
            "summary": (d.get("analysis") or {}).get("transcript_summary"),
            "successful": (d.get("analysis") or {}).get("call_successful"),
            "received_at": now_iso(),
        }
    )
    return {"received": True}


@app.get("/api/records", dependencies=[Depends(require_api_key)])
def records():
    """Full data for you (needs the x-api-key header)."""
    return data.snapshot()


# ---------------------------------------------------------------------------
# Retell voice: the browser starts calls through this proxy, so the secret
# RETELL_API_KEY never reaches the page.
# ---------------------------------------------------------------------------
_recent_calls: dict[str, list[float]] = {}
CALLS_PER_IP = 4  # per 10 minutes, to protect the free credit


@app.post("/api/retell/v3/create-web-call")
async def retell_create_web_call(request: Request):
    if not retell.API_KEY or not retell.AGENT_ID:
        raise HTTPException(status_code=503, detail="Voice agent is not configured yet")

    ip = (request.headers.get("x-forwarded-for") or "unknown").split(",")[0].strip()
    now = time.time()
    hits = [t for t in _recent_calls.get(ip, []) if now - t < 600]
    if len(hits) >= CALLS_PER_IP:
        raise HTTPException(status_code=429, detail="Too many calls from this device. Try again in a few minutes.")
    _recent_calls[ip] = hits + [now]

    # Ignore whatever agent or overrides the browser sent; always use ours.
    status, body = retell.call_api("POST", "/v3/create-web-call", {"agent_id": retell.AGENT_ID})
    if status >= 300:
        raise HTTPException(status_code=502, detail=f"Retell error {status}: {str(body)[:300]}")
    return body


@app.get("/api/admin/retell-setup", dependencies=[Depends(require_api_key)])
def retell_setup(llm_id: str = "", agent_id: str = ""):
    """One-time setup (or update) of the Retell LLM and agent. Needs ?key=TOOL_API_KEY."""
    base_url = os.environ.get("PUBLIC_BASE_URL", "https://safeharbor-voice-agent.vercel.app")
    return retell.setup(base_url, TOOL_API_KEY, llm_id or retell.LLM_ID, agent_id or retell.AGENT_ID)


@app.get("/api/admin/retell-debug", dependencies=[Depends(require_api_key)])
def retell_debug():
    """Tries to create a web call server-side and reports exactly what Retell says."""
    status, body = retell.call_api("POST", "/v3/create-web-call", {"agent_id": retell.AGENT_ID})
    if isinstance(body, dict) and "access_token" in body:
        body = {**body, "access_token": body["access_token"][:12] + "..."}
    agent_status, agent = retell.call_api("GET", f"/get-agent/{retell.AGENT_ID}")
    return {
        "create_web_call": {"status": status, "body": body},
        "agent": {"status": agent_status, "voice_id": agent.get("voice_id"), "is_published": agent.get("is_published"),
                  "version": agent.get("version"), "error": agent.get("error") or agent.get("message")},
    }
