import React, { useMemo, useState } from 'react';
import type { DecisionRecordSummary, SourcesAndPanelsPayload } from '../lib/types';
import {
  formatInteger,
  formatPValue,
  formatShortDate,
  formatStatusLabel,
  shortInstrumentLabel,
  statusTextClass,
} from '../lib/format';

interface DecisionRecordsViewProps {
  records: DecisionRecordSummary[];
  sourcesData: SourcesAndPanelsPayload;
  onSelectStudy: (slug: string) => void;
}

export const DecisionRecordsView: React.FC<DecisionRecordsViewProps> = ({
  records,
  sourcesData,
  onSelectStudy,
}) => {
  const [section, setSection] = useState<'records' | 'sources'>('records');
  const [filterType, setFilterType] = useState<'all' | 'supported_edge' | 'rejected_hypothesis'>(
    'all',
  );
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string>(records[0]?.record_id ?? '');

  const filteredRecords = useMemo(() => {
    const q = search.trim().toLowerCase();
    return records.filter((r) => {
      if (filterType !== 'all' && r.record_type !== filterType) return false;
      if (q) {
        const hay = `${r.record_id} ${r.study} ${r.hypothesis_id} ${r.edge_id ?? ''} ${r.conclusion}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [records, filterType, search]);

  const activeRecord = useMemo(
    () => records.find((r) => r.record_id === selectedId) ?? filteredRecords[0] ?? null,
    [records, selectedId, filteredRecords],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Decision Records &amp; Data Provenance
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            {records.length} ledger-verified statistical decision records and{' '}
            {sourcesData.sources.length} external data-source health probes.
          </p>
        </div>

        <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg self-start">
          <button
            type="button"
            onClick={() => setSection('records')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap shrink-0 ${
              section === 'records'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Decision Records ({records.length})
          </button>
          <button
            type="button"
            onClick={() => setSection('sources')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap shrink-0 ${
              section === 'sources'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Data Sources &amp; Panels ({sourcesData.panels.length})
          </button>
        </div>
      </div>

      {section === 'records' ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <aside className="lg:col-span-4 bg-white border border-slate-200 rounded-lg overflow-hidden">
            <div className="p-4 border-b border-slate-200 space-y-3">
              <label htmlFor="dr-search" className="sr-only">
                Search decision records
              </label>
              <input
                id="dr-search"
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search DR ID, study, or hypothesis…"
                className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-600"
              />
              <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg">
                {(
                  [
                    { id: 'all', label: 'All (21)' },
                    { id: 'supported_edge', label: 'Supported (6)' },
                    { id: 'rejected_hypothesis', label: 'Rejected (15)' },
                  ] as const
                ).map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setFilterType(f.id)}
                    className={`flex-1 px-2 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                      filterType === f.id
                        ? 'bg-white text-slate-900 shadow-xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="divide-y divide-slate-100 max-h-[640px] overflow-y-auto">
              {filteredRecords.map((rec) => {
                const isSelected = activeRecord?.record_id === rec.record_id;
                return (
                  <button
                    key={rec.record_id}
                    type="button"
                    onClick={() => setSelectedId(rec.record_id)}
                    className={`w-full text-left px-4 py-3 block transition-colors ${
                      isSelected ? 'bg-blue-50/70' : 'hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-mono font-semibold text-slate-900">
                        {rec.record_id}
                      </span>
                      <span className={statusTextClass(rec.conclusion)}>
                        {rec.conclusion}
                      </span>
                    </div>
                    <div className="text-xs text-slate-500 font-mono mt-0.5">
                      {rec.study} · {rec.hypothesis_id} v{rec.hypothesis_version} · {rec.trial_id}
                    </div>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="lg:col-span-8 bg-white border border-slate-200 rounded-lg p-6">
            {activeRecord ? (
              <div className="space-y-6">
                <div className="flex flex-wrap items-start justify-between gap-4 pb-4 border-b border-slate-200">
                  <div>
                    <div className="flex items-center gap-2 text-xs">
                      <span className="font-mono font-semibold text-slate-900">
                        {activeRecord.record_id}
                      </span>
                      <span className="text-slate-400">·</span>
                      <span className={statusTextClass(activeRecord.conclusion)}>
                        {activeRecord.conclusion}
                      </span>
                      <span className="text-slate-400">·</span>
                      <span className="text-slate-500">
                        {activeRecord.record_type.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <h2 className="text-lg font-semibold text-slate-900 mt-1">
                      {activeRecord.study} ({activeRecord.hypothesis_id} v
                      {activeRecord.hypothesis_version})
                    </h2>
                    {activeRecord.conclusion_scope && (
                      <p className="text-xs text-slate-600 mt-1.5 leading-relaxed max-w-2xl">
                        {activeRecord.conclusion_scope}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => onSelectStudy(activeRecord.study)}
                    className="px-3.5 py-2 text-xs font-medium text-blue-700 border border-blue-200 hover:bg-blue-50 rounded-md whitespace-nowrap shrink-0"
                  >
                    View Full Study Report
                  </button>
                </div>

                {/* Provenance metadata */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                  <div>
                    <div className="text-slate-500">Preregistration Fingerprint</div>
                    <div className="font-mono text-slate-800 break-all mt-0.5">
                      {activeRecord.preregistration_fingerprint}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">Trial Ledger Hash ({activeRecord.trial_id})</div>
                    <div className="font-mono text-slate-800 break-all mt-0.5">
                      {activeRecord.trial_record_hash}
                    </div>
                  </div>
                  {activeRecord.evidence.sample && (
                    <div>
                      <div className="text-slate-500">Sample Period</div>
                      <div className="font-mono tabular-nums text-slate-800 mt-0.5">
                        {formatShortDate(activeRecord.evidence.sample.first)} to{' '}
                        {formatShortDate(activeRecord.evidence.sample.last)} (n ={' '}
                        {formatInteger(activeRecord.evidence.sample.observations)})
                      </div>
                    </div>
                  )}
                  {activeRecord.evidence.lab_wide && (
                    <div>
                      <div className="text-slate-500">
                        Lab-Wide Multiplicity (m = {activeRecord.evidence.lab_wide.family_size})
                      </div>
                      <div className="font-mono tabular-nums text-slate-800 mt-0.5">
                        Holm p = {formatPValue(activeRecord.evidence.lab_wide.holm_adjusted_p_value)}{' '}
                        · BH p = {formatPValue(activeRecord.evidence.lab_wide.bh_adjusted_p_value)}
                      </div>
                    </div>
                  )}
                </div>

                {/* Family tests table */}
                {activeRecord.evidence.family_tests &&
                  activeRecord.evidence.family_tests.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-slate-900 mb-2">
                        Within-Study Preregistered Holm Family
                      </h3>
                      <div className="overflow-x-auto border border-slate-200 rounded-lg">
                        <table className="w-full text-left border-collapse text-xs">
                          <thead>
                            <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                              <th className="py-2 px-3 font-semibold">Edge</th>
                              <th className="py-2 px-3 font-semibold">Test Key</th>
                              <th className="py-2 px-3 font-semibold text-right">Raw p</th>
                              <th className="py-2 px-3 font-semibold text-right">Holm adj. p</th>
                              <th className="py-2 px-3 font-semibold">Reject H₀</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {activeRecord.evidence.family_tests.map((ft) => (
                              <tr key={ft.test_key}>
                                <td className="py-2 px-3 font-mono text-slate-700">
                                  {ft.edge_id ?? '—'}
                                </td>
                                <td className="py-2 px-3 font-mono text-slate-900">
                                  {ft.test_key}
                                </td>
                                <td className="py-2 px-3 font-mono tabular-nums text-right">
                                  {formatPValue(ft.raw_p_value)}
                                </td>
                                <td className="py-2 px-3 font-mono tabular-nums text-right">
                                  {formatPValue(ft.holm_adjusted_p_value)}
                                </td>
                                <td className="py-2 px-3">
                                  {ft.reject ? (
                                    <span className="text-emerald-700 font-medium">Yes</span>
                                  ) : (
                                    <span className="text-slate-500">No</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                {/* Audit notes & limitations */}
                {activeRecord.audit_notes.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-slate-900 mb-2">Audit Notes</h3>
                    <ul className="list-disc pl-5 space-y-1.5 text-xs text-slate-700 leading-relaxed">
                      {activeRecord.audit_notes.map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {activeRecord.limitations.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-slate-900 mb-2">
                      Documented Limitations
                    </h3>
                    <ul className="list-disc pl-5 space-y-1.5 text-xs text-slate-700 leading-relaxed">
                      {activeRecord.limitations.map((l, i) => (
                        <li key={i}>{l}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-slate-500">No decision record selected.</p>
            )}
          </section>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Panel Freshness Table */}
          <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  Instrument Panel Freshness (12 Tracked Series)
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Probed {formatShortDate(sourcesData.probed_at)} · Accounts for verified
                  publication-lag rules (e.g., 1-trading-day FRED posting lag).
                </p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                    <th className="py-2.5 px-4 font-semibold">Instrument</th>
                    <th className="py-2.5 px-4 font-semibold">Source</th>
                    <th className="py-2.5 px-4 font-semibold">Lag Rule</th>
                    <th className="py-2.5 px-4 font-semibold text-right">Panel Last</th>
                    <th className="py-2.5 px-4 font-semibold text-right">Expected Latest</th>
                    <th className="py-2.5 px-4 font-semibold text-right">Days Behind</th>
                    <th className="py-2.5 px-4 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {sourcesData.panels.map((p) => (
                    <tr key={p.instrument_id} className="hover:bg-slate-50">
                      <td className="py-2.5 px-4 font-medium text-slate-900 whitespace-nowrap">
                        {shortInstrumentLabel(p.instrument_id)}{' '}
                        <span className="font-mono text-slate-400 font-normal">
                          · {p.instrument_id}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 font-mono text-slate-700 whitespace-nowrap">
                        {p.source_id}
                      </td>
                      <td className="py-2.5 px-4 text-slate-600 whitespace-nowrap">
                        {p.lag_kind.replace(/_/g, ' ')}
                      </td>
                      <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-800 whitespace-nowrap">
                        {p.panel_last}
                      </td>
                      <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-600 whitespace-nowrap">
                        {p.expected_latest}
                      </td>
                      <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-800 whitespace-nowrap">
                        {p.days_behind}
                      </td>
                      <td className={`py-2.5 px-4 whitespace-nowrap ${statusTextClass(p.status)}`}>
                        {formatStatusLabel(p.status)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Data Sources Table */}
          <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200">
              <h2 className="text-base font-semibold text-slate-900">
                Registered Public Data Sources ({sourcesData.sources.length})
              </h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                    <th className="py-2.5 px-4 font-semibold">Source</th>
                    <th className="py-2.5 px-4 font-semibold">Provider</th>
                    <th className="py-2.5 px-4 font-semibold">Probe Mode</th>
                    <th className="py-2.5 px-4 font-semibold text-right">Checks (Pass/Fail)</th>
                    <th className="py-2.5 px-4 font-semibold text-right">Documented Quirks</th>
                    <th className="py-2.5 px-4 font-semibold text-right">Last Verified</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {sourcesData.sources.map((s) => (
                    <tr key={s.source_id} className="hover:bg-slate-50">
                      <td className="py-2.5 px-4 font-mono font-semibold text-slate-900 whitespace-nowrap">
                        {s.source_id}
                      </td>
                      <td className="py-2.5 px-4 text-slate-700">{s.provider}</td>
                      <td className="py-2.5 px-4 text-slate-600 whitespace-nowrap">
                        {s.probe_kind}
                      </td>
                      <td className="py-2.5 px-4 font-mono tabular-nums text-right whitespace-nowrap">
                        <span className="text-emerald-700 font-medium">{s.probe_pass}</span> /{' '}
                        <span className={s.probe_fail > 0 ? 'text-rose-700 font-medium' : 'text-slate-500'}>
                          {s.probe_fail}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-700 whitespace-nowrap">
                        {s.quirks}
                      </td>
                      <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-600 whitespace-nowrap">
                        {s.last_verified}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  );
};
