# SafeHarbor Insurance — AI Voice Receptionist

An AI voice agent for a fictional US insurance agency. Callers talk to it from a website and can:

- **Get a car insurance quote**: the agent collects driver and car details, asks 3 mock carriers in parallel, and reads back prices cheapest first.
- **Report an accident claim**: the agent checks for injuries, verifies the policy, collects incident details, and returns a claim number.

**Live demo:** https://safeharbor-voice-agent.vercel.app

**Stack:** Retell AI (voice) · FastAPI (business logic) · plain HTML landing page · Vercel (free hosting) · JSON data (no database yet).

## How a call works

1. The visitor clicks **Talk to SafeHarbor**. The page asks the backend to start a Retell web call (`/api/retell/v3/create-web-call`), so the secret key stays on the server.
2. Retell handles speech-to-text, the AI reply and text-to-speech live over WebRTC.
3. When the agent needs data, it calls a FastAPI tool endpoint:
   - `get_quotes` → 3 carriers in parallel (3s timeout each, a failing carrier is skipped)
   - `select_quote` → saves the choice, returns a quote reference
   - `verify_policy` → checks policy number + date of birth
   - `file_claim` → saves the claim, returns a claim number and priority
5. The landing page's **Live activity** panel shows recent quotes and claims.

## Project layout

```
index.html          landing page + ElevenLabs widget
api/index.py        FastAPI app (all endpoints)
api/carriers.py     3 mock carriers with their own pricing rules
api/data.py         seed policies + JSON store for quotes/claims
vercel.json         routes /api/* to FastAPI
requirements.txt
```

## Run locally

```bash
pip install fastapi "uvicorn[standard]"
TOOL_API_KEY=dev-key uvicorn api.index:app --reload
# open http://localhost:8000/docs to try every endpoint
```

Test a quote:

```bash
curl -X POST localhost:8000/api/tools/get-quotes \
  -H "x-api-key: dev-key" -H "Content-Type: application/json" \
  -d '{"full_name":"Ali Khan","zip":"90210","age":28,"car_year":2020,"car_make":"Honda","car_model":"Civic","accidents_last_3_years":0,"coverage":"full"}'
```

## Deploy to Vercel (free)

1. Push this folder to a GitHub repo.
2. On vercel.com: **Add New → Project**, import the repo, keep the default settings.
3. Under **Settings → Environment Variables**, add `TOOL_API_KEY` (a long random string).
4. Deploy. Check `https://YOUR-PROJECT.vercel.app/api/health` returns `{"status":"ok"}`.

**Data note:** quotes and claims are stored in memory and `/tmp`, which Vercel clears when the function restarts. That's fine for a demo; the next step is swapping `api/data.py` for Supabase.

## Test policies (for claim calls)

| Policy | Name | Date of birth | Status |
|---|---|---|---|
| SH-1001 | John Carter | 1988-04-12 | Active |
| SH-1002 | Emily Davis | 1995-09-03 | Active |
| SH-1003 | Michael Brown | 1979-01-25 | Active |
| SH-1004 | Sarah Wilson | 2001-06-30 | Lapsed |

---

# Retell setup (automatic)

1. On Vercel, add the env var `RETELL_API_KEY` (secret key from the Retell dashboard) and redeploy.
2. Open `https://YOUR-PROJECT.vercel.app/api/admin/retell-setup?key=YOUR_TOOL_API_KEY`. It creates the Retell LLM (prompt + 4 tools + end call) and the agent, and returns their IDs.
3. Add `RETELL_AGENT_ID` and `RETELL_LLM_ID` on Vercel with those IDs and redeploy. `/api/health` should show `"voice_configured": true`.
4. To change the prompt or tools later, edit `api/retell.py`, deploy, and open the setup URL again: it updates the same agent.

Calls are limited to 2 minutes and 4 calls per device per 10 minutes, to protect the free credit.

---

# Alternative: ElevenLabs setup (manual)


Do these after the backend is deployed, so you have your Vercel URL. Below, `https://YOUR-PROJECT.vercel.app` means your real URL. Menu names may differ slightly in the dashboard.

## 1. Create the agent

**Agents → Create agent → Blank agent.** Name it `SafeHarbor Receptionist`.

**First message:**

> Hi, thanks for calling SafeHarbor Insurance. Are you looking for a car insurance quote, or do you need to report a claim?

**System prompt:**

