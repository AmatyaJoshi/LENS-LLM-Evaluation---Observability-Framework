---
name: attribution
version: 1
output: json
---
## System
For each sentence of the reference answer decide whether it can be attributed to the retrieved passages, i.e. the passages contain the information needed to write that sentence. Reply with JSON only: {"answers": [{"answer": "yes|no", "rationale": "..."}]} with one entry per sentence, in order.

Examples:
Passages: [1] "Acme Pro purchases can be refunded within 30 days of purchase." Sentences: [1] "Acme Pro can be refunded within 30 days." [2] "Refunds are credited to the original card."
{"answers": [{"answer": "yes", "rationale": "Passage 1 states it."}, {"answer": "no", "rationale": "Nothing about payment method."}]}

Passages: [1] "The service level is 99.9% monthly uptime." Sentences: [1] "The SLA is 99.9% uptime per month."
{"answers": [{"answer": "yes", "rationale": "Same fact, rephrased."}]}

Passages: [1] "The service level is 99.9% monthly uptime." Sentences: [1] "Support responds within one hour."
{"answers": [{"answer": "no", "rationale": "Not in passages."}]}

Passages: [1] "Lens ingests OTLP over gRPC and HTTP." Sentences: [1] "Lens accepts OTLP/HTTP." [2] "Lens accepts OTLP/gRPC."
{"answers": [{"answer": "yes", "rationale": "Listed."}, {"answer": "yes", "rationale": "Listed."}]}

## User
Retrieved passages:
{{contexts}}

Reference answer sentences:
{{sentences}}

Return one yes/no per sentence.
