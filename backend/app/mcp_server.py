from fastmcp import FastMCP

from app.providers.http import ProviderError, ProviderHTTP
from app.providers.massive import Massive
from app.providers.sec import SEC
from app.providers.x import XProvider
from app.x_sync import store_posts, tracked_posts


def build_server(http: ProviderHTTP) -> FastMCP:
    server = FastMCP("X Investment Research", mask_error_details=True)
    market, sec, x = Massive(http), SEC(http), XProvider(http)

    async def guarded(awaitable):
        try:
            return await awaitable
        except ProviderError as error:
            return error.result()

    @server.tool()
    async def market_get_quote(ticker: str) -> dict:
        """Massive previous trading session OHLCV. EOD, USD, adjusted; NOT a realtime quote. Includes exact as_of."""
        return await guarded(market.quote(ticker))

    @server.tool()
    async def market_get_price_history(ticker: str, start: str, end: str) -> dict:
        """Massive adjusted daily bars, YYYY-MM-DD inclusive, max 730 calendar days. Respect plan access errors."""
        result = await guarded(market.history(ticker, start, end))
        if result.get("available"):
            result["data"] = {key: value for key, value in result["data"].items() if key != "bars"}
        return result

    @server.tool()
    async def market_get_company_profile(ticker: str) -> dict:
        """Massive company name, CIK, exchange and available market cap. Missing metrics remain unknown."""
        return await guarded(market.profile(ticker))

    @server.tool()
    async def sec_get_recent_filings(ticker: str, form: str = "", as_of: str = "") -> dict:
        """SEC official filing metadata (recent submissions). Optional 10-K/10-Q/8-K filter; as_of is filing-date cutoff."""
        return await guarded(sec.filings(ticker, form, as_of))

    @server.tool()
    async def sec_get_company_metric(ticker: str, tag: str, unit: str = "USD", as_of: str = "") -> dict:
        """SEC US-GAAP concept facts, e.g. Revenues, NetIncomeLoss, Assets, PaymentsToAcquirePropertyPlantAndEquipment. Preserve unit/start/end/filed/form/accession. Total capital expenditure is NOT AI capex. Custom tags may be unavailable."""
        return await guarded(sec.metric(ticker, tag, unit, as_of))

    @server.tool()
    async def sec_read_filing(ticker: str, form: str = "10-K", keyword: str = "", as_of: str = "") -> dict:
        """Read bounded passages from the latest official SEC 10-K,10-Q,8-K. Keyword matches literal text. No RAG or embeddings."""
        return await guarded(sec.filing_text(ticker, form, keyword, as_of))

    @server.tool()
    async def x_get_tracked_posts(ticker: str = "", username: str = "", limit: int = 10) -> dict:
        """Read recently checked local X posts. Social claims are leads, never independent verification. Empty means no tracked matching posts."""
        return await tracked_posts(ticker.upper(), username, limit)

    @server.tool()
    async def x_get_post(post_id: str) -> dict:
        """Read a specific public X post by ID; supports long note text. A social post proves only that the author said it."""
        try:
            response = await x.get_posts([post_id])
            rows = x.normalize(response)
            await store_posts(rows)
            return {"available": bool(rows), "provider": "x", "documents": [x.document(row) for row in rows]}
        except ProviderError as error:
            return error.result()

    @server.tool()
    async def x_search_posts(query: str) -> dict:
        """Search recent 7-day X posts, only when explicitly enabled in settings. Does not search the full archive."""
        try:
            response = await x.search(query)
            rows = x.normalize(response)
            await store_posts(rows)
            return {"available": True, "provider": "x", "documents": [x.document(row) for row in rows]}
        except ProviderError as error:
            return error.result()

    return server
