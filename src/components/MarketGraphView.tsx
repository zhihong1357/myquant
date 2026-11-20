import React, { useMemo, useState } from 'react';
import type { GraphEdge, GraphNode, GraphPayload } from '../lib/types';
import {
  formatInteger,
  formatNumber,
  formatPValue,
  formatStatusLabel,
  shortInstrumentLabel,
  statusTextClass,
} from '../lib/format';

interface MarketGraphViewProps {
  data: GraphPayload;
  onSelectStudy: (slug: string) => void;
}

const ASSET_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  crypto: { fill: '#EFF6FF', stroke: '#1D4ED8', text: '#1E3A8A' },
  volatility: { fill: '#FEF3C7', stroke: '#B45309', text: '#78350F' },
  equity: { fill: '#ECFDF5', stroke: '#15803D', text: '#14532D' },
  rates: { fill: '#F1F5F9', stroke: '#475569', text: '#0F172A' },
  credit: { fill: '#FDF2F8', stroke: '#9D174D', text: '#831843' },
  macro: { fill: '#F3E8FF', stroke: '#6B21A8', text: '#581C87' },
};

function extractStudySlug(reportPath: string): string {
  const filename = reportPath.split('/').pop() ?? '';
  const base = filename.replace(/\.md$/, '');
  const overrides: Record<string, string> = {
    'btc-eth-transmission-001': 'btc-eth-001',
    'lowvol-transmission-002': 'lowvol-002',
    'move-vix-transmission-003': 'move-vix-003',
  };
  return overrides[base] ?? base;
}

