"use client";

import { ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import { PhasePage } from "@/components/shared/phase-page";

export default function Page() {
  return (
    <PhasePage
      title="Security"
      description="Live prompt-injection detection over incoming messages, retrieved documents and tool results"
      icon={ShieldAlert}
      phase={6}
      fetcher={api.redteam}
      will={[
        "Flagged traffic with lens.security.injection_score per span",
        "ONNX int8 DeBERTa detector running in the ingest path under 50 ms p95 on CPU",
        "Per-dataset F1 and hard-negative false-positive rate, traceable to result files",
        "Held-out mutator robustness so the numbers are not inflated by easy public sets",
      ]}
    />
  );
}
