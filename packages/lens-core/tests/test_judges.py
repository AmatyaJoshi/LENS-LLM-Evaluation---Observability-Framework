from __future__ import annotations

import pytest

from lens_core.judges import list_prompts, load_prompt
from lens_core.judges.agreement import agreement, cohen_kappa, krippendorff_alpha, spearman_rho
from lens_core.judges.base import extract_json
from lens_core.judges.calibration import (
    IsotonicCalibrator,
    TemperatureScaler,
    brier_score,
    calibrate,
    expected_calibration_error,
)
from lens_core.judges.router import JudgeRouter


def test_all_prompts_parse_and_have_versions_and_fewshots() -> None:
    prompts = list_prompts()
    assert len(prompts) >= 12
    for p in prompts:
        assert p.version.isdigit()
        assert "{{" in p.user
        assert p.system.count("{") >= 4, f"{p.name} needs ≥4 few-shot examples"


def test_prompt_render_and_missing_variable() -> None:
    p = load_prompt("pairwise")
    system, user = p.render({"input": "t", "a": "x", "b": "y"})
    assert "Answer A:\nx" in user and "JSON" in system
    with pytest.raises(KeyError):
        p.render({"input": "t"})


def test_extract_json_tolerates_fences_and_prose() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": [1, 2]} hope that helps') == {"a": [1, 2]}


def test_spearman_and_kappa() -> None:
    assert spearman_rho([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman_rho([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    assert cohen_kappa([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0
    assert cohen_kappa([1, 1, 0, 0], [0, 0, 1, 1]) == pytest.approx(-1.0)
    assert cohen_kappa([1, 0, 1, 0], [1, 0, 0, 1]) == pytest.approx(0.0)


def test_krippendorff_alpha_levels() -> None:
    perfect = [[1, 2, 3, 4], [1, 2, 3, 4]]
    assert krippendorff_alpha(perfect, "interval") == pytest.approx(1.0)
    assert krippendorff_alpha(perfect, "nominal") == pytest.approx(1.0)
    assert krippendorff_alpha(perfect, "ordinal") == pytest.approx(1.0)
    noisy = [[1, 2, 3, 4], [4, 3, 2, 1]]
    assert krippendorff_alpha(noisy, "interval") < 0
    with_missing = [[1, None, 3], [1, 2, 3], [None, 2, 3]]
    assert krippendorff_alpha(with_missing, "interval") == pytest.approx(1.0)


def test_agreement_report() -> None:
    rep = agreement("faithfulness", "frontier", [0.9, 0.2, 0.8, 0.1], "human", [1, 0, 1, 0])
    assert rep.n == 4 and rep.cohen_kappa == 1.0
    assert rep.spearman_rho == pytest.approx(0.894, abs=1e-3)  # ties in the binary reference
    perfect = agreement("m", "j", [0.9, 0.2, 0.8, 0.1], "human", [0.95, 0.1, 0.85, 0.05])
    assert perfect.spearman_rho == pytest.approx(1.0)
    assert rep.mean_abs_error == pytest.approx(0.15)


def test_calibration_tools() -> None:
    preds = [0.9, 0.8, 0.7, 0.2, 0.1, 0.3]
    obs = [1, 1, 0, 0, 0, 1]
    assert 0 <= brier_score(preds, obs) <= 1
    assert 0 <= expected_calibration_error(preds, obs) <= 1
    ts = TemperatureScaler.fit(preds, obs)
    assert 0 < ts.temperature <= 10
    iso = IsotonicCalibrator.fit(preds, obs)
    ys = [iso.apply(p) for p in sorted(preds)]
    assert ys == sorted(ys), "isotonic output must be monotone"
    rep = calibrate("frontier", "faithfulness", preds, obs)
    assert rep.brier_isotonic <= rep.brier_raw + 1e-9
    assert len(rep.bins_raw) == 10


def test_router_from_env_with_cassette(tmp_path) -> None:
    cassette = tmp_path / "c.json"
    cassette.write_text('{"entries": {}}', encoding="utf-8")
    router = JudgeRouter.from_env({"LENS_JUDGE_CASSETTE": str(cassette)})
    assert router.get("frontier").model == "cassette" and router.has("local")
    with pytest.raises(KeyError):
        JudgeRouter().get("frontier")
