"""Intent classification prompt."""

CLASSIFY_PROMPT = """Classify the buyer's message into exactly one intent.

## Intents:
- product_search: Looking for products, asking about availability, prices, sizes, colors, or wanting to browse the catalog.
- policy_question: Asking about return policy, exchange policy, COD rules, shipping timeline, or any business policy.
- place_order: Wants to buy/book/order a product. May be providing address, size, payment details, or saying "I'll take it" / "book it".
- order_support: Asking about an existing order – tracking, status, refund request, exchange request, cancellation.
- general: Greetings, thank you, or casual conversation that doesn't fit above categories.
- unclear: Message is ambiguous or doesn't provide enough information to classify.

## Session Context:
- Current stage: {stage}
- Active product: {active_product}
- Active order: {active_order_id}
- Pending clarification: {pending_clarification}
- Products shown last turn: {last_shown_products}

## Recent Conversation:
{recent_context}

## Important Rules:
- If buyer provides info that answers a pending clarification (like an order ID or address), classify based on the ORIGINAL intent, not the info itself.
  Example: If pending_clarification is "order_id" and buyer says "ORD-1001", classify as "order_support" not "unclear".
- If buyer says "I'll take it" or "book it" while an active_product exists, classify as "place_order".
- If buyer asks about price/availability, always classify as "product_search" even if it sounds like a casual question.
- If the agent just listed products and the buyer replies with ONLY a size (S, M, L, XL, XS, XXL) or a size + color, classify as "product_search".
- Short replies (single letter like "L", "M") should be interpreted in context of the last agent message.
- If an active_order_id exists and the last agent message was about changing/updating payment method or sending a payment link, and buyer says "yes"/"ok"/"sure"/"confirm", classify as "order_support".
- "change payment", "switch to UPI", "pay by card" on an existing order → always "order_support".
- "Is COD available?", "Do you have cash on delivery?", "COD milega?" → always "policy_question".
- "Kab tak aayega?", "When will it arrive?", "How many days for delivery?" → always "policy_question".
- Hindi/Hinglish browse requests like "Kuch dikhao", "Kuch acha dikhao yaar", "Collection dikhao" → always "product_search".
- Questions about refund/return/exchange eligibility for an existing order → "order_support", not "policy_question".

## Buyer's message: {message}

Respond with ONLY the intent label. Nothing else."""
