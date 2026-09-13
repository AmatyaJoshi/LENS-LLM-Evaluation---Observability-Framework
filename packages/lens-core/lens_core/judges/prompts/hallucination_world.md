---
name: hallucination_world
version: 1
output: json
---
## System
No retrieved context is available. Using careful, conservative world knowledge, label each claim: "supported" if it is a well-established fact you are confident about, "contradicted" if it is clearly false, or "unverifiable" if it is obscure, time-sensitive, private, or you are not confident. Prefer "unverifiable" over guessing. Reply with JSON only: {"verdicts": [{"claim": "...", "verdict": "supported|contradicted|unverifiable", "evidence": "short justification or null"}]}.

Examples:
Claims: [1] Paris is the capital of France.
{"verdicts": [{"claim": "Paris is the capital of France.", "verdict": "supported", "evidence": "well-known fact"}]}

Claims: [1] The Pacific is the smallest ocean.
{"verdicts": [{"claim": "The Pacific is the smallest ocean.", "verdict": "contradicted", "evidence": "the Pacific is the largest ocean"}]}

Claims: [1] Acme Corp's CFO resigned last month.
{"verdicts": [{"claim": "Acme Corp's CFO resigned last month.", "verdict": "unverifiable", "evidence": null}]}

Claims: [1] Water boils at 100 °C at sea level. [2] The Acme office has 42 desks.
{"verdicts": [{"claim": "Water boils at 100 °C at sea level.", "verdict": "supported", "evidence": "standard physics"}, {"claim": "The Acme office has 42 desks.", "verdict": "unverifiable", "evidence": null}]}

## User
Question (context only):
{{input}}

Claims:
{{claims}}

Return one verdict per claim, in order.
