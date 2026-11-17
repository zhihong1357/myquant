"""Statistical research primitives. All functions are paper/research only."""

from myquant.stats.bootstrap import (
    BootstrapInterval,
    BootstrapMeanTest,
    block_bootstrap_mean_ci,
    block_bootstrap_mean_test,
)
from myquant.stats.hac import (
    HACCoefficient,
    HACResult,
    newey_west_hac,
)
from myquant.stats.lead_lag import (
    LeadLagCorrelation,
    PartialLeadLagResult,
    lead_lag_scan,
    partial_lead_lag,
)
from myquant.stats.multiple_testing import (
    AdjustedPValue,
    adjust_pvalues,
)
from myquant.stats.regression import OLSResult, ols_fit
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
    "HACCoefficient",
    "HACResult",
    "LeadLagCorrelation",
    "OLSResult",
    "PartialLeadLagResult",
    "adjust_pvalues",
    "annualized_volatility",
    "block_bootstrap_mean_ci",
    "block_bootstrap_mean_test",
    "lead_lag_scan",
    "log_returns",
    "newey_west_hac",
    "ols_fit",
    "partial_lead_lag",
    "realized_variance",
    "realized_volatility",
    "simple_returns",
]
