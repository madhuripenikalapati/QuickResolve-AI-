# QuickResolve AI – Architecture Decision Document

## Overview

QuickResolve AI is a conversational shopping assistant for **Taara Boutique**, handling the complete buyer journey — product discovery, order placement, and post-order support — over a WhatsApp-style interface.

**Core principle: Reliability over complexity.** Every architectural decision optimizes for predictable, grounded responses rather than impressive-sounding features.

---

## Agent Graph (LangGraph)

```
[classify_intent] ──→ [check_context] ──→ [select_tool] ──→ [execute_tool]
        │                    │                                      │
        │ (general/unclear)  │ (missing info)                       ↓
        ↓                    ↓                            [generate_response]
[generate_response]  [generate_response]                           │
                                                                    ↓
                                                         [check_confidence]
                                                          /              \
                                                    (high conf)       (low conf)
                                                         ↓                ↓
                                                [update_memory]       [escalate]
```

### Node Responsibilities

| Node | Type | Responsibility |
|------|------|----------------|
| `classify_intent` | Rule-based + LLM fallback | Classify into 6 intents; fast-path for unambiguous patterns skips LLM call |
| `check_context` | Rule-based | Validate all required fields exist before acting (product, size, address, payment) |
| `select_tool` | Rule-based | Choose tool + prepare args from message + session state |
| `execute_tool` | Deterministic | Call tool(s), catch errors, return structured result |
| `generate_response` | LLM (Groq Llama) | Generate buyer-facing text grounded exclusively in tool output |
| `check_confidence` | Rule-based | Score response reliability, flag for escalation |
| `update_memory` | Deterministic | Persist SessionState after each turn |
| `escalate_to_seller` | Deterministic | Append handoff message when confidence is low |

---

## Tools (Why These Three)

### Why 3 tools instead of more granular ones?
Fewer tools = fewer wrong selections. `search_catalog` handles both browsing and availability; `get_policy` handles all 4 policies via RAG. Each additional tool is another thing that can be called incorrectly or out of order.

### 1. Catalog Tool (`tools/catalog.py`)

Two-path hybrid search:

```
search_catalog(query?, category?, max_price?, size?, color?)
    ├── Path 1 (Structured): Filter by category, price, size, color
    │   └── Returns if ≥2 results found
    └── Path 2 (Vector): FAISS cosine similarity on product embeddings
        └── Fallback for open queries ("something flowy for a wedding")
```

**Why hybrid?** Structured filters handle "kurtas under ₹2000 in size L" with 100% precision — vector search would return semantically close but wrong-price results. Vector handles open-ended queries. Same FAISS infra serves both catalog and policy RAG.

All size keys normalized to uppercase at load time. Product embeddings built from: `"{name}. {category}. {fabric}. {occasions}. {description}"`.

### 2. Order Tool (`tools/orders.py`)

CRUD with business rule validation:
- `get_order(order_id)` — lookup by ID
- `create_order(...)` — validates stock, COD eligibility (amount < ₹5000, not custom-stitched), auto-selects single available size (FREE SIZE sarees), decrements inventory
- `update_order(order_id, updates)` — validates status transition graph before applying

### 3. Policy RAG (`tools/policy_rag.py`)

4 documents embedded at startup, retrieved via FAISS cosine similarity:
- `refund_policy.md` — 7-day window, custom-stitched/sale exclusions
- `exchange_policy.md` — 10-day window, one exchange per order
- `cod_policy.md` — ₹5000 limit, ₹49 convenience fee
- `shipping_policy.md` — 5–7 business days, free shipping above ₹1499

---

## Why LangGraph?

LangGraph gives explicit control over the node execution graph, which is critical for a reliability-first agent:

- **Conditional edges** allow deterministic routing: if context is missing, the agent always asks before acting — no LLM-dependent branching
- **State dict** passes cleanly through all nodes, making debugging straightforward
- **No magic**: every routing decision is readable code, not a prompt

Compared to alternatives: OpenAI Assistants gives less control over when tools are called; a raw ReAct loop (LangChain AgentExecutor) is harder to constrain; a custom state machine without LangGraph is more boilerplate.

---

## Why Groq + Llama 3.1?

- **Latency**: Groq hardware gives ~10× faster inference than OpenAI for streaming WhatsApp-style responses
- **Cost**: Free tier sufficient for demo; dev tier scales cheaply
- **Reliability**: API key rotation built in for rate limit handling

The LLM is only used for two nodes — `classify_intent` (when fast-path fails) and `generate_response`. All routing, tool selection, and context validation is rule-based and doesn't depend on the LLM.

---

## Session Memory

`SessionState` is a dataclass serialized to dict, stored in-memory per `session_id`. Carries:

| Field | Purpose |
|-------|---------|
| `stage` | Conversation stage: `discovery → pre_order → ordering → post_order` |
| `active_product` | Currently selected product, reduces repeat tool calls |
| `active_order_id` | Order context for support turns |
| `pending_size / payment_preference / delivery_address` | Captured once, reused across turns |
| `last_shown_products` | Products shown in last search, enables color/name/ordinal resolution |
| `recent_messages` | Sliding window of last 10 turns, injected into LLM context |
| `pending_clarification` | What the agent last asked for, guides next-turn classification |

