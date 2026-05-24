# PS-3 Guiding Principles — My Responses

---

## 1. Show your thinking, not just your code. The written doc matters as much as the repo.

The reason I built this is personal.

My mom runs a women's clothing boutique on Instagram. She posts her collection — sarees, kurtas, lehengas — and buyers reach out on WhatsApp Business and Instagram DMs. She gets ~1,000 messages a day. My sisters help reply. What we observed: if you reply in minutes, the buyer converts. Reply hours later, they've already bought from someone else.

Most buyers write in Telugu or Telugu+English. Many send back an Instagram post asking "how much?" or "available in XL?". There's no cart, no checkout — just DMs and trust.

When I saw PS-3, I immediately recognised this problem. I built a minimal version of the agent I want my mom to actually use.

**On the agent design choices:**

The biggest decision was where to put intelligence. I chose deterministic Python for all routing and a fast-path rule engine (`_fast_classify`) that handles ~70% of messages without touching the LLM. The LLM is called at most twice per turn — once for classification (only when rules can't decide) and once for response generation.

Why rule-based over LLM for routing? Four concrete reasons:

- **Determinism**: the same message always gets the same intent. LLMs at temperature=0 are mostly consistent but not guaranteed — especially on short, ambiguous messages like "ok" or "XL".
- **Debuggability**: when a rule fails, you see exactly which pattern didn't match and fix it in one line. When an LLM classifier misfires, you don't know why — different tokenization? context bleeding? you can't tell without logging every prompt.
- **Latency**: rule-based fast-classify is 0ms. An LLM classify call adds 500–1,500ms per turn. For ~70% of messages that are unambiguous (a size token, a 6-digit pincode, an order ID), that's wasted time.
- **Cost**: every LLM call burns tokens. At 1,000 messages/day, skipping the classifier LLM for ~70% of messages reduces total token usage by roughly 30–35% (response generation still runs for every message).

The LLM is still used for genuinely ambiguous messages — multi-intent queries, sarcasm, mixed-language requests where rules can't decide. That's the right tradeoff: deterministic code for the easy 70%, LLM for the hard 30%.

The three tool modules were chosen by collapsing what could be six or seven tools into three logical groups. The catalog module (`search_catalog`, `check_availability`, `get_product`) handles all discovery and stock queries. The orders module (`get_order`, `create_order`, `update_order`) handles the full order lifecycle. `get_policy` handles all four policy types via RAG. Fewer decision points = fewer wrong selections. This is the core of "minimal agent, maximum reliability."

---

## 2. Production-first. What breaks when 100k+ users are on the platform? What would you monitor? What would you fix first?

**What breaks, in order:**

| # | What | Why | Users at which it breaks |
|---|------|-----|--------------------------|
| 1 | In-memory sessions | Lost on every restart; can't share across multiple instances | Any server restart |
| 2 | Groq free tier (500K TPD/key) | Each turn uses ~2,000–3,000 tokens (prompt templates + tool results + session context). 4 free keys ≈ 2M tokens/day → supports ~100–150 active users/day | ~100–150 DAU |
| 3 | Single-process FastAPI | `agent.invoke()` blocks 3–8s per request; single uvicorn worker handles 1 blocking call at a time | ~1–4 concurrent |
| 4 | In-memory orders | Lost on every restart; no consistency across instances | Any server restart |
| 5 | difflib fuzzy matching | False positives increase with catalog size | ~200+ products |

**What I'd monitor from Day 1:**

The current production log (`logger.info` in `api/routes/chat.py`) emits these fields per turn:

- `latency_ms` p95 — anything above 8s is a failed conversation
- `tool_errors` rate by tool type — `create_order` failures tell you if stock data is stale
- `escalated` rate — rising escalation = agent hitting its boundary
- `intent=unclear` rate — rising unclear = new message patterns the classifier hasn't seen

One metric not yet in the production log but worth adding:

- `tool_hallucination` rate — requires a post-turn checker that flags price/policy claims made without a supporting tool call. Eval shows 0 hallucination cases (100% clean) after fixing the scorer to correctly attribute COD restriction responses to the order tool. In production, any hallucination on price or policy breaks buyer trust permanently — worth the instrumentation cost.

**What I'd fix first:**

Redis for session store. It's a one-afternoon change (`sessions: dict` → `redis.get/set`) and it unlocks horizontal scaling and restarts without data loss. Everything else can wait. Sessions are the foundation — without them, every other improvement is built on sand.

---

## 3. Eval is not optional. However you define quality, measure it. A system with no eval is a system you cannot improve.

I wrote a custom eval suite because existing frameworks (Ragas, DeepEval) measure the wrong things for this agent. They measure RAG retrieval faithfulness. This agent's failure modes are different: wrong tool selection, missing order fields, classifying "return policy" as `order_support` instead of `policy_question`, inventing a policy rule that wasn't in the tool result.

**4 metrics, 34 test cases across 5 workflows:**

| Metric | Definition | Why It Matters |
|--------|-----------|----------------|
| Task Completion | Did the agent complete what the buyer asked? (pass/partial/fail) | Core correctness — did it actually help? |
| Tool Hallucination | Did the agent state a fact (price, stock, policy) without a supporting tool call? | The most dangerous failure — inventing product details breaks buyer trust permanently |
| Tool Validity | Were the right tools called? Were there duplicate calls? | Wrong tool = wrong answer, even if the LLM sounds confident |
| Graceful Failure | When something went wrong, did the agent handle it without crashing or exposing errors? | Edge cases happen in production. Crashing is worse than saying "I'm not sure." |

**Current scores:** 91% task completion (31/34) · 100% no hallucination (34/34) · 100% tool validity (34/34) · 89% graceful failure (16/18)

**What the eval caught that I would have missed:**
- "Return policy" being routed to `order_support` because the word "return" triggered the wrong rule — **fixed**
- The LLM writing "ORD-XXXX" literally (copied from a prompt example) when an order failed — **fixed**
- Hallucination false positives: ₹5,000 (COD limit from `get_policy`) being flagged as a price hallucination — **fixed** (scorer updated)
- Gift wrapping policy question being answered with exchange policy because the RAG returned the wrong doc — **still a partial** (RAG returns closest match even when no policy exists; fix is a policy-not-found check before returning results)

Three were fixed and verified by re-running. The fourth is the remaining `preorder_adversarial_01` partial in the eval results. Without the eval, I'd have shipped all four without knowing.

---

## 4. Scope ruthlessly. Tell us what you chose not to build and why. That is part of the answer.

| Not Built | Why Not |
|-----------|---------|
| Instagram Graph API / WhatsApp Business API | Integration is 2-3 days of OAuth + webhook setup. The agent logic is what needed proving first. The API layer is additive once the core is reliable. |
| Persistent storage (Redis + PostgreSQL) | In-memory is fine for a demo. Adding persistence before proving the agent's reliability would have been optimising the wrong layer. |
| Per-user auth and rate limiting | No public deployment. Would add before opening to real users. |
| Streaming eval coverage | Streaming is implemented at `/api/chat/stream` and used by the frontend. The eval suite calls the non-streaming endpoint to get deterministic, comparable responses. Streaming itself is not a gap. |
| Langfuse / distributed tracing | Structured JSON logs are in place. A trace store is the next step, not the first. |
| Multi-seller support | One seller (my mom's boutique) is the target. Multi-tenancy is a future architectural change, not something to build speculatively. |
| Voice messages | A significant portion of WhatsApp messages in India are voice notes. Whisper transcription is the fix. Not built because the text agent needed to be solid first. |
| Automated comment replies | Post/reel comment automation is on the roadmap but requires Instagram Graph API integration first. |

The rule: if it doesn't make the agent more reliable for the core 4 workflows (search, order, policy, post-order), it didn't get built.

---

## 5. Be honest about limitations. We want to know what parts of the system you still need to address, not just where it works.

**What doesn't work well right now:**

**Date-dependent refund eligibility.** The LLM doesn't know today's date at inference time. When checking if a buyer is within the 7-day refund window, it may misjudge old orders as recent. Fix is simple — inject `datetime.date.today()` into the response prompt — but I avoided it mid-session to not break other response patterns. This is the most impactful outstanding bug.

**Mid-order topic switches.** Buyer asks about a kurta in L, then switches to asking about sarees, then says "order it." The agent may assemble a mismatched order: saree + size L from the kurta context. Current mitigation catches many cases but not all. Fix requires an `OrderDraft` dataclass scoped to one `(product_id, session)` tuple.

**Telugu classification.** Short messages ("ok", "haan", "XL") contain no Telugu/Hindi keywords, so the keyword-based heuristic classifies them as English. The agent replies in English even when the buyer has been writing in Telugu. Fix: fastText `lid.176.ftz` (917KB) for 176-language single-word classification.

**Multi-product disambiguation.** "Order the silk one" when two silk sarees are in context — agent picks first in list. Should ask "Did you mean Red Silk (₹5,999) or Banarasi Silk (₹6,999)?" Requires a disambiguation node in the graph.

**Groq rate limits under load.** 4-key rotation with 5s sleep handles bursts. At sustained load (>20 concurrent users), this becomes a hard bottleneck. Fix: Groq paid tier or self-hosted Llama 3.1 via Ollama.

**What I'd fix in order if given another week:**
1. Inject today's date into response prompt (1 hour)
2. OrderDraft scoped state (half a day)
3. fastText language detection (half a day)
4. Redis session store (1 day)
5. Instagram Graph API integration (2-3 days)
