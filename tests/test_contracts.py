import pytest
from pydantic import ValidationError

from agmina_runtime.clocks import ClockMap
from agmina_runtime.config import Endpoint, RuntimeConfig
from agmina_runtime.contracts import Job, ModelContract, ResultKind, Usage, strict_json
from conftest import make_job


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}',
                                     '[]', 'null', 'broken', '{"x":'+'['*34+'0'+']'*34+'}'])
def test_strict_json_rejections(text):
    with pytest.raises(ValueError):
        strict_json(text)


def test_json_byte_bound():
    with pytest.raises(ValueError):
        strict_json('{"x":"long"}', max_bytes=5)


@pytest.mark.parametrize("changes", [
    {"deadline_ns": 1}, {"epoch": -1}, {"epoch": True}, {"priority": 9},
    {"clock_id": ""}, {"max_age_ns": None}, {"replace_key": "a"}, {"cacheable": True},
    {"workload": "policy", "discardable": True}, {"allowed_sites": ()},
    {"dependencies": ("j1",)}, {"payload_json": '{"x":NaN}'}, {"unknown_field": 1},
])
def test_job_validation(session, clock, changes):
    with pytest.raises((ValueError, ValidationError)):
        make_job(session, clock.now_ns(), **changes)


def test_historical_allows_old_context(session, clock):
    j = make_job(session, clock.now_ns(), result_kind=ResultKind.HISTORICAL, max_age_ns=None, cacheable=True)
    assert Job.model_validate_json(j.model_dump_json()) == j


def test_context_not_age_authority(session, clock):
    j = make_job(session, clock.now_ns())
    old = j.observations[0].model_copy(update={"id": "history", "capture_ns": 0, "available_ns": 1,
                                             "role": "context"})
    j = make_job(session, clock.now_ns(), observations=j.observations+(old,))
    assert j.latest_ns(session) == j.deadline_ns


def test_old_current_view_controls_age(session, clock):
    j = make_job(session, clock.now_ns())
    old = j.observations[0].model_copy(update={"id": "older", "capture_ns": clock.now_ns()-500_000_000})
    j = make_job(session, clock.now_ns(), observations=j.observations+(old,))
    assert j.latest_ns(session) == clock.now_ns()+500_000_000


def test_clock_uncertainty_consumes_age(session, clock):
    j = make_job(session, clock.now_ns())
    o = j.observations[0].model_copy(update={"uncertainty_ns": 1000})
    j = make_job(session, clock.now_ns(), observations=(o,), max_uncertainty_ns=1000)
    assert j.latest_ns(session) == j.deadline_ns-1000


def test_unavailable_observation(session, clock):
    j = make_job(session, clock.now_ns())
    with pytest.raises(ValueError):
        make_job(session, clock.now_ns(), observations=(j.observations[0].model_copy(
            update={"available_ns": clock.now_ns()+1}),))


@pytest.mark.parametrize("changes", [{"input_tokens": 1, "cached_input_tokens": 2},
    {"reasoning_output_tokens": 1}, {"output_tokens": 5, "reasoning_output_tokens": 6},
    {"cost_microusd": -1}, {"input_tokens": 1.5}, {"input_tokens": True}])
def test_usage_invariants(changes):
    with pytest.raises(ValueError):
        Usage(**changes)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://some-cloud/api", "https://u:p@host/api",
                                 "https://host/api?api_key=x", "https://host/api#fragment"])
def test_endpoint_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        Endpoint(id="e", model="m", pool="p", site="cloud", kind="chat", url=url)


def test_paid_endpoint_needs_reservation():
    with pytest.raises(ValueError):
        Endpoint(id="e", model="m", pool="p", site="cloud", kind="chat",
                 url="https://example.test/chat", externally_billed=True)


def test_sampling_override_rejected():
    with pytest.raises(ValueError):
        Endpoint(id="e", model="m", pool="p", site="local", kind="mock",
                 extra_body_json='{"max_tokens":9999}')


def test_stateful_is_explicitly_unsupported():
    with pytest.raises(ValueError):
        ModelContract(alias="x", weights="a", preprocessing="a", output_schema="a", sampling="a", stateful=True)


def test_clock_maps():
    m = ClockMap("remote", "local", 100, 2, 1000)
    assert m.map(200, target_clock="local", now_ns=500) == (300, 2)
    with pytest.raises(ValueError):
        m.map(200, target_clock="other", now_ns=500)
    with pytest.raises(ValueError):
        m.map(200, target_clock="local", now_ns=1001)
    with pytest.raises(ValueError):
        m.map(True, target_clock="local", now_ns=500)


def test_duplicate_registry_rejected(cfg):
    with pytest.raises(ValueError):
        RuntimeConfig(**{**cfg.model_dump(), "models": cfg.models+cfg.models})
