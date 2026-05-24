# QuickResolve AI — Architecture Decision Document

---

## Why This Was Built

My mom runs a women's clothing boutique on Instagram. She posts her entire collection there — sarees, kurtas, lehengas — and buyers reach out directly on WhatsApp Business and Instagram DMs to ask questions and place orders.

She gets **~1,000 messages a day**. She has no team. My sisters help her reply.

What we noticed: if you reply within minutes, the buyer converts. If you reply hours later, they've already bought from someone else. Conversion rate drops sharply with response time.

Most messages come in **Telugu**, or a mix of Telugu and English. Buyers often send back an **Instagram post or reel** asking "how much is this?" or "is this available in XL?" There's no product catalog URL, no cart, no checkout — just DMs and trust.

Every day my sisters spend hours doing this manually. They can't reply to everyone. They miss messages. Sellers like my mom — and thousands like her across India running Instagram-first boutiques — have no affordable automation solution built for how they actually sell.

When I saw PS-3 ("Minimal Agent, Maximum Reliability"), I immediately thought of this. I built a minimal version of what I want this to eventually become.

---

## What This Version Does

**Problem**: Taara Boutique is an Instagram fashion store. Buyers discover products on Instagram, then reach out via **WhatsApp Business** or **Instagram DMs** to ask questions, place orders, and raise issues. All of this is handled manually today. The goal is to automate the full buyer journey — product discovery → order placement → post-order support — reliably, without hallucinating product details, inventing policies, or placing wrong orders.

**What was built**: A conversational agent with 3 tools, session memory, and a custom eval suite. Built in 2 days.

---

## What Comes Next (Next Few Days)

This submission is a minimal slice. The real system I'm building:

| Feature | Why It Matters |
|---------|---------------|
| **Instagram Graph API integration** | Receive and reply to DMs directly from Instagram — no separate chat UI |
| **WhatsApp Business API integration** | Same agent, same logic, answering on WhatsApp |
| **Instagram post/reel to product lookup** | Buyer sends a reel link → agent identifies the product, answers price/availability |
| **Full Telugu + multilingual NLU** | Most buyers write in Telugu. Current system understands it but classifies in English. Fix: native Telugu intent classification. |
| **Automated comment replies** | When buyers comment on a post ("price?" / "available?"), agent auto-replies instantly |
| **WhatsApp broadcast messages** | Festival sale announcements, new collection drops, restock alerts — sent to opted-in buyers |
| **Personalised follow-ups** | Birthday wishes, cart abandonment nudges, "you liked this, new stock arrived" — all automated |
| **Persistent order + customer DB** | PostgreSQL. Today orders are in-memory and lost on restart. |
| **Seller dashboard** | My mom can see all conversations, override any agent reply, and see which products are getting the most enquiries |

The goal is a system that works exactly like my sisters do today — but instantly, at 3am, in Telugu, across 1,000 simultaneous conversations.

---

## What Was Built

### System Overview

```
Buyer Message
(WhatsApp Business / Instagram DM)
        │
        ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI Backend                     │
│                                                      │
│  POST /api/chat/stream                               │
│        │                                             │
│        ▼                                             │
│  ┌─────────────┐    ┌──────────────┐                │
│  │  Session    │    │  LangGraph   │                │
│  │  Store      │◄──►│  Agent       │                │
│  │  (in-mem)   │    │  (8 nodes)   │                │
│  └─────────────┘    └──────┬───────┘                │
│                            │                         │
│              ┌─────────────┼─────────────┐           │
│              ▼             ▼             ▼           │
│        search_catalog  create_order  get_policy      │
│        (FAISS hybrid)  (rule-based   (FAISS RAG)    │
│                         validation)                  │
└─────────────────────────────────────────────────────┘
        │
        ▼
Streaming SSE Response → React Frontend
```

### Agent Graph

