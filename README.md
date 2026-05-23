# QuickResolve AI

> Meraki Labs Work Trial | PS3: Minimal Agent, Maximum Reliability

AI-powered D2C customer support agent with hybrid search, policy RAG, and order management. Built with LangGraph + Groq (Llama 3.1). Includes custom eval framework with 30+ automated test cases across 4 reliability metrics.

## Demo: Taara Boutique

QuickResolve AI powers customer support for "Taara Boutique" – a fictional Jaipur-based fashion seller on Instagram. It handles the complete buyer journey:

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
- Groq API key (free at [console.groq.com](https://console.groq.com))

### Setup

```bash
git clone https://github.com/madhuripenikalapati/QuickResolve-AI-.git
cd QuickResolve-AI-

# Backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Add your GROQ_API_KEY to .env

# Frontend
cd frontend
npm install
cd ..
```

### .env minimum config

```
GROQ_API_KEY=your_key_here
LLM_PROVIDER=groq
GROQ_MODEL=llama-3.1-8b-instant
GROQ_CLASSIFY_MODEL=llama-3.1-8b-instant
```

### Run

```bash
# Terminal 1: Backend
python3 run.py

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

| Metric | Score |
|--------|-------|
| Task Completion | __%  |
| Tool Hallucination (clean) | __% |
| Valid Tool Use | __% |
| Graceful Failure | __% |

*Run `curl -X POST http://localhost:8000/api/eval/run` to populate*

## Observability

Every turn logs a structured JSON record to stdout:

```json
{
  "trace_id": "a1b2c3d4",
  "session_id": "session-1234567890",
  "event": "turn_complete",
  "intent": "product_search",
  "confidence": 0.92,
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
- **Streaming responses** – LLM responses are buffered. FastAPI + SSE would fix latency feel.
- **Multi-language NLU** – Hindi/Hinglish detection is present but classification still runs in English.
- **Langfuse / tracing** – structured JSON logs are in place; a proper trace store would be next.

**Key design decision:** Rule-based `fast_classify` for bare size tokens and order IDs skips the LLM entirely — 0ms classify for the most common follow-up patterns. LLM only fires when the intent is genuinely ambiguous.

## What Breaks at Scale

| Bottleneck | Why | Fix |
|---|---|---|
| In-memory sessions | Lost on restart, can't horizontally scale | Redis with TTL |
| Groq free tier (500K TPD) | 10k users × 5 turns × 400 tokens = 20M/day | Groq paid tier or self-hosted Llama |
| Single-process FastAPI | `agent.invoke()` blocks ~3–8s per request | `uvicorn --workers 4` + async queue |
| In-memory orders | No persistence, no consistency across instances | PostgreSQL |

At 10–50 concurrent users (demo/hackathon scale): works fine. At 10k DAU: sessions and Groq quota are the first two things that break.

## Author

**Madhuri Penikalapati**  
Built for Meraki Labs founding AI engineer work trial.
