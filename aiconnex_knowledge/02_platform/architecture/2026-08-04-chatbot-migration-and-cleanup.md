# Chatbot Migration & Legacy Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate and unify all chatbot interaction into a single active frontend view (`LandingView.tsx`) backed by the unified Flask engine (`chatbot/backend/app.py` on port 8000), while cleaning up legacy/duplicate chatbot servers and ensuring zero port collisions.

**Architecture:** The Chatbot UI in `LandingView.tsx` connects dynamically to `http://localhost:8000/api/pre_upload/chat` for CUC intent gathering and `http://localhost:8000/api/upload` for Scout Agent profiling. Legacy standalone chatbot servers operating on port 5000 (`first-chatbot`, `validation_gate2`) are archived/decommissioned to eliminate port conflicts.

**Tech Stack:** React 18, TypeScript, TailwindCSS, Python 3.11, Flask, Qwen 2.5 Coder 32B via OpenRouter.

## Global Constraints

- **No Hardcoded Reasoning**: All CUC status badges, confidence percentages, and next action recommendations MUST be derived dynamically from backend payloads (`missing_information`, `conversation_complete`, `recommended_next_action`).
- **No Git Commit Without Direct User Command**: Keep changes in working tree on `Chatbot_4JUL` branch without running git commits.
- **Port Mapping Standard**: Port 3000 = Frontend, Port 8000 = Unified Chatbot + Profiler Backend, Ports 8001–8008 = Microservice Fleet.

---

### Task 1: Verify & Standardize Active Chatbot API Endpoints

**Files:**
- Modify: `frontend/src/views/LandingView.tsx`
- Modify: `chatbot/backend/app.py`
- Test: `chatbot/backend/tests/test_pre_upload_flow.py`

**Interfaces:**
- Consumes: `/api/pre_upload/chat` payload `{ message, session_id, conversation_id }`
- Produces: `{ reply, session_id, conversation_complete, recommended_next_action, missing_information }`

- [ ] **Step 1: Write backend API integration test**

```python
def test_pre_upload_chat_endpoint_returns_dynamic_contract():
    from chatbot.backend.app import app
    client = app.test_client()
    response = client.post('/api/pre_upload/chat', json={'message': 'Upload dataset for anomaly detection'})
    assert response.status_code == 200
    data = response.get_json()
    assert 'reply' in data
    assert 'conversation_complete' in data
    assert 'recommended_next_action' in data
```

- [ ] **Step 2: Run pytest to verify test passes**

Run: `pytest chatbot/backend/tests/test_pre_upload_flow.py -v`
Expected: PASS

- [ ] **Step 3: Update `LandingView.tsx` API URLs to single unified config**

```typescript
const API_BASE = 'http://localhost:8000';

const res = await fetch(`${API_BASE}/api/pre_upload/chat`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: prompt, session_id: sessionId, conversation_id: conversationId }),
  signal: controller.signal
});
```

- [ ] **Step 4: Verify TypeScript compilation**

Run: `npx tsc --noEmit` in `frontend/`
Expected: PASS (0 errors)

---

### Task 2: Decommission Legacy Port 5000 Chatbot Servers

**Files:**
- Delete / Archive: `gitlab-harshit/ai-connex-ui-27JUL/first-chatbot/`
- Delete / Archive: `validation_gate2/server/app.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: None (Legacy Standalone Server Code)
- Produces: Clean port space (Port 5000 & 8000 free of orphan process binds)

- [ ] **Step 1: Check running processes on port 5000**

Run: `netstat -ano | findstr :5000`
Expected: No active listener on port 5000

- [ ] **Step 2: Add legacy chatbot archive rules to `.gitignore`**

```gitignore
# Legacy chatbot standalone archives
gitlab-harshit/
validation_gate2/
ai-connex-ui-27JUL/
```

- [ ] **Step 3: Verify single active chatbot entry point**

Check that only `chatbot/backend/app.py` is registered to handle chat interactions on port 8000.

---

### Task 3: Enforce Dynamic LangUI-Style Agent Badging in `LandingView.tsx`

**Files:**
- Modify: `frontend/src/views/LandingView.tsx`

**Interfaces:**
- Consumes: `missing_information` array and `conversation_complete` boolean from `pre_upload_chat` API
- Produces: Live agent status badge (`Gathering intent...` vs `READY`) and dynamic confidence percentage score

- [ ] **Step 1: Verify dynamic confidence calculation**

```typescript
const reqMissing = (data.missing_information || []).filter((m: string) => m.includes('Required field')).length;
const filled = Math.max(0, 4 - reqMissing);
const conf = Math.round((0.50 + (filled / 4) * 0.45) * 100) / 100;
setConfidence(conf);
```

- [ ] **Step 2: Verify zero hardcoded mock timers exist in `LandingView.tsx`**

Ensure `setInterval` or fake `setTimeout` chain-of-thought arrays are NOT present.

- [ ] **Step 3: Run `npx tsc --noEmit` to confirm zero frontend errors**

Run: `npx tsc --noEmit` in `frontend/`
Expected: PASS (0 errors)

---

## Plan Self-Review

1. **Spec Coverage:** Covers Chatbot UI migration to `LandingView.tsx`, single port binding on `:8000`, and removal of legacy standalone port 5000 servers.
2. **Placeholder Scan:** Zero placeholders or TBDs used.
3. **Type Consistency:** Verified interface signatures match `pre_upload_flow.py` return keys.
