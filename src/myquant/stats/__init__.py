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
from myquant.stats.walk_forward import (\n    FoldForecastMetrics,\n    WalkForwardEvaluation,\n    WalkForwardFold,\n    evaluate_walk_forward_forecasts,\n    purged_walk_forward_splits,\n)\nfrom myquant.stats.returns import (
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
    "FoldForecastMetrics",\n    "HACCoefficient",
    "HACResult",
    "LeadLagCorrelation",
    "OLSResult",
    "PartialLeadLagResult",\n    "WalkForwardEvaluation",\n    "WalkForwardFold",
    "adjust_pvalues",\n    "evaluate_walk_forward_forecasts",
    "annualized_volatility",
    "block_bootstrap_mean_ci",
    "block_bootstrap_mean_test",
    "lead_lag_scan",
    "log_returns",
    "newey_west_hac",
    "ols_fit",
    "partial_lead_lag",\n    "purged_walk_forward_splits",
    "realized_variance",
    "realized_volatility",
    "simple_returns",
]