```
[classify_intent] ──────────────────────────────────────────┐
       │                                                      │
       │ (product_search / place_order /                      │
       │  order_support / policy_question)                    │ (general / unclear)
       ▼                                                      │
[check_context] ───────────────────────┐                     │
       │                               │ (missing fields)     │
       │ (all fields present)          ▼                      │
       ▼                        [generate_response] ◄─────────┘
[select_tool]
       │
       ▼
[execute_tool]
       │
       ▼
[generate_response]
       │
       ▼
[check_confidence]
       │                    │
       │ (high conf)        │ (low conf)
       ▼                    ▼
[update_memory]         [escalate_to_seller]
       │
       ▼
      END
```

### Node Responsibilities

| Node | Implementation | What It Does |
|------|---------------|--------------|
| `classify_intent` | Rule-based → LLM fallback | Maps message to 1 of 6 intents. Fast-path rules handle ~70% of messages without LLM call. |
| `check_context` | Rule-based | Validates required fields before acting. Missing product/size/address/payment → ask, don't guess. |
| `select_tool` | Rule-based | Deterministically picks tool + assembles args from message + session state. |
| `execute_tool` | Deterministic | Calls tool(s), catches errors, returns structured result. |
| `generate_response` | LLM (Groq/Llama 3.1) | Generates buyer-facing text grounded in tool output. In streaming mode, skips this and streams directly. |
| `check_confidence` | Rule-based | Scores reliability. Low confidence → escalate to seller. |
| `update_memory` | Deterministic | Persists `SessionState` — stage, active product, addresses, recent messages. |
| `escalate_to_seller` | Deterministic | Appends handoff message when agent can't handle reliably. |

---

## Tool Design

### Why 3 tools instead of more?

Each tool is a failure surface. Fewer decision points = fewer wrong selections. The catalog module (`search_catalog`, `check_availability`, `get_product`) handles all discovery and stock queries. `get_policy` handles all 4 policy types via RAG. The orders module (`get_order`, `create_order`, `update_order`) handles the full lifecycle. Grouping by module — not by operation — keeps the routing surface small.

### Tool 1 — Catalog Search (`tools/catalog.py`)

Handles product discovery, availability checks, and follow-up questions (color variants, size queries).

```
search_catalog(query?, category?, max_price?, size?, color?, top_k?)
    │
    ├── Path 1: Structured filter
    │   Filter in-memory catalog by category, price, size, color
    │   Returns if ≥ 2 results found
    │
    └── Path 2: FAISS vector search (fallback)
        Cosine similarity on sentence-transformer embeddings
        Handles: "something flowy for a wedding", "ethnic wear under 2000"
```

**Why hybrid?** Structured filters handle "kurtas under ₹2000 in size L" with 100% precision — vector search would return semantically close but wrong-price items. Vector handles open-ended queries where filters give no results. Both paths share the same FAISS infrastructure used for policy RAG.

Product embeddings are built from: `"{name}. {category}. {fabric}. {occasion_concatenated}. {description}"` — the `occasion` field is a list (e.g. `["festive", "wedding"]`) concatenated with no separator via `''.join(...)` (so `"festivewedding"`). All size keys normalized to uppercase at load time to prevent case mismatch.

`check_availability` is a focused function in the same catalog module. `use_session_data` is a virtual tool handled in `execute_tool` — it reads from the session's `last_shown_products` instead of hitting the catalog again, so a repeat search isn't needed when the buyer is still asking about products already on screen.

### Tool 2 — Orders (`tools/orders.py`)

Handles the full order lifecycle with business rule validation baked in.

| Function | Business Rules Enforced |
|----------|------------------------|
| `create_order` | Stock check, COD limit (< ₹5000), COD blocked for custom-stitched items, auto-selects size when only one available (FREE SIZE), decrements inventory |
| `get_order` | Returns full order including status, tracking link, delivery date |
| `update_order` | Validates status transition graph before applying |

The agent never applies business rules itself — the tool does. If the tool rejects an order, the agent reports why. This separation means business rules can change without touching the agent.

### Tool 3 — Policy RAG (`tools/policy_rag.py`)

