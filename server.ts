import express from 'express';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  adjustPValues,
  assessEdgeHygiene,
  DISCONTINUED_INSTRUMENTS,
  filterCleanLabEdges,
  MECHANICAL_EDGE_IDS,
  onlineLordPlusPlus,
  type MultiplicityMethod,
} from './src/lib/quant/multipleTesting.ts';
import {
  mdeCohensD,
  mdeCoefficient,
  mdeMeanRatio,
  mdePartialRSquared,
  mdeStandardizedMean,
} from './src/lib/quant/power.ts';
import {
  estimatePaperExecutionCost,
  legacyLinearCappedImpactBps,
  squareRootImpactBps,
} from './src/lib/quant/executionCosts.ts';
import {
  buildSyntheticL2Book,
  CoupledOrderBook,
  runPerpetualMarginStress,
  simulatePassiveLimitOrder,
  type MarginStressBar,
} from './src/lib/quant/executionEngine.ts';
import {
  runSyntheticLeadLag,
  type FactorTimingMode,
  type SyntheticScenario,
} from './src/lib/quant/leadLag.ts';
import { computeCscvPbo } from './src/lib/quant/overfitting.ts';
import { compareSignRuleVsQP } from './src/lib/quant/portfolioOptimizer.ts';
import { runBitemporalAuditDemo } from './src/lib/engine/bitemporalStore.ts';
import { IncrementalMerkleLedger } from './src/lib/engine/merkleLedger.ts';
import { capturePublicMarketSnapshot } from './src/lib/engine/marketRecorder.ts';
import {
  runUnifiedStrategyPipeline,
  STRATEGY_CATALOG,
  type StrategyId,
} from './src/lib/engine/unifiedPipeline.ts';
import {
  runPurgedWalkForwardAudit,
  runStrategyArena,
} from './src/lib/quant/walkForward.ts';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = __dirname;

const PORT = Number(process.env.PORT ?? 3000);
const IS_PROD = process.env.NODE_ENV === 'production';

function readJsonFile<T>(relPath: string): T {
  const fullPath = path.resolve(ROOT_DIR, relPath);
  return JSON.parse(fs.readFileSync(fullPath, 'utf-8')) as T;
}

interface RawCatalog {
  generated_at: string;
  evidence_probed_at: string;
  counts: Record<string, number>;
  studies: Array<{
    slug: string;
    status: string;
    report_path: string;
    report_exists: boolean;
    anchor_present: boolean;
    hypotheses: string[];
    trials: string[];
  }>;
  trials: Array<{
    trial_id: string;
    hypothesis_id: string;
    study: string;
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
    study: string;
    latest_state: string;
    versions: Array<{
      version: number;
      state: string;
      registered_at: string;
      spec_fingerprint: string;
    }>;
  }>;
  candidates: Array<{
    rank: number | null;
    ranked: boolean;
    source_instrument: string;
    target_instrument: string;
    mechanism: string;
    test_type: string;
    total_score: number | null;
    has_template: boolean;
    unrankable_reason: string | null;
  }>;
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
  missing_optional: Array<{ path: string; reason: string }>;
  post_probe_updates: Array<{ instrument_id: string; note: string; source_file: string }>;
  review: {
    counts: { pass: number; fail: number; unverified: number; note: number };
    per_study_counts: Record<string, { pass: number; fail: number; unverified: number; note: number }>;
  };
}

interface RawRegistry {
  content_hash: string;
  nodes: Array<Record<string, unknown>>;
  edges: Array<{
    edge_id: string;
    source_instrument?: string;
    target_instrument?: string;
    status: string;
    p_value: number | null;
    [key: string]: unknown;
  }>;
}

interface RawAuditSummary {
  calibration: Record<string, Record<string, number>>;
  lab_wide_audit: {
    alpha: number;
    family_size: number;
    holm_survivors: number;
    bh_survivors: number;
    raw_rejections_at_alpha: number;
    expected_false_positives_uncorrected: number;
    bh_expected_false_discoveries_upper_bound: number;
    'storey_pi0_lambda_0.5': number;
    supported_edges: Array<Record<string, unknown>>;
  };
}

interface RawReviewReport {
  reviewed_at: string;
  counts: { pass: number; fail: number; unverified: number; note: number };
  studies: Array<{
    study: string;
    report_path: string;
    counts: { pass: number; fail: number; unverified: number; note: number };
    checks: Array<{
      check_id: string;
      subject: string;
      summary: string;
      verdict: string;
      evidence: string[];
    }>;
  }>;
}

