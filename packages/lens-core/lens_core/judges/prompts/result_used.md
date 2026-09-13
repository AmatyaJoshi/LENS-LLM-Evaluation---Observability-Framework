---
name: result_used
version: 1
output: json
---
## System
Decide whether the final answer actually uses the result returned by a tool (the answer's content depends on or reflects the tool result) rather than ignoring or contradicting it. Reply with JSON only: {"answer": "yes|no", "rationale": "..."}.

Examples:
Tool result: {"refund_days": 30} Answer: "Acme Pro can be refunded within 30 days."
{"answer": "yes", "rationale": "30 days comes from the result."}

Tool result: {"refund_days": 30} Answer: "Acme Pro can be refunded within 14 days."
{"answer": "no", "rationale": "Contradicts the tool result."}

Tool result: {"tests_passed": false, "failing": ["test_login"]} Answer: "All tests pass; the change is safe."
{"answer": "no", "rationale": "Ignores the failing test."}

Tool result: {"tests_passed": false, "failing": ["test_login"]} Answer: "test_login fails after this change, so it is not safe to merge."
{"answer": "yes", "rationale": "Reflects the result."}

## User
Tool: {{tool_name}}
Tool result:
{{tool_result}}

Final answer:
{{output}}

Return JSON.
