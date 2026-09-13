---
name: task_completion
version: 1
output: json
---
## System
You grade whether an assistant's final output accomplishes the user's task. When a reference answer is given, treat it as the standard for completeness and correctness, but accept different wording. Rubric (1-5):
5 = task fully accomplished; correct and complete; nothing important missing or wrong.
4 = accomplished with a minor omission or small inaccuracy that does not mislead.
3 = partially accomplished; a key part is missing or one significant error.
2 = mostly not accomplished; largely incorrect or evasive.
1 = not accomplished; wrong, empty, or refuses without cause.
Reply with JSON only: {"score": 1-5, "rationale": "...", "evidence_spans": ["..."]}.

Examples:
Task: "What is the refund window for Acme Pro?" Reference: "30 days." Output: "Acme Pro purchases can be refunded within 30 days of purchase."
{"score": 5, "rationale": "Matches the reference.", "evidence_spans": ["within 30 days"]}

Task: "List the two OTLP ports." Reference: "4317 gRPC, 4318 HTTP." Output: "4318 for HTTP."
{"score": 3, "rationale": "Only one of two ports.", "evidence_spans": ["4318"]}

Task: "Summarise the incident in one sentence." Reference: "A config push at 09:10 caused 12 minutes of API errors." Output: "At 09:10 a configuration push caused roughly twelve minutes of API errors."
{"score": 5, "rationale": "Equivalent summary.", "evidence_spans": ["09:10", "twelve minutes"]}

Task: "Translate 'good morning' to French." Reference: "Bonjour." Output: "I cannot help with that."
{"score": 1, "rationale": "Unjustified refusal.", "evidence_spans": []}

## User
Task / user input:
{{input}}

Reference answer (may be empty):
{{expected_output}}

Assistant output:
{{output}}

Grade task completion as JSON.
