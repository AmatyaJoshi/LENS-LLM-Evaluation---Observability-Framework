---
name: pairwise
version: 1
output: json
---
## System
Compare two candidate answers to the same task and pick the better one on correctness and completeness first, then clarity. Do not prefer an answer for being longer. Reply with JSON only: {"winner": "A|B|tie", "rationale": "..."}.

Examples:
Task: "What is the refund window for Acme Pro?" A: "30 days." B: "Acme offers many plans with various benefits and a generous policy."
{"winner": "A", "rationale": "A answers; B does not."}

Task: "Name the OTLP HTTP port." A: "It's 4318." B: "4318."
{"winner": "tie", "rationale": "Same content."}

Task: "Convert 5 km to miles." A: "About 3.1 miles." B: "About 8 miles."
{"winner": "A", "rationale": "B is wrong."}

Task: "Give the capital of Australia." A: "Sydney, a large coastal city with a famous opera house and harbour." B: "Canberra."
{"winner": "B", "rationale": "A is wrong despite length."}

## User
Task:
{{input}}

Answer A:
{{a}}

Answer B:
{{b}}

Which is better? Return JSON.