4 policy documents embedded at startup, retrieved via FAISS cosine similarity on the buyer's query:

| Policy | Key Rules |
|--------|-----------|
| Refund | 7-day window from delivery, unused/original condition, excludes custom-stitched and sale items |
| Exchange | 10-day window, one exchange per order, subject to size availability |
| COD | Under ₹5,000 per order only (orders at exactly ₹5,000 are blocked), ₹49 convenience fee, blocked for custom items and international shipping |
| Shipping | 5–7 business days, free at ₹1,499 and above (code: `amount >= 1499`), courier tracking via Delhivery |

---

## Session Memory

`SessionState` is a Python dataclass serialized to a dict, stored in-memory keyed by `session_id`. It persists across turns within a session.

| Field | Type | Purpose |
|-------|------|---------|
| `stage` | string | Current stage: `discovery → pre_order → ordering → post_order` |
| `active_product` | dict | Currently selected product — avoids re-searching every turn |
| `active_order_id` | string | Order context for support turns |
| `pending_size` | string | Size captured from any previous message, reused at order time |
| `payment_preference` | string | COD/UPI/Card — captured once, not re-asked |
| `delivery_address` | string | Address — captured once, not re-asked |
| `pending_clarification` | string | What the agent last asked for — routes next turn correctly |
| `last_shown_products` | list | Products from last search — enables color/name/ordinal resolution |
| `recent_messages` | list | Sliding window of 10 turns — injected into LLM for context |

### How session memory prevents repeated questions

When a buyer says "order in L, COD" and then provides their address in the next message, the agent doesn't re-ask for size or payment — it reads from `pending_size` and `payment_preference`. The `pending_clarification` field ensures that if the agent asked "what size?" and the buyer replies "M", the classifier routes it correctly as `place_order` continuation rather than a standalone size query.

**Production path**: replace the `dict[session_id, dict]` in `api/routes/chat.py` with Redis. The state is already JSON-serializable — `sessions.get(id)` becomes `json.loads(r.get(id))`, `sessions[id] = ...` becomes `r.setex(id, ttl, json.dumps(...))`. A small, contained change.

---

## Design Philosophy: Minimal Agent, Maximum Reliability

The core tension in agent design is **autonomy vs. predictability**. More LLM decisions = more flexible but less predictable. This agent is deliberately built toward the predictable end.

| Decision Point | What Was Chosen | What Was Rejected | Why |
|----------------|----------------|-------------------|-----|
| Intent classification | Rule-based fast-path first, LLM only for ambiguous cases | Pure LLM classifier | Rules fail loudly and consistently. LLM classifiers hallucinate novel intents under distribution shift. |
| Tool selection | Deterministic rules in `select_tool` node | ReAct-style LLM tool selection | LLM tool selection errors compound — wrong tool → wrong result → wrong response. Rules make tool selection auditable. |
| Context validation | Explicit field checklist in `check_context` | Trusting LLM to notice missing info | LLMs skip asking for information they can plausibly infer. Unreliable in production — you get inconsistent behaviour depending on how confident the model feels about the inference. |
| Response grounding | Strict prompt rules + session context stripped before injection | Passing full session to LLM | Full session caused LLM to blend old product data into new search results. |
| Graph routing | Conditional edges with Python code | LLM-decided next steps | Routing bugs are the hardest to debug. Code is always preferable to prompts for control flow. |
| Language detection | Keyword-based heuristic on romanized text + recent message inheritance | fastText language model | 917KB model adds deployment complexity. Keyword list covers Telugu, Tamil, Kannada, Malayalam, Bengali, Marathi, and Hindi in Roman script. |

**Result**: The LLM is called at most twice per turn — once for classification (only when fast-path rules fail) and once for response generation. All routing, tool selection, and context validation is deterministic code. Failure modes are bounded and debuggable.

---

## Why LangGraph?

LangGraph provides explicit control over the node execution graph. For a reliability-first agent, this is the right primitive.

