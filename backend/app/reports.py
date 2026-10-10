import re
from urllib.parse import urlsplit

from sqlalchemy import delete, select

from app.db import now, session_scope, uid
from app.models import Claim, Evidence, Run, Source
from app.schemas import ReportDraft
from app.services import public_row


def canonical_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def assess_claim(draft: dict, sources: dict[str, dict]) -> dict:
    """Conservative, reproducible provenance gates; NOT a truth probability or a calibrated classifier."""
    valid, warnings, seen = [], [], set()
    for evidence in draft.get("evidence", []):
        source = sources.get(evidence["source_id"])
        key = (evidence["source_id"], evidence["stance"])
        if key in seen:
            continue
        seen.add(key)
        if not source:
            warnings.append("引用的 source_id 不属于本次研究，已移除")
            continue
        if canonical_text(evidence["quote"]) not in canonical_text(source["excerpt"]):
            warnings.append("引文无法在保存的原文中定位，已移除")
            continue
        valid.append(evidence)
    verifying = [e for e in valid if sources[e["source_id"]]["source_type"] != "x"]
    supporting = [e for e in verifying if e["stance"] == "support"]
    contradicting = [e for e in verifying if e["stance"] == "contradict"]
    primary = [
        e for e in verifying if sources[e["source_id"]]["source_type"] in {"sec", "market", "company_ir"}
    ]
    # Unique hosts/hashes are descriptive counts, not claims that publishers are independent.
    hosts = {urlsplit(sources[e["source_id"]]["url"]).hostname for e in verifying}
    hashes = {sources[e["source_id"]]["content_hash"] for e in verifying}
    kind = draft["kind"]
    status = draft["assessment"]
    if kind in {"prediction", "opinion"}:
        status = "not_verifiable"
    elif supporting and contradicting:
        status = "conflicting"
    elif not supporting and not contradicting:
        status = "insufficient_evidence"
    elif status in {"supported", "partially_supported"} and not supporting:
        status = "insufficient_evidence"
    elif status == "contradicted" and not contradicting:
        status = "insufficient_evidence"
    elif kind == "inference" and status == "supported":
        status = "partially_supported"
    strength = "none" if not verifying else "primary_present" if primary else "secondary_only"
    return {
        **draft,
        "claim_id": uid(),
        "status": status,
        "evidence": valid,
        "evidence_strength": {
            "label": strength,
            "verifying_sources": len({e["source_id"] for e in verifying}),
            "primary_sources": len({e["source_id"] for e in primary}),
            "distinct_hosts": len(hosts),
            "distinct_content_hashes": len(hashes),
            "has_conflict": bool(supporting and contradicting),
            "rubric_version": "provenance-v1",
            "calibrated_probability": False,
        },
        "validation_warnings": warnings,
    }


async def finalize_report(run_id: str, draft: ReportDraft):
    async with session_scope() as db:
        source_rows = list(await db.scalars(select(Source).where(Source.run_id == run_id)))
        sources = {row.id: public_row(row) for row in source_rows}
        claims = [assess_claim(claim.model_dump(), sources) for claim in draft.claims]
        data = draft.model_dump(mode="json")
        data["claims"] = claims
        for direction in ("positive_factors", "negative_factors"):
            for factor in data[direction]:
                factor["source_ids"] = [
                    source_id for source_id in factor["source_ids"] if source_id in sources
                ]
                factor["evidence_status"] = "cited" if factor["source_ids"] else "unverified_inference"
        data["sources"] = list(sources.values())
        data["generated_at"] = now().isoformat()
        data["assessment_type"] = (
            "AI research synthesis; evidence links checked by code; factual entailment still requires review"
        )
        data["coverage"] = {
            "claims": len(claims),
            "sources": len(sources),
            "supported": sum(c["status"] == "supported" for c in claims),
            "conflicting": sum(c["status"] == "conflicting" for c in claims),
            "unresolved": sum(c["status"] in {"insufficient_evidence", "not_verifiable"} for c in claims),
        }
        warnings = [warning for claim in claims for warning in claim["validation_warnings"]]
        if warnings:
            data["uncertainties"] = list(dict.fromkeys(data["uncertainties"] + warnings))
        if not sources:
            data["uncertainties"].append("本次没有取得可核对的外部来源；摘要不能视为经过证实的事实。")
        # The Run.result is the only serialized report; normalized tables support filters and audit.
        await db.execute(delete(Claim).where(Claim.run_id == run_id))
        for claim in claims:
            db.add(
                Claim(
                    id=claim["claim_id"],
                    run_id=run_id,
                    text=claim["text"],
                    kind=claim["kind"],
                    status=claim["status"],
                    tickers=claim["tickers"],
                    assessment=claim,
                )
            )
            await db.flush()
            for evidence in claim["evidence"]:
                db.add(
                    Evidence(
                        claim_id=claim["claim_id"],
                        source_id=evidence["source_id"],
                        stance=evidence["stance"],
                        quote=evidence["quote"],
                        rationale=evidence["rationale"],
                    )
                )
        run = await db.get(Run, run_id)
        run.result = data
        return data
