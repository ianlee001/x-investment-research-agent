import json
from datetime import UTC, date, datetime
from urllib.parse import quote

from app.providers.http import ProviderError, ProviderHTTP
from app.schemas import normalize_ticker


class Massive:
    """Fixed REST routes keep credentials and arbitrary API paths out of model control."""

    def __init__(self, http: ProviderHTTP):
        self.http = http

    async def request(self, path: str, params=None, ttl=300):
        key = self.http.settings.massive_api_key.get_secret_value()
        if not key:
            raise ProviderError("massive", "not_configured")
        return await self.http.get(
            "massive",
            "https://api.massive.com" + path,
            params=params,
            headers={"Authorization": "Bearer " + key},
            ttl=ttl,
        )

    async def quote(self, ticker: str):
        ticker = normalize_ticker(ticker)
        data = await self.request(f"/v2/aggs/ticker/{quote(ticker)}/prev", {"adjusted": "true"}, ttl=600)
        rows = data.get("results", [])
        if not rows:
            raise ProviderError("massive", "no_data")
        row = rows[0]
        bar_time = datetime.fromtimestamp(row["t"] / 1000, UTC).isoformat()
        result = {
            "ticker": ticker,
            "close": row["c"],
            "open": row["o"],
            "high": row["h"],
            "low": row["l"],
            "volume": row["v"],
            "currency": "USD",
            "as_of": bar_time,
            "session_date": bar_time[:10],
            "price_type": "previous_session_close",
            "adjusted": True,
            "intraday_change_percent": round((row["c"] / row["o"] - 1) * 100, 3) if row["o"] else None,
            "change_basis": "close_vs_same_session_open",
            "is_realtime": False,
        }
        return self.result(ticker, result, f"https://api.massive.com/v2/aggs/ticker/{ticker}/prev", bar_time)

    async def history(self, ticker: str, start: str, end: str):
        ticker = normalize_ticker(ticker)
        try:
            begin, finish = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError:
            raise ProviderError("massive", "invalid_date") from None
        if finish < begin or (finish - begin).days > 730 or finish > date.today():
            raise ProviderError("massive", "date_range_must_be_past_and_at_most_730_days")
        path = f"/v2/aggs/ticker/{quote(ticker)}/range/1/day/{begin}/{finish}"
        data = await self.request(path, {"adjusted": "true", "sort": "asc", "limit": 5000}, ttl=1800)
        bars = data.get("results", [])
        if not bars:
            raise ProviderError("massive", "no_data")
        payload = {
            "ticker": ticker,
            "start": start,
            "end": end,
            "timespan": "day",
            "adjusted": True,
            "currency": "USD",
            "bars": bars,
            "is_realtime": False,
        }
        # A bounded summary for the model; the frontend retains the full daily bar series.
        summary = {
            **payload,
            "bars": bars[-30:],
            "total_bars": len(bars),
            "period_return_percent": round((bars[-1]["c"] / bars[0]["c"] - 1) * 100, 4),
        }
        result = self.result(ticker, summary, "https://api.massive.com" + path, end)
        result["data"] = payload
        return result

    async def profile(self, ticker: str):
        ticker = normalize_ticker(ticker)
        path = f"/v3/reference/tickers/{quote(ticker)}"
        data = await self.request(path, ttl=86400)
        raw = data.get("results", {})
        if not raw:
            raise ProviderError("massive", "no_data")
        allowed = [
            "ticker",
            "name",
            "market",
            "locale",
            "primary_exchange",
            "type",
            "active",
            "currency_name",
            "cik",
            "market_cap",
            "description",
            "homepage_url",
            "total_employees",
            "list_date",
            "last_updated_utc",
        ]
        profile = {key: raw[key] for key in allowed if key in raw}
        return self.result(ticker, profile, "https://api.massive.com" + path, profile.get("last_updated_utc"))

    def result(self, ticker, data, url, published):
        return {
            "available": True,
            "provider": "massive",
            "data": data,
            "documents": [
                {
                    "title": f"Massive · {ticker}",
                    "url": url,
                    "excerpt": json.dumps(data, ensure_ascii=False),
                    "source_type": "market",
                    "published_at": published,
                    "metadata": {
                        "is_realtime": False,
                        "adjusted": True,
                        "entitlement": "actual API response",
                    },
                }
            ],
        }
