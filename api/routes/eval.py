"""Eval endpoints."""

import json
from pathlib import Path
from fastapi import APIRouter
from api.models import EvalRequest

router = APIRouter()


@router.post("/api/eval/run")
async def run_eval(request: EvalRequest):
    from eval.runner import run_eval_suite
    results = await run_eval_suite(test_case_ids=request.test_case_ids)

    output_path = Path("eval/results/latest.json")
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    return results


@router.get("/api/eval/results")
async def get_eval_results():
    results_path = Path("eval/results/latest.json")
    if results_path.exists():
        with open(results_path) as f:
            return json.load(f)
    return {"error": "No eval results found. Run /api/eval/run first."}
