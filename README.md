# SafeHarbor Insurance — AI Voice Receptionist

An AI voice agent for a fictional US insurance agency. Callers talk to it from a website and can:

- **Get a car insurance quote**: the agent collects driver and car details, asks 3 mock carriers in parallel, and reads back prices cheapest first.
- **Report an accident claim**: the agent checks for injuries, verifies the policy, collects incident details, and returns a claim number.

**Live demo:** https://safeharbor-voice-agent.vercel.app

**Stack:** ElevenLabs Agents (voice) · FastAPI (business logic) · plain HTML landing page · Vercel (free hosting) · JSON data (no database yet).

## How a call works

1. The visitor clicks **Talk to SafeHarbor**; the ElevenLabs widget connects.
2. ElevenLabs handles speech-to-text, the AI reply and text-to-speech live.
3. When the agent needs data, it calls a FastAPI tool endpoint:
   - `get_quotes` → 3 carriers in parallel (3s timeout each, a failing carrier is skipped)
   - `select_quote` → saves the choice, returns a quote reference
   - `verify_policy` → checks policy number + date of birth
   - `file_claim` → saves the claim, returns a claim number and priority
4. After the call, ElevenLabs posts the transcript summary to `/api/webhooks/elevenlabs`.
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

# ElevenLabs setup

Do these after the backend is deployed, so you have your Vercel URL. Below, `https://YOUR-PROJECT.vercel.app` means your real URL. Menu names may differ slightly in the dashboard.

## 1. Create the agent

**Agents → Create agent → Blank agent.** Name it `SafeHarbor Receptionist`.

**First message:**

> Hi, thanks for calling SafeHarbor Insurance. Are you looking for a car insurance quote, or do you need to report a claim?

**System prompt:**

```
You are the friendly AI receptionist for SafeHarbor Insurance Agency, an independent car insurance agency in the US. You help with exactly two things: car insurance quotes and reporting car accident claims. Politely decline anything else.

Style: warm, calm and brief. Ask one or two questions at a time. Never read out long lists. Say prices as "145 dollars a month".

QUOTE FLOW
1. Collect: full name, email (optional), ZIP code, age, car year, make and model, number of accidents or tickets in the last 3 years, and coverage type (full coverage or liability only).
2. Read the details back in one short sentence and ask if they're correct.
3. Say "Let me check with our carriers" and call get_quotes.
4. Read the quotes from the tool's message, cheapest first, and ask which one they'd like.
5. Call select_quote with the quote_request_id from get_quotes and the carrier they chose.
6. Give them the quote reference and say a licensed agent will call within one business day to finalize. Never say the policy is active or bound.

CLAIM FLOW
1. First ask if anyone was hurt and if they are safe. If someone is seriously hurt, tell them to call 911 now, then continue only if they want to.
2. Ask for their policy number and date of birth, and call verify_policy. Send the date of birth as YYYY-MM-DD. If not verified, ask them to repeat once; if it fails again, apologize and say an agent will call them back.
3. Collect: when it happened, where, what happened in their own words, whether anyone was injured, whether the car can be driven, whether police were called, and the other driver's name and insurer if there was one.
4. Summarize the incident in one or two sentences and confirm.
5. Call file_claim with all the details (including the same policy number and date of birth).
6. Read the claim number slowly and explain the next step from the tool's message. Never promise the claim will be approved.

If a tool returns an error or "success": false, explain it simply using the tool's message. This is a demo with fictional data; if the caller shares sensitive details like a Social Security number, tell them it isn't needed.
```

**Voice:** any natural voice you like. **LLM:** pick a fast, cheap model from the list.

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
