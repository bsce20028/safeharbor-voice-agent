"""Retell AI setup and API helper (stdlib only, no extra dependencies).

Env vars:
  RETELL_API_KEY   secret key from the Retell dashboard
  RETELL_AGENT_ID  set after running /api/admin/retell-setup once
  RETELL_LLM_ID    optional, lets setup update the same LLM instead of creating one
"""

import json
import os
import urllib.error
import urllib.request

API_KEY = os.environ.get("RETELL_API_KEY", "")
AGENT_ID = os.environ.get("RETELL_AGENT_ID", "")
LLM_ID = os.environ.get("RETELL_LLM_ID", "")
BASE = "https://api.retellai.com"

BEGIN_MESSAGE = "Hi, thanks for calling SafeHarbor Insurance. Are you looking for a car insurance quote, or do you need to report a claim?"

PROMPT = 'Current date and time: {{current_time}}.\n\nYou are the friendly AI receptionist for SafeHarbor Insurance Agency, an independent car insurance agency in the US. You help with exactly two things: car insurance quotes and reporting car accident claims. Politely decline anything else.\n\nHOW YOU SPEAK\n- Everything you write is spoken aloud to the caller. Write ONLY the words you say to them.\n- Never describe your reasoning, the flow, "the next step", or what the user just did. Never repeat a sentence twice.\n- Keep every reply to one or two short sentences. Ask one question at a time.\n- Say prices as "145 dollars a month".\n\nGOLDEN RULE FOR TOOLS\n- Only use information the caller has actually said in this call. NEVER guess, invent, assume or use example values (no made-up policy numbers, dates of birth, names or ZIP codes).\n- If you are missing something a tool needs, ask for it and WAIT for the answer. Do not call the tool in the same turn as asking the question.\n\nQUOTE FLOW\n1. Ask, one at a time: full name, ZIP code, age, car year, make and model, number of accidents or tickets in the last 3 years, and full coverage or liability only. Email is optional; ask once.\n2. Read the details back in one short sentence and ask if they\'re correct.\n3. Only after the caller confirms, say "Let me check with our carriers" and call get_quotes.\n4. Read only each carrier\'s name and monthly price, cheapest first, in one sentence (skip deductibles unless asked), then ask which one they\'d like.\n5. Call select_quote with the quote_request_id from get_quotes and the carrier they chose.\n6. Give the quote reference and say a licensed agent will call within one business day to finalize. Never say the policy is active.\n\nCLAIM FLOW\n1. Ask if anyone was hurt and if everyone is safe. If someone is seriously hurt, tell them to call 911 now.\n2. Ask: "What\'s your policy number and date of birth?" Then STOP and wait for the caller to say both.\n3. Once the caller has said both, call verify_policy. Send the date of birth as YYYY-MM-DD.\n4. If verify_policy\'s message says the policy is NOT ACTIVE: tell the caller "That policy isn\'t active right now, so a licensed agent will call you back to help." Do not ask for the details again and do not file a claim.\n5. If verify_policy\'s message says it couldn\'t match the details: say "Sorry, I couldn\'t find that. Could you say your policy number and date of birth again?" If it fails a second time, apologize and say an agent will call them back.\n6. After verification, ask one at a time: when it happened, where, what happened, whether the car can be driven, whether police were called, and the other driver\'s name and insurer if there was one.\n7. Summarize the incident in one sentence and ask if it\'s correct.\n8. Call file_claim with the details, the same policy number and date of birth, and incident_date as YYYY-MM-DD (use today\'s date for "yesterday" etc.).\n9. Read the claim number slowly and give the next step from the tool\'s message. Never promise approval.\n\nIf any other tool returns "success": false, explain it in one short sentence. This is a demo with fictional data; if the caller shares sensitive details like a Social Security number, say it isn\'t needed. When the caller is done, say a short goodbye and call end_call.'


