# QuickResolve AI

> Meraki Labs Work Trial | PS3: Minimal Agent, Maximum Reliability

My mom runs a women's clothing boutique on Instagram. She gets ~1,000 messages a day on WhatsApp and Instagram DMs — buyers asking prices, placing orders, checking stock. My sisters reply manually. If they reply fast, the buyer converts. If they're late, the sale is gone.

I built this to fix that.

---

## Demo: Taara Boutique

QuickResolve AI powers customer support for **Taara Boutique** — an Instagram fashion store that receives buyer messages on **WhatsApp Business** and **Instagram DMs**. Buyers discover products on Instagram, then message directly to ask questions, place orders, and resolve issues. The agent handles the complete buyer journey across both channels:

- **Product Discovery** – hybrid search (structured filters + vector similarity) across 50 products with real product images
- **Policy Q&A** – RAG over 4 policy documents (refund, exchange, COD, shipping)
- **Order Placement** – validates stock, COD eligibility, creates orders with payment links
- **Post-Order Support** – tracking, refund eligibility checks, exchange handling

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent Framework | LangGraph (state machine, 8 nodes) |
| LLM | Groq — `llama-3.1-8b-instant` (classify + response) |
| Search | sentence-transformers (all-MiniLM-L6-v2) + FAISS |
| Backend | Python 3.9+ + FastAPI |
| Frontend | React (Vite) + Tailwind CSS |
| Eval | Custom framework – 4 metrics, 30+ test cases |

## Quick Start

### Prerequisites
- Python 3.9+
- Node.js 18+
- Groq API key — **free, no credit card needed** → [console.groq.com](https://console.groq.com) → sign up → API Keys → Create key

### Setup

```bash
git clone https://github.com/madhuripenikalapati/QuickResolve-AI-.git
cd QuickResolve-AI-

# 1. Backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Copy .env — pre-obtained keys are already included, ready to run
cp .env.example .env

# 3. Frontend
cd frontend && npm install && cd ..
```

### .env — no changes needed to run

`.env.example` ships with 5 pre-obtained Groq keys (free tier, no credit card). Copy it and run:

```
GROQ_API_KEY=gsk_...            ← pre-filled, works immediately
GROQ_API_KEYS=gsk_...,gsk_...  ← 4 extra keys for round-robin rotation
GROQ_MODEL=llama-3.1-8b-instant
GROQ_CLASSIFY_MODEL=llama-3.1-8b-instant
LLM_PROVIDER=groq
```

**More keys = faster throughput.** Each free Groq key gives 6,000 TPM. 5 keys = 30,000 TPM effective capacity. The system rotates keys round-robin after every call — not just on failure — so load spreads evenly. To add your own: get a free key at [console.groq.com](https://console.groq.com) and append it to `GROQ_API_KEYS`.

### Run

```bash
# Terminal 1: Backend
source venv/bin/activate          # Windows: venv\Scripts\activate
python3 run.py
```

> **First run only**: the server downloads the `all-MiniLM-L6-v2` sentence-transformer model (~22MB) to build the FAISS index. This takes 30–60s. You'll see `Application startup complete` when it's ready.

```bash
# Terminal 2: Frontend
cd frontend
npm run dev
```

Open http://localhost:5173

### Run Eval Suite

```bash
curl -X POST http://localhost:8000/api/eval/run
```

Or use the **Eval** tab in the UI.

## Architecture

```
User Message
    → classify_intent (llama-3.1-8b-instant, with rule-based fast path)
    → check_context (rule-based: size follow-up, product pinning)
    → select_tool (rule-based)
    → execute_tool (3 tools)
    → generate_response (llama-3.1-8b-instant, grounded in tool output)
    → check_confidence (rule-based)
    → update_memory (extracts size, address, payment from message)
    → END / escalate_to_seller
```

**3 Tools:**
1. **Catalog Lookup** – structured filters first, vector similarity fallback
2. **Order Manager** – CRUD with validation (stock, COD eligibility, status transitions)
3. **Policy RAG** – sentence-transformers + FAISS over 4 policy documents

**Session Memory:**
- `pending_size`, `delivery_address`, `payment_preference` persist across turns
- `active_product` pinned from `last_shown_products` by name-matching
- `recent_messages` used for confirmation-flow context

**4 Eval Metrics:**
| Metric | What It Measures |
|--------|-----------------|
| Task Completion Rate | Did the agent complete the user's request? |
| Tool Hallucination Rate | Did the agent state facts without calling a tool? |
| Invalid Tool Use Rate | Were the right tools called with valid arguments? |
| Graceful Failure Rate | Did the agent handle edge cases without crashing? |

## Eval Results

| Metric | Score | Detail |
|--------|-------|--------|
| Task Completion | **94%** | 32/34 pass |
| No Hallucination | **94%** | 32/34 clean |
| Valid Tool Use | **100%** | 34/34 valid |
| Graceful Failure | **89%** | 16/18 graceful |

Run `curl -X POST http://localhost:8000/api/eval/run` or use the **Eval** tab in the UI to re-run.

## Observability

Every turn logs a structured JSON record to stdout:

```json
{
  "trace_id": "a1b2c3d4",
  "session_id": "session-1234567890",
  "event": "turn_complete",
  "intent": "product_search",
  "confidence": 1.0,
  "tools": ["search_catalog"],
  "tool_errors": [],
  "escalated": false,
  "latency_ms": 1843
}
```

What to monitor in production: `latency_ms` p95, `tool_errors` rate, `escalated` rate, `confidence` distribution.

## Project Structure

```
QuickResolve-AI-/
├── agent/          # LangGraph state machine + nodes
├── tools/          # 3 tools + mock data
├── eval/           # Test cases + scoring
├── api/            # FastAPI backend
├── frontend/       # React + Tailwind UI
├── docs/           # Architecture doc
├── run.py          # Entry point
└── requirements.txt
```

## What I Built, What I Skipped, and Why

**Built:** Complete agent with 3 tools, 4 workflows, session memory, eval framework, product image cards, and a two-panel debug UI.

**Scoped out:**
- **Persistent storage** – sessions and orders are in-memory dicts. Redis + PostgreSQL for production.
- **Auth/rate limiting** – no per-user limits on `/api/chat`. Needed before any public deployment.
- **Multi-language NLU** – Hindi/Hinglish classification is present but native Telugu intent classification is not. Short replies ("ok", "haan") default to English.
- **Langfuse / tracing** – structured JSON logs are in place; a proper trace store would be next.

**Key design decision:** Rule-based `fast_classify` for bare size tokens and order IDs skips the LLM entirely — 0ms classify for the most common follow-up patterns. LLM only fires when the intent is genuinely ambiguous.

## What Breaks at Scale

| Bottleneck | Why | Fix |
|---|---|---|
| In-memory sessions | Lost on restart, can't horizontally scale | Redis with TTL |
| Groq free tier (500K TPD/key) | Each turn uses ~2,000–3,000 tokens (prompts + tool results + session). 4 free keys ≈ 2M tokens/day — supports ~100–150 active users/day | Groq paid tier or self-hosted Llama |
| Single-process FastAPI | `agent.invoke()` blocks ~3–8s per request | `uvicorn --workers 4` + async queue |
| In-memory orders | No persistence, no consistency across instances | PostgreSQL |

At 10–50 concurrent users (demo/hackathon scale): works fine. At 10k DAU: sessions and Groq quota are the first two things that break.

## Author

**Madhuri Penikalapati**  
Built for Meraki Labs founding AI engineer work trial.
