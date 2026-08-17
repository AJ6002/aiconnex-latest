"""
aiconnex_agent/parser/conversation_parser.py
=============================================
Main Conversation Parser Orchestrator running the 6 sub-modules:
  1. PromptBuilder
  2. ContextManager
  3. SemanticExtractor
  4. StructuredOutputValidator
  5. ConfidenceScorer
  6. ClarificationGenerator
"""

from __future__ import annotations

import logging
from typing import Dict, Any

from agentic.state import MasterAgentState
from agentic.parser.prompt_builder import PromptBuilder
from agentic.parser.context_manager import ContextManager
from agentic.parser.semantic_extractor import SemanticExtractor
from agentic.parser.output_validator import StructuredOutputValidator
from agentic.parser.confidence_scorer import ConfidenceScorer
from agentic.parser.clarification_generator import ClarificationGenerator

logger = logging.getLogger(__name__)

# Module Singletons
prompt_builder = PromptBuilder()
context_manager = ContextManager()
semantic_extractor = SemanticExtractor()
output_validator = StructuredOutputValidator()
confidence_scorer = ConfidenceScorer()
clarification_generator = ClarificationGenerator()


def real_conversation_parser_node(state: MasterAgentState) -> Dict[str, Any]:
    """Real Conversation Parser Node running all 6 sub-modules.

    LEGACY / PRE-v1-SPLIT: kept unmodified and still callable so nothing
    currently wired to it (graph.py, existing tests) breaks. The Pre-Upload
    v1 architecture supersedes this with the split nodes below
    (conversation_manager_node -> intent_extraction_node -> contract_manager_node
    -> conversation_planner_node -> response_writer_node -> upload_gate_node).
    graph.py is rewired onto the split chain in Task 8 — until then, both
    exist side by side.
    """
    logger.info("[ConversationParser] Executing 6-module pipeline")
    user_prompt = state.messages[-1]["content"] if state.messages else ""
    
    # 1 & 2. Prompt & Context
    sys_prompt = prompt_builder.build_system_prompt(user_prompt)
    ctx = context_manager.update_context(user_prompt, state.messages)
    
    # 3. Semantic Extraction
    raw_dict = semantic_extractor.extract(user_prompt, sys_prompt)
    
    # 4. Output Validation
    cuc = output_validator.validate(raw_dict)
    
    # 5. Confidence Scoring
    score = confidence_scorer.score(cuc)
    cuc.goal.confidence = score
    
    # 6. Clarification Generation (if score < 0.85)
    clarifications = []
    if score < 0.85:
        clarifications = clarification_generator.generate(cuc)
        cuc.clarifications_required = clarifications
        
    cuc_dict = cuc.model_dump() if hasattr(cuc, "model_dump") else cuc.dict()
    
    return {
        "cuc": cuc_dict,
        "active_agent": "clarification" if score < 0.85 else "planner",
        "confidence_score": score,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Pre-Upload v1 Architecture (Task 4): split nodes
# ═══════════════════════════════════════════════════════════════════════════
#
# The two node functions below extract sub-modules 1+2 (PromptBuilder +
# ContextManager) and 3 (SemanticExtractor) out of the fused function above
# into standalone LangGraph nodes, per the v1 responsibility table:
#
#   conversation_manager_node — owns: session, history, context window.
#                                does NOT own: intent extraction.
#   intent_extraction_node    — owns: structured extraction from conversation.
#                                does NOT own: planning, chat generation.
#
# Pure extraction — zero behavior change vs. the fused node's first three
# steps. intent_extraction_node writes its raw dict to state.latest_extraction
# (added in Task 3) rather than validating it into a CUC directly — that
# validation+merge responsibility now belongs to contract_manager_node,
# not to extraction.


def conversation_manager_node(state: MasterAgentState) -> Dict[str, Any]:
    """Owns: session bookkeeping, rolling history, context window.

    Reads the latest user message and the prior message history, and
    produces a Conversation Context dict (last_user_prompt, history,
    turn_count) that intent_extraction_node consumes next — it does NOT
    read state.messages directly, enforcing the node boundary.

    NOTE (parity with the legacy fused node): ContextManager.update_context()
    appends user_prompt onto the history it's given. Since state.messages
    already includes this turn's message by the time this node runs, the
    produced `history` list contains one duplicate trailing entry — this
    matches the fused node's existing (unused-downstream) behavior exactly
    and is not fixed here to keep this task a pure extraction, not a
    behavior change. `history` itself is not currently consumed by any
    downstream node.
    """
    user_prompt = state.messages[-1]["content"] if state.messages else ""
    context = context_manager.update_context(user_prompt, state.messages)
    logger.info(f"[ConversationManager] turn_count={context.get('turn_count')}")
    return {
        "memory_context": context,
        "active_agent": "intent_extraction",
    }


def intent_extraction_node(state: MasterAgentState) -> Dict[str, Any]:
    """Owns: structured extraction from the conversation (LLM-backed, with
    deterministic heuristic fallback inside SemanticExtractor).

    Reads state.memory_context (produced by conversation_manager_node) for
    the prompt to extract from, builds the system prompt via PromptBuilder,
    and writes the raw extraction dict to state.latest_extraction for
    contract_manager_node to merge. Does NOT validate into a CUC and does
    NOT decide what happens next — those are contract_manager_node's and
    conversation_planner_node's jobs respectively.
    """
    user_prompt = state.memory_context.get("last_user_prompt", "") if state.memory_context else ""
    if not user_prompt and state.messages:
        # Defensive fallback if this node is ever invoked without
        # conversation_manager_node having run first in the same pass.
        user_prompt = state.messages[-1]["content"]

    sys_prompt = prompt_builder.build_system_prompt(user_prompt)
    raw_dict = semantic_extractor.extract(user_prompt, sys_prompt)

    logger.info(f"[IntentExtraction] extracted primary_intent="
                f"{raw_dict.get('goal', {}).get('primary_intent', 'unknown')!r}")
    return {
        "latest_extraction": raw_dict,
        "active_agent": "contract_manager",
    }
