import pytest

from ledgerlight.knowledge.llm_extraction import extract_with_llm


def test_not_run_when_llm_provider_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    result = extract_with_llm("AUD_RESIGN", "some chunk text")
    assert result.status == "not_run"
    assert result.fields is None
    assert result.cost_usd == 0.0
    assert result.reason is not None


def test_not_run_when_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = extract_with_llm("AUD_RESIGN", "some chunk text")
    assert result.status == "not_run"


def test_unknown_event_type_raises() -> None:
    with pytest.raises(ValueError, match="unknown event_type_code"):
        extract_with_llm("NOT_A_REAL_CODE", "text")


def test_gate_open_but_no_client_wired_raises_not_implemented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test-key-not-a-real-secret")
    with pytest.raises(NotImplementedError):
        extract_with_llm("AUD_RESIGN", "some chunk text")