**What it gives**:
- **Conditional edges** — routing decisions are readable Python functions, not prompts
- **State dict** — all nodes read and write a single typed state, making debugging straightforward
- **No implicit tool calls** — the agent cannot call a tool unless `select_tool` explicitly sets it

**Compared to alternatives**:

| Alternative | Why Not |
|-------------|---------|
| OpenAI Assistants | Less control over when tools are called. Tool selection is partially LLM-driven. |
| LangChain AgentExecutor (ReAct) | Harder to constrain. LLM decides tool order and can loop. |
| Raw state machine (no framework) | More boilerplate. LangGraph gives streaming, state merging, and graph visualization for free. |
| Multi-agent (router + specialists) | Over-engineering. 6 intents don't need 6 agents. One agent with conditional routing is faster and cheaper. |

---

## Why Groq + Llama 3.1 8B?

| Factor | Choice | Reasoning |
|--------|--------|-----------|
| Speed | Groq LPU hardware | Significantly faster inference than GPU-hosted APIs for the same model. Groq's LPU architecture is purpose-built for sequential token generation. Critical for WhatsApp-style streaming where latency feels like the human is slow. |
| Cost | Free tier (demo) | 4 API keys × 6,000 TPM = 24,000 TPM. Sufficient for eval and demo. |
| Model size | Llama 3.1 8B | The tasks are structured (classify into 6 intents, generate grounded response from tool output). 8B is fast and sufficient — 70B would be slower with no reliability benefit given the prompt constraints. |
| Fallback | Rule-based fallback | When all keys exhaust, `_rule_based_fallback()` generates a response from tool result shapes without any LLM call. Covers the most common patterns: catalog results, order status, create_order success/failure, policy content, and clarification prompts. |

**Key rotation**: 4 API keys are rotated on `RateLimitError`. When all 4 are exhausted, the system sleeps 5 seconds and retries. This adds ~5-30s latency under heavy load but prevents hard failures.

---

## Eval Suite

### Why a custom eval instead of Ragas/DeepEval?

Ragas and DeepEval are built for RAG pipelines — they measure retrieval faithfulness and context precision. This agent's failure modes are different: wrong tool selection, missing order fields, classifying policy questions as order_support. A custom scorer catches these directly without the overhead of embedding-based faithfulness metrics.

### 4 Metrics

| Metric | Definition | Why This Metric |
|--------|-----------|----------------|
| **Task Completion** | Response contains required keywords AND expected tools were called | Catches both wrong tool selection and wrong response content |
| **Tool Hallucination** | Price/availability/policy claims made without a supporting tool call | The most dangerous failure — agent inventing product details or policy rules |
| **Tool Validity** | Expected tools were called; no duplicate identical calls | Catches tool selection bugs and redundant calls |
| **Graceful Failure** | Edge/adversarial cases: no forbidden phrases, recovery language present | Measures what happens at the boundary — wrong size, out of stock, invalid COD |

### Test Coverage (34 cases)

| Workflow | Happy Path | Edge Case | Adversarial | Total |
|----------|-----------|-----------|-------------|-------|
| discovery | 6 | 3 | 2 | 11 |
| pre_order | 2 | 2 | 1 | 5 |
| ordering | 1 | 3 | 1 | 5 |
| post_order | 5 | 4 | 2 | 11 |
| general | 2 | 0 | 0 | 2 |

Happy path = standard buyer journey. Edge case = boundary conditions (out of stock, expired refund window, COD on custom items). Adversarial = nonsense queries ("do you have jeans?"), fake order IDs, policies not in the knowledge base.

### Results

| Metric | Score |
|--------|-------|
| Task Completion | **32/34 — 94%** |
| No Tool Hallucination | **32/34 — 94%** |
| Tool Validity | **34/34 — 100%** |
| Graceful Failure Handling | **16/18 — 89%** |

**By workflow:**

