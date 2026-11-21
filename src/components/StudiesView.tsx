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
import { useI18n } from '../lib/i18n';
import { MarkdownViewer } from './MarkdownViewer';

interface StudiesViewProps {
  studies: StudyListItem[];
  initialSlug?: string | null;
}

export const StudiesView: React.FC<StudiesViewProps> = ({ studies, initialSlug }) => {
  const { bi } = useI18n();
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
          {bi('实证研究报告与对抗式独立复核', 'Empirical Studies & Adversarial Reviews')}
        </h1>
        <p className="text-sm text-slate-600 mt-1">
          {bi(
            `完整收录全部 ${studies.length} 项预注册实证研究，包含不可篡改实验账本、假设版本号、原始研究报告与 Stage 6D 自动化复核清单。`,
            `All ${studies.length} preregistered studies with immutable ledger trials, hypothesis versions, full Markdown reports, and Stage 6D read-only audit checks.`
          )}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Study List */}
        <aside className="lg:col-span-4 bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="p-4 border-b border-slate-200 space-y-3">
            <label htmlFor="study-search" className="sr-only">
              {bi('搜索研究', 'Search studies')}
            </label>
            <input
              id="study-search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={bi('搜索研究代号、假设或试验号…', 'Search study, hypothesis, or trial…')}
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
                  {vf === 'all'
                    ? bi(`全部 (${studies.length})`, `All (${studies.length})`)
                    : vf === 'supported'
                      ? bi('含成立结果', 'Has Supported')
                      : bi('全部证伪', 'All Rejected')}
                </button>
              ))}
            </div>
          </div>

          <div className="divide-y divide-slate-100 max-h-[680px] overflow-y-auto">
            {filteredStudies.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-500">
                {bi('没有匹配当前筛选条件的研究。', 'No studies match the current filter.')}
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
                          ? bi(`${s.supported_trials} 项成立`, `${s.supported_trials} supported`)
                          : bi('空结果 / 证伪', 'Null / Rejected')}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-500 font-mono">
                      {s.hypotheses.join(', ')} · {s.trials.join(', ')}
                    </div>
                    <div className="mt-1 text-[11px] text-slate-500 font-mono tabular-nums">
                      {bi('审计：', 'Audit: ')}
                      {s.review_counts.pass} {bi('通过', 'pass')} · {s.review_counts.fail}{' '}
                      {bi('失败', 'fail')} · {s.review_counts.unverified}{' '}
                      {bi('未复验', 'unverified')}
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
                {selectedSlug || bi('请选择一项研究', 'Select a study')}
              </div>
              {detail && (
                <div className="text-xs text-slate-500 font-mono mt-0.5">
                  {detail.report_path} · {detail.trials.length} {bi('条试验记录', 'trial record(s)')} ·{' '}
                  {detail.review_checks.length} {bi('项审计检查', 'audit checks')}
                </div>
              )}
            </div>

            <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg">
              {(
                [
                  { id: 'report', zh: '完整报告', en: 'Study Report' },
                  { id: 'trials', zh: '试验与假设版本', en: 'Trials & Hypotheses' },
                  { id: 'review', zh: '对抗式审计', en: 'Adversarial Audit' },
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
                  {bi(t.zh, t.en)}
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

            {error && !loading && <div className="text-sm text-rose-700 py-4">{error}</div>}

            {detail && !loading && detailTab === 'report' && (
              <MarkdownViewer content={detail.markdown} />
            )}

            {detail && !loading && detailTab === 'trials' && (
              <div className="space-y-6">
                <div>
                  <h2 className="text-sm font-semibold text-slate-900 mb-3">
                    {bi('不可篡改试验账本记录', 'Immutable Trial Ledger Records')}
                  </h2>
                  <div className="overflow-x-auto border border-slate-200 rounded-lg">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                          <th className="py-2.5 px-3 font-semibold">{bi('试验号', 'Trial')}</th>
                          <th className="py-2.5 px-3 font-semibold">{bi('主检验项', 'Primary Test')}</th>
                          <th className="py-2.5 px-3 font-semibold text-right">{bi('效应量', 'Effect')}</th>
                          <th className="py-2.5 px-3 font-semibold text-right">{bi('原始 p', 'Raw p')}</th>
                          <th className="py-2.5 px-3 font-semibold text-right">{bi('校正 p', 'Adj. p')}</th>
                          <th className="py-2.5 px-3 font-semibold text-right">n</th>
                          <th className="py-2.5 px-3 font-semibold">{bi('结论', 'Outcome')}</th>
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
                                <span className="text-rose-700 font-medium">{bi('失败', 'Failed')}</span>
                              ) : tr.supported ? (
                                <span className="text-emerald-700 font-medium">{bi('成立', 'Supported')}</span>
                              ) : (
                                <span className="text-slate-600 font-medium">{bi('证伪', 'Rejected')}</span>
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
                    {bi('预注册假设历史版本', 'Preregistered Hypothesis Versions')}
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
                              <span>
                                {bi('状态：', 'State: ')}
                                {v.state}
                              </span>
                              <span>·</span>
                              <span className="text-slate-500">
                                {bi('指纹：', 'Fingerprint: ')}
                                {v.spec_fingerprint.slice(0, 14)}…
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
                  {bi(
                    '确定性 Stage 6D 只读核查：逐项校验哈希链、预注册指纹、Holm 重算、报告表格一致性与 PIT 时间戳。',
                    'Deterministic Stage 6D audit checks verifying ledger hash-chains, anchors, preregistration fingerprints, Holm recomputation, report-table alignment, and PIT timestamps.'
                  )}
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
