"""Benchmark the turn router on labelled turns: Jev's lookup choice and the
extractor's search arguments (app.agent.turn_judge / app.agent.turn_router).

For each case in cases.json it sends, at the same time as the agent does, the
Jev request with the lookup question and the extractor request for each model
given, then reports lookup accuracy, argument accuracy and latency.

Run from backend/ so the backend environment and .env are used:
    cd backend && uv run python ../scripts/router_bench/run.py \
        --models openai/gpt-5.4-nano google/gemini-3.1-flash-lite
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parents[1] / "backend"))

from app.agent import turn_judge, turn_router  # noqa: E402
from app.agent.turn_gate import address_form  # noqa: E402
from app.agent.turn_judge import Exchange  # noqa: E402
from app.config import get_settings  # noqa: E402

# The agent only prefetches when Jev is at least this sure of its choice.
MIN_P = 0.6


async def _timed(coro):
    started = time.perf_counter()
    result = await coro
    return result, (time.perf_counter() - started) * 1000


def _same(expected, got) -> bool:
    if isinstance(expected, list):
        return isinstance(got, list) and {str(x).lower() for x in expected} == {
            str(x).lower() for x in got
        }
    if isinstance(expected, (int, float)) and isinstance(got, (int, float)):
        return float(expected) == float(got)
    return str(expected).lower() == str(got).lower()


def _args_ok(expected: dict, got: dict, allow_extra: list[str] | bool) -> tuple[bool, str]:
    problems = [
        f"{k}={got.get(k)!r} (want {v!r})" for k, v in expected.items() if not _same(v, got.get(k))
    ]
    if allow_extra is not True:
        problems += [f"extra {k}={v!r}" for k, v in got.items() if k not in expected and k not in allow_extra]
    return not problems, "; ".join(problems)


async def _run(models: list[str], cases_path: Path, judge_model: str) -> None:
    data = json.loads(cases_path.read_text(encoding="utf-8"))
    histories = {
        k: [Exchange(e["role"], e["text"]) for e in v] for k, v in data["histories"].items()
    }
    settings = get_settings()
    key = settings.openrouter_api_key
    if not key:
        sys.exit("OPENROUTER_API_KEY is not set")
    url = turn_judge.decisions_url(settings.openrouter_base_url)

    jev_rows, ext_rows = [], {m: [] for m in models}
    async with httpx.AsyncClient() as client:
        for case in data["cases"]:
            history = histories[case["h"]]
            jev_payload = turn_judge.build_request(
                judge_model,
                history,
                case["utterance"],
                "listening",
                address_form(case["utterance"]),
                lookup=True,
                knowledge_base=True,
            )
            ext_payloads = [
                turn_router.build_request(
                    m,
                    history,
                    case["utterance"],
                    settings.router_reasoning_effort,
                )
                for m in models
            ]
            results = await asyncio.gather(
                _timed(turn_judge.judge(client, url, key, jev_payload, timeout_s=15)),
                *(
                    _timed(turn_router.extract(client, settings.openrouter_base_url, key, p, 15))
                    for p in ext_payloads
                ),
            )
            (judgement, jev_ms), ext_results = results[0], results[1:]
            lookup_ok = judgement.lookup == case["lookup"]
            jev_rows.append({"case": case, "j": judgement, "ms": jev_ms, "ok": lookup_ok})
            lp = "?" if judgement.lookup_p is None else f"{judgement.lookup_p:.2f}"
            print(f"{case['id']} jev {'ok' if lookup_ok else 'XX'} {judgement.lookup}({lp}) "
                  f"{jev_ms:5.0f}ms  {case['utterance']}  [expected tool: {case['expected_tool']}]")

            for model, (args, ms) in zip(models, ext_results):
                row = {"case": case, "ms": ms, "error": args is None, "ok": None, "why": ""}
                if args is not None and "packages" in case:
                    row["ok"], row["why"] = _args_ok(
                        case["packages"], args.packages, case.get("allow_extra", [])
                    )
                ext_rows[model].append(row)
                if row["ok"] is not None or row["error"]:
                    mark = "ERR" if row["error"] else "ok " if row["ok"] else "XX "
                    shown = "" if args is None else json.dumps(
                        args.packages, ensure_ascii=False
                    )
                    print(f"     {model[:28]:28} {mark} {ms:5.0f}ms {shown} {row['why']}")

    _report(jev_rows, ext_rows, settings.turn_judge_timeout_ms)


def _p(ms: list[float]) -> str:
    ms = sorted(ms)
    p95 = ms[min(len(ms) - 1, int(round(0.95 * (len(ms) - 1))))]
    return f"p50={statistics.median(ms):.0f}ms p95={p95:.0f}ms max={ms[-1]:.0f}ms"


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def _report(jev_rows: list[dict], ext_rows: dict[str, list[dict]], timeout_ms: int) -> None:
    print("\n== Jev lookup choice ==")
    print("Correct:", _pct(sum(r["ok"] for r in jev_rows), len(jev_rows)))
    search_cases = [r for r in jev_rows if r["case"]["lookup"] != "none"]
    none_cases = [r for r in jev_rows if r["case"]["lookup"] == "none"]
    prefetch = [
        r for r in search_cases
        if r["ok"] and r["j"].lookup != "none" and (r["j"].lookup_p or 0) >= MIN_P
    ]
    print(f"Lookup turns that would prefetch (right choice, P >= {MIN_P}):", _pct(len(prefetch), len(search_cases)))
    wrong = [r for r in none_cases if r["j"].lookup != "none" and (r["j"].lookup_p or 0) >= MIN_P]
    print("No-lookup turns that would prefetch anyway:", _pct(len(wrong), len(none_cases)))
    print("Latency:", _p([r["ms"] for r in jev_rows]),
          f"| over {timeout_ms}ms:", _pct(sum(r["ms"] > timeout_ms for r in jev_rows), len(jev_rows)))

    for model, rows in ext_rows.items():
        scored = [r for r in rows if r["ok"] is not None]
        print(f"\n== Extractor {model} ==")
        print("Arguments right:", _pct(sum(r["ok"] for r in scored), len(scored)))
        print("Errors:", _pct(sum(r["error"] for r in rows), len(rows)))
        print("Latency:", _p([r["ms"] for r in rows]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=[get_settings().router_model])
    parser.add_argument("--judge-model", default="typesafe/jev-1.13")
    parser.add_argument("--cases", type=Path, default=_HERE / "cases.json")
    args = parser.parse_args()
    asyncio.run(_run(args.models, args.cases, args.judge_model))


if __name__ == "__main__":
    main()
