# tests/test_real_conversation_parser_node.py
import pytest
from agentic.state import MasterAgentState
from agentic.parser.conversation_parser import real_conversation_parser_node


def test_5_real_user_prompts():
    prompts = [
        ("upload suyash2.zip", "compile_zip", 0.95, "planner"),
        ("what's my model accuracy", "query_status", 0.88, "planner"),
        ("run anomaly detection", "detect_anomalies", 0.88, "planner"),
        ("train RUL model on NASA FD001", "train_rul", 0.88, "planner"),
        ("do something random", "general", 0.50, "clarification"),
    ]
    
    for prompt_text, expected_intent, min_score, expected_next_agent in prompts:
        state = MasterAgentState(messages=[{"role": "user", "content": prompt_text}])
        res = real_conversation_parser_node(state)
        
        assert res["cuc"]["goal"]["primary_intent"] == expected_intent
        if expected_next_agent == "planner":
            assert res["confidence_score"] >= min_score
        else:
            assert res["confidence_score"] < 0.85
        assert res["active_agent"] == expected_next_agent
