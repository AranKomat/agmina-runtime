"""Audit retained OpenRouter generation IDs without making model inference calls."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FIELDS = (
    "id", "request_id", "provider_name", "model", "upstream_id", "created_at",
    "data_region", "finish_reason", "total_cost", "usage", "generation_time", "latency",
)


def generation_ids(ledger: Path) -> list[dict]:
    db = sqlite3.connect(ledger)
    rows = []
    for job_id, receipt in db.execute("SELECT id, receipt FROM jobs ORDER BY id"):
        value = json.loads(receipt)
        provider_id = value.get("provider_request_id")
        if provider_id:
            rows.append({"ledger": str(ledger), "job_id": job_id, "generation_id": provider_id})
    db.close()
    return rows


def fetch(base_url: str, token: str, generation_id: str) -> dict:
    url = base_url.rstrip("/") + "/generation?" + urlencode({"id": generation_id})
    request = Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            body = json.load(response)
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            return {"generation_id": generation_id, "status": "invalid_response"}
        return {"generation_id": generation_id, "status": "ok",
                **{field: data.get(field) for field in FIELDS if field in data}}
    except HTTPError as exc:
        return {"generation_id": generation_id, "status": "http_error", "http_status": exc.code}
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"generation_id": generation_id, "status": "query_error",
                "error_type": type(exc).__name__}


def audit(ledgers: tuple[Path, ...], out: Path, *, base_url: str, credential_env: str) -> dict:
    if out.exists():
        raise FileExistsError(f"Output already exists: {out}")
    token = os.environ.get(credential_env)
    if not token:
        raise ValueError(f"Missing {credential_env}")
    refs = []
    for ledger in ledgers:
        refs.extend(generation_ids(ledger))
    unique = {}
    for ref in refs:
        unique.setdefault(ref["generation_id"], ref)
    records = []
    for generation_id in sorted(unique):
        record = fetch(base_url, token, generation_id)
        record.update({k: unique[generation_id][k] for k in ("ledger", "job_id")})
        records.append(record)
    successful = [r for r in records if r["status"] == "ok"]
    providers = sorted({r.get("provider_name") for r in successful if r.get("provider_name")})
    models = sorted({r.get("model") for r in successful if r.get("model")})
    result = {
        "protocol": "R4 retained generation metadata audit",
        "ledgers": [str(path) for path in ledgers],
        "generation_ids_found": len(refs),
        "generation_ids_unique": len(records),
        "successful_metadata": len(successful),
        "failed_metadata_queries": len(records) - len(successful),
        "providers": providers,
        "models": models,
        "records": records,
        "metadata_only": True,
        "model_calls": 0,
        "native_actions": 0,
        "quality_claim": False,
    }
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--credential-env", default="OPENROUTER_API_KEY")
    args = parser.parse_args()
    print(json.dumps(audit(tuple(args.ledger), args.out, base_url=args.base_url,
                           credential_env=args.credential_env), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
