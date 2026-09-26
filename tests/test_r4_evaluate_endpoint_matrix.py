import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_SPEC = spec_from_file_location(
    "r4_evaluate_endpoint_matrix",
    Path(__file__).parents[1] / "tools" / "r4_evaluate_endpoint_matrix.py",
)
_MODULE = module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MODULE)
evaluate = _MODULE.evaluate
served_model_matches_config = _MODULE.served_model_matches_config


def test_served_model_revision_matches_configured_base_name():
    assert served_model_matches_config(
        "z-ai/glm-5.3-flash-20260826", "z-ai/glm-5.3-flash"
    )
    assert served_model_matches_config("z-ai/glm-5.3-flash", "z-ai/glm-5.3-flash")
    assert not served_model_matches_config("z-ai/glm-5.3-flash-mini", "z-ai/glm-5.3-flash")


def test_evaluator_pins_revision_from_generation_audit(tmp_path):
    prep = tmp_path / "prep"
    runs = tmp_path / "runs"
    prep.mkdir()
    expected_plan = {"jobs": [{"id": "j1"}]}
    (prep / "plan.json").write_text(json.dumps(expected_plan))

    audit_records = []
    for scheduler in ("fifo", "edf", "slack"):
        root = runs / scheduler
        root.mkdir(parents=True)
        (root / "config.json").write_text(json.dumps({
            "scheduler": scheduler,
            "endpoints": [{"id": "endpoint", "model_name": "z-ai/glm-5.3-flash"}],
        }))
        (root / "plan.json").write_text(json.dumps(expected_plan))
        (root / "report.json").write_text(json.dumps({
            "offered": 1,
            "states": {"consumed": 1},
            "budget": {"attempts": 1, "unknown_attempts": 0, "held_microusd": 0,
                        "known_microusd": 1},
            "timing": {},
        }))
        audit_records.append({
            "ledger": str(root / "ledger.sqlite"),
            "job_id": "j1",
            "status": "ok",
            "provider_name": "Together",
            "model": "z-ai/glm-5.3-flash-20260826",
        })

    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"records": audit_records}))
    result = evaluate(prep, runs, tmp_path / "evaluation.json", audit)
    assert result["generation_metadata_complete"] is True
    assert result["served_provider_revision_pinned"] is True
