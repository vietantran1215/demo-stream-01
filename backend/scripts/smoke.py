"""Tiny smoke runner for the demo API.

Usage:
    python scripts/smoke.py
    python scripts/smoke.py --live
"""

from __future__ import annotations

import argparse
import json
import uuid

import httpx


BASE_URL = "http://localhost:8000"


def parse_sse(response: httpx.Response):
    event_name = "message"
    data_lines: list[str] = []

    for line in response.iter_lines():
        if line == "":
            if data_lines:
                yield event_name, json.loads("\n".join(data_lines))
            event_name = "message"
            data_lines = []
            continue

        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())


def run_stream(client: httpx.Client, path: str, payload: dict) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    with client.stream("POST", path, json=payload) as response:
        response.raise_for_status()
        for event, data in parse_sse(response):
            events.append((event, data))
            if event == "token":
                print(data["content"], end="", flush=True)
            elif event not in {"done"}:
                print(f"\n[{event}] {data}")
    print()
    return events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Call model-backed routes too.")
    args = parser.parse_args()

    with httpx.Client(base_url=BASE_URL, timeout=120) as client:
        health = client.get("/health")
        health.raise_for_status()
        assert health.json() == {"status": "ok"}
        print("PASS health")

        if not args.live:
            print("\nModel-backed smoke tests skipped. Run with --live to execute them.")
            print("\nManual scenarios:")
            print("1. What is LangGraph in one paragraph?")
            print("2. Summarize this incident: The checkout API returned HTTP 503...")
            print("3. Reply to the customer saying their refund has been approved...")
            return

        scenarios = [
            ("general", "What is LangGraph in one paragraph?"),
            (
                "summarize",
                "Summarize this incident: The checkout API returned HTTP 503 from 09:31 to 10:04. "
                "A bad configuration was deployed at 09:27. Rollback completed at 10:02.",
            ),
        ]

        for name, prompt in scenarios:
            print(f"\n=== {name} ===")
            thread_id = str(uuid.uuid4())
            events = run_stream(client, f"/api/chat/{thread_id}", {"message": prompt})
            assert not any(event == "interrupt" for event, _ in events)
            print(f"PASS {name}")

        print("\n=== support_reply + HITL ===")
        thread_id = str(uuid.uuid4())
        events = run_stream(
            client,
            f"/api/chat/{thread_id}",
            {
                "message": (
                    "Reply to the customer saying their refund has been approved and will arrive "
                    "in 3-5 business days."
                )
            },
        )
        assert any(event == "interrupt" for event, _ in events)

        resumed = run_stream(
            client,
            f"/api/chat/{thread_id}/resume",
            {"approved": True},
        )
        assert any(event == "action" for event, _ in resumed)
        print("PASS support_reply + HITL approve")


if __name__ == "__main__":
    main()
