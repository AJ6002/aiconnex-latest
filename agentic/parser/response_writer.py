"""
aiconnex_agent/parser/response_writer.py
===========================================
response_writer_node — Pre-Upload v1 Architecture (Task 6)

Generalizes the legacy ClarificationGenerator (which only ever produced
clarification questions) into a node that renders whichever action
conversation_planner_node decided (ask | summarize | confirm) into natural
client-facing text. Owns: natural language generation only.
Does NOT own: business logic / deciding what to say (that's the
ConversationPlan it receives) — this node only converts a decision into words.

'recommend_upload' and 'wait' are NOT handled here:
  - recommend_upload is upload_gate_node's responsibility (Task 7) — it
    speaks via the HITL InterruptPayload, not response_writer_node.
  - wait means no user input has arrived yet; there's nothing to write.

Reuses the existing ClarificationGenerator's real LLM call + heuristic
fallback pattern for the 'ask' action (that's exactly what it already does),
and adds new LLM-backed generation for 'summarize' and 'confirm', each with
its own deterministic template fallback so a failed/unavailable LLM never
leaves the user without a response.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from agentic.llm import get_llm
from agentic.parser.clarification_generator import ClarificationGenerator
from agentic.registries.registry_loader import get_field_value
from agentic.schemas import ConversationPlan, ConversationUnderstandingContract
from agentic.state import MasterAgentState

logger = logging.getLogger(__name__)

_clarification_generator = ClarificationGenerator()

STALL_MARKER = "[STALL_WARNING]"


def _strip_stall_marker(rationale: str) -> tuple[str, bool]:
    if rationale.startswith(STALL_MARKER):
        return rationale[len(STALL_MARKER):].strip(), True
    return rationale, False


def _parse_json_response(text: str) -> dict:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")
    return json.loads(match.group(0))


def _field_label(field_path: str) -> str:
    """Turn a dotted field path into a human phrase, e.g. 'goal.task_family' -> 'the problem type'."""
    labels = {
        "goal.primary_intent": "the primary task you want to accomplish",
        "goal.task_family": "the problem type (e.g. regression, anomaly detection, forecasting)",
    }
    return labels.get(field_path, field_path.rsplit(".", 1)[-1].replace("_", " "))


def _render_ask(plan: ConversationPlan, cuc: ConversationUnderstandingContract, stalled: bool) -> str:
    """'ask' action: reuse the existing ClarificationGenerator (real LLM + template fallback),
    which already speaks naturally about whatever's missing on the CUC. When stalled, the
    rationale is passed through so the LLM prompt can naturally vary its phrasing — no
    hardcoded numbered menu is introduced here, per the architecture decision against that."""
    questions = _clarification_generator.generate(cuc)
    text = " ".join(questions) if questions else f"Could you tell me {_field_label(plan.target_field or '')}?"
    if stalled:
        # Nudge phrasing without a menu: add one soft example, still just prose.
        text += " For example, are you trying to predict a value, detect anomalies, or forecast something?"
    return text


def _render_summarize(cuc: ConversationUnderstandingContract) -> str:
    """'summarize' action: recap the understood CUC fields via LLM, with a deterministic
    template fallback (goal + any observed files) if the LLM call fails."""
    prompt = (
        "Summarize, in one short friendly paragraph, what you understand about the user's "
        "goal so far, then say you'll ask them to upload their dataset next.\n\n"
        f"Primary intent: {cuc.goal.primary_intent}\n"
        f"Problem type: {cuc.goal.task_family}\n"
        f"Mentioned files: {cuc.observed.get('mentioned_files', [])}\n"
        'Respond with ONLY a JSON object: {"summary": "<text>"}'
    )
    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_json_response(text)
        summary = parsed.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        raise ValueError("LLM returned an empty/invalid summary")
    except Exception as exc:
        logger.warning(f"[ResponseWriter] LLM summarize failed, falling back to template: {exc}")
        return (
            f"Got it — you're looking to {cuc.goal.primary_intent.replace('_', ' ')} "
            f"using a {cuc.goal.task_family} approach. Next, please upload your dataset "
            f"so we can get started."
        )


def _render_confirm(plan: ConversationPlan, cuc: ConversationUnderstandingContract) -> str:
    """'confirm' action: ask the user to resolve a detected contradiction, via LLM with a
    deterministic template fallback that states both values plainly."""
    contradiction = next(
        (c for c in cuc.contradictions if c.field_path == plan.target_field and not c.resolved), None
    )
    if contradiction is None:
        # Defensive: plan said confirm but the contradiction it referenced is gone/resolved.
        return "Could you confirm the detail you just mentioned? I want to make sure I have it right."

    prompt = (
        "The user previously said one thing, then said something that seems to contradict it. "
        "Write one short, polite question asking them to confirm which is correct — do not "
        "assume either is right.\n\n"
        f"Field: {_field_label(contradiction.field_path)}\n"
        f"Previously understood: {contradiction.previous_value}\n"
        f"Just said: {contradiction.new_value}\n"
        'Respond with ONLY a JSON object: {"question": "<text>"}'
    )
    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_json_response(text)
        question = parsed.get("question")
        if isinstance(question, str) and question.strip():
            return question.strip()
        raise ValueError("LLM returned an empty/invalid question")
    except Exception as exc:
        logger.warning(f"[ResponseWriter] LLM confirm failed, falling back to template: {exc}")
        return (
            f"Just to confirm — earlier you mentioned {_field_label(contradiction.field_path)} "
            f"as '{contradiction.previous_value}', but now it sounds like '{contradiction.new_value}'. "
            f"Which one is correct?"
        )


def render_response(plan: ConversationPlan, cuc: ConversationUnderstandingContract) -> str:
    """Pure-ish rendering dispatch (LLM calls happen inside, but no LangGraph
    state plumbing here — independently testable with a mocked LLM)."""
    rationale, stalled = _strip_stall_marker(plan.rationale)

    if plan.action == "ask":
        return _render_ask(plan, cuc, stalled)
    if plan.action == "summarize":
        return _render_summarize(cuc)
    if plan.action == "confirm":
        return _render_confirm(plan, cuc)

    raise ValueError(
        f"response_writer_node cannot render action={plan.action!r}. "
        f"'recommend_upload' is upload_gate_node's responsibility; 'wait' has nothing to render."
    )


def response_writer_node(state: MasterAgentState) -> dict:
    """LangGraph node wrapper. Reads state.conversation_plan + state.cuc,
    writes state.response_text, then PAUSES the graph via interrupt() to
    wait for the user's next message — mirroring the exact pattern the
    legacy clarification_node already uses (interrupt(), capture the resume
    value, append it to state.messages). Without this pause, wiring this
    node's loop-back edge straight to conversation_manager_node (Task 8)
    would re-run the whole chain instantly on the same stale message inside
    one synchronous graph.stream() call instead of genuinely waiting for a
    new user turn.

    Reuses interrupt_type='clarification' for ask/summarize/confirm alike —
    from the existing SSE consumer's perspective (backend/app.py's
    _stream_agent_events, ChatView.tsx) this is identical to "the bot said
    something and is waiting for a reply", requiring no new frontend work.
    """
    plan_dict = state.conversation_plan
    if plan_dict is None:
        raise ValueError("response_writer_node invoked with no conversation_plan set")
    plan = ConversationPlan.model_validate(plan_dict) if isinstance(plan_dict, dict) else plan_dict

    text = render_response(plan, state.cuc)
    logger.info(f"[ResponseWriter] action={plan.action} -> {len(text)} chars")

    from langgraph.types import interrupt
    from agentic.schemas import InterruptPayload

    payload = InterruptPayload(
        interrupt_type="clarification",
        questions=[text],
        options=[],
        reason=f"conversation_plan.action={plan.action}",
    )
    user_reply = interrupt(payload.model_dump())

    result: dict = {
        "response_text": text,
        "active_agent": "conversation_manager",
    }
    if isinstance(user_reply, str) and user_reply.strip():
        # messages has no LangGraph reducer, so returning a list REPLACES it —
        # rebuild the full history explicitly (same pattern as the legacy
        # clarification_node's answer-ingestion fix earlier this session).
        result["messages"] = list(state.messages) + [{"role": "user", "content": user_reply.strip()}]
    return result
