"""Statistical research primitives. All functions are paper/research only."""

from myquant.stats.bootstrap import (
    BootstrapInterval,
    BootstrapMeanTest,
    block_bootstrap_mean_ci,
    block_bootstrap_mean_test,
)
from myquant.stats.lead_lag import LeadLagCorrelation, lead_lag_scan
from myquant.stats.multiple_testing import (
    AdjustedPValue,
    adjust_pvalues,
)
from myquant.stats.returns import (
    annualized_volatility,
    log_returns,
    realized_variance,
    realized_volatility,
    simple_returns,
)

__all__ = [
    "AdjustedPValue",
    "BootstrapInterval",
    "BootstrapMeanTest",
    "LeadLagCorrelation",
    "adjust_pvalues",
    "annualized_volatility",
    "block_bootstrap_mean_ci",
    "block_bootstrap_mean_test",
    "lead_lag_scan",
    "log_returns",
    "realized_variance",
    "realized_volatility",
    "simple_returns",
]
