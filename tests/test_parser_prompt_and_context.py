# tests/test_parser_prompt_and_context.py
import pytest
from agentic.parser.prompt_builder import PromptBuilder
from agentic.parser.context_manager import ContextManager


def test_prompt_builder():
    builder = PromptBuilder()
    prompt = builder.build_system_prompt(user_prompt="upload suyash2.zip")
    assert "ConversationUnderstandingContract" in prompt
    assert "upload suyash2.zip" in prompt


def test_context_manager():
    ctx_mgr = ContextManager()
    updated = ctx_mgr.update_context("upload suyash2.zip", history=[])
    assert updated["last_user_prompt"] == "upload suyash2.zip"
    assert len(updated["history"]) == 1
