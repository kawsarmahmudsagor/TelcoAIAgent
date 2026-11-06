"""Jev's wrap-up answer on run_94-style turns, each asked twice. wrap_up True =
"closing the topic": the agent then offers more help; a no to that offer must
score False, or the agent asks "anything else?" again instead of saying goodbye.

Run from backend/:  uv run python ../scripts/judge_bench/wrapup.py
"""

import asyncio
import sys

import httpx

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[2] / "backend"))

from app.agent import turn_judge as tj
from app.config import get_settings

# (agent's last line, customer's turn, expected wrap_up)
CASES = [
    ("ঠিক আছে, এখন প্যাকেজটা নিচ্ছি না। আর কোনো বিষয়ে সাহায্য লাগবে?", "না, আ-আর কোন help লাগবে না। Thank you", False),
    ("আর কিছু জানতে চান?", "না, ধন্যবাদ", False),
    ("Anything else I can help you with?", "no that's all, thanks", False),
    ("আর কিছু লাগবে?", "হ্যাঁ, আমার পয়েন্ট কত?", False),
    ("আপনার ব্যালেন্স ৯৮.৫০ টাকা।", "আচ্ছা, ঠিক আছে", True),
    ("৩৪৯ টাকায় ১৫ জিবি, মেয়াদ ৩০ দিন। চাইলে প্যাকেজটা চালু করে দেবো?", "না, লাগবে না", True),
    ("আপনার ব্যালেন্সে প্যাকেজটা নেওয়ার মতো টাকা নেই। রিচার্জ করে নিতে চাইলে বলবেন?",
     "আচ্ছা যেহেতু আমার এখন ব্যালেন্স নেই, সো প্যাকেজটা এখন আমি নিতে চাচ্ছি না", True),
    ("আপনার ১৫ জিবি ডাটা আছে, মেয়াদ ২৮ নভেম্বর পর্যন্ত।", "thanks!", True),
]

async def run(label: str) -> int:
    s = get_settings()
    url = tj.decisions_url(s.openrouter_base_url)
    right = 0
    async with httpx.AsyncClient() as client:
        for bot, text, want in CASES:
            got = []
            for _ in range(2):
                payload = tj.build_request(
                    s.turn_judge_model,
                    [tj.Exchange("assistant", bot)],
                    text,
                    "listening",
                    intent=True,
                )
                j = await tj.judge(client, url, s.openrouter_api_key, payload, 5.0)
                ok = j.wrap_up_p is not None and (j.wrap_up_p >= 0.5) == want
                right += ok
                got.append(f"{j.wrap_up_p}{'' if ok else ' WRONG'}")
            print(f"[{label}] want={want!s:5} {got}  {text[:40]}")
    print(f"[{label}] {right}/{2 * len(CASES)} right\n")
    return right


async def main() -> None:
    await run("wrap_up")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
