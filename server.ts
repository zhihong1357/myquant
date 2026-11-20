import express from 'express';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { adjustPValues } from './src/lib/quant/multipleTesting.ts';
import type { MultiplicityMethod } from './src/lib/quant/multipleTesting.ts';
import {
  mdeCohensD,
  mdeCoefficient,
  mdeMeanRatio,
  mdePartialRSquared,
  mdeStandardizedMean,
} from './src/lib/quant/power.ts';
import { estimatePaperExecutionCost } from './src/lib/quant/executionCosts.ts';
import { runSyntheticLeadLag } from './src/lib/quant/leadLag.ts';
import type { SyntheticScenario } from './src/lib/quant/leadLag.ts';

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
    res.json({
      content_hash: registry.content_hash,
      nodes: registry.nodes,
      edges: registry.edges,
      candidates: catalog.candidates,
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

  // Quantitative kernel interactive API routes
  app.post('/api/tools/multiple-testing', (req, res) => {
    try {
      const body = req.body as {
        mode?: 'custom' | 'lab_family';
        pValues?: number[];
        labels?: string[];
        method?: MultiplicityMethod;
        alpha?: number;
      };
      const method: MultiplicityMethod = body.method ?? 'holm';
      const alpha = typeof body.alpha === 'number' ? body.alpha : 0.05;

      let pValues: number[];
      let labels: string[];
      if (body.mode === 'lab_family') {
        const tested = registry.edges.filter(
          (e) =>
            (e.status === 'supported' || e.status === 'rejected') && typeof e.p_value === 'number',
        );
        pValues = tested.map((e) => e.p_value as number);
        labels = tested.map((e) => `${e.edge_id} (${String(e.hypothesis_id)} · ${String(e.ledger_test_key)})`);
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
      };
      const alpha = typeof body.alpha === 'number' ? body.alpha : 0.05;
      const power = typeof body.power === 'number' ? body.power : 0.8;

      if (body.design === 'lead_lag_ols') {
        res.json(mdePartialRSquared(Math.round(Number(body.observations)), alpha, power));
      } else if (body.design === 'event_study_car') {
        res.json(
          mdeStandardizedMean(
            Math.round(Number(body.observations)),
            alpha,
            power,
            body.oneSided ?? true,
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
        controlCommonFactor?: boolean;
        seed?: number;
      };
      const result = runSyntheticLeadLag({
        scenario: body.scenario ?? 'source_leads_target',
        observations: Number(body.observations ?? 1000),
        beta: Number(body.beta ?? 0.15),
        commonFactorLoading: Number(body.commonFactorLoading ?? 0.6),
        lagSteps: Number(body.lagSteps ?? 1),
        maxHacLag: Number(body.maxHacLag ?? 5),
        controlCommonFactor: Boolean(body.controlCommonFactor ?? true),
        seed: Number(body.seed ?? 2026),
      });
      res.json(result);
    } catch (err) {
      res.status(400).json({ error: err instanceof Error ? err.message : 'Invalid simulation input' });
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