interface RawEvidenceReport {
  probed_at: string;
  sources: Array<{
    source_id: string;
    checks: Array<{
      check_id: string;
      status: string;
      evidence: string;
      latest_date: string | null;
    }>;
  }>;
}

// Load immutable lab datasets into memory at boot
const catalog = readJsonFile<RawCatalog>('research/library-6e/catalog.json');
const registry = readJsonFile<RawRegistry>('research/graph/registry.json');
const auditSummary = readJsonFile<RawAuditSummary>('research/statistical-audit-2b/summary.json');
const reviewReport = readJsonFile<RawReviewReport>('research/review-6d/review_report.json');
const evidenceReport = readJsonFile<RawEvidenceReport>('research/evidence-6b/evidence_report.json');

const decisionRecordsDir = path.resolve(ROOT_DIR, 'research/decision-records/records');
const decisionRecords = fs
  .readdirSync(decisionRecordsDir)
  .filter((name) => name.endsWith('.json'))
  .sort()
  .map((name) =>
    JSON.parse(fs.readFileSync(path.join(decisionRecordsDir, name), 'utf-8')) as Record<
      string,
      unknown
    >,
  );

// Initialize persistent O(1) Incremental Merkle Ledger for Unified Strategy Engine
const ledgerPath = path.resolve(ROOT_DIR, 'data/institutional-ledger.jsonl');
const merkleLedger = new IncrementalMerkleLedger(ledgerPath);
if (merkleLedger.getEntries().length === 0) {
  // Seed 3 deterministic baseline paper trials across the 3 tradable strategies so CSCV-PBO & Online LORD++ are live on boot
  const seedConfigs: Array<{ strategyId: StrategyId; mode: 'qp_optimized' | 'legacy_sign_rule'; seed: number }> = [
    { strategyId: 'perp_carry_funding', mode: 'qp_optimized', seed: 2026 },
    { strategyId: 'volume_clock_ofi', mode: 'qp_optimized', seed: 2042 },
    { strategyId: 'macro_event_vrp', mode: 'qp_optimized', seed: 2088 },
  ];
  for (const cfg of seedConfigs) {
    runUnifiedStrategyPipeline(
      {
        strategyId: cfg.strategyId,
        optimizerMode: cfg.mode,
        periods: 240,
        targetAnnualVol: 0.14,
        maxLeverage: 2.0,
        linearCostBps: 6.5,
        seed: cfg.seed,
        persistToLedger: true,
      },
      merkleLedger,
    );
  }
}

function buildLedgerOverview() {
  const entries = merkleLedger.getEntries();
  const anchor = merkleLedger.getAnchor();
  const integrity = merkleLedger.verifyIntegrity();
  const pValues = entries.map((e) => e.record.rawPValue);
  const lord = pValues.length > 0 ? onlineLordPlusPlus(pValues, 0.05) : [];

  const returnMatrix = entries
    .map((e) => e.record.netReturns)
    .filter((r) => Array.isArray(r) && r.length >= 64);

  let cscvPbo: {
    numStrategies: number;
    observations: number;
    numSubsets: number;
    combinationsEvaluated: number;
    pbo: number;
    meanRelativeOosRank: number;
    medianLogit: number;
    degradationSlope: number;
  } | null = null;

  if (returnMatrix.length >= 2) {
    try {
      const res = computeCscvPbo(returnMatrix, 8, 70, 2026);
      cscvPbo = {
        numStrategies: res.numStrategies,
        observations: res.observations,
        numSubsets: res.numSubsets,
        combinationsEvaluated: res.combinationsEvaluated,
        pbo: res.pbo,
        meanRelativeOosRank: res.meanRelativeOosRank,
        medianLogit: res.medianLogit,
        degradationSlope: res.degradationSlope,
      };
    } catch {
      cscvPbo = null;
    }
  }

  let latestProof = null;
  if (entries.length > 0) {
    const idx = entries.length - 1;
    const p = merkleLedger.proveInclusion(idx);
    latestProof = {
      index: idx,
      leafHash: p.leafHash,
      merkleRoot: p.merkleRoot,
      proofDepth: p.proof.length,
      verified: p.verified,
    };
  }

  return {
    strategies: STRATEGY_CATALOG,
    anchor,
    integrity,
    cscvPbo,
    onlineLordRejections: lord.filter((r) => r.reject).length,
    latestProof,
    entries: entries.map((e, i) => ({
      index: e.index,
      leafHash: e.leafHash,
      chainHash: e.chainHash,
      merkleRootAfter: e.merkleRootAfter,
      trialId: e.record.trialId,
      strategyId: e.record.strategyId,
      strategyName: e.record.strategyName,
      mode: e.record.mode,
      recordedAt: e.record.recordedAt,
      seed: e.record.seed,
      observations: e.record.observations,
      netSharpe: e.record.netSharpe,
      grossSharpe: e.record.grossSharpe,
      annualizedVolPct: e.record.annualizedVolPct,
      maxDrawdownPct: e.record.maxDrawdownPct,
      totalNetReturnPct: e.record.totalNetReturnPct,
      avgDailyTurnover: e.record.avgDailyTurnover,
      liquidated: e.record.liquidated,
      rawPValue: e.record.rawPValue,
      deflatedSharpeRatio: e.record.deflatedSharpeRatio,
      lordAlphaThreshold: lord[i]?.alphaThreshold ?? null,
      lordAccepted: lord[i]?.reject ?? false,
    })),
  };
}

