"""Policy retrieval tool using RAG (sentence-transformers + FAISS)."""

from pathlib import Path
from tools.embeddings import embed_texts, build_faiss_index, search_index

_policies = []
_policy_index = None


def _load_policies():
    global _policies, _policy_index

    policy_dir = Path(__file__).parent / "mock_data" / "policies"

    for policy_file in sorted(policy_dir.glob("*.md")):
        content = policy_file.read_text()
        name = policy_file.stem.replace("_", " ").title()
        _policies.append({"name": name, "filename": policy_file.name, "content": content})

    texts = [p["content"] for p in _policies]
    embeddings = embed_texts(texts)
    _policy_index = build_faiss_index(embeddings)


_load_policies()


def get_policy(query: str, top_k: int = 2) -> dict:
    if not _policy_index:
        return {"error": "Policy index not initialized"}

    results = search_index(_policy_index, query, top_k=top_k)

    if not results:
        return {"error": "No relevant policy found", "policy_name": None, "content": None, "relevance_score": 0.0}

    best_idx, best_score = results[0]
    best_policy = _policies[best_idx]

    all_results = [{"policy_name": _policies[idx]["name"], "relevance_score": round(score, 3)} for idx, score in results]

    return {
        "policy_name": best_policy["name"],
        "content": best_policy["content"],
        "relevance_score": round(best_score, 3),
        "all_results": all_results,
    }
