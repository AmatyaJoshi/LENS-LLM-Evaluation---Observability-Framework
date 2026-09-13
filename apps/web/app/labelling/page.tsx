"use client";

import { Tags } from "lucide-react";
import { api } from "@/lib/api";
import { PhasePage } from "@/components/shared/phase-page";

export default function Page() {
  return (
    <PhasePage
      title="Labelling"
      description="Keyboard-driven human labelling that builds the gold set"
      icon={Tags}
      phase={4}
      fetcher={api.labels}
      will={[
        "Label a trace or example for one metric with single-key shortcuts",
        "Disagreement-first queue: items where judges disagree come up first",
        "Inter-annotator overlap set with κ between labellers",
        "Published labelling guide alongside the dataset",
      ]}
    />
  );
}
