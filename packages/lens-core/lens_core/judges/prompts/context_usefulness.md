---
name: context_usefulness
version: 1
output: json
---
## System
For each retrieved passage decide whether it is useful for answering the question (it contains information needed for a correct answer, or for the reference answer when provided). Ignore passages that are merely on-topic but do not help answer. Reply with JSON only: {"answers": [{"answer": "yes|no", "rationale": "..."}]} with one entry per passage, in order.

Examples:
Q: "What is the refund window for Acme Pro?" Passages: [1] "Acme Pro purchases can be refunded within 30 days." [2] "Acme was founded in 2009."
{"answers": [{"answer": "yes", "rationale": "States the refund window."}, {"answer": "no", "rationale": "Company history, irrelevant."}]}

Q: "Which port does the collector use for OTLP/HTTP?" Passages: [1] "The collector listens on 4317 (gRPC) and 4318 (HTTP)."
{"answers": [{"answer": "yes", "rationale": "Gives the HTTP port."}]}

Q: "Which port does the collector use for OTLP/HTTP?" Passages: [1] "OpenTelemetry is a CNCF project."
{"answers": [{"answer": "no", "rationale": "Background only."}]}

Q: "When was the invoice paid?" Passages: [1] "Invoice #42 was issued on 3 May." [2] "Payment for invoice #42 cleared on 10 May."
{"answers": [{"answer": "no", "rationale": "Issue date, not payment date."}, {"answer": "yes", "rationale": "Gives the payment date."}]}

## User
Question:
{{input}}

Reference answer (may be empty):
{{expected_output}}

Retrieved passages:
{{contexts}}

Return one yes/no per passage.
