import asyncio
import hashlib
import json
import time
from contextvars import ContextVar
from datetime import timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import now, session_scope
from app.models import ProviderCache, RateSlot
from app.services import increment_usage

current_run: ContextVar[str | None] = ContextVar("current_run", default=None)


class ProviderError(Exception):
    def __init__(self, provider: str, code: str, *, retryable=False, http_status=None):
        self.provider, self.code, self.retryable, self.http_status = provider, code, retryable, http_status
        # Never include request URLs, response bodies, authorization headers, or credentials.
        super().__init__(f"{provider}: {code}" + (f" (HTTP {http_status})" if http_status else ""))

    def result(self):
        return {
            "available": False,
            "provider": self.provider,
            "reason": self.code,
            "http_status": self.http_status,
            "retryable": self.retryable,
            "documents": [],
        }


async def throttle(provider: str, interval: float):
    async with session_scope() as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "rate:" + provider})
        slot = await db.get(RateSlot, provider)
        timestamp = time.time()
        start = max(timestamp, slot.next_at if slot else 0)
        if slot:
            slot.next_at = start + interval
        else:
            db.add(RateSlot(provider=provider, next_at=start + interval))
    await asyncio.sleep(max(0, start - time.time()))


class ProviderHTTP:
    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(
            timeout=self.settings.http_timeout_seconds,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    async def close(self):
        await self.client.aclose()

    async def get(self, provider: str, url: str, *, params=None, headers=None, ttl=0, as_text=False):
        cache_key = hashlib.sha256(json.dumps([provider, url, params], sort_keys=True).encode()).hexdigest()
        if ttl:
            async with session_scope() as db:
                cached = await db.get(ProviderCache, cache_key)
                if cached and cached.expires_at > now():
                    return cached.data["value"]
        for attempt in range(3):
            run_id = current_run.get()
            if run_id:
                await increment_usage(run_id, "external_requests", 1, self.settings.max_external_requests)
            interval = (
                60 / self.settings.massive_requests_per_minute
                if provider == "massive"
                else 0.2
                if provider == "sec"
                else 0.1
            )
            await throttle(provider, interval)
            try:
                response = await self.client.get(url, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
                    continue
                raise ProviderError(provider, "network_unavailable", retryable=True) from None
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                try:
                    delay = float(response.headers.get("retry-after", 2 ** (attempt + 1)))
                    if response.headers.get("x-rate-limit-reset"):
                        delay = max(delay, float(response.headers["x-rate-limit-reset"]) - time.time())
                except ValueError:
                    delay = 4
                if delay > 30:
                    raise ProviderError(
                        provider, "rate_limited", retryable=True, http_status=response.status_code
                    )
                await asyncio.sleep(max(1, delay))
                continue
            if response.status_code >= 400:
                code = {
                    401: "invalid_credentials",
                    402: "quota_or_payment_required",
                    403: "not_entitled_or_forbidden",
                    404: "not_found",
                    429: "rate_limited",
                }.get(response.status_code, "upstream_error")
                raise ProviderError(
                    provider,
                    code,
                    retryable=response.status_code >= 500 or response.status_code == 429,
                    http_status=response.status_code,
                )
            if 300 <= response.status_code < 400:
                raise ProviderError(provider, "unexpected_redirect", http_status=response.status_code)
            if len(response.content) > 35_000_000:
                raise ProviderError(provider, "response_too_large")
            try:
                data = response.text if as_text else response.json()
            except ValueError:
                raise ProviderError(provider, "invalid_json") from None
            if ttl:
                async with session_scope() as db:
                    await db.execute(
                        insert(ProviderCache)
                        .values(
                            key=cache_key, data={"value": data}, expires_at=now() + timedelta(seconds=ttl)
                        )
                        .on_conflict_do_update(
                            index_elements=[ProviderCache.key],
                            set_={"data": {"value": data}, "expires_at": now() + timedelta(seconds=ttl)},
                        )
                    )
            return data
        raise ProviderError(provider, "retry_exhausted")
