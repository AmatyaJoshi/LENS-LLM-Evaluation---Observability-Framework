"use client";

import { Scale } from "lucide-react";
import { api } from "@/lib/api";
import { PhasePage } from "@/components/shared/phase-page";

export default function Page() {
  return (
    <PhasePage
      title="Judge quality"
      description="How good the judges themselves are, measured against human labels"
      icon={Scale}
      phase={4}
      fetcher={api.labels}
      will={[
        "Cohen's κ, Krippendorff's α and Spearman ρ per judge × metric, against the human gold set",
        "Calibration curves (temperature scaling / isotonic) per judge",
        "Cost and p95 latency per 1k evaluations: frontier vs second-opinion vs distilled local judge",
        "Disagreement queue feeding the labelling UI",
      ]}
    />
  );
}