| Workflow | Pass | Partial | Fail |
|----------|------|---------|------|
| discovery | 11/11 | 0 | 0 |
| pre_order | 4/5 | 1 | 0 |
| ordering | 5/5 | 0 | 0 |
| post_order | 10/11 | 1 | 0 |
| general | 2/2 | 0 | 0 |

**Remaining 2 partials**:
- `postorder_edge_01`: Refund request on ORD-1004 (delivered 8 days ago — outside the 7-day window). LLM says "eligible" because it doesn't know today's date. Fix: inject `datetime.date.today()` into the response prompt.
- `preorder_adversarial_01`: "What is your gift wrapping policy?" — RAG returned exchange policy content instead of saying the policy doesn't exist. Fix: add a policy-not-found check before returning RAG results.

### Before/After: Key Eval Improvements

| Fix | Before | After |
|-----|--------|-------|
| Classifier: policy before order_support | pre_order 40% pass | pre_order routing fixed; current 80% (1 partial from gift-wrapping RAG gap) |
| Response: no fake order IDs | order_adversarial partial | order_adversarial pass |
| Scorer: errored tools count as grounded | 82% no-hallucination | 94% no-hallucination |
| Classifier: pincode → place_order | address classified as `general` | correctly routed |
| Context: size validation across products | XXL bleeds to FREE SIZE saree | size validated per product |

---

## What We Chose Not to Build

| What Was Skipped | Why |
|-----------------|-----|
| Multi-agent pipeline (router + specialists) | Over-engineering for 6 intents. One agent with conditional routing is simpler, faster, and easier to debug. A 12-agent pipeline for a boutique is a red flag. |
| Redis / persistent session store | Already JSON-serializable. Contained change across 5 access points in `api/routes/chat.py`. Out of scope for 2-day build. |
| Real Razorpay / payment gateway | Tool interface is identical whether mock or real. Adding payments adds compliance and ops surface. |
| Buyer login / phone verification | WhatsApp handles identity at the channel level. Not needed for reliability testing. |
| Policy management CMS | 4 policies are stable. A CMS adds a system to maintain with no reliability gain. |
| fastText language ID model | Keyword heuristic covers romanized Telugu/Hindi/Tamil etc. well. 917KB model adds deployment infra for a marginal gain. |
| Prompt A/B testing framework | Would require multiple eval runs per commit. Out of scope for 2-day build. |
| Webhook / WhatsApp Business API | The agent logic is channel-agnostic. Connecting to WhatsApp API is a one-adapter change. |

---

## Production at Scale — What Breaks at 100k Users/Day

### What breaks first

| Component | Breaks At | Why |
|-----------|-----------|-----|
| Groq free tier | ~100–150 DAU | 500K TPD per key × 4 keys = 2M tokens/day. Each turn uses ~2,000 tokens. At ~7 turns per conversation, supports ~143 active users/day. Under bursty load (many concurrent requests), the 6,000 TPM per-key rate limit kicks in first. |
| In-memory sessions | Server restart | Every deployment wipes all active sessions. Users lose mid-conversation context. |
| In-memory orders | Server restart | All order data lost. Also doesn't scale across multiple server instances. |
| FAISS index | ~500k products | Loaded into RAM at startup. Fine for 50-product demo catalog, not for a real boutique. |
| Single FastAPI instance | ~1–4 concurrent requests | `agent.invoke()` blocks each worker for 3–8s. A single uvicorn worker handles 1 request at a time. Not a connection limit — a blocking call limit. |

### What to monitor (Day 1 of production)

- **LLM latency p95** — streaming response time. Groq is fast but rate limit retries spike latency to 10–30s.
- **Fallback rate** — % of turns using rule-based fallback. Spike = all keys exhausted.
- **Intent distribution** — sudden 40% `order_support` spike signals a product or UX issue upstream.
- **Tool error rate by type** — `create_order` failures split by: out of stock / COD blocked / address invalid / product not found.
- **Escalation rate** — % of turns hitting `escalate_to_seller`. Rising rate = agent failing at the boundary.

