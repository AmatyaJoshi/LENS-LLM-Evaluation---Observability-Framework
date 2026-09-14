import { describe, expect, it } from "vitest";
import { fmtMs, fmtInt, fmtCompact, fmtPct, fmtUsd, shortId, truncate } from "@/lib/format";

describe("format helpers", () => {
  it("formats durations across ranges", () => {
    expect(fmtMs(0.4)).toBe("400 µs");
    expect(fmtMs(12)).toBe("12 ms");
    expect(fmtMs(1500)).toBe("1.50 s");
    expect(fmtMs(65000)).toBe("1m 5s");
    expect(fmtMs(NaN)).toBe("–");
  });
  it("formats numbers, percents and money", () => {
    expect(fmtInt(1234)).toBe("1,234");
    expect(fmtCompact(1500)).toBe("1.5K");
    expect(fmtPct(0.0667)).toBe("6.7%");
    expect(fmtUsd(0)).toBe("$0.00");
    expect(fmtUsd(0.0009)).toBe("$0.0009");
    expect(fmtUsd(2.5)).toBe("$2.50");
  });
  it("shortens ids and truncates text", () => {
    expect(shortId("0af7651916cd43dd", 8)).toBe("0af76519");
    expect(truncate("hello world", 6)).toBe("hello…");
    expect(truncate("hi", 6)).toBe("hi");
  });
});
