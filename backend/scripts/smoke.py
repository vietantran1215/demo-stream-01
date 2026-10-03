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
            elif event != "done":
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
            return

        print("\n=== general ===")
        thread_id = str(uuid.uuid4())
        general = run_stream(
            client,
            f"/api/chat/{thread_id}",
            {"message": "What is LangGraph in one paragraph?"},
        )
        assert any(event == "token" for event, _ in general)
        assert not any(event == "interrupt" for event, _ in general)
        print("PASS general")

        print("\n=== summarize ===")
        thread_id = str(uuid.uuid4())
        summarized = run_stream(
            client,
            f"/api/chat/{thread_id}",
            {
                "message": (
                    "Summarize this incident: The checkout API returned HTTP 503 from 09:31 "
                    "to 10:04. A bad configuration was deployed at 09:27. "
                    "Rollback completed at 10:02."
                )
            },
        )
        assert any(event == "token" for event, _ in summarized)
        assert any(
            event == "skill" and data.get("name") == "summarize"
            for event, data in summarized
        )
        print("PASS summarize + skill")

        print("\n=== support agent + HITL middleware + approve ===")
        thread_id = str(uuid.uuid4())
        support = run_stream(
            client,
            f"/api/chat/{thread_id}",
            {
                "message": (
                    "Reply to the customer saying their refund has been approved and will "
                    "arrive in 3-5 business days."
                )
            },
        )

        assert any(
            event == "skill" and data.get("name") == "support-reply"
            for event, data in support
        )

        interrupts = [
            data
            for event, data in support
            if event == "interrupt"
        ]
        assert len(interrupts) == 1
        assert interrupts[0]["value"]["action"] == "send_support_reply"
        assert interrupts[0]["value"]["draft"]
        assert not any(event == "tool" for event, _ in support)

        resumed = run_stream(
            client,
            f"/api/chat/{thread_id}/resume",
            {"approved": True},
        )

        tool_progress = [
            data.get("progress")
            for event, data in resumed
            if event == "tool"
        ]
        assert tool_progress == [0, 30, 60, 90, 100]
        assert any(
            event == "tool" and data.get("phase") == "completed"
            for event, data in resumed
        )

        print("PASS support agent + built-in HITL + streamed tool progress")


if __name__ == "__main__":
    main()
