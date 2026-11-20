import React, { useEffect, useMemo, useState } from 'react';
import type { StudyDetail, StudyListItem } from '../lib/types';
import {
  formatInteger,
  formatNumber,
  formatPValue,
  formatShortDate,
  formatStatusLabel,
  statusTextClass,
} from '../lib/format';
import { MarkdownViewer } from './MarkdownViewer';

interface StudiesViewProps {
  studies: StudyListItem[];
  initialSlug?: string | null;
}

export const StudiesView: React.FC<StudiesViewProps> = ({ studies, initialSlug }) => {
  const [selectedSlug, setSelectedSlug] = useState<string>(
    initialSlug && studies.some((s) => s.slug === initialSlug)
      ? initialSlug
      : studies[0]?.slug ?? '',
  );
  const [search, setSearch] = useState('');
  const [verdictFilter, setVerdictFilter] = useState<'all' | 'supported' | 'rejected'>('all');
  const [detailTab, setDetailTab] = useState<'report' | 'trials' | 'review'>('report');
  const [detail, setDetail] = useState<StudyDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialSlug && studies.some((s) => s.slug === initialSlug)) {
      setSelectedSlug(initialSlug);
    }
  }, [initialSlug, studies]);

  useEffect(() => {
    if (!selectedSlug) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`/api/studies/${encodeURIComponent(selectedSlug)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Failed to load study ${selectedSlug}`);
        return r.json() as Promise<StudyDetail>;
      })
      .then((payload) => {
        if (!cancelled) {
          setDetail(payload);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unable to fetch study report');
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedSlug]);

  const filteredStudies = useMemo(() => {
    const q = search.trim().toLowerCase();
    return studies.filter((s) => {
      if (verdictFilter === 'supported' && s.supported_trials === 0) return false;
      if (verdictFilter === 'rejected' && s.supported_trials > 0) return false;
      if (q) {
        const hay = `${s.slug} ${s.hypotheses.join(' ')} ${s.trials.join(' ')}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [studies, search, verdictFilter]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
          Empirical Studies &amp; Adversarial Reviews
        </h1>
        <p className="text-sm text-slate-600 mt-1">
          All {studies.length} preregistered studies with immutable ledger trials, hypothesis
          versions, full Markdown reports, and Stage 6D read-only audit checks.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Study List */}
        <aside className="lg:col-span-4 bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="p-4 border-b border-slate-200 space-y-3">
            <label htmlFor="study-search" className="sr-only">
              Search studies
            </label>
            <input
              id="study-search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search study, hypothesis, or trial…"
              className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-600"
            />
            <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg">
              {(['all', 'supported', 'rejected'] as const).map((vf) => (
                <button
                  key={vf}
                  type="button"
                  onClick={() => setVerdictFilter(vf)}
                  className={`flex-1 px-2.5 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                    verdictFilter === vf
                      ? 'bg-white text-slate-900 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {vf === 'all' ? 'All (13)' : vf === 'supported' ? 'Has Supported' : 'All Rejected'}
                </button>
              ))}
            </div>
          </div>

          <div className="divide-y divide-slate-100 max-h-[680px] overflow-y-auto">
            {filteredStudies.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-500">
                No studies match the current filter.
              </div>
            ) : (
              filteredStudies.map((s) => {
                const isSelected = s.slug === selectedSlug;
                return (
                  <button
                    key={s.slug}
                    type="button"
                    onClick={() => setSelectedSlug(s.slug)}
                    className={`w-full text-left px-4 py-3 transition-colors block ${
                      isSelected ? 'bg-blue-50/70' : 'hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={`font-mono text-xs font-semibold ${
                          isSelected ? 'text-blue-800' : 'text-slate-900'
                        }`}
                      >
                        {s.slug}
                      </span>
                      <span
                        className={`text-xs whitespace-nowrap ${
                          s.supported_trials > 0
                            ? 'text-emerald-700 font-medium'
                            : 'text-slate-500'
                        }`}
                      >
                        {s.supported_trials > 0
                          ? `${s.supported_trials} supported`
                          : 'Null / Rejected'}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-500 font-mono">
                      {s.hypotheses.join(', ')} · {s.trials.join(', ')}
                    </div>
                    <div className="mt-1 text-[11px] text-slate-500 font-mono tabular-nums">
                      Audit: {s.review_counts.pass} pass · {s.review_counts.fail} fail ·{' '}
                      {s.review_counts.unverified} unverified
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </aside>

        {/* Right Detail Panel */}
        <section className="lg:col-span-8 bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-mono text-sm font-semibold text-slate-900">
                {selectedSlug || 'Select a study'}
              </div>
              {detail && (
                <div className="text-xs text-slate-500 font-mono mt-0.5">
                  {detail.report_path} · {detail.trials.length} trial record(s) ·{' '}
                  {detail.review_checks.length} audit checks
                </div>
              )}
            </div>

            <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg">
              {(
                [
                  { id: 'report', label: 'Study Report' },
                  { id: 'trials', label: 'Trials & Hypotheses' },
                  { id: 'review', label: 'Adversarial Audit' },
                ] as const
              ).map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setDetailTab(t.id)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap shrink-0 ${
                    detailTab === t.id
                      ? 'bg-white text-slate-900 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div className="p-6">
            {loading && (
              <div className="space-y-3 py-8">
                <div className="h-5 w-1/2 bg-slate-100 rounded animate-pulse" />
                <div className="h-4 w-full bg-slate-100 rounded animate-pulse" />
                <div className="h-4 w-5/6 bg-slate-100 rounded animate-pulse" />
              </div>
            )}

            {error && !loading && (
              <div className="text-sm text-rose-700 py-4">{error}</div>
            )}

            {detail && !loading && detailTab === 'report' && (
              <MarkdownViewer content={detail.markdown} />
            )}

            {detail && !loading && detailTab === 'trials' && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900 mb-3">
                    Immutable Trial Ledger Records
                  </h2>
                  <div className="overflow-x-auto border border-slate-200 rounded-lg">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                          <th className="py-2.5 px-3 font-semibold">Trial</th>
                          <th className="py-2.5 px-3 font-semibold">Primary Test</th>
                          <th className="py-2.5 px-3 font-semibold text-right">Effect</th>
                          <th className="py-2.5 px-3 font-semibold text-right">Raw p</th>
                          <th className="py-2.5 px-3 font-semibold text-right">Adj. p</th>
                          <th className="py-2.5 px-3 font-semibold text-right">n</th>
                          <th className="py-2.5 px-3 font-semibold">Outcome</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {detail.trials.map((tr) => (
                          <tr key={tr.trial_id}>
                            <td className="py-2.5 px-3 font-mono font-semibold text-slate-900 whitespace-nowrap">
                              {tr.trial_id}
                              <div className="text-[11px] font-normal text-slate-500">
                                {tr.hypothesis_id}
                              </div>
                            </td>
                            <td className="py-2.5 px-3 font-mono text-slate-700">
                              {tr.primary_test ?? '—'}
                              {tr.failure_reason && (
                                <div className="text-[11px] text-rose-700 mt-0.5 max-w-xs">
                                  {tr.failure_reason}
                                </div>
                              )}
                            </td>
                            <td className="py-2.5 px-3 font-mono tabular-nums text-right text-slate-800 whitespace-nowrap">
                              {tr.primary_effect_value !== null
                                ? `${formatNumber(tr.primary_effect_value, 4)} (${tr.primary_effect_label ?? ''})`
                                : '—'}
                            </td>
                            <td className="py-2.5 px-3 font-mono tabular-nums text-right text-slate-800 whitespace-nowrap">
                              {formatPValue(tr.primary_raw_p_value)}
                            </td>
                            <td className="py-2.5 px-3 font-mono tabular-nums text-right text-slate-800 whitespace-nowrap">
                              {formatPValue(tr.primary_adjusted_p_value)}
                            </td>
                            <td className="py-2.5 px-3 font-mono tabular-nums text-right text-slate-600 whitespace-nowrap">
                              {formatInteger(tr.observations)}
                            </td>
                            <td className="py-2.5 px-3 whitespace-nowrap">
                              {tr.status === 'failed' ? (
                                <span className="text-rose-700 font-medium">Failed</span>
                              ) : tr.supported ? (
                                <span className="text-emerald-700 font-medium">Supported</span>
                              ) : (
                                <span className="text-slate-600 font-medium">Rejected</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div>
                  <h2 className="text-sm font-semibold text-slate-900 mb-3">
                    Preregistered Hypothesis Versions
                  </h2>
                  <div className="divide-y divide-slate-200 border border-slate-200 rounded-lg">
                    {detail.hypotheses.map((h) => (
                      <div key={h.hypothesis_id} className="p-4">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono font-semibold text-slate-900">
                            {h.hypothesis_id}
                          </span>
                          <span className={statusTextClass(h.latest_state)}>
                            {formatStatusLabel(h.latest_state)}
                          </span>
                        </div>
                        <div className="mt-2 space-y-1.5">
                          {h.versions.map((v) => (
                            <div
                              key={v.version}
                              className="text-xs text-slate-600 font-mono flex flex-wrap items-center gap-x-3 gap-y-1"
                            >
                              <span>v{v.version}</span>
                              <span>·</span>
                              <span>{formatShortDate(v.registered_at)}</span>
                              <span>·</span>
                              <span>State: {v.state}</span>
                              <span>·</span>
                              <span className="text-slate-500">
                                Fingerprint: {v.spec_fingerprint.slice(0, 14)}…
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {detail && !loading && detailTab === 'review' && (
              <div className="space-y-3">
                <p className="text-xs text-slate-600">
                  Deterministic Stage 6D audit checks verifying ledger hash-chains, anchors,
                  preregistration fingerprints, Holm recomputation, report-table alignment, and PIT
                  timestamps.
                </p>
                <div className="divide-y divide-slate-200 border border-slate-200 rounded-lg">
                  {detail.review_checks.map((chk, idx) => (
                    <div key={`${chk.check_id}-${idx}`} className="p-4">
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="font-mono font-semibold text-slate-900">
                          {chk.check_id}{' '}
                          <span className="font-normal text-slate-500">· {chk.subject}</span>
                        </span>
                        <span className={`uppercase text-[11px] ${statusTextClass(chk.verdict)}`}>
                          {chk.verdict}
                        </span>
                      </div>
                      <p className="text-xs text-slate-700 mt-1">{chk.summary}</p>
                      {chk.evidence.length > 0 && (
                        <ul className="mt-1.5 space-y-0.5 text-[11px] font-mono text-slate-500">
                          {chk.evidence.map((ev, eIdx) => (
                            <li key={eIdx} className="break-all">
                              {ev}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};
