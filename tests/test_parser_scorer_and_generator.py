# tests/test_parser_scorer_and_generator.py
import pytest
from agentic.schemas import ConversationUnderstandingContract
from agentic.parser.confidence_scorer import ConfidenceScorer
from agentic.parser.clarification_generator import ClarificationGenerator


def test_confidence_scorer_high():
    cuc = ConversationUnderstandingContract(
        goal={"primary_intent": "compile_zip"},
        observed={"mentioned_files": ["suyash2.zip"]}
    )
    scorer = ConfidenceScorer()
    score = scorer.score(cuc)
    assert score >= 0.90


def test_confidence_scorer_low():
    cuc = ConversationUnderstandingContract(
        goal={"primary_intent": "general"},
        observed={"mentioned_files": []}
    )
    scorer = ConfidenceScorer()
    score = scorer.score(cuc)
    assert score < 0.85


def test_clarification_generator():
    cuc = ConversationUnderstandingContract(
        goal={"primary_intent": "general"}
    )
    gen = ClarificationGenerator()
    questions = gen.generate(cuc)
    assert len(questions) >= 1
    assert any("dataset" in q.lower() or "goal" in q.lower() or "would you like" in q.lower() for q in questions)


# --- Real LLM call path tests (both modules now default to use_llm=True) ---

class _StubLLM:
    """Test-local stub returning a fixed response, for direct control over LLM output."""
    def __init__(self, content: str):
        self._content = content

    def invoke(self, prompt: str):
        class _Resp:
            content = self._content
        return _Resp()


def test_confidence_scorer_uses_real_llm_call_path_by_default(monkeypatch):
    import agentic.parser.confidence_scorer as cs_module
    monkeypatch.setattr(cs_module, "get_llm", lambda *a, **kw: _StubLLM('{"confidence": 0.97, "reasoning": "clear"}'))

    scorer = ConfidenceScorer()  # default is now use_llm=True
    assert scorer.use_llm is True
    cuc = ConversationUnderstandingContract(goal={"primary_intent": "train_rul"}, observed={"mentioned_files": ["a.zip"]})
    assert scorer.score(cuc) == 0.97


def test_confidence_scorer_rejects_out_of_range_and_falls_back(monkeypatch):
    import agentic.parser.confidence_scorer as cs_module
    monkeypatch.setattr(cs_module, "get_llm", lambda *a, **kw: _StubLLM('{"confidence": 1.5}'))

    scorer = ConfidenceScorer()
    cuc = ConversationUnderstandingContract(goal={"primary_intent": "compile_zip"}, observed={"mentioned_files": ["a.zip"]})
    # Falls back to the rule-based ladder, which resolves this to 0.95.
    assert scorer.score(cuc) == 0.95


def test_confidence_scorer_falls_back_on_network_error(monkeypatch):
    import agentic.parser.confidence_scorer as cs_module

    def _raise(*a, **kw):
        raise ConnectionError("simulated failure")
    monkeypatch.setattr(cs_module, "get_llm", _raise)

    scorer = ConfidenceScorer()
    cuc = ConversationUnderstandingContract(goal={"primary_intent": "general"}, observed={"mentioned_files": []})
    assert scorer.score(cuc) == 0.50


def test_confidence_scorer_use_llm_false_skips_llm_entirely(monkeypatch):
    import agentic.parser.confidence_scorer as cs_module

    def _should_not_be_called(*a, **kw):
        raise AssertionError("get_llm() must not be called when use_llm=False")
    monkeypatch.setattr(cs_module, "get_llm", _should_not_be_called)

    scorer = ConfidenceScorer(use_llm=False)
    cuc = ConversationUnderstandingContract(goal={"primary_intent": "compile_zip"}, observed={"mentioned_files": ["a.zip"]})
    assert scorer.score(cuc) == 0.95


def test_clarification_generator_uses_real_llm_call_path_by_default(monkeypatch):
    import agentic.parser.clarification_generator as cg_module
    monkeypatch.setattr(cg_module, "get_llm", lambda *a, **kw: _StubLLM('{"questions": ["Which archive should I use?"]}'))

    gen = ClarificationGenerator()  # default is now use_llm=True
    assert gen.use_llm is True
    cuc = ConversationUnderstandingContract(goal={"primary_intent": "general"})
    questions = gen.generate(cuc)
    assert questions == ["Which archive should I use?"]


def test_clarification_generator_falls_back_on_empty_llm_questions(monkeypatch):
    import agentic.parser.clarification_generator as cg_module
    monkeypatch.setattr(cg_module, "get_llm", lambda *a, **kw: _StubLLM('{"questions": []}'))

    gen = ClarificationGenerator()
    cuc = ConversationUnderstandingContract(goal={"primary_intent": "general"})
    questions = gen.generate(cuc)
    # Falls back to templates.
    assert len(questions) >= 1


def test_clarification_generator_falls_back_on_network_error(monkeypatch):
    import agentic.parser.clarification_generator as cg_module

    def _raise(*a, **kw):
        raise ConnectionError("simulated failure")
    monkeypatch.setattr(cg_module, "get_llm", _raise)

    gen = ClarificationGenerator()
    cuc = ConversationUnderstandingContract(goal={"primary_intent": "general"})
    questions = gen.generate(cuc)
    assert len(questions) >= 1


def test_clarification_generator_use_llm_false_skips_llm_entirely(monkeypatch):
    import agentic.parser.clarification_generator as cg_module

    def _should_not_be_called(*a, **kw):
        raise AssertionError("get_llm() must not be called when use_llm=False")
    monkeypatch.setattr(cg_module, "get_llm", _should_not_be_called)

    gen = ClarificationGenerator(use_llm=False)
    cuc = ConversationUnderstandingContract(goal={"primary_intent": "general"})
    questions = gen.generate(cuc)
    assert len(questions) >= 1
