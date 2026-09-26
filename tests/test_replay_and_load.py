import json

import pytest

from agmina_runtime.contracts import ResultKind
from agmina_runtime.load import LoadItem, LoadPlan, run_load
from agmina_runtime.replay import ReplayRequest, Trace, replay, synthetic_trace
from agmina_runtime.scheduling import Candidate, rank
from agmina_runtime.telemetry import percentile


@pytest.mark.parametrize("seed",range(10))
def test_replay_causal_complete_deterministic(seed):
    trace=synthetic_trace(seed=seed,seconds=2,robots=2,cameras=3,profile_error=True)
    for mode in ("fifo","edf","slack"):
        r=replay(trace,mode)
        assert r==replay(trace,mode)
        assert len(r["records"])==len(trace.requests)
        assert r["physical_task_success"] is None and r["gpu_speedup"] is None
        intervals=[]
        for row in r["records"]:
            if row["started_ns"] is not None:
                assert row["started_ns"]>=row["release_ns"]
                assert row["completed_ns"]>row["started_ns"]
                intervals.append((row["started_ns"],row["completed_ns"]))
            assert row["state"] in {"completed_in_time","completed_late","expired_before_dispatch"}
        intervals.sort()
        assert all(intervals[i][1]<=intervals[i+1][0] for i in range(len(intervals)-1))
        assert sum(g["offered"] for g in r["by_workload"].values())==len(trace.requests)


def test_fifo_edf_differ_only_order():
    a=Candidate("a",0,100,10,1)
    b=Candidate("b",1,30,10,1)
    assert rank(a,1,"fifo")<rank(b,1,"fifo")
    assert rank(b,1,"edf")<rank(a,1,"edf")


def test_nonpreemption_negative_control():
    def row(id,at,deadline,service):
        return ReplayRequest(id=id,session=id,workload=id,release_ns=at,capture_ns=at,
                             deadline_ns=deadline,profile_ns=service,service_ns=service,priority=1,
                             max_age_ns=deadline-at)
    t=Trace(provenance="synthetic negative control",synthetic=True,duration_ns=100,requests=(
        row("background",0,100,50),row("urgent",1,20,10)))
    for mode in ("fifo","edf","slack"):
        r=replay(t,mode)
        assert r["records"][1]["state"]=="expired_before_dispatch"


def test_percentiles_are_descriptive():
    assert percentile([], .95) is None
    assert percentile([1,2,3], .95)==3


async def test_load_clock_continues(tmp_path,cfg):
    items=tuple(LoadItem(id=f"j{i}",session="video",model="model",workload="semantic",
        release_ms=i*2,deadline_after_ms=1000,evidence_hashes=("0"*64,),
        payload_json='{"fixture_delay_s":0.015}') for i in range(4))
    plan=LoadPlan(provenance="synthetic request arrival test",synthetic_inputs=True,jobs=items)
    out=tmp_path/"load"
    report=await run_load(cfg,plan,out)
    assert report["offered"]==4 and report["source_clock_continues"]
    events=[json.loads(x) for x in (out/"trace.jsonl").read_text().splitlines()]
    submissions=[x["at_ns"] for x in events if x["kind"]=="submitted"]
    # This is a causal-arrival check, not a latency SLO.  Shared CI runners can
    # pause the event loop well beyond the 150 ms local-development margin.
    assert max(submissions)-min(submissions)<500_000_000
    assert report["states"]["consumed"]==4
    with pytest.raises(FileExistsError):
        await run_load(cfg,plan,out)


async def test_load_historical_cache_control_reuses_stable_evidence(tmp_path, cfg):
    cached_cfg = cfg.model_copy(update={"cache_entries": 8})
    items = tuple(LoadItem(
        id=job_id, session="video", model="model", workload="semantic", release_ms=release_ms,
        deadline_after_ms=1000, result_kind=ResultKind.HISTORICAL, evidence_hashes=("0" * 64,),
        observation_ids=("camera-frame-0",), cacheable=True,
        payload_json='{"fixture_delay_s":0.001}')
        for job_id, release_ms in (("first", 0), ("duplicate", 0)))
    plan = LoadPlan(provenance="historical cache ablation", synthetic_inputs=True, jobs=items)
    report = await run_load(cached_cfg, plan, tmp_path / "cache")
    assert report["states"]["consumed"] == 2
    assert report["cache_hits"] == 1


def test_load_rejects_unsafe_ablation_controls():
    common = dict(id="job", session="video", model="model", workload="semantic", release_ms=0,
                  deadline_after_ms=1000, evidence_hashes=("0" * 64,), payload_json="{}")
    with pytest.raises(ValueError, match="replace_key"):
        LoadItem(**common, replace_key="latest")
    with pytest.raises(ValueError, match="Policy"):
        LoadItem(**{**common, "workload": "policy"}, discardable=True)
    with pytest.raises(ValueError, match="observation_ids"):
        LoadItem(**common, observation_ids=("a", "b"))


async def test_load_injected_transport_loss_quarantines_mock_pool(tmp_path, cfg):
    item = LoadItem(id="loss", session="video", model="model", workload="semantic", release_ms=0,
                    deadline_after_ms=1000, evidence_hashes=("0" * 64,),
                    payload_json='{"fixture_unknown":true}')
    plan = LoadPlan(provenance="injected transport-loss control", synthetic_inputs=True, jobs=(item,))
    report = await run_load(cfg, plan, tmp_path / "loss")
    assert report["states"] == {"unknown": 1}
    assert report["budget"]["unknown_attempts"] == 1
    assert report["quarantined_pools"] == ["gpu"]
