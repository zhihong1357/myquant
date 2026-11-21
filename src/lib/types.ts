export interface LabCounts {
  broken_links: number;
  candidates_ranked: number;
  candidates_total: number;
  candidates_unrankable: number;
  decision_records: number;
  edges_descriptive: number;
  edges_pending: number;
  edges_rejected: number;
  edges_supported: number;
  edges_total: number;
  hypotheses: number;
  hypothesis_versions: number;
  missing_optional: number;
  nodes: number;
  panels: number;
  sources: number;
  studies: number;
  templates: number;
  trials_completed: number;
  trials_failed: number;
  trials_reserved: number;
  trials_total: number;
}

export interface SupportedEdgeAudit {
  edge_id: string;
  study: string;
  hypothesis_id: string;
  trial_id: string;
  test_type: string;
  raw_p_value: number;
  holm_adjusted_p_value: number;
  holm_significant: boolean;
  bh_adjusted_p_value: number;
  bh_significant: boolean;
  caveat?: string;
  bootstrap_ci_lower?: number;
  bootstrap_ci_upper?: number;
}

export interface FailedTrialItem {
  trial_id: string;
  hypothesis_id: string;
  study: string;
  failure_reason: string;
}

export interface CalibrationDiagnostic {
  label: string;
  metric: string;
  observed: number;
  target: number;
  monte_carlo_se: number;
  replications: number;
  observations?: number;
  family_size?: number;
}

export interface OverviewPayload {
  generated_at: string;
  evidence_probed_at: string;
  counts: LabCounts;
  audit: {
    alpha: number;
    family_size: number;
    supported_total: number;
    holm_survivors: number;
    bh_survivors: number;
    raw_rejections_at_alpha: number;
    expected_false_positives_uncorrected: number;
    bh_expected_false_discoveries_upper_bound: number;
    storey_pi0_lambda_0_5: number;
    supported_edges: SupportedEdgeAudit[];
  };
  review: {
    reviewed_at: string;
    counts: {
      pass: number;
      fail: number;
      unverified: number;
      note: number;
    };
  };
  calibration: CalibrationDiagnostic[];
  failed_trials: FailedTrialItem[];
  missing_optional: Array<{ path: string; reason: string }>;
  post_probe_updates: Array<{ instrument_id: string; note: string; source_file: string }>;
}

export interface GraphNode {
  instrument_id: string;
  short_label: string;
  name: string;
  asset_class: string;
  instrument_type: string;
  calendar_id: string;
  studies: string[];
}

export interface EdgeHygieneInfo {
  edgeId: string;
  isMechanicalIdentity: boolean;
  usesDiscontinuedSeries: boolean;
  cleanForPlanner: boolean;
  reason: string | null;
}

export interface GraphEdge {
  edge_id: string;
  source_instrument: string;
  target_instrument: string;
  status: 'supported' | 'rejected' | 'descriptive' | 'pending_forward' | string;
  test_type: string;
  hypothesis_id: string;
  trial_id: string;
  frequency: string;
  method: string;
  coefficient: number | null;
  standard_error: number | null;
  t_statistic: number | null;
  p_value: number | null;
  holm_adjusted_p_value: number | null;
  partial_r_squared: number | null;
  observations: number | null;
  verdict_summary: string;
  report_path: string;
  ledger_test_key: string;
  condition?: string | null;
  common_factor_control?: string | null;
  cost_gate?: {
    verdict: string;
    gross_daily_edge?: number;
    net_daily_edge?: number;
    note?: string;
  } | null;
  hygiene?: EdgeHygieneInfo;
}

export interface RankedCandidate {
  rank: number | null;
  ranked: boolean;
  source_instrument: string;
  target_instrument: string;
  mechanism: string;
  test_type: string;
  total_score: number | null;
  has_template: boolean;
  unrankable_reason: string | null;
}

export interface GraphPayload {
  content_hash: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  candidates: RankedCandidate[];
  hygiene_summary?: {
    total_edges: number;
    clean_edges: number;
    excluded_edges: number;
    discontinued_instruments: string[];
    mechanical_edge_ids: string[];
  };
}

export interface StudyListItem {
  slug: string;
  status: string;
  report_path: string;
  report_exists: boolean;
  anchor_present: boolean;
  hypotheses: string[];
  trials: string[];
  review_counts: {
    pass: number;
    fail: number;
    unverified: number;
    note: number;
  };
  supported_trials: number;
  completed_trials: number;
  failed_trials: number;
}

export interface StudyDetail {
  slug: string;
  report_path: string;
  markdown: string;
  trials: Array<{
    trial_id: string;
    hypothesis_id: string;
    status: string;
    supported: boolean | null;
    primary_test: string | null;
    primary_test_type: string | null;
    primary_effect_label: string | null;
    primary_effect_value: number | null;
    primary_raw_p_value: number | null;
    primary_adjusted_p_value: number | null;
    secondary_effect_label: string | null;
    secondary_effect_value: number | null;
    observations: number | null;
    failure_reason: string | null;
    recorded_at: string;
    record_hash: string;
  }>;
  hypotheses: Array<{
    hypothesis_id: string;
    latest_state: string;
    versions: Array<{
      version: number;
      state: string;
      registered_at: string;
      spec_fingerprint: string;
    }>;
  }>;
  review_checks: Array<{
    check_id: string;
    subject: string;
    summary: string;
    verdict: 'pass' | 'fail' | 'unverified' | 'note' | string;
    evidence: string[];
  }>;
}

