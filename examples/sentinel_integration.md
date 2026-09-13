# Sentinel → Lens integration

Sentinel (Project 1) is the primary dogfood source for Lens (SPEC.md §12). Phase 1 only needs
Sentinel's spans to arrive in ClickHouse and reconstruct into a `Trajectory`.

## 1. Export OTLP from Sentinel

Sentinel is instrumented with OpenLLMetry (Traceloop). Point it at the Lens collector:

```bash
# in Sentinel's environment
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318     # Lens collector, OTLP/HTTP
export OTEL_SERVICE_NAME=sentinel                            # becomes Trajectory.app
export TRACELOOP_BASE_URL=http://localhost:4318              # if using Traceloop.init()
export TRACELOOP_TELEMETRY=false
```

Or, from inside the compose network, `http://otel-collector:4318`. gRPC on `4317` also works.

## 2. What Lens reads from Sentinel spans (no code changes required)

| Sentinel span | OpenLLMetry attribute(s) | Lens mapping (SPEC.md §4) |
|---|---|---|
| LangGraph graph run | `traceloop.span.kind=workflow`, `traceloop.entity.name=<graph>` | `agent_step`, root of the trajectory |
| LangGraph node (`hunt`, `verify`, `explain`, …) | `traceloop.span.kind=task`/`agent`, `traceloop.entity.name=<node>` | `agent_step` (agent) or `chain` (task); node name becomes the step label |
| LLM call | `gen_ai.system`, `gen_ai.request.model`, `gen_ai.prompt.{i}.*`, `gen_ai.completion.0.*`, `gen_ai.usage.*` | `LLMCall` |
| Tool call (`read_file`, `run_tests`, …) | `traceloop.span.kind=tool`, `traceloop.entity.name`, `traceloop.entity.input/output` | `ToolCall` (call id linked back to the requesting LLM message by name) |

## 3. Optional Lens attributes worth adding in Sentinel

Set these on the root span (or via the Lens SDK once it ships in phase 8):

| Attribute | Purpose |
|---|---|
| `lens.run.id` | Sentinel audit run id → `Trajectory.run_id` |
| `lens.session.id` | groups several audits of the same repo |
| `sentinel.*` (any) | copied verbatim into `Trajectory.metadata` (e.g. `sentinel.repo`, `sentinel.finding.confidence`) |
| `lens.eval.expected_output` | ground truth for offline evaluation (phase 3) |

For nodes that behave like LangGraph agent steps but are decorated as Traceloop `task`s, decorate
them with `@agent` (or set `traceloop.span.kind=agent`) so each node becomes its own `Step`.

## 4. Verify

```bash
docker compose up -d --wait
# run one Sentinel audit, then:
curl -s localhost:8000/traces?app=sentinel | jq '.[0]'
curl -s localhost:8000/traces/<trace_id>/trajectory | jq '.steps[] | {name, llm: .llm_call.model, tools: [.tool_calls[].name]}'
docker compose exec clickhouse clickhouse-client -u lens --password lens \
  -q "SELECT kind, count() FROM lens.spans WHERE app='sentinel' GROUP BY kind"
```
