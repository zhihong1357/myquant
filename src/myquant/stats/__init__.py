"""Statistical research primitives. All functions are paper/research only."""

from myquant.stats.bootstrap import (
    BootstrapInterval,
    BootstrapMeanTest,
    block_bootstrap_mean_ci,
    block_bootstrap_mean_test,
)
from myquant.stats.event_study import (
    EventClusterResult,
    EventStudyResult,
    EventWindowObservation,
    event_study,
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
from myquant.stats.walk_forward import (
    FoldForecastMetrics,
    WalkForwardEvaluation,
    WalkForwardFold,
    evaluate_walk_forward_forecasts,
    purged_walk_forward_splits,
)

__all__ = [
    "AdjustedPValue",
    "BootstrapInterval",
    "BootstrapMeanTest",
    "EventClusterResult",
    "EventStudyResult",
    "EventWindowObservation",
    "FoldForecastMetrics",
    "HACCoefficient",
    "HACResult",
    "LeadLagCorrelation",
    "OLSResult",
    "PartialLeadLagResult",
    "WalkForwardEvaluation",
    "WalkForwardFold",
    "adjust_pvalues",
    "annualized_volatility",
    "block_bootstrap_mean_ci",
    "block_bootstrap_mean_test",
    "evaluate_walk_forward_forecasts",
    "event_study",
    "lead_lag_scan",
    "log_returns",
    "newey_west_hac",
    "ols_fit",
    "partial_lead_lag",
    "purged_walk_forward_splits",
    "realized_variance",
    "realized_volatility",
    "simple_returns",
]
