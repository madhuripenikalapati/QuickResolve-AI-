# QuickResolve AI – Architecture

## Design Philosophy

**Reliability over complexity.** Every architectural decision optimizes for predictable, grounded responses rather than impressive-sounding features.

- 3 tools instead of 10: fewer tools = fewer failure modes
- Rule-based routing instead of LLM-based: deterministic control flow
- Tool-grounded response generation: GPT-4o only generates text; it never invents facts
- Eval-first: 30+ test cases written before implementation

---

## Agent Graph (LangGraph)

```
[classify_intent] ──→ [check_context] ──→ [select_tool] ──→ [execute_tool]
        │                    │                                      │
        │ (general/unclear)  │ (missing info)                      ↓
        ↓                    ↓                            [generate_response]
[generate_response]  [generate_response]                          │
                                                                   ↓
                                                        [check_confidence]
                                                         /              \
                                                   (high conf)       (low conf)
                                                        ↓                ↓
                                               [update_memory]       [escalate]
```

### Node Responsibilities

| Node | Type | Responsibility |
|------|------|---------------|
| `classify_intent` | LLM | Classify message into 6 intents using GPT-4o |
| `check_context` | Rule-based | Validate all required info exists before acting |
| `select_tool` | Rule-based | Choose tool + prepare args from message + session |
| `execute_tool` | Deterministic | Call tool(s), catch errors, return structured result |
| `generate_response` | LLM | Generate buyer-facing text grounded in tool output |
| `check_confidence` | Rule-based | Score response reliability, flag for escalation |
| `update_memory` | Deterministic | Update SessionState sliding window |
| `escalate_to_seller` | Deterministic | Append escalation message, hand off |

---

## Tools

### 1. Catalog Tool (`tools/catalog.py`)

Two-path hybrid search:

```
search_catalog(query?, category?, max_price?, size?, color?)
    ├── Path 1 (Structured): Filter by category, price, size, color
    │   └── Returns if ≥2 results found
    └── Path 2 (Vector): FAISS cosine similarity on product embeddings
        └── Fallback when structured search yields < 2 results
```

Product embeddings are built once on module load from a rich text field:
`"{name}. {category}. {fabric}. {occasions}. {description}"`

### 2. Order Tool (`tools/orders.py`)

CRUD with business rule validation:
- `get_order(order_id)` – lookup by ID
- `create_order(...)` – validates stock availability, COD eligibility (amount < ₹5000, not custom-stitched), then creates and decrements inventory
- `update_order(order_id, updates)` – validates status transition graph before applying

### 3. Policy RAG (`tools/policy_rag.py`)

4 documents embedded at startup, retrieved via FAISS cosine similarity:
- `refund_policy.md` – 7-day window, custom-stitched/sale exclusions
- `exchange_policy.md` – 10-day window, one exchange per order
- `cod_policy.md` – ₹5000 limit, ₹49 convenience fee
- `shipping_policy.md` – 5-7 business days, free shipping above ₹1499

---

## Session Memory

`SessionState` is a dataclass serialized to dict and stored in-memory per `session_id`. It carries:
- Conversation stage (`discovery → pre_order → ordering → post_order`)
- Active product and order context (reduces need for repeat tool calls)
- Sliding window of last 5 message exchanges (injected into system prompt)
- Pending clarification state (guides next-turn classification)

Production upgrade: replace `dict[session_id, dict]` in `api/routes/chat.py` with Redis.

---

## Eval Framework

### 4 Metrics

| Metric | Implementation |
|--------|---------------|
| **Task Completion** | Check response contains required terms + expected tools were called |
| **Tool Hallucination** | Detect price/availability/policy claims without corresponding tool call |
| **Invalid Tool Use** | Verify expected tools were called; detect duplicate identical calls |
| **Graceful Failure** | For edge/adversarial cases: verify no forbidden terms, recovery language present |

### Test Coverage (33 cases)

| Workflow | Happy Path | Edge Case | Adversarial |
|----------|-----------|-----------|-------------|
| discovery | 5 | 3 | 2 |
| pre_order | 2 | 2 | 1 |
| ordering | 1 | 3 | 1 |
| post_order | 4 | 4 | 2 |
| general | 2 | 0 | 0 |

---

## Key Design Decisions

### Why hybrid search instead of pure vector?
Structured filters handle "kurtas under ₹2000 in size L" with 100% precision – vector search would return semantically similar but wrong-price results. Vector handles open queries like "something flowy for a wedding" where no exact filters apply. Same FAISS infra serves both catalog and policy RAG.

### Why rule-based routing over LLM routing?
Control flow determinism. An LLM router adds latency and can hallucinate routing decisions. The 6 intent classes map cleanly to rule-checkable patterns; the cost of determinism is ~50 lines of regex.

### Why 3 tools instead of more granular ones?
Fewer tools = fewer wrong tool selections. `search_catalog` handles both browsing and availability; `get_policy` handles all 4 policies via RAG. Each additional tool is another thing that can be called incorrectly or out of order.

### Why in-memory session storage?
Simplicity for demo. The session dict is already serializable; swapping to Redis requires changing one line (`sessions[id]` → `redis.set(id, json.dumps(data))`).