function buildCalibrationList() {
  const c = auditSummary.calibration;
  return [
    {
      label: 'Newey-West HAC Size (i.i.d.)',
      metric: 'Rejection rate at α = 0.05',
      observed: c['hac_size_iid'].rejection_rate,
      target: c['hac_size_iid'].alpha,
      monte_carlo_se: c['hac_size_iid'].monte_carlo_se,
      replications: c['hac_size_iid'].replications,
      observations: c['hac_size_iid'].observations,
    },
    {
      label: 'Newey-West HAC Size (AR(1) φ = 0.3)',
      metric: 'Rejection rate at α = 0.05',
      observed: c['hac_size_ar1_0.3'].rejection_rate,
      target: c['hac_size_ar1_0.3'].alpha,
      monte_carlo_se: c['hac_size_ar1_0.3'].monte_carlo_se,
      replications: c['hac_size_ar1_0.3'].replications,
      observations: c['hac_size_ar1_0.3'].observations,
    },
    {
      label: 'Block-Bootstrap 95% CI Coverage (i.i.d.)',
      metric: 'Empirical coverage (block = 10)',
      observed: c['bootstrap_coverage_iid'].coverage,
      target: c['bootstrap_coverage_iid'].confidence_level,
      monte_carlo_se: c['bootstrap_coverage_iid'].monte_carlo_se,
      replications: c['bootstrap_coverage_iid'].replications,
      observations: c['bootstrap_coverage_iid'].observations,
    },
    {
      label: 'Block-Bootstrap 95% CI Coverage (AR(1) φ = 0.3)',
      metric: 'Empirical coverage (block = 10)',
      observed: c['bootstrap_coverage_ar1_0.3'].coverage,
      target: c['bootstrap_coverage_ar1_0.3'].confidence_level,
      monte_carlo_se: c['bootstrap_coverage_ar1_0.3'].monte_carlo_se,
      replications: c['bootstrap_coverage_ar1_0.3'].replications,
      observations: c['bootstrap_coverage_ar1_0.3'].observations,
    },
    {
      label: 'Holm FWER (Independent, m = 36)',
      metric: 'Family-wise error rate at α = 0.05',
      observed: c['holm_fwer_independent'].family_wise_error_rate,
      target: c['holm_fwer_independent'].alpha,
      monte_carlo_se: c['holm_fwer_independent'].monte_carlo_se,
      replications: c['holm_fwer_independent'].replications,
      family_size: c['holm_fwer_independent'].family_size,
    },
    {
      label: 'Holm FWER (Correlated ρ = 0.3, m = 36)',
      metric: 'Family-wise error rate at α = 0.05',
      observed: c['holm_fwer_correlated_0.3'].family_wise_error_rate,
      target: c['holm_fwer_correlated_0.3'].alpha,
      monte_carlo_se: c['holm_fwer_correlated_0.3'].monte_carlo_se,
      replications: c['holm_fwer_correlated_0.3'].replications,
      family_size: c['holm_fwer_correlated_0.3'].family_size,
    },
  ];
}

