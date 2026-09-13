---
name: question_generation
version: 1
output: json
---
## System
Given an answer, write {{k}} distinct questions that this answer would be a direct and complete response to. Do not use information beyond the answer. Questions should be natural, specific and non-redundant. Reply with JSON only: {"questions": ["...", "..."]}.

Examples:
Answer: "Acme Pro purchases can be refunded within 30 days of purchase."
{"questions": ["What is the refund window for Acme Pro?", "How long do I have to return Acme Pro?", "Can I get a refund on Acme Pro after two weeks?"]}

Answer: "The store is open from 9am to 6pm on weekdays."
{"questions": ["What are the store's weekday opening hours?", "When does the store close on a Tuesday?", "Is the store open at 8am on Monday?"]}

Answer: "I don't have information about that."
{"questions": ["Can you tell me about that topic?", "Do you know anything about it?", "What do you know regarding this?"]}

Answer: "Use `pip install lens-sdk` and call lens.init()."
{"questions": ["How do I install and initialise the Lens SDK in Python?", "What command installs lens-sdk?", "How do I set up Lens tracing in a Python app?"]}

## User
Answer:
{{output}}

Write exactly {{k}} questions as JSON.
