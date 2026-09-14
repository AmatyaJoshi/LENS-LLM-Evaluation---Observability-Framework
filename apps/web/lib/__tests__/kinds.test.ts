import { describe, expect, it } from "vitest";
import { kindOf, KIND_LABEL, KIND_ORDER } from "@/lib/kinds";

describe("span kinds", () => {
  it("maps known kinds and falls back to other", () => {
    expect(kindOf("llm")).toBe("llm");
    expect(kindOf("retrieval")).toBe("retrieval");
    expect(kindOf("nonsense")).toBe("other");
  });
  it("has a label for every ordered kind", () => {
    for (const k of KIND_ORDER) expect(KIND_LABEL[k]).toBeTruthy();
  });
});