async function createServer() {
  const app = express();
  app.use(express.json({ limit: '1mb' }));

  app.get('/api/health', (_req, res) => {
    res.json({ status: 'ok', service: 'myquant-alpha-lab' });
  });

  app.get('/api/lab/overview', (_req, res) => {
    const failedTrials = catalog.trials
      .filter((t) => t.status === 'failed')
      .map((t) => ({
        trial_id: t.trial_id,
        hypothesis_id: t.hypothesis_id,
        study: t.study,
        failure_reason: t.failure_reason ?? 'Recorded failure',
      }));

    res.json({
      generated_at: catalog.generated_at,
      evidence_probed_at: catalog.evidence_probed_at,
      counts: catalog.counts,
      audit: {
        alpha: auditSummary.lab_wide_audit.alpha,
        family_size: auditSummary.lab_wide_audit.family_size,
        supported_total: auditSummary.lab_wide_audit.supported_edges.length,
        holm_survivors: auditSummary.lab_wide_audit.holm_survivors,
        bh_survivors: auditSummary.lab_wide_audit.bh_survivors,
        raw_rejections_at_alpha: auditSummary.lab_wide_audit.raw_rejections_at_alpha,
        expected_false_positives_uncorrected:
          auditSummary.lab_wide_audit.expected_false_positives_uncorrected,
        bh_expected_false_discoveries_upper_bound:
          auditSummary.lab_wide_audit.bh_expected_false_discoveries_upper_bound,
        storey_pi0_lambda_0_5: auditSummary.lab_wide_audit['storey_pi0_lambda_0.5'],
        supported_edges: auditSummary.lab_wide_audit.supported_edges,
      },
      review: {
        reviewed_at: reviewReport.reviewed_at,
        counts: reviewReport.counts,
      },
      calibration: buildCalibrationList(),
      failed_trials: failedTrials,
      missing_optional: catalog.missing_optional,
      post_probe_updates: catalog.post_probe_updates,
    });
  });

  app.get('/api/graph', (_req, res) => {
    const taggedEdges = registry.edges.map((edge) => ({
      ...edge,
      hygiene: assessEdgeHygiene(edge),
    }));
    const cleanCount = taggedEdges.filter((e) => e.hygiene.cleanForPlanner).length;

    res.json({
      content_hash: registry.content_hash,
      nodes: registry.nodes,
      edges: taggedEdges,
      candidates: catalog.candidates,
      hygiene_summary: {
        total_edges: taggedEdges.length,
        clean_edges: cleanCount,
        excluded_edges: taggedEdges.length - cleanCount,
        discontinued_instruments: Array.from(DISCONTINUED_INSTRUMENTS),
        mechanical_edge_ids: Array.from(MECHANICAL_EDGE_IDS),
      },
    });
  });

  app.get('/api/studies', (_req, res) => {
    const list = catalog.studies.map((s) => {
      const studyTrials = catalog.trials.filter((t) => t.study === s.slug);
      return {
        ...s,
        review_counts: catalog.review.per_study_counts[s.slug] ?? {
          pass: 0,
          fail: 0,
          unverified: 0,
          note: 0,
        },
        supported_trials: studyTrials.filter((t) => t.supported === true).length,
        completed_trials: studyTrials.filter((t) => t.status === 'completed').length,
        failed_trials: studyTrials.filter((t) => t.status === 'failed').length,
      };
    });
    res.json(list);
  });

  app.get('/api/studies/:slug', (req, res) => {
    const slug = req.params.slug;
    const study = catalog.studies.find((s) => s.slug === slug);
    if (!study) {
      res.status(404).json({ error: `Study '${slug}' not found` });
      return;
    }

    let markdown = '';
    const reportFullPath = path.resolve(ROOT_DIR, study.report_path);
    if (reportFullPath.startsWith(path.resolve(ROOT_DIR, 'docs/studies')) && fs.existsSync(reportFullPath)) {
      markdown = fs.readFileSync(reportFullPath, 'utf-8');
    }

    const trials = catalog.trials.filter((t) => t.study === slug);
    const hypotheses = catalog.hypotheses.filter((h) => h.study === slug);
    const reviewStudy = reviewReport.studies.find((r) => r.study === slug);

    res.json({
      slug: study.slug,
      report_path: study.report_path,
      markdown,
      trials,
      hypotheses,
      review_checks: reviewStudy?.checks ?? [],
    });
  });

  app.get('/api/decision-records', (_req, res) => {
    res.json(decisionRecords);
  });

  app.get('/api/sources', (_req, res) => {
    const checksBySource = new Map(
      evidenceReport.sources.map((s) => [s.source_id, s.checks]),
    );
    const sources = catalog.sources.map((s) => ({
      ...s,
      checks: checksBySource.get(s.source_id) ?? [],
    }));
    res.json({
      probed_at: evidenceReport.probed_at,
      sources,
      panels: catalog.panels,
    });
  });

  // ============================================================================
  // Upgraded Quantitative Statistical & Cost Workbench Endpoints
  // ============================================================================

  app.post('/api/tools/multiple-testing', (req, res) => {
    try {
      const body = req.body as {
        mode?: 'custom' | 'lab_family';
        pValues?: number[];
        labels?: string[];
        method?: MultiplicityMethod;
        alpha?: number;
        excludeUncleanEdges?: boolean;
      };
      const method: MultiplicityMethod = body.method ?? 'holm';
      const alpha = typeof body.alpha === 'number' ? body.alpha : 0.05;

      let pValues: number[];
      let labels: string[];
      let excludedEdges: Array<{ edgeId: string; reason: string | null }> = [];

      if (body.mode === 'lab_family') {
        const allTested = registry.edges.filter(
          (e) =>
            (e.status === 'supported' || e.status === 'rejected') && typeof e.p_value === 'number',
        );
        let activeTested = allTested;
        if (body.excludeUncleanEdges) {
          const filtered = filterCleanLabEdges(allTested);
          activeTested = filtered.clean;
          excludedEdges = filtered.excluded.map((x) => ({
            edgeId: x.edge.edge_id,
            reason: x.assessment.reason,
          }));
        }
        pValues = activeTested.map((e) => e.p_value as number);
        labels = activeTested.map(
          (e) => `${e.edge_id} (${String(e.hypothesis_id)} · ${String(e.ledger_test_key)})`,
        );
      } else {
        if (!Array.isArray(body.pValues) || body.pValues.length === 0) {
          res.status(400).json({ error: 'Provide at least one p-value between 0 and 1.' });
          return;
        }
        pValues = body.pValues.map(Number);
        labels = pValues.map((_, i) => body.labels?.[i] ?? `Test ${i + 1}`);
      }

      const adjusted = adjustPValues(pValues, method, alpha).map((row, idx) => ({
        ...row,
        label: labels[idx],
      }));

      res.json({
        method,
        alpha,
        familySize: adjusted.length,
        rejections: adjusted.filter((r) => r.reject).length,
        excludedEdges,
        results: adjusted,
      });
    } catch (err) {
      res.status(400).json({ error: err instanceof Error ? err.message : 'Invalid input' });
    }
  });

  app.post('/api/tools/mde', (req, res) => {
    try {
      const body = req.body as {
        design: 'lead_lag_ols' | 'event_study_car' | 'cohens_d' | 'mean_ratio' | 'coefficient';
        observations?: number;
        groupSize2?: number;
        alpha?: number;
        power?: number;
        oneSided?: boolean;
        standardError?: number;
        meanBaseline?: number;
        lag1Autocorr?: number;
        distinctRegimeCount?: number;
      };
      const alpha = typeof body.alpha === 'number' ? body.alpha : 0.05;
      const power = typeof body.power === 'number' ? body.power : 0.8;
      const lag1Autocorr = typeof body.lag1Autocorr === 'number' ? body.lag1Autocorr : 0;
      const distinctRegimeCount =
        typeof body.distinctRegimeCount === 'number' && body.distinctRegimeCount > 0
          ? body.distinctRegimeCount
          : undefined;

      if (body.design === 'lead_lag_ols') {
        res.json(
          mdePartialRSquared(
            Math.round(Number(body.observations)),
            alpha,
            power,
            lag1Autocorr,
            distinctRegimeCount,
          ),
        );
      } else if (body.design === 'event_study_car') {
        res.json(
          mdeStandardizedMean(
            Math.round(Number(body.observations)),
            alpha,
            power,
            body.oneSided ?? true,
            lag1Autocorr,
          ),
        );
      } else if (body.design === 'cohens_d') {
        res.json(
          mdeCohensD(
            Math.round(Number(body.observations)),
            Math.round(Number(body.groupSize2)),
            alpha,
            power,
          ),
        );
      } else if (body.design === 'mean_ratio') {
        res.json(
          mdeMeanRatio(
            Number(body.meanBaseline),
            Number(body.standardError),
            alpha,
            power,
            Math.round(Number(body.observations ?? 100)),
          ),
        );
      } else if (body.design === 'coefficient') {
        res.json(
          mdeCoefficient(
            Number(body.standardError),
            alpha,
            power,
            body.oneSided ?? false,
            Math.round(Number(body.observations ?? 100)),
          ),
        );
      } else {
        res.status(400).json({ error: 'Unknown design type' });
      }
    } catch (err) {
      res.status(400).json({ error: err instanceof Error ? err.message : 'Invalid MDE input' });
    }
  });

  app.post('/api/tools/execution-cost', (req, res) => {
    try {
      const body = req.body as Parameters<typeof estimatePaperExecutionCost>[0];
      res.json(estimatePaperExecutionCost(body));
    } catch (err) {
      res.status(400).json({ error: err instanceof Error ? err.message : 'Invalid cost input' });
    }
  });

  app.post('/api/tools/synthetic-lead-lag', (req, res) => {
    try {
      const body = req.body as {
        scenario?: SyntheticScenario;
        observations?: number;
        beta?: number;
        commonFactorLoading?: number;
        lagSteps?: number;
        maxHacLag?: number;
        autoBandwidth?: boolean;
        controlCommonFactor?: boolean;
        factorTiming?: FactorTimingMode;
        seed?: number;
      };
      const result = runSyntheticLeadLag({
        scenario: body.scenario ?? 'source_leads_target',
        observations: Number(body.observations ?? 1000),
        beta: Number(body.beta ?? 0.15),
        commonFactorLoading: Number(body.commonFactorLoading ?? 0.6),
        lagSteps: Number(body.lagSteps ?? 1),
        maxHacLag: Number(body.maxHacLag ?? 5),
        autoBandwidth: body.autoBandwidth !== undefined ? Boolean(body.autoBandwidth) : true,
        controlCommonFactor: Boolean(body.controlCommonFactor ?? true),
        factorTiming: body.factorTiming ?? 'pit_lagged',
        seed: Number(body.seed ?? 2026),
      });
      res.json(result);
    } catch (err) {
      res.status(400).json({ error: err instanceof Error ? err.message : 'Invalid simulation input' });
    }
  });

  // ============================================================================
  // Institutional Strategy Engine, Coupled L2 Physics, QP Optimizer & Bitemporal APIs
  // ============================================================================

  app.post('/api/tools/execution-sim', (req, res) => {
    try {
      const body = req.body as {
        midPrice?: number;
        topLevelContracts?: number;
        childContracts?: number;
        leverage?: number;
        crashDrawdownPct?: number;
        side?: 'long' | 'short';
      };

      const midPrice = Math.max(100, Number(body.midPrice ?? 92_000));
      const topLevel = Math.max(5, Number(body.topLevelContracts ?? 35));
      const childContracts = Math.max(5, Number(body.childContracts ?? 120));
      const leverage = Math.max(1, Math.min(20, Number(body.leverage ?? 10)));
      const crashPct = Math.max(2, Math.min(40, Number(body.crashDrawdownPct ?? 12))) / 100;
      const side = body.side === 'short' ? 'short' : 'long';

      // 1. Coupled Mutable L2 Book-Walking across 3 sequential child orders
      const snapshot = buildSyntheticL2Book({
        midPrice,
        spreadBps: 1.2,
        topLevelContracts: topLevel,
        levels: 20,
        tickSize: 0.1,
        lotSize: 0.01,
      });
      const book = new CoupledOrderBook(snapshot);
      const initialTop5Depth = book.getTopNDepth('buy', 5);
      const childFills = [1, 2, 3].map((childIndex) => {
        const f = book.executeTakerOrder('buy', childContracts, 320, 500_000);
        return {
          childIndex,
          requestedContracts: f.requestedContracts,
          filledContracts: f.filledContracts,
          vwapFillPrice: f.vwapFillPrice,
          levelsSwept: f.levelsSwept,
          bookWalkSlippageBps: f.bookWalkSlippageBps,
          permanentImpactBps: f.permanentImpactBps,
          totalEffectiveCostBps: f.totalEffectiveCostBps,
          remainingTop5DepthAfter: f.remainingTop5DepthAfter,
        };
      });

      // 2. Impact comparison curve: Unbounded Square-Root vs Legacy 5 bps Linear Cap
      const multiples = [0.25, 0.5, 1.0, 2.0, 3.5, 5.0, 7.5, 10.0];
      const impactCurve = multiples.map((mult) => {
        const qty = Math.round(initialTop5Depth * mult);
        const sq = squareRootImpactBps({
          orderQuantity: qty,
          depth: initialTop5Depth,
          coefficientBps: 5.0,
          dailyVolBps: 320,
          advContracts: 500_000,
        });
        const leg = legacyLinearCappedImpactBps(qty, initialTop5Depth, 5.0) ?? 0;
        return {
          depthMultiple: mult,
          orderContracts: qty,
          squareRootBps: sq.impactBps,
          legacyCappedBps: leg,
        };
      });

      // 3. Passive Limit Queue-Position & Adverse Selection Markout
      const passiveMarkout = simulatePassiveLimitOrder({
        side: 'buy',
        limitPrice: snapshot.bids[0].price,
        orderContracts: Math.round(topLevel * 0.4),
        queueAheadContracts: null, // Demonstrates conservative non-zero fallback!
        medianLevelDepthContracts: topLevel,
        tapePrints: [
          { tsOffsetSec: 2, price: snapshot.bids[0].price, size: topLevel * 0.6, aggressorSide: 'sell' },
          { tsOffsetSec: 5, price: snapshot.bids[0].price - 12, size: topLevel * 0.8, aggressorSide: 'sell' },
        ],
        postFillMid1s: snapshot.bids[0].price - 18,
        postFillMid10s: snapshot.bids[0].price - 45,
        postFillMid60s: snapshot.bids[0].price - 92,
      });

      // 4. OKX Tiered Margin & Intraday Flash-Wick Forced Liquidation Stress
      const bars: MarginStressBar[] = [];
      const baseMs = Date.UTC(2026, 10, 18, 0, 0, 0);
      const pathMultipliers = [
        { o: 1.0, h: 1.008, l: 0.994, c: 1.004 },
        { o: 1.004, h: 1.012, l: 0.996, c: 1.009 },
        { o: 1.009, h: 1.015, l: 0.982, c: 0.988 },
        // Bar 3: Severe adverse intraday wick followed by partial recovery
        side === 'long'
          ? { o: 0.988, h: 0.995, l: 1 - crashPct, c: 1 - crashPct * 0.38 }
          : { o: 0.988, h: 1 + crashPct, l: 0.985, c: 1 + crashPct * 0.35 },
        // Bars 4-7: V-shaped rebound that hides the wipeout in legacy margin-free backtests!
        side === 'long'
          ? { o: 1 - crashPct * 0.38, h: 1.015, l: 0.955, c: 1.008 }
          : { o: 1 + crashPct * 0.35, h: 1.04, l: 0.985, c: 0.99 },
        side === 'long'
          ? { o: 1.008, h: 1.032, l: 1.002, c: 1.028 }
          : { o: 0.99, h: 0.995, l: 0.968, c: 0.972 },
        side === 'long'
          ? { o: 1.028, h: 1.048, l: 1.02, c: 1.042 }
          : { o: 0.972, h: 0.978, l: 0.952, c: 0.958 },
        side === 'long'
          ? { o: 1.042, h: 1.058, l: 1.035, c: 1.052 }
          : { o: 0.958, h: 0.965, l: 0.942, c: 0.948 },
      ];

      for (let i = 0; i < pathMultipliers.length; i++) {
        const m = pathMultipliers[i];
        bars.push({
          timestampIso: new Date(baseMs + i * 8 * 3600_000).toISOString(),
          open: midPrice * m.o,
          high: midPrice * m.h,
          low: midPrice * m.l,
          close: midPrice * m.c,
          markPrice: midPrice * m.c,
          fundingRate: 0.00012,
          isFundingBoundary: i > 0,
        });
      }

      const marginStress = runPerpetualMarginStress({
        initialCashUsdt: 100_000,
        side,
        targetLeverage: leverage,
        bars,
      });

      res.json({
        referenceMid: snapshot.midPrice,
        initialTop5Depth,
        childFills,
        impactCurve,
        passiveMarkout,
        marginStress,
      });
    } catch (err) {
      res.status(400).json({ error: err instanceof Error ? err.message : 'Execution simulation failed' });
    }
  });

  app.post('/api/tools/portfolio-qp', (req, res) => {
    try {
      const body = req.body as {
        periods?: number;
        signalStrength?: number;
        linearCostBps?: number;
        riskAversion?: number;
        targetAnnualVol?: number;
        seed?: number;
      };
      const result = compareSignRuleVsQP({
        periods: body.periods !== undefined ? Number(body.periods) : 360,
        signalStrength: body.signalStrength !== undefined ? Number(body.signalStrength) : 0.09,
        linearCostBps: body.linearCostBps !== undefined ? Number(body.linearCostBps) : 7.5,
        riskAversion: body.riskAversion !== undefined ? Number(body.riskAversion) : 5.0,
        targetAnnualVol: body.targetAnnualVol !== undefined ? Number(body.targetAnnualVol) : 0.16,
        seed: body.seed !== undefined ? Number(body.seed) : 2026,
      });
      res.json(result);
    } catch (err) {
      res.status(400).json({ error: err instanceof Error ? err.message : 'Portfolio QP failed' });
    }
  });

  app.post('/api/engine/bitemporal-asof', (req, res) => {
    try {
      const body = req.body as { sourceId?: 'fred' | 'deribit' | 'okx-public'; instrumentId?: string };
      res.json(
        runBitemporalAuditDemo({
          sourceId: body.sourceId ?? 'fred',
          instrumentId: body.instrumentId,
        }),
      );
    } catch (err) {
      res.status(400).json({ error: err instanceof Error ? err.message : 'Bitemporal audit failed' });
    }
  });

  app.get('/api/engine/recorder/snapshot', async (req, res) => {
    try {
      const inst = typeof req.query.inst === 'string' ? req.query.inst : 'crypto:btc-usdt-perp';
      const snap = await capturePublicMarketSnapshot(inst);
      res.json(snap);
    } catch (err) {
      res.status(500).json({ error: err instanceof Error ? err.message : 'Recorder snapshot failed' });
    }
  });

  app.get('/api/engine/ledger', (_req, res) => {
    res.json(buildLedgerOverview());
  });

  app.post('/api/engine/run-strategy', (req, res) => {
    try {
      const body = req.body as {
        strategyId?: StrategyId;
        optimizerMode?: 'qp_optimized' | 'legacy_sign_rule';
        periods?: number;
        targetAnnualVol?: number;
        maxLeverage?: number;
        linearCostBps?: number;
        seed?: number;
        persistToLedger?: boolean;
      };
      const runOutput = runUnifiedStrategyPipeline(
        {
          strategyId: body.strategyId ?? 'perp_carry_funding',
          optimizerMode: body.optimizerMode ?? 'qp_optimized',
          periods: body.periods !== undefined ? Number(body.periods) : 240,
          targetAnnualVol: body.targetAnnualVol !== undefined ? Number(body.targetAnnualVol) : 0.14,
          maxLeverage: body.maxLeverage !== undefined ? Number(body.maxLeverage) : 2.0,
          linearCostBps: body.linearCostBps !== undefined ? Number(body.linearCostBps) : 6.5,
          seed: body.seed !== undefined ? Number(body.seed) : 2026,
          persistToLedger: body.persistToLedger !== undefined ? Boolean(body.persistToLedger) : true,
        },
        merkleLedger,
      );
      res.json({
        run: runOutput,
        ledger: buildLedgerOverview(),
      });
    } catch (err) {
      res.status(400).json({ error: err instanceof Error ? err.message : 'Strategy run failed' });
    }
  });

  app.post('/api/engine/walk-forward', (req, res) => {
    try {
      const body = req.body as {
        strategyId?: StrategyId;
        optimizerMode?: 'qp_optimized' | 'legacy_sign_rule';
        periods?: number;
        numFolds?: number;
        purgeGapBars?: number;
        embargoBars?: number;
        targetAnnualVol?: number;
        maxLeverage?: number;
        linearCostBps?: number;
        seed?: number;
      };
      const report = runPurgedWalkForwardAudit(
        {
          strategyId: body.strategyId ?? 'perp_carry_funding',
          optimizerMode: body.optimizerMode ?? 'qp_optimized',
          periods: body.periods !== undefined ? Number(body.periods) : 300,
          numFolds: body.numFolds !== undefined ? Number(body.numFolds) : 5,
          purgeGapBars: body.purgeGapBars !== undefined ? Number(body.purgeGapBars) : 6,
          embargoBars: body.embargoBars !== undefined ? Number(body.embargoBars) : 4,
          targetAnnualVol: body.targetAnnualVol !== undefined ? Number(body.targetAnnualVol) : 0.14,
          maxLeverage: body.maxLeverage !== undefined ? Number(body.maxLeverage) : 2.0,
          linearCostBps: body.linearCostBps !== undefined ? Number(body.linearCostBps) : 6.5,
          seed: body.seed !== undefined ? Number(body.seed) : 2026,
        },
        merkleLedger,
      );
      res.json(report);
    } catch (err) {
      res.status(400).json({ error: err instanceof Error ? err.message : 'Walk-forward audit failed' });
    }
  });

  app.post('/api/engine/arena', (req, res) => {
    try {
      const body = req.body as {
        periods?: number;
        targetAnnualVol?: number;
        maxLeverage?: number;
        linearCostBps?: number;
        seed?: number;
      };
      const report = runStrategyArena(
        {
          periods: body.periods !== undefined ? Number(body.periods) : 280,
          targetAnnualVol: body.targetAnnualVol !== undefined ? Number(body.targetAnnualVol) : 0.14,
          maxLeverage: body.maxLeverage !== undefined ? Number(body.maxLeverage) : 2.0,
          linearCostBps: body.linearCostBps !== undefined ? Number(body.linearCostBps) : 6.5,
          seed: body.seed !== undefined ? Number(body.seed) : 2026,
        },
        merkleLedger,
      );
      res.json(report);
    } catch (err) {
      res.status(400).json({ error: err instanceof Error ? err.message : 'Strategy arena failed' });
    }
  });

  if (!IS_PROD) {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true, hmr: false },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distDir = path.resolve(ROOT_DIR, 'dist');
    app.use(express.static(distDir));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distDir, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`MyQuant Alpha Lab server listening on http://0.0.0.0:${PORT}`);
  });
}

createServer().catch((err) => {
  console.error('Failed to start MyQuant server:', err);
  process.exit(1);
});
