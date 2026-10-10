import json
import re

from bs4 import BeautifulSoup

from app.providers.http import ProviderError, ProviderHTTP


class SEC:
    def __init__(self, http: ProviderHTTP):
        self.http = http

    async def request(self, url: str, *, ttl=1800, as_text=False):
        ua = self.http.settings.sec_user_agent
        if "@" not in ua:
            raise ProviderError("sec", "SEC_USER_AGENT_contact_required")
        return await self.http.get(
            "sec",
            url,
            headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"},
            ttl=ttl,
            as_text=as_text,
        )

    async def company(self, ticker: str):
        from app.schemas import normalize_ticker

        ticker = normalize_ticker(ticker)
        data = await self.request("https://www.sec.gov/files/company_tickers.json", ttl=86400)
        for row in data.values():
            if row["ticker"].upper() == ticker:
                return {"ticker": ticker, "cik": str(row["cik_str"]).zfill(10), "name": row["title"]}
        raise ProviderError("sec", "company_not_found")

    async def filings(self, ticker: str, form="", as_of=""):
        company = await self.company(ticker)
        url = f"https://data.sec.gov/submissions/CIK{company['cik']}.json"
        result = await self.request(url)
        recent = result.get("filings", {}).get("recent", {})
        rows = []
        for i, filing_form in enumerate(recent.get("form", [])):
            if form and filing_form not in {form, form + "/A"}:
                continue
            filed = recent["filingDate"][i]
            if as_of and filed > as_of:
                continue
            accession = recent["accessionNumber"][i]
            doc = recent["primaryDocument"][i]
            rows.append(
                {
                    "form": filing_form,
                    "filed": filed,
                    "report_date": recent.get("reportDate", [""] * (i + 1))[i],
                    "accession": accession,
                    "primary_document": doc,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(company['cik'])}/{accession.replace('-', '')}/{doc}",
                }
            )
            if len(rows) >= 8:
                break
        return {
            "available": True,
            "provider": "sec",
            "company": company,
            "data": rows,
            "documents": [
                {
                    "title": f"{company['name']} SEC submissions",
                    "url": url,
                    "excerpt": json.dumps(rows, ensure_ascii=False),
                    "source_type": "sec",
                    "metadata": {"cik": company["cik"], "scope": "recent_filings_not_full_archive"},
                }
            ],
        }

    async def metric(self, ticker: str, tag: str, unit="USD", as_of=""):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,160}", tag) or not re.fullmatch(r"[A-Za-z/]{1,30}", unit):
            raise ProviderError("sec", "invalid_metric")
        company = await self.company(ticker)
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{company['cik']}/us-gaap/{tag}.json"
        data = await self.request(url, ttl=3600)
        values = data.get("units", {}).get(unit, [])
        values = [row for row in values if not as_of or row.get("filed", "9999") <= as_of]
        values.sort(key=lambda row: (row.get("filed", ""), row.get("end", "")), reverse=True)
        # Keep amendments/comparative periods visible. Never equate differently timed periods.
        selected = values[:16]
        if not selected:
            raise ProviderError("sec", "metric_or_unit_unavailable")
        payload = {
            "company": company,
            "taxonomy": "us-gaap",
            "tag": tag,
            "unit": unit,
            "label": data.get("label"),
            "description": data.get("description"),
            "facts": selected,
            "scope": "standard_taxonomy_entity_wide",
            "as_of_filter": as_of or None,
        }
        return {
            "available": True,
            "provider": "sec",
            "data": payload,
            "documents": [
                {
                    "title": f"{ticker} · SEC {tag} ({unit})",
                    "url": url,
                    "excerpt": json.dumps(payload, ensure_ascii=False),
                    "source_type": "sec",
                    "published_at": selected[0].get("filed"),
                    "metadata": {"tag": tag, "unit": unit, "cik": company["cik"]},
                }
            ],
        }

    async def filing_text(self, ticker: str, form="10-K", keyword="", as_of=""):
        if form not in {"10-K", "10-Q", "8-K"}:
            raise ProviderError("sec", "unsupported_form")
        filings = await self.filings(ticker, form, as_of)
        if not filings["data"]:
            raise ProviderError("sec", "filing_not_found")
        filing = filings["data"][0]
        html = await self.request(filing["url"], ttl=86400, as_text=True)
        soup = BeautifulSoup(html, "html.parser")
        for node in soup(["script", "style", "ix:header", "noscript"]):
            node.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        offsets = [0]
        if keyword.strip():
            offsets = [
                max(0, match.start() - 350)
                for match in re.finditer(re.escape(keyword[:100]), text, flags=re.I)
            ][:5]
            if not offsets:
                return {
                    "available": True,
                    "provider": "sec",
                    "data": {"matching_passages": 0, "filing": filing},
                    "documents": [],
                }
        documents = []
        for offset in offsets[:5]:
            excerpt = text[offset : offset + 2200]
            documents.append(
                {
                    "title": f"{ticker} {filing['form']} filed {filing['filed']}",
                    "url": filing["url"],
                    "excerpt": excerpt,
                    "source_type": "sec",
                    "published_at": filing["filed"],
                    "metadata": {
                        "accession": filing["accession"],
                        "report_date": filing["report_date"],
                        "text_start": offset,
                        "text_end": offset + len(excerpt),
                        "parser": "html-whitespace-v1",
                    },
                }
            )
        return {"available": True, "provider": "sec", "data": filing, "documents": documents}
