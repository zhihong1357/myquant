import React from 'react';
import { ArrowRight } from 'lucide-react';
import type { OverviewPayload } from '../lib/types';
import { formatInteger, formatNumber, formatPValue, formatShortDate } from '../lib/format';

interface OverviewViewProps {
  data: OverviewPayload;
  onSelectStudy: (slug: string) => void;
  onNavigate: (tab: 'graph' | 'studies' | 'decisions' | 'workbench') => void;
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  data,
  onSelectStudy,
  onNavigate,
}) => {
  const { counts, audit, review, calibration, failed_trials } = data;

  return (
    <div className="space-y-8">
      {/* Header summary */}
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Research Intelligence Overview
          </h1>
          <p className="text-sm text-slate-600 mt-1 max-w-3xl leading-relaxed">
            Empirical cross-market expectation transmission ledger. Paper-only, point-in-time
            audited, and hash-chained across all preregistered hypotheses and failed trials.
          </p>
        </div>
        <div className="text-xs text-slate-500 font-mono tabular-nums whitespace-nowrap">
          Catalog built {formatShortDate(data.generated_at)} · Evidence probed{' '}
          {formatShortDate(data.evidence_probed_at)}
        </div>
      </div>

      {/* Primary KPI Strip (single elevation, hairline dividers, zero pill clutter) */}
      <section aria-label="Laboratory metrics" className="bg-white border border-slate-200 rounded-lg">
        <div className="grid grid-cols-2 lg:grid-cols-4 divide-y lg:divide-y-0 lg:divide-x divide-slate-200">
          <div className="p-5">
            <div className="text-xs font-medium text-slate-500">Empirical Studies</div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-bold text-slate-900 font-mono tabular-nums">
                {counts.studies}
              </span>
              <span className="text-xs text-slate-500 font-mono tabular-nums">
                {counts.hypotheses} hypotheses · {counts.trials_total} trials
              </span>
            </div>
            <button
              type="button"
              onClick={() => onNavigate('studies')}
              className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-blue-700 hover:text-blue-800 whitespace-nowrap"
            >
              Inspect study reports <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
            </button>
          </div>

          <div className="p-5">
            <div className="text-xs font-medium text-slate-500">Market Graph Edges</div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-bold text-slate-900 font-mono tabular-nums">
                {counts.edges_total}
              </span>
              <span className="text-xs text-slate-500 font-mono tabular-nums">
                {counts.edges_supported} supported · {counts.edges_rejected} rejected
              </span>
            </div>
            <button
              type="button"
              onClick={() => onNavigate('graph')}
              className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-blue-700 hover:text-blue-800 whitespace-nowrap"
            >
              Explore {counts.nodes} market nodes <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
            </button>
          </div>

          <div className="p-5">
            <div className="text-xs font-medium text-slate-500">
              Lab-Wide Multiple-Testing Survivors
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-bold text-emerald-700 font-mono tabular-nums">
                {audit.holm_survivors}
              </span>
              <span className="text-xs text-slate-500 font-mono tabular-nums">
                Holm · {audit.bh_survivors} BH of {audit.family_size} tested
              </span>
            </div>
            <div className="mt-3 text-xs text-slate-500 font-mono tabular-nums">
              α = {audit.alpha} · E[FP uncorrected] = {audit.expected_false_positives_uncorrected}
            </div>
          </div>

          <div className="p-5">
            <div className="text-xs font-medium text-slate-500">Adversarial Review Audit</div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-bold text-slate-900 font-mono tabular-nums">
                {review.counts.pass}
              </span>
              <span className="text-xs text-emerald-700 font-mono tabular-nums font-medium">
                pass · {review.counts.fail} fail
              </span>
            </div>
            <div className="mt-3 text-xs text-slate-500 font-mono tabular-nums">
              {review.counts.unverified} unverified · {review.counts.note} MDE notes ·{' '}
              {counts.broken_links} broken links
            </div>
          </div>
        </div>
      </section>

      {/* Supported Edges Lab-Wide Audit Table */}
      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Supported Edges Under Lab-Wide Multiplicity Correction
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Post-hoc second-layer adjustment across all {audit.family_size} tested market edges
              (Storey π₀ = {formatNumber(audit.storey_pi0_lambda_0_5, 2)} · BH FDR upper bound ={' '}
              {formatNumber(audit.bh_expected_false_discoveries_upper_bound, 2)} false discoveries).
            </p>
          </div>
          <button
            type="button"
            onClick={() => onNavigate('workbench')}
            className="text-xs font-medium text-blue-700 hover:text-blue-800 whitespace-nowrap shrink-0 self-start sm:self-auto"
          >
            Recompute in Workbench
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs text-slate-600">
                <th className="py-2.5 px-4 font-semibold">Edge</th>
                <th className="py-2.5 px-4 font-semibold">Study / Hypothesis</th>
                <th className="py-2.5 px-4 font-semibold">Design</th>
                <th className="py-2.5 px-4 font-semibold text-right">Raw p</th>
                <th className="py-2.5 px-4 font-semibold text-right">Holm adj. p</th>
                <th className="py-2.5 px-4 font-semibold text-right">BH adj. p</th>
                <th className="py-2.5 px-4 font-semibold">Lab-Wide Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {audit.supported_edges.map((edge) => (
                <tr key={edge.edge_id} className="hover:bg-slate-50/70">
                  <td className="py-3 px-4 font-mono text-xs font-semibold text-slate-900 whitespace-nowrap">
                    {edge.edge_id}
                  </td>
                  <td className="py-3 px-4">
                    <button
                      type="button"
                      onClick={() => onSelectStudy(edge.study)}
                      className="text-xs font-medium text-blue-700 hover:underline text-left"
                    >
                      {edge.study}
                    </button>
                    <div className="text-xs text-slate-500 font-mono">
                      {edge.hypothesis_id} · {edge.trial_id}
                    </div>
                    {edge.caveat && (
                      <p className="text-xs text-amber-800 mt-1 max-w-md leading-snug">
                        Caveat: {edge.caveat}
                      </p>
                    )}
                  </td>
                  <td className="py-3 px-4 text-xs text-slate-600 whitespace-nowrap">
                    {edge.test_type.replace(/_/g, ' ')}
                  </td>
                  <td className="py-3 px-4 text-xs font-mono tabular-nums text-right text-slate-800 whitespace-nowrap">
                    {formatPValue(edge.raw_p_value)}
                  </td>
                  <td className="py-3 px-4 text-xs font-mono tabular-nums text-right text-slate-800 whitespace-nowrap">
                    {formatPValue(edge.holm_adjusted_p_value)}
                  </td>
                  <td className="py-3 px-4 text-xs font-mono tabular-nums text-right text-slate-800 whitespace-nowrap">
                    {formatPValue(edge.bh_adjusted_p_value)}
                  </td>
                  <td className="py-3 px-4 text-xs whitespace-nowrap">
                    {edge.holm_significant ? (
                      <span className="text-emerald-700 font-medium">Holm + BH survivor</span>
                    ) : edge.bh_significant ? (
                      <span className="text-amber-700 font-medium">BH only (Holm dropped)</span>
                    ) : (
                      <span className="text-rose-700 font-medium">Dropped lab-wide</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Two-column lower grid: Calibration Diagnostics + Failed Trials & Integrity */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        {/* Calibration diagnostics */}
        <section className="xl:col-span-7 bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-base font-semibold text-slate-900">
              Statistical Kernel Calibration (Stage 2B)
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Monte Carlo validation of Newey-West HAC size, block-bootstrap coverage, and Holm
              FWER control under null and AR(1) / correlated settings.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                  <th className="py-2.5 px-4 font-semibold">Diagnostic</th>
                  <th className="py-2.5 px-4 font-semibold text-right">Target</th>
                  <th className="py-2.5 px-4 font-semibold text-right">Observed</th>
                  <th className="py-2.5 px-4 font-semibold text-right">MC SE</th>
                  <th className="py-2.5 px-4 font-semibold text-right">Reps</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {calibration.map((row) => (
                  <tr key={row.label} className="hover:bg-slate-50/70">
                    <td className="py-2.5 px-4">
                      <div className="font-medium text-slate-900">{row.label}</div>
                      <div className="text-slate-500">{row.metric}</div>
                    </td>
                    <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-600 whitespace-nowrap">
                      {row.target.toFixed(4)}
                    </td>
                    <td className="py-2.5 px-4 font-mono tabular-nums text-right font-semibold text-slate-900 whitespace-nowrap">
                      {row.observed.toFixed(4)}
                    </td>
                    <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-500 whitespace-nowrap">
                      ±{row.monte_carlo_se.toFixed(4)}
                    </td>
                    <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-600 whitespace-nowrap">
                      {formatInteger(row.replications)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Retained Failed Trials & Integrity Notes */}
        <section className="xl:col-span-5 bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-base font-semibold text-slate-900">
              Retained Failed Trials &amp; Ledger Exceptions
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Failed experiments are permanently recorded in append-only hash chains rather than
              deleted.
            </p>
          </div>
          <div className="divide-y divide-slate-100">
            {failed_trials.map((ft) => (
              <div key={ft.trial_id} className="px-6 py-3.5">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="font-mono font-semibold text-rose-700">
                    {ft.trial_id} · {ft.hypothesis_id}
                  </span>
                  <button
                    type="button"
                    onClick={() => onSelectStudy(ft.study)}
                    className="text-blue-700 hover:underline font-medium whitespace-nowrap"
                  >
                    {ft.study}
                  </button>
                </div>
                <p className="text-xs text-slate-600 mt-1 leading-relaxed font-mono">
                  {ft.failure_reason}
                </p>
              </div>
            ))}
            {data.missing_optional.map((m) => (
              <div key={m.path} className="px-6 py-3.5 bg-amber-50/40">
                <div className="text-xs font-medium text-amber-800">
                  Missing optional integrity file
                </div>
                <div className="text-xs font-mono text-slate-700 mt-0.5 break-all">{m.path}</div>
                <div className="text-xs text-slate-600 mt-0.5">{m.reason}</div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
};