export interface DecisionRecordSummary {
  record_id: string;
  record_type: 'supported_edge' | 'rejected_hypothesis' | string;
  conclusion: string;
  conclusion_scope?: string;
  study: string;
  hypothesis_id: string;
  hypothesis_version: number;
  edge_id: string | null;
  trial_id: string;
  report_path: string;
  preregistration_fingerprint: string;
  trial_record_hash: string;
  audit_notes: string[];
  limitations: string[];
  evidence: {
    primary_test?: Record<string, unknown>;
    lab_wide?: {
      family_size: number;
      holm_adjusted_p_value: number;
      holm_significant: boolean;
      bh_adjusted_p_value: number;
      bh_significant: boolean;
    } | null;
    family_tests?: Array<{
      edge_id?: string;
      test_key: string;
      raw_p_value: number;
      holm_adjusted_p_value: number;
      reject: boolean;
    }>;
    sample?: {
      first?: string;
      last?: string;
      observations?: number;
      panel_rows?: number;
    };
  };
}

export interface SourcesAndPanelsPayload {
  probed_at: string;
  sources: Array<{
    source_id: string;
    provider: string;
    probe_kind: string;
    last_verified: string;
    probe_pass: number;
    probe_fail: number;
    probe_skip: number;
    quirks: number;
    used_by: string[];
    checks: Array<{
      check_id: string;
      status: string;
      evidence: string;
      latest_date: string | null;
    }>;
  }>;
  panels: Array<{
    instrument_id: string;
    source_id: string;
    panel_last: string;
    expected_latest: string;
    days_behind: number;
    status: string;
    lag_kind: string;
    latest_from: string;
  }>;
}

export interface LedgerTrialRow {
  index: number;
  leafHash: string;
  chainHash: string;
  merkleRootAfter: string;
  trialId: string;
  strategyId: string;
  strategyName: string;
  mode: 'qp_optimized' | 'legacy_sign_rule';
  recordedAt: string;
  seed: number;
  observations: number;
  netSharpe: number;
  grossSharpe: number;
  annualizedVolPct: number;
  maxDrawdownPct: number;
  totalNetReturnPct: number;
  avgDailyTurnover: number;
  liquidated: boolean;
  rawPValue: number;
  deflatedSharpeRatio: number;
  lordAlphaThreshold: number | null;
  lordAccepted: boolean;
}

export interface LedgerOverviewPayload {
  strategies: Array<{
    id: 'perp_carry_funding' | 'volume_clock_ofi' | 'macro_event_vrp';
    name: string;
    universe: string[];
    cadence: string;
    mechanism: string;
    economicBasis: string;
  }>;
  anchor: {
    count: number;
    latestChainHash: string;
    merkleRoot: string;
    updatedAt: string;
  };
  integrity: {
    valid: boolean;
    checkedCount: number;
    error: string | null;
  };
  cscvPbo: {
    numStrategies: number;
    observations: number;
    numSubsets: number;
    combinationsEvaluated: number;
    pbo: number;
    meanRelativeOosRank: number;
    medianLogit: number;
    degradationSlope: number;
  } | null;
  onlineLordRejections: number;
  latestProof: {
    index: number;
    leafHash: string;
    merkleRoot: string;
    proofDepth: number;
    verified: boolean;
  } | null;
  entries: LedgerTrialRow[];
}

export interface ExecutionSimPayload {
  referenceMid: number;
  initialTop5Depth: number;
  childFills: Array<{
    childIndex: number;
    requestedContracts: number;
    filledContracts: number;
    vwapFillPrice: number;
    levelsSwept: number;
    bookWalkSlippageBps: number;
    permanentImpactBps: number;
    totalEffectiveCostBps: number;
    remainingTop5DepthAfter: number;
  }>;
  impactCurve: Array<{
    depthMultiple: number;
    orderContracts: number;
    squareRootBps: number;
    legacyCappedBps: number;
  }>;
  passiveMarkout: {
    queueAheadUsed: number;
    conservativeFallbackApplied: boolean;
    filledContracts: number;
    fillRate: number;
    touchOnlyFills: number;
    tradeThroughFills: number;
    avgFillPrice: number | null;
    markout1sBps: number | null;
    markout10sBps: number | null;
    markout60sBps: number | null;
    adverseSelectionDetected: boolean;
  };
  marginStress: {
    initialEquity: number;
    finalEquity: number;
    liquidated: boolean;
    liquidationTimestamp: string | null;
    liquidationPrice: number | null;
    liquidationFeePaid: number;
    peakLeverage: number;
    maxDrawdownPct: number;
    totalFundingPaid: number;
    totalFeesPaid: number;
    naiveNoMarginFinalEquity: number;
    equityCurve: Array<{
      timestampIso: string;
      equity: number;
      naiveEquity: number;
      marginRatio: number;
      liquidated: boolean;
    }>;
  };
}