**Production upgrade**: replace `dict[session_id, dict]` in `api/routes/chat.py` with Redis — one-line change since the state is already JSON-serializable.

---

## Eval Suite

### 4 Metrics

| Metric | What It Measures |
|--------|-----------------|
| **Task Completion** | Response contains required terms + correct tools were called |
| **Tool Hallucination** | Price/availability/policy claims made without a corresponding tool call |
| **Tool Validity** | Expected tools were called; no duplicate identical calls |
| **Graceful Failure** | Edge/adversarial cases: no forbidden terms, recovery language present |

### Test Coverage (33 cases)

| Workflow | Happy Path | Edge Case | Adversarial |
|----------|-----------|-----------|-------------|
| discovery | 5 | 3 | 2 |
| pre_order | 2 | 2 | 1 |
| ordering | 1 | 3 | 1 |
| post_order | 4 | 4 | 2 |
| general | 2 | 0 | 0 |

### Results (34 test cases)

| Metric | Score |
|--------|-------|
| Task Completion — pass | 25/34 (74%) |
| Task Completion — partial | 8/34 (24%) |
| Task Completion — fail | 1/34 (3%) |
| No Hallucination | 24/34 (71%) |
| Tool Validity | 33/34 (97%) |
| Graceful Failure Handling | 13/18 (72%) |

**By workflow:**

| Workflow | Pass | Partial | Fail |
|----------|------|---------|------|
| discovery | 10/11 | 1 | 0 |
| pre_order | 3/5 | 1 | 1 |
| ordering | 4/5 | 1 | 0 |
| post_order | 7/11 | 4 | 0 |
| general | 1/2 | 1 | 0 |

The 10 hallucination flags are almost entirely in post_order turns where the LLM restates policy details (e.g. "7-day window") from session context rather than a fresh `get_policy` call — the content is correct but the scorer penalises it as ungrounded. The 1 tool validity failure is a duplicate `get_order` call on a multi-turn support case.

---

## Where the Agent Breaks — and What It Would Take to Fix It

### 1. Cross-session size bleed
**What breaks**: `pending_size` (e.g. "XXL" from an earlier kurta search) carries into a new product order. A FREE SIZE saree gets ordered with size=XXL, which fails stock check.

**Current mitigation**: `_select_order_tool` validates cached size against active product's sizes and discards it if invalid. `check_context` re-validates pending_size against product sizes.

**What it would take to fully fix**: Clear `pending_size` in `update_memory` when `active_product` changes. Requires tracking "previous active_product" in session state.

---

### 2. Multi-turn order collection across intents
**What breaks**: If the user switches topic mid-order ("actually show me lehengas") and comes back, the partial order state (pending_size, address) is still in session but `active_product` may have changed. The agent may assemble an order with mismatched context.

**What it would take to fix**: Explicit ordering sub-state separate from discovery session state. An `OrderDraft` dataclass that is scoped to one product and reset when the product changes.

---

### 3. Multi-product disambiguation
**What breaks**: "Show me sarees" returns 9 results. User says "order the silk one" — both Red Silk Saree and Banarasi Silk Saree score equally on "silk". The agent picks the higher-scoring one, but if they're tied it's the first in the list.

**What it would take to fix**: When score is tied, ask the user: "Did you mean the Red Silk Saree (₹5999) or the Banarasi Silk Saree (₹6999)?" Requires a disambiguation node in the graph before `select_tool`.

---

### 4. LLM hallucination under rate limits
**What breaks**: When all Groq API keys are exhausted, `generate_response` falls back to rule-based templates. These templates handle ~8 tool result shapes. Novel shapes (e.g. a policy+order combo) return "I'm having trouble fetching that right now."

**What it would take to fix**: Expand rule-based fallback coverage, or add a local fallback model (e.g. Ollama) for the response generation node only.

---

### 5. No persistent order confirmation
**What breaks**: Orders are created in an in-memory dict (`_orders` in `tools/orders.py`). A server restart wipes all orders. Payment links point to a mock URL.

**What it would take to fix**: Persist to SQLite/Postgres. Replace mock payment link with a real payment gateway (Razorpay, PayU). Out of scope for demo but a one-file change in `tools/orders.py`.

---

### 6. Fuzzy matching false positives at scale
**What breaks**: The tool selector uses `difflib.get_close_matches` for typo correction on category and color names. With a larger catalog (500+ products, 50+ colors), the edit-distance threshold that works now (0.80) may produce more false positives.

**What it would take to fix**: Replace difflib with a small embedding-based nearest-neighbor lookup for entity resolution. Same FAISS infra already present.

---

### 7. Language detection on short messages
**What breaks**: Messages like "ok", "XL", "haan" are classified as English by the character-level heuristic in `language_detect.py`. The agent replies in English even if the user has been writing in Telugu.

**Current mitigation**: Inherit language from `recent_messages` when the current message is ≤4 words.

**What it would take to fix**: Use a proper language ID model (e.g. `fastText` lid.176.ftz, 917KB) instead of the character heuristic.
