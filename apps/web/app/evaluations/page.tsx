"use client";

import { FlaskConical } from "lucide-react";
import { api } from "@/lib/api";
import { PhasePage } from "@/components/shared/phase-page";

export default function Page() {
  return (
    <PhasePage
      title="Evaluations"
      description="Offline and online scoring of traces with versioned, calibrated judges"
      icon={FlaskConical}
      phase={3}
      fetcher={api.evals}
      will={[
        "Runs list with git SHA, dataset, judge model and cost",
        "Metric trends across commits with regression thresholds",
        "Per-example drill-down: score, rationale, evidence spans",
        "Side-by-side comparison of two runs",
      ]}
      metrics={[
        {
          name: "Faithfulness",
          formula:
            "Claims extracted from the answer, each checked against retrieved context by NLI; fraction supported.",
        },
        {
          name: "Answer relevance",
          formula:
            "Questions generated from the answer, embedded and compared to the user input; mean cosine similarity.",
        },
        {
          name: "Context precision",
          formula: "Rank-weighted fraction of retrieved chunks judged useful for the answer.",
        },
        {
          name: "Context recall",
          formula: "Sentences of the expected answer attributable to retrieved context / total.",
        },
        {
          name: "Hallucination",
          formula: "Inverse faithfulness with a contradicted vs unverifiable split.",
        },
      ]}
    />
  );
}
