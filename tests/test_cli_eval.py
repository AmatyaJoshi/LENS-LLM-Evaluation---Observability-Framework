from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lens_core.cli import app, compare, markdown_summary, parse_thresholds

runner = CliRunner()


def _cassette(tmp_path: Path) -> Path:
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps(
            {
                "entries": {
                    "claim_extraction": [{"claims": ["a"]}] * 4,
                    "claim_verification": [{"verdicts": [{"claim": "a", "verdict": "supported"}]}]
                    * 4,
                }
            }
        ),
        encoding="utf-8",
    )
    return p


def test_eval_local_on_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LENS_JUDGE_CASSETTE", str(_cassette(tmp_path)))
    data = tmp_path / "golden.jsonl"
    data.write_text(
        json.dumps({"question": "q", "answer": "a", "contexts": ["c"]})
        + "\n"
        + json.dumps({"question": "q2", "answer": "a2", "contexts": ["c2"]})
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "results.json"
    result = runner.invoke(
        app,
        [
            "eval",
            "--dataset",
            str(data),
            "--app",
            "demo",
            "--metrics",
            "faithfulness",
            "--local",
            "--out",
            str(out),
            "--sha",
            "abc",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "faithfulness" in result.output and "1.000" in result.output
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["summary"]["metrics"] == {"faithfulness": 1.0}
    assert report["judge"]["model"] == "cassette" and len(report["items"]) == 2


def test_thresholds_and_compare() -> None:
    thr = parse_thresholds("faithfulness:-0.03, hallucination:+0.02")
    assert thr == {"faithfulness": -0.03, "hallucination": 0.02}
    rows = compare(
        {"faithfulness": 0.80, "hallucination": 0.15, "answer_relevance": 0.9},
        {"faithfulness": 0.85, "hallucination": 0.10, "answer_relevance": 0.905},
        thr,
        {"faithfulness": True, "hallucination": False, "answer_relevance": True},
    )
    by = {r["metric"]: r for r in rows}
    assert by["faithfulness"]["regressed"] is True  # dropped 0.05 > 0.03 allowed
    assert by["hallucination"]["regressed"] is True  # rose 0.05 > 0.02 allowed
    assert by["answer_relevance"]["regressed"] is False  # within default 0.02 tolerance
    md = markdown_summary(rows, title="t")
    assert "❌ regression" in md and "| faithfulness |" in md


def test_ci_offline_with_baseline_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LENS_JUDGE_CASSETTE", str(_cassette(tmp_path)))
    monkeypatch.setenv("LENS_ENDPOINT", "http://127.0.0.1:9")  # unreachable → offline mode
    data = tmp_path / "g.jsonl"
    data.write_text(
        json.dumps({"question": "q", "answer": "a", "contexts": ["c"]}) + "\n", encoding="utf-8"
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"summary": {"metrics": {"faithfulness": 1.0}}}), encoding="utf-8"
    )
    summary = tmp_path / "summary.md"
    ok = runner.invoke(
        app,
        [
            "ci",
            "--dataset",
            str(data),
            "--app",
            "demo",
            "--metrics",
            "faithfulness",
            "--baseline-file",
            str(baseline),
            "--summary-file",
            str(summary),
            "--sha",
            "abc",
        ],
    )
    assert ok.exit_code == 0, ok.output
    assert "no regressions" in ok.output and summary.read_text(encoding="utf-8").startswith(
        "### Lens evaluation gate"
    )

    # a baseline far above what we can reach → regression → exit 1
    baseline.write_text(
        json.dumps({"summary": {"metrics": {"faithfulness": 1.5}}}), encoding="utf-8"
    )
    bad = runner.invoke(
        app,
        [
            "ci",
            "--dataset",
            str(data),
            "--app",
            "demo",
            "--metrics",
            "faithfulness",
            "--baseline-file",
            str(baseline),
            "--sha",
            "abc",
        ],
    )
    assert bad.exit_code == 1 and "REGRESSION" in bad.output
