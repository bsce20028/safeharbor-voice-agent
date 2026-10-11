"""Mock insurance carriers.

Each carrier has its own pricing rules and behaviour, like real carriers:
- Liberty Shield: fast and reliable
- Summit Mutual: slower to respond, cheaper for safe drivers
- Harborline Insurance: sometimes fails (to show error handling)

All carriers share one interface: `async quote(driver) -> dict`.
"""

import asyncio
import random
from datetime import date


def _base_premium(d: dict) -> float:
    """Shared starting price (monthly, USD) from the driver's risk factors."""
    price = 95.0 if d["coverage"] == "full" else 55.0

    age = d["age"]
    if age < 21:
        price *= 1.8
    elif age < 25:
        price *= 1.4
    elif age > 70:
        price *= 1.2

    car_age = max(0, date.today().year - d["car_year"])
    if d["coverage"] == "full":
        # newer cars cost more to repair or replace
        price *= 1.25 if car_age <= 3 else (1.0 if car_age <= 8 else 0.85)

    price *= 1 + 0.35 * min(d["accidents_last_3_years"], 3)

    # a little regional variation from the ZIP code
    zip_digit = int(d["zip"][0]) if d["zip"][:1].isdigit() else 5
    price *= 1 + (zip_digit - 5) * 0.02
    return price


class LibertyShield:
    name = "Liberty Shield"

    async def quote(self, d: dict) -> dict:
        await asyncio.sleep(0.2)
        price = _base_premium(d) * 1.05
        return {"carrier": self.name, "monthly_premium": round(price), "deductible": 500}


class SummitMutual:
    name = "Summit Mutual"

    async def quote(self, d: dict) -> dict:
        await asyncio.sleep(1.2)  # slower carrier
        price = _base_premium(d)
        price *= 0.88 if d["accidents_last_3_years"] == 0 else 1.1  # rewards clean records
        return {"carrier": self.name, "monthly_premium": round(price), "deductible": 1000}


class HarborlineInsurance:
    name = "Harborline Insurance"

    async def quote(self, d: dict) -> dict:
        await asyncio.sleep(0.6)
        if random.random() < 0.25:
            raise RuntimeError("Harborline rating service unavailable")
        price = _base_premium(d) * (0.95 if d["age"] >= 30 else 1.15)
        return {"carrier": self.name, "monthly_premium": round(price), "deductible": 750}


CARRIERS = [LibertyShield(), SummitMutual(), HarborlineInsurance()]
CARRIER_TIMEOUT_SECONDS = 3.0


async def get_all_quotes(driver: dict) -> tuple[list[dict], list[str]]:
    """Ask every carrier at the same time. Returns (quotes, failed_carrier_names)."""

    async def safe_quote(carrier):
        try:
            return await asyncio.wait_for(carrier.quote(driver), CARRIER_TIMEOUT_SECONDS)
        except Exception:
            return carrier.name  # failed or too slow

    results = await asyncio.gather(*(safe_quote(c) for c in CARRIERS))
    quotes = sorted((r for r in results if isinstance(r, dict)), key=lambda q: q["monthly_premium"])
    failed = [r for r in results if isinstance(r, str)]
    return quotes, failed
