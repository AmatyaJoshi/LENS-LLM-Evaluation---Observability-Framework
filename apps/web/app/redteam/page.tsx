"use client";

import { Crosshair } from "lucide-react";
import { api } from "@/lib/api";
import { PhasePage } from "@/components/shared/phase-page";

export default function Page() {
  return (
    <PhasePage
      title="Red team"
      description="Continuous adversarial testing of your own application with attack success rate over time"
      icon={Crosshair}
      phase={5}
      fetcher={api.redteam}
      will={[
        "150+ probes across direct/indirect injection, jailbreak, exfiltration, tool abuse and denial-of-wallet",
        "Automatic mutators (paraphrase, encoding, translation, confusables, multi-turn) with lineage",
        "ASR by category, mutator and git SHA: the before/after-defence chart",
        "Detector-caught rate: how many successful attacks the live detector flagged",
        "Success is defined only as a policy violation of the target, never as harmful content",
      ]}
    />
  );
}
