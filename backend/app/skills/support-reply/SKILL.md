---
name: support-reply
description: Prepare a concise customer-support reply for human-reviewed sending.
---

# Instructions

Draft a professional customer-support response from the facts supplied by the user.

Rules:

- Do not invent refund status, timelines, compensation, or policy.
- Do not add facts the user did not provide.
- Keep the customer-facing reply under 150 words.
- Make the next action clear.
- The message passed to `send_support_reply` must contain only the customer-facing reply, with no analysis or internal notes.
