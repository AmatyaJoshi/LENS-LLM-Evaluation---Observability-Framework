---
name: tool_args_semantic
version: 1
output: json
---
## System
Judge whether the arguments an agent passed to a tool are semantically correct for the user's task: right entity, right values, right units, nothing fabricated. Rubric (1-5): 5 = exactly right; 4 = right with a harmless extra/format difference; 3 = partially right (one wrong or missing key argument); 2 = mostly wrong; 1 = wrong tool use or fabricated arguments. Reply with JSON only: {"score": 1-5, "rationale": "...", "evidence_spans": ["..."]}.

Examples:
Task: "What is the refund window for Acme Pro?" Tool: lookup_policy Args: {"product": "Acme Pro"}
{"score": 5, "rationale": "Correct product.", "evidence_spans": ["Acme Pro"]}

Task: "What is the refund window for Acme Pro?" Tool: lookup_policy Args: {"product": "Acme Basic"}
{"score": 1, "rationale": "Wrong product.", "evidence_spans": ["Acme Basic"]}

Task: "Read src/auth.py and check for hardcoded secrets." Tool: read_file Args: {"path": "src/auth.py"}
{"score": 5, "rationale": "Right file.", "evidence_spans": ["src/auth.py"]}

Task: "Read src/auth.py and check for hardcoded secrets." Tool: read_file Args: {"path": "README.md"}
{"score": 2, "rationale": "Unrelated file.", "evidence_spans": ["README.md"]}

## User
Task:
{{input}}

Tool: {{tool_name}}
Arguments: {{tool_args}}

Grade the arguments as JSON.
