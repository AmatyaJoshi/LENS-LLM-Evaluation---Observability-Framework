"""Answer relevance (SPEC.md §5.2).

    relevance = mean( cos(E(input), E(q_i)) for i in 1..k ) blended with a rubric grade

1. The judge writes k questions the output would answer (``question_generation``).
2. Each is embedded together with the user's input; the mean cosine similarity
   measures how well the output stays on the asked question (RAGAS-style).
3. A 1-5 rubric grade (``relevance_rubric``) is mapped to [0, 1]. The final value
   is the mean of the two components; when the judge has no embedding model the
   rubric alone is used (recorded in sub-scores so the two paths are distinguishable).
"""

from __future__ import annotations

from typing import ClassVar

from lens_core.judges.base import Judge
from lens_core.judges.prompts import load_prompt
from lens_core.metrics._shared import Questions, RubricScore, cosine, rubric_to_unit
from lens_core.metrics.base import BaseMetric, EvalItem, MetricResult, Requirement
from lens_core.metrics.registry import register_metric

K_QUESTIONS = 3


@register_metric
class AnswerRelevance(BaseMetric):
    name: ClassVar[str] = "answer_relevance"
    version: ClassVar[str] = "1"
    requires: ClassVar[frozenset[Requirement]] = frozenset({"input", "output"})
    description: ClassVar[str] = (
        "How directly the output addresses the input: generated-question similarity plus rubric."
    )

    async def _score(self, item: EvalItem, judge: Judge) -> MetricResult:
        assert item.input is not None and item.output is not None
        q_prompt = load_prompt("question_generation")
        r_prompt = load_prompt("relevance_rubric")

        questions_parsed, _ = await judge.judge(
            q_prompt, {"output": item.output, "k": K_QUESTIONS}, Questions
        )
        questions = [q for q in questions_parsed.questions if q.strip()][:K_QUESTIONS]

        sub: dict[str, float] = {}
        components: list[float] = []
        similarities: list[float] = []
        if questions:
            embeddings = await judge.embed([item.input, *questions])
            if embeddings and len(embeddings) == len(questions) + 1:
                anchor = embeddings[0]
                similarities = [max(0.0, cosine(anchor, e)) for e in embeddings[1:]]
                emb_score = sum(similarities) / len(similarities)
                sub["embedding_similarity"] = emb_score
                components.append(emb_score)

        rubric, _ = await judge.judge(
            r_prompt, {"input": item.input, "output": item.output}, RubricScore
        )
        rubric_unit = rubric_to_unit(rubric.score)
        sub["rubric"] = rubric_unit
        components.append(rubric_unit)

        value = sum(components) / len(components)
        rationale = f"rubric {rubric.score}/5: {rubric.rationale}"
        if similarities:
            rationale += f"; mean question similarity {sub['embedding_similarity']:.2f}"
        return MetricResult(
            metric=self.name,
            version=self.version,
            value=value,
            rationale=rationale,
            sub_scores=sub,
            details={
                "generated_questions": questions,
                "similarities": similarities,
                "evidence_spans": rubric.evidence_spans,
            },
            judge_prompt_version=f"{q_prompt.name}@{q_prompt.version};{r_prompt.name}@{r_prompt.version}",
        )