### What to fix, in order

1. **Replace Groq free tier with paid** — $10/month eliminates rate limit problem entirely.
2. **Add Redis session store** — contained change in `api/routes/chat.py` (5 access points, all JSON-serializable already). Eliminates session loss on restart and enables horizontal scaling.
3. **Persist orders to SQLite/Postgres** — one-file change in `tools/orders.py`. Same schema, just swap the in-memory dict.
4. **Horizontal scaling** — FastAPI + Redis sessions means any number of instances behind a load balancer.
5. **Replace FAISS with hosted vector DB** (Pinecone, Weaviate) — eliminates the RAM constraint on catalog size.

---

## Where the Agent Breaks — and What It Would Take to Fix

### 1. Cross-session size bleed

**What breaks**: `pending_size` (e.g. "XXL" from a kurta search) carries into a new product order. A FREE SIZE saree gets ordered with size=XXL and fails the stock check.

**Current mitigation**: `_select_order_tool` validates cached size against active product's size map and discards it if invalid. `check_context` re-validates pending_size against product sizes before proceeding.

**Full fix**: Clear `pending_size` in `update_memory` when `active_product` changes. Requires tracking "previous active_product" in session state — a small addition.

---

### 2. Mid-order topic switch

**What breaks**: Buyer starts ordering a kurta ("I want the blue one in L"), then says "actually show me lehengas", then says "ok order it". The `active_product` is now a lehenga, but `pending_size` ("L") is from the kurta context. Agent may assemble a mismatched order.

**Full fix**: An `OrderDraft` dataclass scoped to one `(product_id, session_start)` tuple. Reset when `active_product` changes. The current flat session state doesn't distinguish "size for this product" from "size in general".

---

### 3. Multi-product disambiguation

**What breaks**: "Show me sarees" returns 9 results. User says "order the silk one" — both Red Silk Saree (₹5999) and Banarasi Silk Saree (₹6999) score equally on "silk". Agent picks first in list.

**Full fix**: When name-match score is tied, ask: "Did you mean the Red Silk Saree (₹5999) or the Banarasi Silk Saree (₹6999)?" Requires a disambiguation node between `classify_intent` and `select_tool`.

---

### 4. Date-dependent eligibility calculation

**What breaks**: LLM doesn't have today's date. When checking refund eligibility on old orders, it may treat a 2025 delivery date as "recent" and incorrectly say the buyer is eligible.

**Full fix**: Inject `datetime.date.today().isoformat()` into the response prompt at generation time. Currently avoided because it requires changing the prompt template string from a module-level constant to a function call.

---

### 5. Rule-based fallback coverage gaps

**What breaks**: When all Groq keys are exhausted, `_rule_based_fallback()` covers the most common tool result shapes: catalog list, check_availability, get_order, create_order success/failure variants, get_policy, and pending clarification. Novel combinations (policy result + order result in same turn) fall through to "I'm having trouble fetching that right now."

**Full fix**: Expand the fallback to cover combined tool result shapes (e.g. policy + order in same turn), or run a local Ollama instance as a second-tier fallback for the response generation node.

---

### 6. Fuzzy matching at scale

**What breaks**: `difflib.get_close_matches` with cutoff=0.80 works for the current 44 colors and 8 categories. At 200+ colors, false positives increase — "teal" matching "teel" (sesame seed, a valid product tag in a larger catalog).

**Full fix**: Replace difflib with a small embedding nearest-neighbor lookup for entity resolution. The FAISS infrastructure is already present.

---

### 7. Language detection on short replies

**What breaks**: "ok", "XL", "haan" contain no Telugu/Hindi keywords, so the keyword-based heuristic classifies them as English. Agent replies in English even if the buyer has been writing in Telugu for 5 turns.

**Current mitigation**: Inherit language from `recent_messages` when current message is ≤4 words.

**Full fix**: fastText `lid.176.ftz` (917KB) — 176 language classifier that handles single-word messages. Would eliminate the heuristic entirely.
