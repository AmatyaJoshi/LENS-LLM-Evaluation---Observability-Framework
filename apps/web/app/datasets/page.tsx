"use client";

import { Database } from "lucide-react";
import { api } from "@/lib/api";
import { PhasePage } from "@/components/shared/phase-page";

export default function Page() {
  return (
    <PhasePage
      title="Datasets"
      description="Golden sets built from real traces, split without leakage"
      icon={Database}
      phase={4}
      fetcher={api.datasets}
      will={[
        "Create datasets and promote selected traces into them",
        "Train / dev / test splits by source document to avoid leakage",
        "Import JSONL with input, expected output and contexts",
        "Datasets feed lens eval and the CI regression gate",
      ]}
    />
  );
}
