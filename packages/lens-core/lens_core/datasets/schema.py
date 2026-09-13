"""Dataset records (SPEC.md §3.2) as exchanged between CLI, API and training scripts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from lens_core.metrics.base import EvalItem, ExpectedTool
from lens_core.trace.model import Trajectory

Split = Literal["train", "dev", "test"]
SplitStrategy = Literal["random", "by_source_document", "manual"]


class ExampleRecord(BaseModel):
    id: str | None = None
    input: str
    expected_output: str | None = None
    contexts: list[str] = Field(default_factory=list)
    expected_tools: list[ExpectedTool] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    split: Split = "train"
    source_trace_id: str | None = None
    # optional recorded output (for scoring a dataset without re-running the app)
    output: str | None = None

    def to_eval_item(self, trajectory: Trajectory | None = None) -> EvalItem:
        return EvalItem(
            id=self.id,
            input=self.input,
            output=self.output if trajectory is None else (trajectory.final_output or self.output),
            contexts=self.contexts
            if trajectory is None or not trajectory.retrievals
            else [d.text for r in trajectory.retrievals for d in r.documents if d.text],
            expected_output=self.expected_output,
            expected_tools=self.expected_tools,
            trajectory=trajectory,
            trace_id=trajectory.trace_id if trajectory else self.source_trace_id,
            metadata={**self.metadata, **(trajectory.metadata if trajectory else {})},
        )

    @classmethod
    def from_trajectory(cls, t: Trajectory, *, expected_output: str | None = None) -> ExampleRecord:
        expected = expected_output or t.metadata.get("lens.eval.expected_output")
        return cls(
            id=t.trace_id,
            input=t.user_input or "",
            expected_output=str(expected) if expected is not None else None,
            contexts=[d.text for r in t.retrievals for d in r.documents if d.text],
            expected_tools=[ExpectedTool(name=c.name, args=c.args or None) for c in t.tool_calls]
            or None,
            metadata={k: v for k, v in t.metadata.items() if k not in ("span_count",)},
            source_trace_id=t.trace_id,
            output=t.final_output,
        )


class DatasetSpec(BaseModel):
    name: str
    description: str | None = None
    split_strategy: SplitStrategy = "random"
    examples: list[ExampleRecord] = Field(default_factory=list)
