"""Small real end-to-end check. Uses paid provider quotas. Does not auto-approve personal changes."""

import argparse
import json

import httpx
from app.config import ROOT, get_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "status"])
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()
    config = get_settings()
    headers = (
        {"Authorization": "Bearer " + config.app_auth_token.get_secret_value()}
        if config.app_auth_token.get_secret_value()
        else {}
    )
    client = httpx.Client(
        base_url=f"http://127.0.0.1:{config.app_port}/api/v1", headers=headers, timeout=30, trust_env=False
    )
    path = ROOT / ".runtime" / "live-smoke.json"
    if args.action == "start":
        response = client.post(
            "/research/runs",
            json={
                "question": "请只核对三项：NVDA 上一交易日收盘价、最新 SEC 10-Q 的提交日期、Tavily 搜索得到的 NVIDIA 官方投资者关系网页。"
                "不要额外调查财务指标或保存个人数据。按问题范围使用三个外部读取工具后生成报告，并列出确切原文证据。",
                "ticker": "NVDA",
            },
        )
        response.raise_for_status()
        run = response.json()
        path.write_text(json.dumps({"run_id": run["id"]}, indent=2), encoding="utf-8")
        print(json.dumps({"run_id": run["id"], "status": run["status"]}))
    else:
        run_id = args.run_id or json.loads(path.read_text(encoding="utf-8"))["run_id"]
        response = client.get(f"/research/runs/{run_id}")
        response.raise_for_status()
        run = response.json()
        report = run.get("result") or {}
        result = {
            "run_id": run_id,
            "status": run["status"],
            "error": run["error"],
            "usage": run["usage"],
            "source_count": len(run["sources"]),
            "report_title": report.get("title"),
            "coverage": report.get("coverage"),
            "citation_warnings": [
                warning
                for claim in report.get("claims", [])
                for warning in claim.get("validation_warnings", [])
            ],
        }
        print(json.dumps(result, ensure_ascii=True))
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