export const MarketGraphView: React.FC<MarketGraphViewProps> = ({ data, onSelectStudy }) => {
  const [subTab, setSubTab] = useState<'edges' | 'candidates'>('edges');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(
    data.edges.find((e) => e.status === 'supported')?.edge_id ?? data.edges[0]?.edge_id ?? null,
  );
  const [searchQuery, setSearchQuery] = useState('');
  const [candidateFilter, setCandidateFilter] = useState<'all' | 'ranked' | 'templates' | 'unrankable'>('all');

  // Compute deterministic circular layout grouped by asset class
  const nodePositions = useMemo(() => {
    const ordered = [...data.nodes].sort((a, b) =>
      a.asset_class !== b.asset_class
        ? a.asset_class.localeCompare(b.asset_class)
        : a.short_label.localeCompare(b.short_label),
    );
    const cx = 380;
    const cy = 235;
    const rx = 270;
    const ry = 178;
    const map = new Map<string, { x: number; y: number; node: GraphNode }>();
    ordered.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / ordered.length - Math.PI / 2;
      map.set(node.instrument_id, {
        x: cx + rx * Math.cos(angle),
        y: cy + ry * Math.sin(angle),
        node,
      });
    });
    return map;
  }, [data.nodes]);

  const filteredEdges = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return data.edges.filter((e) => {
      if (statusFilter !== 'all' && e.status !== statusFilter) return false;
      if (
        selectedNodeId &&
        e.source_instrument !== selectedNodeId &&
        e.target_instrument !== selectedNodeId
      ) {
        return false;
      }
      if (q) {
        const hay = `${e.edge_id} ${e.hypothesis_id} ${e.trial_id} ${e.source_instrument} ${e.target_instrument} ${e.test_type} ${e.ledger_test_key}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [data.edges, statusFilter, selectedNodeId, searchQuery]);

  const selectedEdge: GraphEdge | null = useMemo(
    () => data.edges.find((e) => e.edge_id === selectedEdgeId) ?? filteredEdges[0] ?? null,
    [data.edges, selectedEdgeId, filteredEdges],
  );

  const filteredCandidates = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return data.candidates.filter((c) => {
      if (candidateFilter === 'ranked' && !c.ranked) return false;
      if (candidateFilter === 'templates' && !c.has_template) return false;
      if (candidateFilter === 'unrankable' && c.ranked) return false;
      if (
        selectedNodeId &&
        c.source_instrument !== selectedNodeId &&
        c.target_instrument !== selectedNodeId
      ) {
        return false;
      }
      if (q) {
        const hay = `${c.source_instrument} ${c.target_instrument} ${c.mechanism} ${c.unrankable_reason ?? ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [data.candidates, candidateFilter, selectedNodeId, searchQuery]);

  // Unique directed pairs for clean graph rendering
  const graphLines = useMemo(() => {
    const pairs = new Map<string, GraphEdge[]>();
    for (const e of filteredEdges) {
      if (!nodePositions.has(e.source_instrument) || !nodePositions.has(e.target_instrument)) continue;
      const key = `${e.source_instrument}__${e.target_instrument}`;
      const existing = pairs.get(key) ?? [];
      existing.push(e);
      pairs.set(key, existing);
    }
    return Array.from(pairs.values()).map((edges) => {
      const supported = edges.find((x) => x.status === 'supported');
      return {
        primary: supported ?? edges[0],
        count: edges.length,
        hasSupported: Boolean(supported),
      };
    });
  }, [filteredEdges, nodePositions]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Cross-Market Graph &amp; Edge Registry
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            {data.nodes.length} provider-neutral instruments · {data.edges.length} ledger-verified
            edges · {data.candidates.length} untested planner candidates.
          </p>
        </div>
        <div className="text-xs font-mono text-slate-500 whitespace-nowrap">
          Registry SHA-256: {data.content_hash.slice(0, 12)}…
        </div>
      </div>

      {/* Interactive SVG Graph + Inspector split */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-stretch">
        <section className="xl:col-span-8 bg-white border border-slate-200 rounded-lg p-5 flex flex-col">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg">
              {(['all', 'supported', 'rejected', 'descriptive', 'pending_forward'] as const).map(
                (st) => (
                  <button
                    key={st}
                    type="button"
                    aria-pressed={statusFilter === st}
                    onClick={() => setStatusFilter(st)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap shrink-0 ${
                      statusFilter === st
                        ? 'bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/80'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {st === 'all' ? 'All Edges' : formatStatusLabel(st)}
                  </button>
                ),
              )}
            </div>

            {selectedNodeId && (
              <button
                type="button"
                onClick={() => setSelectedNodeId(null)}
                className="text-xs font-medium text-blue-700 hover:text-blue-800 whitespace-nowrap"
              >
                Clear node filter ({shortInstrumentLabel(selectedNodeId)})
              </button>
            )}
          </div>

          <div className="w-full overflow-x-auto flex-1 flex items-center justify-center bg-slate-50/70 rounded-lg border border-slate-100">
            <svg
              viewBox="0 0 760 470"
              className="w-full max-w-[760px] h-auto"
              role="img"
              aria-label="Cross-market instrument transmission graph"
            >
              <defs>
                <marker
                  id="arrow-supported"
                  viewBox="0 0 10 10"
                  refX="32"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1.5 L 10 5 L 0 8.5 z" fill="#15803D" />
                </marker>
                <marker
                  id="arrow-muted"
                  viewBox="0 0 10 10"
                  refX="32"
                  refY="5"
                  markerWidth="5"
                  markerHeight="5"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1.5 L 10 5 L 0 8.5 z" fill="#94A3B8" />
                </marker>
              </defs>

              {/* Directed edges */}
              {graphLines.map(({ primary, hasSupported }) => {
                const src = nodePositions.get(primary.source_instrument);
                const tgt = nodePositions.get(primary.target_instrument);
                if (!src || !tgt) return null;

                const isSelf = primary.source_instrument === primary.target_instrument;
                const isSelected = selectedEdge?.edge_id === primary.edge_id;
                const stroke = hasSupported
                  ? '#15803D'
                  : isSelected
                    ? '#1D4ED8'
                    : '#CBD5E1';
                const strokeWidth = isSelected ? 2.8 : hasSupported ? 2.2 : 1.2;

                if (isSelf) {
                  const dx = src.x - 380;
                  const dy = src.y - 235;
                  const len = Math.hypot(dx, dy) || 1;
                  const ox = (dx / len) * 36;
                  const oy = (dy / len) * 36;
                  return (
                    <circle
                      key={primary.edge_id}
                      cx={src.x + ox}
                      cy={src.y + oy}
                      r={16}
                      fill="none"
                      stroke={stroke}
                      strokeWidth={strokeWidth}
                      className="cursor-pointer"
                      onClick={() => setSelectedEdgeId(primary.edge_id)}
                    />
                  );
                }

                const mx = (src.x + tgt.x) / 2;
                const my = (src.y + tgt.y) / 2;
                const nx = -(tgt.y - src.y) * 0.1;
                const ny = (tgt.x - src.x) * 0.1;
                const d = `M ${src.x} ${src.y} Q ${mx + nx} ${my + ny} ${tgt.x} ${tgt.y}`;

                return (
                  <path
                    key={primary.edge_id}
                    d={d}
                    fill="none"
                    stroke={stroke}
                    strokeWidth={strokeWidth}
                    strokeDasharray={hasSupported ? undefined : '4 3'}
                    markerEnd={hasSupported ? 'url(#arrow-supported)' : 'url(#arrow-muted)'}
                    className="cursor-pointer transition-opacity"
                    opacity={isSelected || hasSupported ? 0.95 : 0.65}
                    onClick={() => setSelectedEdgeId(primary.edge_id)}
                  />
                );
              })}

              {/* Instrument nodes */}
              {Array.from(nodePositions.values()).map(({ x, y, node }) => {
                const palette = ASSET_COLORS[node.asset_class] ?? ASSET_COLORS.rates;
                const isSelected = selectedNodeId === node.instrument_id;
                const parts = node.short_label.includes('_')
                  ? node.short_label.split('_')
                  : [node.short_label];
                return (
                  <g
                    key={node.instrument_id}
                    transform={`translate(${x}, ${y})`}
                    className="cursor-pointer"
                    onClick={() =>
                      setSelectedNodeId((prev) =>
                        prev === node.instrument_id ? null : node.instrument_id,
                      )
                    }
                  >
                    <circle
                      r={isSelected ? 30 : 27}
                      fill={palette.fill}
                      stroke={isSelected ? '#0F172A' : palette.stroke}
                      strokeWidth={isSelected ? 2.5 : 1.5}
                    />
                    {parts.length === 2 ? (
                      <text
                        textAnchor="middle"
                        fill={palette.text}
                        fontSize="9.5"
                        fontWeight="600"
                        fontFamily="IBM Plex Mono, monospace"
                      >
                        <tspan x="0" dy="-0.15em">
                          {parts[0]}
                        </tspan>
                        <tspan x="0" dy="1.2em">
                          {parts[1]}
                        </tspan>
                      </text>
                    ) : (
                      <text
                        textAnchor="middle"
                        dy="0.35em"
                        fill={palette.text}
                        fontSize="10"
                        fontWeight="600"
                        fontFamily="IBM Plex Mono, monospace"
                      >
                        {node.short_label}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <div>
              Solid green lines indicate supported edges · Dashed lines indicate rejected or
              descriptive tests · Click any node to filter connected edges.
            </div>
          </div>
        </section>

        {/* Selected Edge / Node Inspector */}
        <aside className="xl:col-span-4 bg-white border border-slate-200 rounded-lg p-5 flex flex-col justify-between">
          {selectedEdge ? (
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-sm font-semibold text-slate-900">
                    {selectedEdge.edge_id}
                  </span>
                  <span className={`text-xs ${statusTextClass(selectedEdge.status)}`}>
                    {formatStatusLabel(selectedEdge.status)}
                  </span>
                </div>
                <h2 className="text-base font-semibold text-slate-900 mt-1">
                  {shortInstrumentLabel(selectedEdge.source_instrument)} →{' '}
                  {shortInstrumentLabel(selectedEdge.target_instrument)}
                </h2>
                <div className="text-xs text-slate-500 font-mono mt-0.5">
                  {selectedEdge.hypothesis_id} · {selectedEdge.trial_id} · {selectedEdge.frequency} ·{' '}
                  {selectedEdge.test_type.replace(/_/g, ' ')}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 pt-3 border-t border-slate-200 text-xs">
                <div>
                  <div className="text-slate-500">Coefficient</div>
                  <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                    {formatNumber(selectedEdge.coefficient, 5)}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500">t-Statistic</div>
                  <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                    {formatNumber(selectedEdge.t_statistic, 3)}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500">Raw p-Value</div>
                  <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                    {formatPValue(selectedEdge.p_value)}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500">Holm adj. p</div>
                  <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                    {formatPValue(selectedEdge.holm_adjusted_p_value)}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500">Partial R²</div>
                  <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                    {formatNumber(selectedEdge.partial_r_squared, 5)}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500">Observations (n)</div>
                  <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                    {formatInteger(selectedEdge.observations)}
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-200 space-y-2 text-xs">
                <div>
                  <span className="text-slate-500">Method: </span>
                  <span className="text-slate-800">{selectedEdge.method}</span>
                </div>
                {selectedEdge.common_factor_control && (
                  <div>
                    <span className="text-slate-500">Control: </span>
                    <span className="text-slate-800">{selectedEdge.common_factor_control}</span>
                  </div>
                )}
                {selectedEdge.cost_gate && (
                  <div>
                    <span className="text-slate-500">Cost gate: </span>
                    <span className={statusTextClass(selectedEdge.cost_gate.verdict)}>
                      {selectedEdge.cost_gate.verdict.toUpperCase()}
                    </span>
                    {selectedEdge.cost_gate.note && (
                      <span className="text-slate-600"> — {selectedEdge.cost_gate.note}</span>
                    )}
                  </div>
                )}
                <p className="text-slate-600 leading-relaxed pt-1">{selectedEdge.verdict_summary}</p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Select an edge to inspect its ledger record.</p>
          )}

          {selectedEdge && (
            <div className="pt-4 mt-4 border-t border-slate-200">
              <button
                type="button"
                onClick={() => onSelectStudy(extractStudySlug(selectedEdge.report_path))}
                className="w-full py-2 px-4 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md transition-colors"
              >
                Open Study Report ({extractStudySlug(selectedEdge.report_path)})
              </button>
            </div>
          )}
        </aside>
      </div>

      {/* Sub-navigation between Edge Registry and Candidate Planner */}
      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg self-start">
            <button
              type="button"
              onClick={() => setSubTab('edges')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap shrink-0 ${
                subTab === 'edges'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Tested Edges ({filteredEdges.length})
            </button>
            <button
              type="button"
              onClick={() => setSubTab('candidates')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap shrink-0 ${
                subTab === 'candidates'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Untested Planner Candidates ({filteredCandidates.length})
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {subTab === 'candidates' && (
              <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg">
                {(['all', 'ranked', 'templates', 'unrankable'] as const).map((cf) => (
                  <button
                    key={cf}
                    type="button"
                    onClick={() => setCandidateFilter(cf)}
                    className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                      candidateFilter === cf
                        ? 'bg-white text-slate-900 shadow-xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {cf === 'all'
                      ? 'All'
                      : cf === 'ranked'
                        ? 'Ranked'
                        : cf === 'templates'
                          ? 'With Template'
                          : 'Unrankable'}
                  </button>
                ))}
              </div>
            )}

            <label className="sr-only" htmlFor="graph-search">
              Filter instruments or edges
            </label>
            <input
              id="graph-search"
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter edge, instrument, or hypothesis…"
              className="px-3 py-1.5 text-xs border border-slate-300 rounded-md w-64 focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-600"
            />
          </div>
        </div>

        {subTab === 'edges' ? (
          <div className="overflow-x-auto">
            {filteredEdges.length === 0 ? (
              <div className="p-8 text-center text-sm text-slate-500">
                No edges match the active filters.
              </div>
            ) : (
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                    <th className="py-2.5 px-4 font-semibold">Edge</th>
                    <th className="py-2.5 px-4 font-semibold">Pair</th>
                    <th className="py-2.5 px-4 font-semibold">Hypothesis / Test</th>
                    <th className="py-2.5 px-4 font-semibold text-right">Coef</th>
                    <th className="py-2.5 px-4 font-semibold text-right">Raw p</th>
                    <th className="py-2.5 px-4 font-semibold text-right">Holm p</th>
                    <th className="py-2.5 px-4 font-semibold text-right">n</th>
                    <th className="py-2.5 px-4 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredEdges.map((edge) => {
                    const isSelected = selectedEdge?.edge_id === edge.edge_id;
                    return (
                      <tr
                        key={edge.edge_id}
                        onClick={() => setSelectedEdgeId(edge.edge_id)}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? 'bg-blue-50/70' : 'hover:bg-slate-50'
                        }`}
                      >
                        <td className="py-2.5 px-4 font-mono font-semibold text-slate-900 whitespace-nowrap">
                          {edge.edge_id}
                        </td>
                        <td className="py-2.5 px-4 font-medium text-slate-800 whitespace-nowrap">
                          {shortInstrumentLabel(edge.source_instrument)} →{' '}
                          {shortInstrumentLabel(edge.target_instrument)}
                        </td>
                        <td className="py-2.5 px-4 text-slate-600">
                          <span className="font-mono text-slate-800">{edge.hypothesis_id}</span>
                          <span className="mx-1.5 text-slate-400">·</span>
                          <span className="font-mono">{edge.ledger_test_key}</span>
                        </td>
                        <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-800 whitespace-nowrap">
                          {formatNumber(edge.coefficient, 4)}
                        </td>
                        <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-800 whitespace-nowrap">
                          {formatPValue(edge.p_value)}
                        </td>
                        <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-800 whitespace-nowrap">
                          {formatPValue(edge.holm_adjusted_p_value)}
                        </td>
                        <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-600 whitespace-nowrap">
                          {formatInteger(edge.observations)}
                        </td>
                        <td className={`py-2.5 px-4 whitespace-nowrap ${statusTextClass(edge.status)}`}>
                          {formatStatusLabel(edge.status)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            {filteredCandidates.length === 0 ? (
              <div className="p-8 text-center text-sm text-slate-500">
                No planner candidates match the active filters.
              </div>
            ) : (
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                    <th className="py-2.5 px-4 font-semibold text-right">Rank</th>
                    <th className="py-2.5 px-4 font-semibold">Candidate Pair</th>
                    <th className="py-2.5 px-4 font-semibold">Mechanism</th>
                    <th className="py-2.5 px-4 font-semibold text-right">Planner Score</th>
                    <th className="py-2.5 px-4 font-semibold">Draft Template</th>
                    <th className="py-2.5 px-4 font-semibold">Notes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredCandidates.slice(0, 80).map((c, idx) => (
                    <tr key={`${c.source_instrument}-${c.target_instrument}-${idx}`} className="hover:bg-slate-50">
                      <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-600">
                        {c.rank ?? '—'}
                      </td>
                      <td className="py-2.5 px-4 font-medium text-slate-900 whitespace-nowrap">
                        {shortInstrumentLabel(c.source_instrument)} →{' '}
                        {shortInstrumentLabel(c.target_instrument)}
                      </td>
                      <td className="py-2.5 px-4 text-slate-600 whitespace-nowrap">
                        {c.mechanism} · {c.test_type.replace(/_/g, ' ')}
                      </td>
                      <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-900 whitespace-nowrap">
                        {c.total_score !== null ? c.total_score.toFixed(2) : 'Unrankable'}
                      </td>
                      <td className="py-2.5 px-4 whitespace-nowrap">
                        {c.has_template ? (
                          <span className="text-emerald-700 font-medium">Available</span>
                        ) : (
                          <span className="text-slate-400">None</span>
                        )}
                      </td>
                      <td className="py-2.5 px-4 text-slate-500">
                        {c.unrankable_reason ?? 'Untested pair (no evidence implied)'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </section>
    </div>
  );
};
