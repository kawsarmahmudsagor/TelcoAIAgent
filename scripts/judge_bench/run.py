"""Benchmark the voice-turn relevance judge (Jev via OpenRouter) on labelled cases.

Sends each case in cases.json through the same request builder the agent uses
(app.agent.turn_judge) and reports accuracy per language, false rejects of real
customer turns, false barge-ins, latency and cost.

Run from backend/ so the backend environment and .env are used:
    cd backend && uv run python ../scripts/judge_bench/run.py [--model typesafe/jev-1.13]

--lookup also asks the turn router's lookup question on listening cases, as the
agent does with ROUTER_ENABLED, to compare latency and the timeout rate.
--topic (with --lookup) also asks the filler's topic question, as the agent
does with quick fillers on, and prints Jev's topic for each listening case.
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

from app.agent.turn_gate import Thresholds, address_form  # noqa: E402
from app.agent.turn_judge import Exchange, build_request, decisions_url, judge  # noqa: E402
from app.config import get_settings  # noqa: E402

DROP_P = Thresholds().drop_p
INTERRUPT_P = 0.5


async def _run(model: str, cases_path: Path, lookup: bool, topic: bool) -> None:
    data = json.loads(cases_path.read_text(encoding="utf-8"))
    histories = {
        k: [Exchange(e["role"], e["text"]) for e in v] for k, v in data["histories"].items()
    }
    settings = get_settings()
    if not settings.openrouter_api_key:
        sys.exit("OPENROUTER_API_KEY is not set")
    url = decisions_url(settings.openrouter_base_url)

    results = []
    async with httpx.AsyncClient() as client:
        for case in data["cases"]:
            payload = build_request(
                model,
                histories[case["h"]],
                case["utterance"],
                case["bot_state"],
                address_form(case["utterance"]),
                lookup=lookup and case["bot_state"] == "listening",
                topic=topic and lookup and case["bot_state"] == "listening",
            )
            started = time.perf_counter()
            judgement = await judge(client, url, settings.openrouter_api_key, payload, timeout_s=15)
            p = judgement.p
            ms = (time.perf_counter() - started) * 1000
            results.append({**case, "p": p, "ms": ms})
            shown = "ERR " if p is None else f"{p:.2f}"
            mark = _mark(case["expected"], p)
            print(f"{case['id']:5} {case['expected'][:4]:4} {case['bot_state'][:5]:5} "
                  f"{shown} {ms:6.0f}ms {mark} {case['utterance']}"
                  + (f"  [topic {judgement.topic} {judgement.topic_p}]" if judgement.topic else ""))

    _report(results, settings.turn_judge_timeout_ms)


def _mark(expected: str, p: float | None) -> str:
    if p is None:
        return "?"
    if expected == "addressed":
        return "ok" if p >= DROP_P else "XX"
    return "ok" if p < DROP_P else "XX"


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def _report(results: list[dict], timeout_ms: int) -> None:
    ok = [r for r in results if r["p"] is not None]
    errors = len(results) - len(ok)
    yes = [r for r in ok if r["expected"] == "addressed"]
    no = [r for r in ok if r["expected"] == "not_addressed"]

    print("\n== Listening gate (all states) ==")
    print(f"Real turns dropped (P < {DROP_P}):       ", _pct(sum(r["p"] < DROP_P for r in yes), len(yes)))
    print("Noise/bystanders/off-topic dropped:     ", _pct(sum(r["p"] < DROP_P for r in no), len(no)))

    print("\n== Per group ==")
    groups: dict[tuple[str, str, str], list[float]] = {}
    for r in ok:
        groups.setdefault((r["expected"], r["lang"], r["stt"]), []).append(r["p"])
    for (expected, lang, stt), ps in sorted(groups.items()):
        print(f"{expected:13} {lang:3} {stt:10} n={len(ps):2} mean P={statistics.mean(ps):.2f} "
              f"min={min(ps):.2f} max={max(ps):.2f}")

    speaking = [r for r in ok if r["bot_state"] == "speaking"]
    s_yes = [r for r in speaking if r["expected"] == "addressed"]
    s_no = [r for r in speaking if r["expected"] == "not_addressed"]
    print("\n== Barge-in (bot speaking, interrupt at P >= 0.5) ==")
    print("Real barge-ins that interrupt:", _pct(sum(r["p"] >= INTERRUPT_P for r in s_yes), len(s_yes)))
    print("Bystander speech that interrupts:", _pct(sum(r["p"] >= INTERRUPT_P for r in s_no), len(s_no)))

    hard = [r for r in ok if r.get("hard")]
    if hard:
        print("\n== Hard (ambiguous) cases ==")
        for r in hard:
            print(f"{r['id']:5} {r['expected']:13} P={r['p']:.2f} {r['utterance']}")

    ms = sorted(r["ms"] for r in ok)
    if ms:
        p95 = ms[min(len(ms) - 1, int(round(0.95 * (len(ms) - 1))))]
        print(f"\nLatency: p50={statistics.median(ms):.0f}ms p95={p95:.0f}ms max={ms[-1]:.0f}ms")
        # The agent gives up after this and accepts the turn unjudged.
        slow = sum(m > timeout_ms for m in ms)
        print(f"Slower than the agent's {timeout_ms}ms timeout:", _pct(slow, len(ms)))
    print(f"Errors: {errors}/{len(results)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="typesafe/jev-1.13")
    parser.add_argument("--cases", type=Path, default=_HERE / "cases.json")
    parser.add_argument("--lookup", action="store_true", help="also ask the lookup question")
    parser.add_argument(
        "--topic", action="store_true", help="also ask the topic question (with --lookup)"
    )
    args = parser.parse_args()
    asyncio.run(_run(args.model, args.cases, args.lookup, args.topic))


if __name__ == "__main__":
    main()
