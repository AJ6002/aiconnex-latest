# tests/test_parser_extractor_and_validator.py
import json
import pytest
from agentic.schemas import ConversationUnderstandingContract
from agentic.parser.semantic_extractor import SemanticExtractor
from agentic.parser.output_validator import StructuredOutputValidator


def test_semantic_extractor_heuristic_fallback():
    extractor = SemanticExtractor(use_llm=False)
    raw = extractor.extract("upload suyash2.zip archive")
    assert raw["goal"]["primary_intent"] == "compile_zip"
    assert "suyash2.zip" in raw["observed"]["mentioned_files"]


def test_semantic_extractor_train_intent_not_hijacked_by_zip_filename():
    # Regression test: a .zip filename mentioned inside a training prompt
    # must not cause the bare "zip" keyword substring match inside
    # "compile_zip" to hijack the intent away from "train_rul".
    extractor = SemanticExtractor(use_llm=False)
    raw = extractor.extract("train RUL model on suyash2.zip")
    assert raw["goal"]["primary_intent"] == "train_rul"


def test_structured_output_validator():
    validator = StructuredOutputValidator()
    raw_dict = {
        "goal": {"raw_prompt": "upload suyash2.zip", "primary_intent": "compile_zip"},
        "observed": {"mentioned_files": ["suyash2.zip"]},
        "inferred": {"domain": "Compressor Telemetry"},
    }
    cuc = validator.validate(raw_dict)
    assert isinstance(cuc, ConversationUnderstandingContract)
    assert cuc.goal.primary_intent == "compile_zip"



# --- Real LLM call path tests (SemanticExtractor now defaults to use_llm=True) ---

class _StubLLM:
    """Test-local stub returning a fixed response, for direct control over LLM output."""
    def __init__(self, content: str):
        self._content = content

    def invoke(self, prompt: str):
        class _Resp:
            content = self._content
        return _Resp()


def test_semantic_extractor_uses_real_llm_call_path_by_default(monkeypatch):
    import agentic.parser.semantic_extractor as se_module

    llm_response = json.dumps({
        "goal": {"primary_intent": "train_rul"},
        "observed": {"mentioned_files": ["nasa_fd001.zip"], "mentioned_columns": []},
        "inferred": {"domain": "Aircraft Engine"},
    })
    monkeypatch.setattr(se_module, "get_llm", lambda *a, **kw: _StubLLM(llm_response))

    extractor = SemanticExtractor()  # default is now use_llm=True
    assert extractor.use_llm is True

    raw = extractor.extract("train RUL model on nasa_fd001.zip")
    assert raw["goal"]["primary_intent"] == "train_rul"
    assert raw["observed"]["mentioned_files"] == ["nasa_fd001.zip"]


def test_semantic_extractor_handles_markdown_fenced_json(monkeypatch):
    import agentic.parser.semantic_extractor as se_module

    fenced = "```json\n" + json.dumps({"goal": {"primary_intent": "compile_zip"}}) + "\n```"
    monkeypatch.setattr(se_module, "get_llm", lambda *a, **kw: _StubLLM(fenced))

    extractor = SemanticExtractor()
    raw = extractor.extract("compile this")
    assert raw["goal"]["primary_intent"] == "compile_zip"


def test_semantic_extractor_rejects_hallucinated_intent_and_falls_back(monkeypatch):
    import agentic.parser.semantic_extractor as se_module

    # LLM hallucinates a plugin/intent that isn't in the valid set.
    hallucinated = json.dumps({"goal": {"primary_intent": "per_partition_anomaly_detection"}})
    monkeypatch.setattr(se_module, "get_llm", lambda *a, **kw: _StubLLM(hallucinated))

    extractor = SemanticExtractor()
    raw = extractor.extract("train RUL model on suyash2.zip")
    # Falls back to the deterministic heuristic, which correctly resolves train_rul.
    assert raw["goal"]["primary_intent"] == "train_rul"


def test_semantic_extractor_falls_back_on_network_error(monkeypatch):
    import agentic.parser.semantic_extractor as se_module

    def _raise_llm(*a, **kw):
        raise ConnectionError("simulated Ollama connection failure")

    monkeypatch.setattr(se_module, "get_llm", _raise_llm)

    extractor = SemanticExtractor()
    raw = extractor.extract("upload suyash2.zip archive")
    assert raw["goal"]["primary_intent"] == "compile_zip"


def test_semantic_extractor_falls_back_on_malformed_json(monkeypatch):
    import agentic.parser.semantic_extractor as se_module

    monkeypatch.setattr(se_module, "get_llm", lambda *a, **kw: _StubLLM("not valid json at all"))

    extractor = SemanticExtractor()
    raw = extractor.extract("run anomaly detection now")
    assert raw["goal"]["primary_intent"] == "detect_anomalies"


def test_semantic_extractor_use_llm_false_skips_llm_entirely(monkeypatch):
    import agentic.parser.semantic_extractor as se_module

    def _should_not_be_called(*a, **kw):
        raise AssertionError("get_llm() must not be called when use_llm=False")

    monkeypatch.setattr(se_module, "get_llm", _should_not_be_called)

    extractor = SemanticExtractor(use_llm=False)
    raw = extractor.extract("upload suyash2.zip archive")
    assert raw["goal"]["primary_intent"] == "compile_zip"
