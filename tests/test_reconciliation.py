import json

import pytest

from agmina_runtime.reconciliation import load_records, preflight, reconcile_file
from agmina_runtime.runtime import Runtime
from conftest import make_job


def _ledger(cfg, tmp_path, clock):
    runtime = Runtime(cfg, tmp_path / "db", clock=clock)
    session = runtime.open_session("s", "t")
    for jid in ("j1", "j2"):
        job = make_job(session, clock.now_ns(), id=jid)
        runtime.submit(job)
        runtime.store.reserve(job, cfg.endpoints[0], clock.now_ns())
        runtime.store.settle(job, None)
    return runtime


def test_load_json_and_jsonl_rejects_duplicates(tmp_path):
    value = {"job_id": "j1", "actual_microusd": 4, "evidence_ref": "provider:gen-1"}
    path = tmp_path / "charges.json"
    path.write_text(json.dumps({"records": [value]}))
    assert load_records(path) == (("j1", 4, "provider:gen-1"),)
    path.write_text(json.dumps(value) + "\n" + json.dumps(value) + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_records(path)


def test_dry_run_does_not_write_and_apply_is_atomic(cfg, tmp_path, clock):
    runtime = _ledger(cfg, tmp_path, clock)
    path = tmp_path / "charges.jsonl"
    path.write_text("\n".join(json.dumps({"job_id": jid, "actual_microusd": charge,
                                             "evidence_ref": f"export:{jid}"})
                             for jid, charge in (("j1", 3), ("j2", 0))) + "\n")
    dry = reconcile_file(runtime.store, cfg.tenant, path, apply=False, now_ns=clock.now_ns())
    assert dry["mode"] == "dry-run"
    assert runtime.store.budget()["unknown_attempts"] == 2
    applied = reconcile_file(runtime.store, cfg.tenant, path, apply=True, now_ns=clock.now_ns())
    assert applied["mode"] == "apply"
    assert runtime.store.budget()["known_microusd"] == 3
    assert runtime.store.budget()["unknown_attempts"] == 0
    assert len([e for e in runtime.store.export_events() if e["kind"] == "charge_reconciled"]) == 2
    runtime.store.close()


def test_preflight_rejects_unknown_and_already_settled(cfg, tmp_path, clock):
    runtime = _ledger(cfg, tmp_path, clock)
    with pytest.raises(ValueError, match="Unknown"):
        preflight(runtime.store, cfg.tenant, (("missing", 1, "export:x"),))
    runtime.store.reconcile(cfg.tenant, "j1", 2, "export:j1", clock.now_ns())
    with pytest.raises(ValueError, match="already settled"):
        preflight(runtime.store, cfg.tenant, (("j1", 2, "export:j1-again"),))
    runtime.store.close()