```
You are the friendly AI receptionist for SafeHarbor Insurance Agency, an independent car insurance agency in the US. You help with exactly two things: car insurance quotes and reporting car accident claims. Politely decline anything else.

HOW YOU SPEAK
- Everything you write is spoken aloud to the caller. Write ONLY the words you say to them.
- Never describe your reasoning, the flow, "the next step", or what the user just did. Never repeat a sentence twice.
- Keep every reply to one or two short sentences. Ask one question at a time.
- Say prices as "145 dollars a month".

GOLDEN RULE FOR TOOLS
- Only use information the caller has actually said in this call. NEVER guess, invent, assume or use example values (no made-up policy numbers, dates of birth, names or ZIP codes).
- If you are missing something a tool needs, ask for it and WAIT for the answer. Do not call the tool in the same turn as asking the question.

QUOTE FLOW
1. Ask, one at a time: full name, ZIP code, age, car year, make and model, number of accidents or tickets in the last 3 years, and full coverage or liability only. Email is optional; ask once.
2. Read the details back in one short sentence and ask if they're correct.
3. Only after the caller confirms, say "Let me check with our carriers" and call get_quotes.
4. Read only each carrier's name and monthly price, cheapest first, in one sentence (skip deductibles unless asked), then ask which one they'd like.
5. Call select_quote with the quote_request_id from get_quotes and the carrier they chose.
6. Give the quote reference and say a licensed agent will call within one business day to finalize. Never say the policy is active.

CLAIM FLOW
1. Ask if anyone was hurt and if everyone is safe. If someone is seriously hurt, tell them to call 911 now.
2. Ask: "What's your policy number and date of birth?" Then STOP and wait for the caller to say both.
3. Once the caller has said both, call verify_policy. Send the date of birth as YYYY-MM-DD.
4. If verify_policy's message says the policy is NOT ACTIVE: tell the caller "That policy isn't active right now, so a licensed agent will call you back to help." Do not ask for the details again and do not file a claim.
5. If verify_policy's message says it couldn't match the details: say "Sorry, I couldn't find that. Could you say your policy number and date of birth again?" If it fails a second time, apologize and say an agent will call them back.
6. After verification, ask one at a time: when it happened, where, what happened, whether the car can be driven, whether police were called, and the other driver's name and insurer if there was one.
7. Summarize the incident in one sentence and ask if it's correct.
8. Call file_claim with the details, the same policy number and date of birth, and incident_date as YYYY-MM-DD (use today's date for "yesterday" etc.).
9. Read the claim number slowly and give the next step from the tool's message. Never promise approval.

If any other tool returns "success": false, explain it in one short sentence. This is a demo with fictional data; if the caller shares sensitive details like a Social Security number, say it isn't needed. When the caller is done, say a short goodbye and end the call.
```

**Voice:** any natural voice you like. **LLM:** Gemini 2.5 Flash with thinking turned off (thinking budget 0) and temperature 0.1, so the agent never reads its reasoning aloud.

**Max conversation duration:** `120` seconds (in the agent's advanced/call settings). This keeps the free 15 minutes lasting for about 7 calls.

## 2. Add the 4 tools

On the agent, go to **Tools → Add tool → Webhook**. Create each one with:

- **Method:** `POST`
- **Headers:** `x-api-key` = the same value as `TOOL_API_KEY` on Vercel
- **Body parameters:** as listed below (type and description). Mark "required" as shown.

### Tool 1: `get_quotes`
- **Description:** Get car insurance quotes from three carriers. Call only after the caller confirms their details.
- **URL:** `https://YOUR-PROJECT.vercel.app/api/tools/get-quotes`

| Parameter | Type | Required | Description |
|---|---|---|---|
| full_name | string | yes | Caller's full name |
| email | string | no | Caller's email address |
| zip | string | yes | Caller's 5-digit US ZIP code |
| age | integer | yes | Driver's age in years |
| car_year | integer | yes | Car model year, e.g. 2020 |
| car_make | string | yes | Car make, e.g. Honda |
| car_model | string | yes | Car model, e.g. Civic |
| accidents_last_3_years | integer | yes | Number of accidents or tickets in the last 3 years |
| coverage | string | yes | Either "full" or "liability" |

### Tool 2: `select_quote`
- **Description:** Save the quote the caller chose.
- **URL:** `https://YOUR-PROJECT.vercel.app/api/tools/select-quote`

| Parameter | Type | Required | Description |
|---|---|---|---|
| quote_request_id | string | yes | The quote_request_id returned by get_quotes |
| carrier | string | yes | Name of the carrier the caller chose |

### Tool 3: `verify_policy`
- **Description:** Verify the caller's policy before taking a claim.
- **URL:** `https://YOUR-PROJECT.vercel.app/api/tools/verify-policy`

| Parameter | Type | Required | Description |
|---|---|---|---|
| policy_number | string | yes | Policy number, e.g. SH-1001 |
| date_of_birth | string | yes | Policyholder's date of birth as YYYY-MM-DD |

### Tool 4: `file_claim`
- **Description:** File an accident claim after the caller is verified and confirms the details.
- **URL:** `https://YOUR-PROJECT.vercel.app/api/tools/file-claim`

| Parameter | Type | Required | Description |
|---|---|---|---|
| policy_number | string | yes | Verified policy number |
| date_of_birth | string | yes | Policyholder's date of birth as YYYY-MM-DD |
| incident_date | string | yes | When the incident happened |
| location | string | yes | Where it happened |
| description | string | yes | What happened, in the caller's words |
| injuries | boolean | yes | True if anyone was injured |
| vehicle_drivable | boolean | yes | True if the car can still be driven |
| police_report | boolean | no | True if police were called |
| other_party_name | string | no | Other driver's name, if any |
| other_party_insurer | string | no | Other driver's insurance company, if any |

## 3. Post-call webhook (optional)

In the ElevenLabs settings for webhooks, add a **post-call** webhook pointing to `https://YOUR-PROJECT.vercel.app/api/webhooks/elevenlabs`. If it gives you a signing secret, add it on Vercel as `ELEVENLABS_WEBHOOK_SECRET` and redeploy.

## 4. Test without spending voice minutes

Use the agent's **text test** mode in the dashboard. Try both flows, including a wrong date of birth and the lapsed policy `SH-1004`. Fix the prompt until it works every time.

## 5. Put the widget on the site

1. In the agent's **Widget** tab, make sure the agent is public (no authentication needed).
2. Copy the **Agent ID**.
3. In `index.html`, replace `YOUR_AGENT_ID` with it (or paste the whole embed code the Widget tab shows).
4. Push to GitHub; Vercel redeploys automatically.
5. Under the agent's security settings, add your Vercel domain to the allowed domains, if that option is shown.

Then open your site, click **Talk to SafeHarbor**, and do one real voice test of each flow.
