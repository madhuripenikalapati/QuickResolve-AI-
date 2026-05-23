from __future__ import annotations
"""Product catalog tool with hybrid search (structured + vector)."""

import json
from pathlib import Path
from tools.embeddings import embed_texts, build_faiss_index, search_index

_catalog = {}
_product_list = []
_product_index = None
CATALOG_COLORS: set[str] = set()
CATALOG_CATEGORIES: set[str] = set()


def _load_catalog():
    global _catalog, _product_list, _product_index, CATALOG_COLORS, CATALOG_CATEGORIES

    data_path = Path(__file__).parent / "mock_data" / "products.json"
    with open(data_path, "r") as f:
        _catalog = json.load(f)

    # Normalize size keys to uppercase so all lookups ("FREE SIZE", "Free Size") match
    for product in _catalog.values():
        if "sizes" in product:
            product["sizes"] = {k.upper(): v for k, v in product["sizes"].items()}

    _product_list = list(_catalog.items())

    descriptions = []
    for pid, product in _product_list:
        text = f"{product['name']}. {product['category']}. {product['fabric']}. "
        text += f"{''.join(product.get('occasion', []))}. {product['description']}"
        descriptions.append(text)
        for color in product.get("colors", []):
            CATALOG_COLORS.add(color.lower())
        if product.get("category"):
            CATALOG_CATEGORIES.add(product["category"].lower())

    embeddings = embed_texts(descriptions)
    _product_index = build_faiss_index(embeddings)


_load_catalog()


def search_catalog(
    query: str | None = None,
    category: str | None = None,
    max_price: int | None = None,
    min_price: int | None = None,
    size: str | None = None,
    color: str | None = None,
    colors: list[str] | None = None,  # OR filter — matches any of the given colors
    top_k: int = 5,
) -> list[dict]:
    results = []

    # Normalise: merge single color into colors list for uniform handling
    all_colors = [c.lower() for c in (colors or [])]
    if color and color.lower() not in all_colors:
        all_colors.append(color.lower())

    def _color_matches(product: dict, wanted: str) -> bool:
        pc = product.get("colors", [])
        primary_match = pc and pc[0].lower() == wanted
        name_match = wanted in product["name"].lower()
        any_match = any(c.lower() == wanted for c in pc)
        return primary_match or name_match or (any_match and len(pc) <= 2)

    if category or max_price or min_price or size or all_colors:
        for pid, product in _product_list:
            match = True

            if category and product["category"].lower() != category.lower():
                match = False
            if max_price and product["price"] > max_price:
                match = False
            if min_price and product["price"] < min_price:
                match = False
            if size:
                size_upper = size.upper()
                has_free_size = product["sizes"].get("FREE SIZE", 0) > 0
                if not has_free_size:
                    if size_upper not in product["sizes"] or product["sizes"][size_upper] == 0:
                        match = False
            if all_colors:
                if not any(_color_matches(product, c) for c in all_colors):
                    match = False

            if match:
                result = {**product, "product_id": pid}
                if size:
                    result["requested_size_available"] = product["sizes"].get(size.upper(), 0) > 0
                    result["requested_size_stock"] = product["sizes"].get(size.upper(), 0)
                results.append(result)

        if len(results) >= 2 or not query:
            return results[:top_k]

    if query:
        vector_results = search_index(_product_index, query, top_k=top_k)
        seen_ids = {r["product_id"] for r in results}

        for idx, score in vector_results:
            pid, product = _product_list[idx]
            if pid not in seen_ids and score > 0.2:
                result = {**product, "product_id": pid, "similarity_score": round(score, 3)}
                if size:
                    result["requested_size_available"] = product["sizes"].get(size.upper(), 0) > 0
                    result["requested_size_stock"] = product["sizes"].get(size.upper(), 0)
                results.append(result)
                seen_ids.add(pid)

        return results[:top_k]

    return results[:top_k]


def get_product(product_id: str) -> dict | None:
    product = _catalog.get(product_id)
    if product:
        return {**product, "product_id": product_id}
    return None


def check_availability(product_id: str, size: str) -> dict:
    product = _catalog.get(product_id)
    if not product:
        return {"error": f"Product {product_id} not found", "available": False}

    size_upper = size.upper()
    quantity = product["sizes"].get(size_upper, 0)
    other_sizes = {s: qty for s, qty in product["sizes"].items() if qty > 0 and s != size_upper}

    return {
        "product_id": product_id,
        "product_name": product["name"],
        "size": size_upper,
        "available": quantity > 0,
        "quantity": quantity,
        "other_sizes_available": other_sizes,
        # Full product data so frontend can render the product card
        "product": {**product, "product_id": product_id},
    }
