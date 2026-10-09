"""Measure a short local model response; no prompt or reply is written to disk."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.config import Settings
from nexus.models import OllamaProvider


PROMPT = (
    'Return only a JSON object with exactly these keys: "product" and "reversed_list". '
    'Set product to 13 times 17. Reverse the order of the array elements below, '
    'keeping every string exactly unchanged: ["alpha", "beta", "gamma"]. '
    'Do not include code, markdown, or explanation.'
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="temporarily benchmark a different installed Ollama model")
    parser.add_argument("--prompt", default=PROMPT, help="use a custom prompt instead of the built-in structured task")
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.model:
        settings = replace(settings, model=args.model)
    provider = OllamaProvider(settings)
    status = provider.health_check()
    if not status.connected or not status.model_available:
        print(status.message)
        return 1

    started = perf_counter()
    response = "".join(provider.stream_chat([{"role": "user", "content": args.prompt}]))
    elapsed = perf_counter() - started
    metrics = provider.last_metrics or {}
    structured_valid = None
    if args.prompt == PROMPT:
        candidate = response.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                candidate = "\n".join(lines[1:-1]).strip()
        try:
            structured = json.loads(candidate)
            structured_valid = structured == {"product": 221, "reversed_list": ["gamma", "beta", "alpha"]}
        except json.JSONDecodeError:
            structured_valid = False
    result = {
        "model": settings.model,
        "prompt": args.prompt,
        "response": response,
        "structured_output_valid": structured_valid,
        "strict_json_only": structured_valid and not response.strip().startswith("```"),
        "wall_time_seconds": round(elapsed, 3),
        "server_total_seconds": round(metrics["total_duration"] / 1e9, 3) if "total_duration" in metrics else None,
        "model_load_seconds": round(metrics["load_duration"] / 1e9, 3) if "load_duration" in metrics else None,
        "generated_tokens": metrics.get("eval_count"),
        "generation_tokens_per_second": (
            round(metrics["eval_count"] / (metrics["eval_duration"] / 1e9), 2)
            if metrics.get("eval_count") and metrics.get("eval_duration")
            else None
        ),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