def call_api(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode() or "{}"
            return resp.status, json.loads(text)
    except urllib.error.HTTPError as e:
        text = e.read().decode()
        try:
            return e.code, json.loads(text)
        except ValueError:
            return e.code, {"error": text[:500]}


def _tool(name, description, url, key, properties, required, speak=False, message=""):
    tool = {
        "type": "custom",
        "name": name,
        "description": description,
        "url": url,
        "method": "POST",
        "headers": {"x-api-key": key},
        "parameters": {"type": "object", "properties": properties, "required": required},
        "args_at_root": True,
        "speak_during_execution": speak,
        "speak_after_execution": True,
        "timeout_ms": 15000,
    }
    if speak:
        tool["execution_message_description"] = message
    return tool


def _s(desc):
    return {"type": "string", "description": desc}


def _i(desc):
    return {"type": "integer", "description": desc}


def _b(desc):
    return {"type": "boolean", "description": desc}


def build_tools(base_url: str, key: str) -> list[dict]:
    u = base_url.rstrip("/") + "/api/tools/"
    return [
        _tool(
            "get_quotes",
            "Get car insurance quotes from three carriers. Call only after the caller has confirmed all their details.",
            u + "get-quotes", key,
            {
                "full_name": _s("Caller's full name"),
                "email": _s("Caller's email, if given"),
                "zip": _s("5-digit US ZIP code"),
                "age": _i("Driver's age in years"),
                "car_year": _i("Car model year, e.g. 2020"),
                "car_make": _s("Car make, e.g. Honda"),
                "car_model": _s("Car model, e.g. Civic"),
                "accidents_last_3_years": _i("Number of accidents or tickets in the last 3 years"),
                "coverage": {"type": "string", "enum": ["full", "liability"], "description": "Coverage type"},
            },
            ["full_name", "zip", "age", "car_year", "car_make", "car_model", "accidents_last_3_years", "coverage"],
            speak=True, message="Say briefly that you are checking with the carriers.",
        ),
        _tool(
            "select_quote", "Save the quote the caller chose.", u + "select-quote", key,
            {"quote_request_id": _s("The quote_request_id returned by get_quotes"), "carrier": _s("Carrier the caller chose")},
            ["quote_request_id", "carrier"],
        ),
        _tool(
            "verify_policy",
            "Verify the caller's policy. Only call after the caller has said BOTH their policy number and date of birth.",
            u + "verify-policy", key,
            {"policy_number": _s("Policy number the caller said, e.g. SH-1001"), "date_of_birth": _s("Date of birth the caller said, as YYYY-MM-DD")},
            ["policy_number", "date_of_birth"],
        ),
        _tool(
            "file_claim", "File an accident claim after the caller is verified and confirms the details.", u + "file-claim", key,
            {
                "policy_number": _s("Verified policy number"),
                "date_of_birth": _s("Policyholder date of birth as YYYY-MM-DD"),
                "incident_date": _s("Incident date as YYYY-MM-DD"),
                "location": _s("Where it happened"),
                "description": _s("What happened, in the caller's words"),
                "injuries": _b("True if anyone was injured"),
                "vehicle_drivable": _b("True if the car can still be driven"),
                "police_report": _b("True if police were called"),
                "other_party_name": _s("Other driver's name, if any"),
                "other_party_insurer": _s("Other driver's insurer, if any"),
            },
            ["policy_number", "date_of_birth", "incident_date", "location", "description", "injuries", "vehicle_drivable"],
        ),
        {"type": "end_call", "name": "end_call", "description": "End the call after saying goodbye, once the caller is done."},
    ]


MODELS = ["gpt-4.1-mini", "gpt-4o-mini", None]  # first one Retell accepts wins
VOICES = ["11labs-Adrian", "retell-Cimo"]


def setup(base_url: str, key: str, llm_id: str = "", agent_id: str = "") -> dict:
    if not API_KEY:
        return {"ok": False, "error": "RETELL_API_KEY is not set on Vercel"}
    llm_body = {
        "general_prompt": PROMPT,
        "begin_message": BEGIN_MESSAGE,
        "model_temperature": 0.1,
        "general_tools": build_tools(base_url, key),
    }
    errors = []
    if llm_id:
        status, res = call_api("PATCH", f"/update-retell-llm/{llm_id}", llm_body)
        if status >= 300:
            return {"ok": False, "step": "update llm", "status": status, "error": res}
    else:
        for model in MODELS:
            body = dict(llm_body, **({"model": model} if model else {}))
            status, res = call_api("POST", "/create-retell-llm", body)
            if status < 300:
                llm_id = res["llm_id"]
                break
            errors.append({"model": model, "status": status, "error": res})
        if not llm_id:
            return {"ok": False, "step": "create llm", "errors": errors}

    agent_body = {
        "agent_name": "SafeHarbor Receptionist",
        "response_engine": {"type": "retell-llm", "llm_id": llm_id},
        "language": "en-US",
        "max_call_duration_ms": 120000,
        "end_call_after_silence_ms": 20000,
    }
    if agent_id:
        status, res = call_api("PATCH", f"/update-agent/{agent_id}", agent_body)
        if status >= 300:
            return {"ok": False, "step": "update agent", "status": status, "error": res, "llm_id": llm_id}
    else:
        for voice in VOICES:
            status, res = call_api("POST", "/create-agent", dict(agent_body, voice_id=voice))
            if status < 300:
                agent_id = res["agent_id"]
                break
            errors.append({"voice": voice, "status": status, "error": res})
        if not agent_id:
            return {"ok": False, "step": "create agent", "errors": errors, "llm_id": llm_id}
    return {"ok": True, "llm_id": llm_id, "agent_id": agent_id, "notes": errors}
