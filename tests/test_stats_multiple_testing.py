import pytest

from myquant.contracts import MultiplicityCorrection
from myquant.stats.multiple_testing import adjust_pvalues


def adjusted_values(results):
    return [item.adjusted_p_value for item in results]


def test_bonferroni_adjusts_values_and_preserves_input_order():
    results = adjust_pvalues(
        [0.01, 0.04, 0.03],
        method=MultiplicityCorrection.BONFERRONI,
        target_error_rate=0.05,
    )
    assert adjusted_values(results) == pytest.approx([0.03, 0.12, 0.09])
    assert [item.original_index for item in results] == [0, 1, 2]
    assert [item.reject for item in results] == [True, False, False]


def test_holm_step_down_adjusted_p_values():
    results = adjust_pvalues(
        [0.01, 0.04, 0.03],
        method=MultiplicityCorrection.HOLM,
    )
    assert adjusted_values(results) == pytest.approx([0.03, 0.06, 0.06])


def test_benjamini_hochberg_adjusts_false_discovery_rate():
    results = adjust_pvalues(
        [0.01, 0.04, 0.03],
        method=MultiplicityCorrection.BENJAMINI_HOCHBERG,
    )
    assert adjusted_values(results) == pytest.approx([0.03, 0.04, 0.04])


def test_tied_p_values_are_stable_and_input_order_is_preserved():
    results = adjust_pvalues(
        [0.02, 0.02, 0.01],
        method=MultiplicityCorrection.HOLM,
    )
    assert [item.original_index for item in results] == [0, 1, 2]
    assert adjusted_values(results) == pytest.approx([0.04, 0.04, 0.03])


def test_none_correction_is_only_allowed_for_one_planned_test():
    result = adjust_pvalues([0.03], method=MultiplicityCorrection.NONE)
    assert result[0].adjusted_p_value == pytest.approx(0.03)
    with pytest.raises(ValueError, match="single planned test"):
        adjust_pvalues(
            [0.01, 0.02],
            method=MultiplicityCorrection.NONE,
        )


def test_p_value_validation_is_strict():
    with pytest.raises(ValueError, match="must not be empty"):
        adjust_pvalues([], method=MultiplicityCorrection.HOLM)
    with pytest.raises(ValueError, match="closed interval"):
        adjust_pvalues([1.2], method=MultiplicityCorrection.HOLM)
    with pytest.raises(ValueError, match="finite"):
        adjust_pvalues([float("nan")], method=MultiplicityCorrection.HOLM)
    with pytest.raises(ValueError, match="target_error_rate"):
        adjust_pvalues(
            [0.01],
            method=MultiplicityCorrection.NONE,
            target_error_rate=1.0,
        )


def test_adjust_pvalues_matches_statsmodels_golden_values():
    # Golden adjusted p-values from statsmodels 0.15.0 multipletests on
    # the fixed input below; myquant matches exactly (Bonferroni/Holm)
    # or to about 7e-18 (Benjamini-Hochberg).
    p_values = [0.001, 0.01, 0.04, 0.03, 0.5, 0.9]
    expected = {
        MultiplicityCorrection.BONFERRONI: [0.006, 0.06, 0.24, 0.18, 1.0, 1.0],
        MultiplicityCorrection.HOLM: [0.006, 0.05, 0.12, 0.12, 1.0, 1.0],
        MultiplicityCorrection.BENJAMINI_HOCHBERG: [
            0.006,
            0.03,
            0.06,
            0.06,
            0.6,
            0.9,
        ],
    }
    for method, values in expected.items():
        results = adjust_pvalues(p_values, method=method)
        assert adjusted_values(results) == pytest.approx(values, abs=1e-12)
