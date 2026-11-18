"""Tests for the standard-normal CDF and quantile helpers."""

import math

import pytest

from myquant.stats._normal import (
    normal_cdf,
    normal_pdf,
    normal_ppf,
    normal_sf,
    normal_two_sided_p_value,
)


def test_normal_cdf_known_values():
    assert normal_cdf(0.0) == pytest.approx(0.5)
    assert normal_cdf(1.959963984540054) == pytest.approx(0.975, abs=1e-12)
    assert normal_cdf(-1.959963984540054) == pytest.approx(0.025, abs=1e-12)
    assert normal_cdf(3.0) == pytest.approx(0.9986501019683699, abs=1e-12)


def test_normal_ppf_known_values():
    assert normal_ppf(0.5) == pytest.approx(0.0, abs=1e-12)
    assert normal_ppf(0.975) == pytest.approx(1.959963984540054, abs=1e-9)
    assert normal_ppf(0.025) == pytest.approx(-1.959963984540054, abs=1e-9)
    assert normal_ppf(0.001) == pytest.approx(-3.090232306167813, abs=1e-9)
    assert normal_ppf(0.999) == pytest.approx(3.090232306167813, abs=1e-9)
    assert normal_ppf(0.8) == pytest.approx(0.8416212335729143, abs=1e-9)
    assert normal_ppf(0.95) == pytest.approx(1.6448536269514722, abs=1e-9)


def test_normal_ppf_round_trips_through_cdf():
    for p in (0.0001, 0.01, 0.1, 0.3, 0.5, 0.7, 0.9, 0.99, 0.9999):
        assert normal_cdf(normal_ppf(p)) == pytest.approx(p, abs=1e-9)


def test_normal_ppf_rejects_endpoints_and_out_of_range():
    for bad in (0.0, 1.0, -0.1, 1.1, math.nan, math.inf):
        with pytest.raises(ValueError):
            normal_ppf(bad)


def test_normal_cdf_rejects_non_finite():
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError):
            normal_cdf(bad)


def test_normal_sf_and_two_sided_p_value():
    assert normal_sf(0.0) == pytest.approx(0.5)
    assert normal_sf(1.959963984540054) == pytest.approx(0.025, abs=1e-12)
    assert normal_two_sided_p_value(0.0) == pytest.approx(1.0)
    assert normal_two_sided_p_value(1.959963984540054) == pytest.approx(0.05, abs=1e-9)
    assert normal_two_sided_p_value(-1.959963984540054) == pytest.approx(0.05, abs=1e-9)


def test_normal_pdf():
    assert normal_pdf(0.0) == pytest.approx(1.0 / math.sqrt(2.0 * math.pi))
    assert normal_pdf(1.0) == pytest.approx(0.24197072451914337)
