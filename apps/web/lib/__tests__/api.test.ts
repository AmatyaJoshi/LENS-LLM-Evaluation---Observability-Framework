import { describe, expect, it } from "vitest";
import { windowToSinceNs } from "@/lib/api";

describe("windowToSinceNs", () => {
  it("returns undefined for all-time and a past ns otherwise", () => {
    const now = 1_000_000_000_000; // ms
    expect(windowToSinceNs("all", now)).toBeUndefined();
    expect(windowToSinceNs("1h", now)).toBe((now - 3600_000) * 1e6);
    expect(windowToSinceNs("24h", now)).toBe((now - 86_400_000) * 1e6);
  });
});
