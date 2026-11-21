import React, { useEffect, useState } from 'react';
import { formatNumber, formatPValue } from '../lib/format';
import { useI18n } from '../lib/i18n';
import type { MultiplicityMethod } from '../lib/quant/multipleTesting';
import type { MinimumDetectableEffect } from '../lib/quant/power';
import type { PaperExecutionCostBreakdown } from '../lib/quant/executionCosts';
import type { FactorTimingMode, LeadLagResult, SyntheticScenario } from '../lib/quant/leadLag';

export type WorkbenchSubTab = 'multiplicity' | 'mde' | 'costs' | 'lead_lag';

interface QuantWorkbenchViewProps {
  activeSubTab?: WorkbenchSubTab;
  onChangeSubTab?: (tab: WorkbenchSubTab) => void;
}

interface MultiplicityResponse {
  method: MultiplicityMethod;
  alpha: number;
  familySize: number;
  rejections: number;
  excludedEdges?: Array<{ edgeId: string; reason: string | null }>;
  results: Array<{
    originalIndex: number;
    label: string;
    rawPValue: number;
    adjustedPValue: number;
    alphaThreshold?: number;
    reject: boolean;
  }>;
}

export const QuantWorkbenchView: React.FC<QuantWorkbenchViewProps> = ({
  activeSubTab,
  onChangeSubTab,
}) => {
  const { bi } = useI18n();
  const [internalTool, setInternalTool] = useState<WorkbenchSubTab>('multiplicity');
  const tool = activeSubTab ?? internalTool;
  const setTool = (next: WorkbenchSubTab) => {
    setInternalTool(next);
    onChangeSubTab?.(next);
  };

  // Tool 1: Multiple testing state
  const [mtMethod, setMtMethod] = useState<MultiplicityMethod>('online_lord_pp');
  const [mtAlpha, setMtAlpha] = useState('0.05');
  const [mtExcludeUnclean, setMtExcludeUnclean] = useState(true);
  const [mtInput, setMtInput] = useState('0.00017, 0.00290, 0.00982, 0.03999, 0.22690, 0.71779');
  const [mtResult, setMtResult] = useState<MultiplicityResponse | null>(null);
  const [mtError, setMtError] = useState<string | null>(null);
  const [mtLoading, setMtLoading] = useState(false);

  // Tool 2: MDE Power state
  const [mdeDesign, setMdeDesign] = useState<
    'lead_lag_ols' | 'event_study_car' | 'cohens_d' | 'mean_ratio'
  >('lead_lag_ols');
  const [mdeObs, setMdeObs] = useState('1414');
  const [mdeGroup2, setMdeGroup2] = useState('2009');
  const [mdeAlpha, setMdeAlpha] = useState('0.05');
  const [mdePower, setMdePower] = useState('0.80');
  const [mdeRho, setMdeRho] = useState('0.90');
  const [mdeRegimes, setMdeRegimes] = useState('69');
  const [mdeOneSided, setMdeOneSided] = useState(true);
  const [mdeBaseMean, setMdeBaseMean] = useState('0.025');
  const [mdeStdErr, setMdeStdErr] = useState('0.0018');
  const [mdeResult, setMdeResult] = useState<MinimumDetectableEffect | null>(null);
  const [mdeError, setMdeError] = useState<string | null>(null);

  // Tool 3: Paper Execution Cost state
  const [costPrice, setCostPrice] = useState('92000');
  const [costQty, setCostQty] = useState('250');
  const [costSide, setCostSide] = useState<'buy' | 'sell'>('buy');
  const [costRole, setCostRole] = useState<'taker' | 'maker'>('taker');
  const [costSpread, setCostSpread] = useState('1.5');
  const [costSlippage, setCostSlippage] = useState('1.0');
  const [costImpactCoeff, setCostImpactCoeff] = useState('5.0');
  const [costDepth, setCostDepth] = useState('120');
  const [costDailyVol, setCostDailyVol] = useState('320');
  const [costAdv, setCostAdv] = useState('500000');
  const [costHoldHours, setCostHoldHours] = useState('0.5');
  const [costEntryIso, setCostEntryIso] = useState('2026-11-18T07:45:00Z');
  const [costFundingBps, setCostFundingBps] = useState('1.0');
  const [costRoundTrip, setCostRoundTrip] = useState(true);
  const [costResult, setCostResult] = useState<PaperExecutionCostBreakdown | null>(null);
  const [costError, setCostError] = useState<string | null>(null);

  // Tool 4: Synthetic Lead-Lag state
  const [llScenario, setLlScenario] = useState<SyntheticScenario>('source_leads_target');
  const [llObs, setLlObs] = useState('1000');
  const [llBeta, setLlBeta] = useState('0.18');
  const [llFactor, setLlFactor] = useState('1.40');
  const [llLag, setLlLag] = useState('1');
  const [llHacLag, setLlHacLag] = useState('5');
  const [llAutoBw, setLlAutoBw] = useState(true);
  const [llControlFactor, setLlControlFactor] = useState(true);
  const [llFactorTiming, setLlFactorTiming] = useState<FactorTimingMode>('pit_lagged');
  const [llSeed, setLlSeed] = useState('2026');
  const [llResult, setLlResult] = useState<LeadLagResult | null>(null);
  const [llError, setLlError] = useState<string | null>(null);

  // Auto-run active tool on first view so beginners immediately see live output
  useEffect(() => {
    if (tool === 'multiplicity' && !mtResult) {
      void runMultipleTesting('lab_family');
    } else if (tool === 'mde' && !mdeResult) {
      void runMdeDirect();
    } else if (tool === 'costs' && !costResult) {
      void runCostsDirect();
    } else if (tool === 'lead_lag' && !llResult) {
      void runLeadLagDirect();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tool]);

  async function runMultipleTesting(
    mode: 'custom' | 'lab_family',
    override?: { method?: MultiplicityMethod; excludeUnclean?: boolean },
  ) {
    setMtError(null);
    setMtLoading(true);
    try {
      const alphaNum = Number(mtAlpha);
      const payload: Record<string, unknown> = {
        mode,
        method: override?.method ?? mtMethod,
        alpha: alphaNum,
        excludeUncleanEdges: override?.excludeUnclean ?? mtExcludeUnclean,
      };
      if (mode === 'custom') {
        const parsed = mtInput
          .split(/[\s,;]+/)
          .map((s) => s.trim())
          .filter(Boolean)
          .map(Number);
        if (parsed.length === 0 || parsed.some((v) => !Number.isFinite(v) || v < 0 || v > 1)) {
          throw new Error(
            bi(
              '请输入逗号分隔且严格位于 0 到 1 之间的 p 值。',
              'Enter comma-separated p-values strictly between 0 and 1.'
            ),
          );
        }
        payload.pValues = parsed;
      }
      const res = await fetch('/api/tools/multiple-testing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? 'Failed to compute adjustments');
      setMtResult(json as MultiplicityResponse);
    } catch (err) {
      setMtError(err instanceof Error ? err.message : 'Calculation error');
    } finally {
      setMtLoading(false);
    }
  }

  async function runMdeDirect(override?: {
    design?: 'lead_lag_ols' | 'event_study_car' | 'cohens_d' | 'mean_ratio';
    observations?: number;
    lag1Autocorr?: number;
    distinctRegimeCount?: number;
  }) {
    setMdeError(null);
    try {
      const res = await fetch('/api/tools/mde', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          design: override?.design ?? mdeDesign,
          observations: override?.observations ?? Number(mdeObs),
          groupSize2: Number(mdeGroup2),
          alpha: Number(mdeAlpha),
          power: Number(mdePower),
          oneSided: mdeOneSided,
          meanBaseline: Number(mdeBaseMean),
          standardError: Number(mdeStdErr),
          lag1Autocorr: override?.lag1Autocorr ?? Number(mdeRho),
          distinctRegimeCount:
            override !== undefined
              ? override.distinctRegimeCount
              : mdeRegimes.trim() === ''
                ? undefined
                : Number(mdeRegimes),
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? 'MDE calculation failed');
      setMdeResult(json as MinimumDetectableEffect);
    } catch (err) {
      setMdeError(err instanceof Error ? err.message : 'Invalid MDE parameters');
    }
  }

  async function runMde(e: React.FormEvent) {
    e.preventDefault();
    await runMdeDirect();
  }

  async function runCostsDirect(override?: {
    quantityContracts?: number;
    orderBookDepthContracts?: number | null;
    holdingHours?: number;
    entryTimestampIso?: string;
  }) {
    setCostError(null);
    try {
      const depthVal =
        override && 'orderBookDepthContracts' in override
          ? override.orderBookDepthContracts
          : costDepth.trim() === ''
            ? null
            : Number(costDepth);
      const res = await fetch('/api/tools/execution-cost', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          price: Number(costPrice),
          quantityContracts: override?.quantityContracts ?? Number(costQty),
          contractValue: 0.01,
          side: costSide,
          executionRole: costRole,
          spreadBps: Number(costSpread),
          marketSlippageBps: Number(costSlippage),
          impactCoefficientBps: Number(costImpactCoeff),
          orderBookDepthContracts: depthVal,
          dailyVolBps: Number(costDailyVol),
          advContracts: Number(costAdv),
          holdingHours: override?.holdingHours ?? Number(costHoldHours),
          entryTimestampIso:
            override?.entryTimestampIso ??
            (costEntryIso.trim() === '' ? undefined : costEntryIso.trim()),
          fundingRateBpsPer8h: Number(costFundingBps),
          roundTrip: costRoundTrip,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? 'Cost simulation failed');
      setCostResult(json as PaperExecutionCostBreakdown);
    } catch (err) {
      setCostError(err instanceof Error ? err.message : 'Invalid cost parameters');
    }
  }

  async function runCosts(e: React.FormEvent) {
    e.preventDefault();
    await runCostsDirect();
  }

  async function runLeadLagDirect(override?: {
    scenario?: SyntheticScenario;
    factorTiming?: FactorTimingMode;
    beta?: number;
    commonFactorLoading?: number;
  }) {
    setLlError(null);
    try {
      const res = await fetch('/api/tools/synthetic-lead-lag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario: override?.scenario ?? llScenario,
          observations: Number(llObs),
          beta: override?.beta ?? Number(llBeta),
          commonFactorLoading: override?.commonFactorLoading ?? Number(llFactor),
          lagSteps: Number(llLag),
          maxHacLag: Number(llHacLag),
          autoBandwidth: llAutoBw,
          controlCommonFactor: llControlFactor,
          factorTiming: override?.factorTiming ?? llFactorTiming,
          seed: Number(llSeed),
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? 'Simulation failed');
      setLlResult(json as LeadLagResult);
    } catch (err) {
      setLlError(err instanceof Error ? err.message : 'Invalid simulation parameters');
    }
  }

  async function runLeadLag(e: React.FormEvent) {
    e.preventDefault();
    await runLeadLagDirect();
  }

  const isOnlineMethod = mtMethod === 'online_lord_pp' || mtMethod === 'online_saffron';

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            {bi('确定性统计排雷与成本检验工作台', 'Deterministic Statistical & Cost Workbench')}
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            {bi(
              '不用手写代码，直接用一键预设场景验证 4 大量化核心防线：在线序列防过拟合、自相关缩水样本量、无上限平方根滑点、防偷看未来 QR-HAC 回归。',
              'Hardened institutional statistical kernel: Online LORD++/SAFFRON sequential FDR, autocorrelation-adjusted Nₑff power analysis, unbounded square-root impact with fail-closed depth, and PIT-safe Householder QR + Andrews HAC inference.'
            )}
          </p>
        </div>
      </div>

      {/* Tool Selector */}
      <div className="flex flex-wrap items-center gap-1 p-1 bg-slate-100 rounded-lg self-start w-fit">
        {(
          [
            { id: 'multiplicity', zh: '1. 在线防过拟合 (LORD++)', en: 'Online & Static FDR' },
            { id: 'mde', zh: '2. 有效样本量体检 (Nₑff)', en: 'Effective-N MDE Power' },
            { id: 'costs', zh: '3. 平方根滑点与资金费率', en: 'Square-Root Costs' },
            { id: 'lead_lag', zh: '4. 防偷看未来回归 (QR-HAC)', en: 'PIT Lead-Lag QR-HAC' },
          ] as const
        ).map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTool(item.id)}
            className={`px-3.5 py-2 text-xs font-medium rounded-md transition-colors whitespace-nowrap shrink-0 ${
              tool === item.id
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            {bi(item.zh, item.en)}
          </button>
        ))}
      </div>

      {/* TOOL 1: MULTIPLE TESTING (ONLINE LORD++ / SAFFRON + STATIC) */}
      {tool === 'multiplicity' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <div className="lg:col-span-5 bg-white border border-slate-200 rounded-lg p-6 space-y-4">
            <h2 className="text-base font-semibold text-slate-900">
              {bi('序列在线 FDR 与静态多重检验防线', 'Sequential Online FDR & Static FWER Control')}
            </h2>
            <p className="text-xs text-slate-600 leading-relaxed">
              {bi(
                '普通研究一边看结果一边继续挖新因子，传统静态检验早就失效。Online LORD++ / SAFFRON 按时间顺序动态分配 α 预算，并自动剔除机械恒等边 E0026 与停更指数 TYVIX。',
                'Online LORD++ and SAFFRON remain valid when new hypotheses are chosen adaptively from prior outcomes. Hygiene filtering strips mechanical identity E0026 and discontinued TYVIX edges.'
              )}
            </p>

            {/* 1-Click Beginner Presets */}
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => {
                  setMtMethod('online_lord_pp');
                  setMtExcludeUnclean(true);
                  void runMultipleTesting('lab_family', {
                    method: 'online_lord_pp',
                    excludeUnclean: true,
                  });
                }}
                className="px-2.5 py-1 text-[11px] font-medium text-blue-800 bg-blue-50 hover:bg-blue-100 rounded border border-blue-200"
              >
                {bi('一键体检：真实 42 条边 (已去噪)', 'Preset: Audit Real Lab Family (Clean)')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setMtMethod('online_saffron');
                  void runMultipleTesting('custom', { method: 'online_saffron' });
                }}
                className="px-2.5 py-1 text-[11px] font-medium text-emerald-800 bg-emerald-50 hover:bg-emerald-100 rounded border border-emerald-200"
              >
                {bi('一键演示：SAFFRON 连续 6 次挖因子', 'Preset: SAFFRON 6-Trial Sequence')}
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="mt-method" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('多重检验算法', 'Correction Method')}
                </label>
                <select
                  id="mt-method"
                  value={mtMethod}
                  onChange={(e) => setMtMethod(e.target.value as MultiplicityMethod)}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white"
                >
                  <option value="online_lord_pp">
                    {bi('Online LORD++ (在线序列 FDR)', 'Online LORD++ (Sequential FDR)')}
                  </option>
                  <option value="online_saffron">
                    {bi('Online SAFFRON (自适应在线 FDR)', 'Online SAFFRON (Adaptive FDR)')}
                  </option>
                  <option value="holm">{bi('Holm (静态严格 FWER)', 'Holm (Static FWER)')}</option>
                  <option value="benjamini_hochberg">
                    {bi('Benjamini–Hochberg (静态 FDR)', 'Benjamini–Hochberg (Static FDR)')}
                  </option>
                  <option value="bonferroni">
                    {bi('Bonferroni (最保守静态)', 'Bonferroni (Static FWER)')}
                  </option>
                </select>
              </div>
              <div>
                <label htmlFor="mt-alpha" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('目标显著性水平 α', 'Target α')}
                </label>
                <input
                  id="mt-alpha"
                  type="number"
                  step="0.01"
                  min="0.001"
                  max="0.5"
                  value={mtAlpha}
                  onChange={(e) => setMtAlpha(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
            </div>

            <label className="flex items-center gap-2 text-xs text-slate-700">
              <input
                type="checkbox"
                checked={mtExcludeUnclean}
                onChange={(e) => setMtExcludeUnclean(e.target.checked)}
              />
              {bi(
                '开启卫生过滤：自动剔除机械恒等边 E0026 与停更指数 TYVIX',
                'Exclude mechanical identity (E0026) & discontinued TYVIX from Lab Family'
              )}
            </label>

            <div>
              <label htmlFor="mt-pvalues" className="block text-xs font-medium text-slate-700 mb-1">
                {bi('自定义 p 值序列（按历史试验先后顺序）', 'Custom Raw p-Values (chronological order)')}
              </label>
              <textarea
                id="mt-pvalues"
                rows={3}
                value={mtInput}
                onChange={(e) => setMtInput(e.target.value)}
                className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
              />
            </div>

            {mtError && <p className="text-xs text-rose-700">{mtError}</p>}

            <div className="flex flex-wrap gap-2 pt-1">
              <button
                type="button"
                disabled={mtLoading}
                onClick={() => runMultipleTesting('lab_family')}
                className="px-4 py-2 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md transition-colors whitespace-nowrap"
              >
                {bi('审计实验室真实边集', 'Audit Real Lab Family')}
              </button>
              <button
                type="button"
                disabled={mtLoading}
                onClick={() => runMultipleTesting('custom')}
                className="px-4 py-2 text-xs font-medium text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-md transition-colors whitespace-nowrap"
              >
                {bi('校正自定义序列', 'Adjust Custom Sequence')}
              </button>
            </div>
          </div>

          <div className="lg:col-span-7 bg-white border border-slate-200 rounded-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-slate-900">
                {bi('多重检验裁决结果', 'Adjustment Output')}
              </h3>
              {mtResult && (
                <span className="text-xs font-mono tabular-nums text-slate-600">
                  {bi(
                    `共 ${mtResult.familySize} 项检验中通过 ${mtResult.rejections} 项 (α = ${mtResult.alpha})`,
                    `${mtResult.rejections} rejected of ${mtResult.familySize} (α = ${mtResult.alpha})`
                  )}
                </span>
              )}
            </div>

            {mtResult && (
              <div className="px-6 py-3 bg-blue-50/50 border-b border-blue-100 text-xs text-slate-800 leading-relaxed">
                <span className="font-semibold text-blue-950">
                  {bi('大白话解读：', 'Plain-Language Takeaway: ')}
                </span>
                {bi(
                  `如果只看单个原始 p < 0.05，很容易把运气当实力。经过严格的 ${mtResult.method} 多重校验后，${mtResult.familySize} 项检验里只有 ${mtResult.rejections} 项真正过关，其余全部被判为证据不足。`,
                  `Evaluating raw p < 0.05 invites data-mining noise. Under ${mtResult.method}, only ${mtResult.rejections} of ${mtResult.familySize} tests clear the adjusted significance bar.`
                )}
              </div>
            )}

            {mtResult?.excludedEdges && mtResult.excludedEdges.length > 0 && (
              <div className="px-6 py-2.5 bg-amber-50/70 border-b border-amber-200 text-xs text-amber-900">
                {bi(
                  `卫生过滤已自动排除 ${mtResult.excludedEdges.length} 条污染/停更边：`,
                  `Hygiene Filter excluded ${mtResult.excludedEdges.length} unclean edges: `
                )}
                <span className="font-mono">
                  {mtResult.excludedEdges.map((e) => e.edgeId).join(', ')}
                </span>
              </div>
            )}

            {mtResult ? (
              <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                      <th className="py-2.5 px-4 font-semibold">{bi('检验对象', 'Test')}</th>
                      <th className="py-2.5 px-4 font-semibold text-right">{bi('原始 p', 'Raw p')}</th>
                      {isOnlineMethod ? (
                        <th className="py-2.5 px-4 font-semibold text-right">
                          {bi('动态门槛 αₜ', 'Online αₜ')}
                        </th>
                      ) : (
                        <th className="py-2.5 px-4 font-semibold text-right">
                          {bi('校正后 p', 'Adjusted p')}
                        </th>
                      )}
                      <th className="py-2.5 px-4 font-semibold">{bi('最终结论', 'Decision')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {mtResult.results.map((r) => (
                      <tr key={r.originalIndex} className={r.reject ? 'bg-emerald-50/40' : ''}>
                        <td className="py-2 px-4 font-mono text-slate-800">{r.label}</td>
                        <td className="py-2 px-4 font-mono tabular-nums text-right">
                          {formatPValue(r.rawPValue)}
                        </td>
                        <td className="py-2 px-4 font-mono tabular-nums text-right font-semibold">
                          {isOnlineMethod
                            ? formatPValue(r.alphaThreshold ?? null)
                            : formatPValue(r.adjustedPValue)}
                        </td>
                        <td className="py-2 px-4 whitespace-nowrap">
                          {r.reject ? (
                            <span className="text-emerald-700 font-medium">
                              {bi('显著 (拒绝 H₀)', 'Reject H₀')}
                            </span>
                          ) : (
                            <span className="text-slate-500">
                              {bi('不显著 (保留 H₀)', 'Retain H₀')}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-center text-xs text-slate-500">
                {bi('点击左侧预设即可立即运行。', 'Click any preset on the left to compute.')}
              </div>
            )}
          </div>
        </div>
      )}

      {/* TOOL 2: AUTOCORRELATION-ADJUSTED N_eff MDE POWER ANALYZER */}
      {tool === 'mde' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <form
            onSubmit={runMde}
            className="lg:col-span-5 bg-white border border-slate-200 rounded-lg p-6 space-y-4"
          >
            <h2 className="text-base font-semibold text-slate-900">
              {bi('自相关校正有效样本量 (Nₑff) 功效计算器', 'Autocorrelation-Adjusted MDE (Nₑff) Calculator')}
            </h2>
            <p className="text-xs text-slate-600 leading-relaxed">
              {bi(
                '月度宏观数据拉成日频虽然看起来有 1,414 行，但每天值都几乎一样（自相关 ρ=0.90），真实独立信息远没那么多！本工具自动计算真实最小可检出效应 (MDE)。',
                'Eliminates i.i.d. power overestimation on persistent macro/credit step-functions via AR(1) Bartlett effective sample size Nₑff = n(1 − ρ)/(1 + ρ) and optional regime cap.'
              )}
            </p>

            {/* 1-Click Presets */}
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => {
                  setMdeDesign('lead_lag_ols');
                  setMdeObs('1414');
                  setMdeRho('0.90');
                  setMdeRegimes('69');
                  void runMdeDirect({
                    design: 'lead_lag_ols',
                    observations: 1414,
                    lag1Autocorr: 0.9,
                    distinctRegimeCount: 69,
                  });
                }}
                className="px-2.5 py-1 text-[11px] font-medium text-amber-800 bg-amber-50 hover:bg-amber-100 rounded border border-amber-200"
              >
                {bi('预设：月度 CPI 假样本 (n=1414, ρ=0.9)', 'Preset: Monthly CPI (n=1414, ρ=0.90)')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setMdeDesign('lead_lag_ols');
                  setMdeObs('1000');
                  setMdeRho('0.10');
                  setMdeRegimes('');
                  void runMdeDirect({
                    design: 'lead_lag_ols',
                    observations: 1000,
                    lag1Autocorr: 0.1,
                    distinctRegimeCount: undefined,
                  });
                }}
                className="px-2.5 py-1 text-[11px] font-medium text-emerald-800 bg-emerald-50 hover:bg-emerald-100 rounded border border-emerald-200"
              >
                {bi('预设：高频低自相关信号 (ρ=0.1)', 'Preset: Clean Fast Signal (ρ=0.10)')}
              </button>
            </div>

            <div>
              <label htmlFor="mde-design" className="block text-xs font-medium text-slate-700 mb-1">
                {bi('研究统计设计', 'Study Design')}
              </label>
              <select
                id="mde-design"
                value={mdeDesign}
                onChange={(e) =>
                  setMdeDesign(
                    e.target.value as 'lead_lag_ols' | 'event_study_car' | 'cohens_d' | 'mean_ratio',
                  )
                }
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white"
              >
                <option value="lead_lag_ols">
                  {bi('领先-滞后回归偏 R² (支持 Nₑff 校正)', 'Lead-Lag OLS Partial R² (Nₑff adjusted)')}
                </option>
                <option value="event_study_car">
                  {bi('事件研究累计异常收益 CAR (支持 Nₑff)', 'Event-Study Standardized Mean CAR (Nₑff)')}
                </option>
                <option value="cohens_d">
                  {bi('双组均值对比 (Cohen’s d)', "Two-Group Mean Comparison (Cohen's d)")}
                </option>
                <option value="mean_ratio">
                  {bi('窗口 / 基准均值倍率', 'Window / Baseline Mean Ratio')}
                </option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="mde-obs" className="block text-xs font-medium text-slate-700 mb-1">
                  {mdeDesign === 'cohens_d'
                    ? bi('实验窗口样本量 (n₁)', 'Window Group (n₁)')
                    : bi('原始数据行数 (n)', 'Raw Observations (n)')}
                </label>
                <input
                  id="mde-obs"
                  type="number"
                  min="1"
                  value={mdeObs}
                  onChange={(e) => setMdeObs(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>

              {mdeDesign === 'cohens_d' && (
                <div>
                  <label htmlFor="mde-g2" className="block text-xs font-medium text-slate-700 mb-1">
                    {bi('对照基准样本量 (n₂)', 'Baseline Group (n₂)')}
                  </label>
                  <input
                    id="mde-g2"
                    type="number"
                    min="1"
                    value={mdeGroup2}
                    onChange={(e) => setMdeGroup2(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                  />
                </div>
              )}

              <div>
                <label htmlFor="mde-alpha" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('显著性水平 α', 'Alpha (α)')}
                </label>
                <input
                  id="mde-alpha"
                  type="number"
                  step="0.01"
                  value={mdeAlpha}
                  onChange={(e) => setMdeAlpha(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>

              <div>
                <label htmlFor="mde-power" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('统计功效 (1 − β)', 'Power (1 − β)')}
                </label>
                <input
                  id="mde-power"
                  type="number"
                  step="0.05"
                  value={mdePower}
                  onChange={(e) => setMdePower(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>

              {(mdeDesign === 'lead_lag_ols' || mdeDesign === 'event_study_car') && (
                <div>
                  <label htmlFor="mde-rho" className="block text-xs font-medium text-slate-700 mb-1">
                    {bi('一阶自相关系数 ρ', 'AR(1) Persistence (ρ)')}
                  </label>
                  <input
                    id="mde-rho"
                    type="number"
                    step="0.05"
                    min="-0.95"
                    max="0.98"
                    value={mdeRho}
                    onChange={(e) => setMdeRho(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                  />
                </div>
              )}

              {mdeDesign === 'lead_lag_ols' && (
                <div>
                  <label
                    htmlFor="mde-regimes"
                    className="block text-xs font-medium text-slate-700 mb-1"
                  >
                    {bi('独立发布次数上限', 'Distinct Releases Cap')}
                  </label>
                  <input
                    id="mde-regimes"
                    type="number"
                    min="1"
                    placeholder={bi('可选（如 69 次 CPI）', 'Optional (e.g. 69 CPI)')}
                    value={mdeRegimes}
                    onChange={(e) => setMdeRegimes(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                  />
                </div>
              )}
            </div>

            {mdeDesign === 'event_study_car' && (
              <label className="flex items-center gap-2 text-xs text-slate-700">
                <input
                  type="checkbox"
                  checked={mdeOneSided}
                  onChange={(e) => setMdeOneSided(e.target.checked)}
                />
                {bi('单侧方向性检验（对应 FOMC 事件研究）', 'One-sided directional test (FOMC CAR)')}
              </label>
            )}

            {mdeDesign === 'mean_ratio' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="mde-base" className="block text-xs font-medium text-slate-700 mb-1">
                    {bi('基准均值', 'Baseline Mean')}
                  </label>
                  <input
                    id="mde-base"
                    type="number"
                    step="0.001"
                    value={mdeBaseMean}
                    onChange={(e) => setMdeBaseMean(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                  />
                </div>
                <div>
                  <label htmlFor="mde-se" className="block text-xs font-medium text-slate-700 mb-1">
                    {bi('差值标准误', 'SE of Difference')}
                  </label>
                  <input
                    id="mde-se"
                    type="number"
                    step="0.0001"
                    value={mdeStdErr}
                    onChange={(e) => setMdeStdErr(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                  />
                </div>
              </div>
            )}

            {mdeError && <p className="text-xs text-rose-700">{mdeError}</p>}

            <button
              type="submit"
              className="px-4 py-2 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md transition-colors"
            >
              {bi('计算真实 Nₑff 检测下限', 'Compute Nₑff Adjusted MDE')}
            </button>
          </form>

          <div className="lg:col-span-7 bg-white border border-slate-200 rounded-lg p-6">
            <h3 className="text-sm font-semibold text-slate-900 mb-4">
              {bi('真实可检出下限 vs. 传统独立同分布假象', 'Effective Detection Limit vs. Naive i.i.d. Assumption')}
            </h3>
            {mdeResult ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pb-4 border-b border-slate-200">
                  <div>
                    <div className="text-xs text-slate-500">
                      {bi('真实最小可检出效应', 'Adjusted MDE (True Floor)')}
                    </div>
                    <div className="text-2xl font-bold font-mono tabular-nums text-blue-700 mt-1">
                      {formatNumber(mdeResult.minimumDetectableEffect, 6)}
                    </div>
                    <div className="text-[11px] font-mono text-slate-500 mt-0.5">
                      {mdeResult.effectMeasure}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">
                      {bi('传统 i.i.d. 虚低门槛', 'Naive i.i.d. MDE')}
                    </div>
                    <div className="text-xl font-semibold font-mono tabular-nums text-slate-500 mt-1">
                      {formatNumber(mdeResult.naiveMde ?? mdeResult.minimumDetectableEffect, 6)}
                    </div>
                    <div className="text-[11px] font-mono text-amber-700 mt-0.5">
                      {mdeResult.inflationFactor
                        ? bi(
                            `真实门槛飙升 ${mdeResult.inflationFactor.toFixed(1)}×`,
                            `${mdeResult.inflationFactor.toFixed(1)}× floor inflation`
                          )
                        : bi('无序列自相关惩罚', 'No serial penalty')}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">
                      {bi('缩水后有效样本量 Nₑff', 'Effective Sample Size (Nₑff)')}
                    </div>
                    <div className="text-xl font-semibold font-mono tabular-nums text-slate-900 mt-1">
                      {(mdeResult.effectiveSampleSize ?? mdeResult.sampleSize).toLocaleString('en-US')}
                    </div>
                    <div className="text-[11px] font-mono text-slate-500 mt-0.5">
                      {bi(
                        `原始共 ${mdeResult.sampleSize.toLocaleString('en-US')} 行`,
                        `of ${mdeResult.sampleSize.toLocaleString('en-US')} raw rows`
                      )}
                    </div>
                  </div>
                </div>
                <div className="p-3.5 bg-blue-50/50 border border-blue-200 rounded-md text-xs text-slate-800 leading-relaxed">
                  <span className="font-semibold text-blue-950">
                    {bi('大白话解读：', 'Plain-Language Takeaway: ')}
                  </span>
                  {bi(
                    `表面上有 ${mdeResult.sampleSize.toLocaleString('en-US')} 行数据，但扣除序列重复（自相关）后，真正独立的样本只剩 ${(mdeResult.effectiveSampleSize ?? mdeResult.sampleSize).toLocaleString('en-US')} 个！任何低于 ${formatNumber(mdeResult.minimumDetectableEffect, 5)} 的所谓「显著效应」，大概率都是样本量不够带来的赢家诅咒幻觉。`,
                    `Accounting for serial persistence collapses effective degrees of freedom from ${mdeResult.sampleSize.toLocaleString('en-US')} to ${(mdeResult.effectiveSampleSize ?? mdeResult.sampleSize).toLocaleString('en-US')}. Any claimed significant effect below ${formatNumber(mdeResult.minimumDetectableEffect, 5)} carries severe winner's-curse inflation risk.`
                  )}
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-500">
                {bi('请选择左侧预设并运行计算。', 'Select a study design and compute.')}
              </p>
            )}
          </div>
        </div>
      )}

      {/* TOOL 3: UNBOUNDED SQUARE-ROOT EXECUTION COSTS */}
      {tool === 'costs' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <form
            onSubmit={runCosts}
            className="lg:col-span-5 bg-white border border-slate-200 rounded-lg p-6 space-y-4"
          >
            <div>
              <h2 className="text-base font-semibold text-slate-900">
                {bi('无上限平方根成本门控与精准资金费率', 'Unbounded Square-Root & Fail-Closed Cost Gate')}
              </h2>
              <p className="text-xs text-slate-600 mt-1">
                {bi(
                  '彻底修复旧代码「大单滑点封死 5 bps」「缺盘口深度按 0 算」以及「持仓半小时跨过 08:00 却漏算资金费率」三大隐形亏钱坑。',
                  'Eliminates the legacy 5 bps impact cap and missing-depth = 0 bug, plus exact UTC 00/08/16 funding boundary crossings.'
                )}
              </p>
            </div>

            {/* 1-Click Presets */}
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => {
                  setCostQty('500');
                  setCostDepth('120');
                  setCostHoldHours('0.5');
                  setCostEntryIso('2026-11-18T07:45:00Z');
                  void runCostsDirect({
                    quantityContracts: 500,
                    orderBookDepthContracts: 120,
                    holdingHours: 0.5,
                    entryTimestampIso: '2026-11-18T07:45:00Z',
                  });
                }}
                className="px-2.5 py-1 text-[11px] font-medium text-rose-800 bg-rose-50 hover:bg-rose-100 rounded border border-rose-200"
              >
                {bi('预设：500 张大单打穿 120 张盘口', 'Preset: 500 cts vs 120 Depth')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setCostQty('250');
                  setCostDepth('');
                  setCostHoldHours('0.5');
                  setCostEntryIso('2026-11-18T07:45:00Z');
                  void runCostsDirect({
                    quantityContracts: 250,
                    orderBookDepthContracts: null,
                    holdingHours: 0.5,
                    entryTimestampIso: '2026-11-18T07:45:00Z',
                  });
                }}
                className="px-2.5 py-1 text-[11px] font-medium text-amber-800 bg-amber-50 hover:bg-amber-100 rounded border border-amber-200"
              >
                {bi('预设：盘口深度缺失 (Fail-Closed 惩罚)', 'Preset: Missing Depth (Fail-Closed)')}
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="cost-price" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('参考价 (USDT)', 'Ref Price (USDT)')}
                </label>
                <input
                  id="cost-price"
                  type="number"
                  value={costPrice}
                  onChange={(e) => setCostPrice(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="cost-qty" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('下单张数 (0.01 BTC/张)', 'Contracts (0.01 BTC ea)')}
                </label>
                <input
                  id="cost-qty"
                  type="number"
                  value={costQty}
                  onChange={(e) => setCostQty(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="cost-side" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('交易方向', 'Position Side')}
                </label>
                <select
                  id="cost-side"
                  value={costSide}
                  onChange={(e) => setCostSide(e.target.value as 'buy' | 'sell')}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white"
                >
                  <option value="buy">{bi('做多 (买入)', 'Long (Buy)')}</option>
                  <option value="sell">{bi('做空 (卖出)', 'Short (Sell)')}</option>
                </select>
              </div>
              <div>
                <label htmlFor="cost-role" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('吃单 / 挂单角色', 'Execution Role')}
                </label>
                <select
                  id="cost-role"
                  value={costRole}
                  onChange={(e) => setCostRole(e.target.value as 'taker' | 'maker')}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white"
                >
                  <option value="taker">{bi('市价吃单 Taker (5 bps)', 'Taker (5 bps)')}</option>
                  <option value="maker">{bi('限价挂单 Maker (2 bps)', 'Resting Maker (2 bps)')}</option>
                </select>
              </div>
              <div>
                <label htmlFor="cost-spread" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('买卖点差 (bps)', 'Bid-Ask Spread (bps)')}
                </label>
                <input
                  id="cost-spread"
                  type="number"
                  step="0.1"
                  value={costSpread}
                  onChange={(e) => setCostSpread(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="cost-slippage" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('单边基础滑点 (bps)', 'Slippage (bps/leg)')}
                </label>
                <input
                  id="cost-slippage"
                  type="number"
                  step="0.1"
                  value={costSlippage}
                  onChange={(e) => setCostSlippage(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="cost-impact" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('冲击系数 (bps)', 'Sweep Coeff (bps)')}
                </label>
                <input
                  id="cost-impact"
                  type="number"
                  step="0.5"
                  value={costImpactCoeff}
                  onChange={(e) => setCostImpactCoeff(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="cost-depth" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('前 5 档深度 (留空=保守惩罚)', 'Top-5 Depth (blank=penalty)')}
                </label>
                <input
                  id="cost-depth"
                  type="number"
                  placeholder={bi('缺失时触发 Fail-Closed', 'Missing -> Penalty')}
                  value={costDepth}
                  onChange={(e) => setCostDepth(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="cost-vol" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('日波动率 (bps)', 'Daily Vol (bps)')}
                </label>
                <input
                  id="cost-vol"
                  type="number"
                  value={costDailyVol}
                  onChange={(e) => setCostDailyVol(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="cost-adv" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('日均成交量 ADV (张)', 'ADV (contracts)')}
                </label>
                <input
                  id="cost-adv"
                  type="number"
                  value={costAdv}
                  onChange={(e) => setCostAdv(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="cost-hold" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('持仓时长 (小时)', 'Holding Horizon (hrs)')}
                </label>
                <input
                  id="cost-hold"
                  type="number"
                  step="0.25"
                  value={costHoldHours}
                  onChange={(e) => setCostHoldHours(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="cost-funding" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('8h 资金费率 (bps)', 'Funding (bps/8h)')}
                </label>
                <input
                  id="cost-funding"
                  type="number"
                  step="0.1"
                  value={costFundingBps}
                  onChange={(e) => setCostFundingBps(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
            </div>

            <div>
              <label htmlFor="cost-entry" className="block text-xs font-medium text-slate-700 mb-1">
                {bi('精确 UTC 开仓时间（自动捕获 00/08/16 整点结算）', 'Exact UTC Entry Timestamp (00/08/16 crossings)')}
              </label>
              <input
                id="cost-entry"
                type="text"
                value={costEntryIso}
                onChange={(e) => setCostEntryIso(e.target.value)}
                className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
              />
            </div>

            <label className="flex items-center gap-2 text-xs text-slate-700">
              <input
                type="checkbox"
                checked={costRoundTrip}
                onChange={(e) => setCostRoundTrip(e.target.checked)}
              />
              {bi('按双边完整来回计费（开仓 + 平仓）', 'Round-trip trade (entry + exit leg)')}
            </label>

            {costError && <p className="text-xs text-rose-700">{costError}</p>}

            <button
              type="submit"
              className="px-4 py-2 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md transition-colors"
            >
              {bi('计算真实冲击与资金成本', 'Simulate Square-Root Cost Gate')}
            </button>
          </form>

          <div className="lg:col-span-7 bg-white border border-slate-200 rounded-lg p-6">
            <h3 className="text-sm font-semibold text-slate-900 mb-4">
              {bi('交易成本拆解与旧上限漏洞审计', 'Cost Gate & Legacy Cap Audit Breakdown')}
            </h3>
            {costResult ? (
              <div className="space-y-4">
                {costResult.failClosedPenaltyApplied && (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-md text-xs text-amber-900">
                    {bi(
                      `已触发 Fail-Closed 缺深度保守惩罚：盘口深度为空/零，系统拒绝按 0 bps 虚报，强制施加基于波动率的保守冲击底线 ${costResult.impactBps.toFixed(2)} bps。`,
                      `Fail-Closed Missing-Depth Penalty Active: L2 depth was null/zero. A conservative volatility-scaled impact floor (${costResult.impactBps.toFixed(2)} bps) was enforced.`
                    )}
                  </div>
                )}

                <div className="grid grid-cols-3 gap-4 pb-4 border-b border-slate-200">
                  <div>
                    <div className="text-xs text-slate-500">{bi('名义本金', 'Notional Value')}</div>
                    <div className="text-lg font-bold font-mono tabular-nums text-slate-900 mt-1">
                      ${costResult.notionalUsdt.toLocaleString('en-US', { maximumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">{bi('总交易磨损 (bps)', 'Total Cost (bps)')}</div>
                    <div className="text-lg font-bold font-mono tabular-nums text-rose-700 mt-1">
                      {costResult.totalBps.toFixed(2)} bps
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">{bi('实付摩擦金额', 'Total Cost (USDT)')}</div>
                    <div className="text-lg font-bold font-mono tabular-nums text-slate-900 mt-1">
                      ${costResult.totalUsdt.toFixed(2)}
                    </div>
                  </div>
                </div>

                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-600">
                      <th className="py-2 font-semibold">{bi('成本分项', 'Component')}</th>
                      <th className="py-2 font-semibold text-right">{bi('基点 (bps)', 'Basis Points')}</th>
                      <th className="py-2 font-semibold text-right">USDT</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono tabular-nums">
                    <tr>
                      <td className="py-2 font-sans text-slate-700">{bi('交易所手续费', 'Exchange Fee')}</td>
                      <td className="py-2 text-right">{costResult.feeBps.toFixed(2)}</td>
                      <td className="py-2 text-right">${costResult.feeUsdt.toFixed(2)}</td>
                    </tr>
                    <tr>
                      <td className="py-2 font-sans text-slate-700">{bi('跨点差成本', 'Half-Spread Crossing')}</td>
                      <td className="py-2 text-right">{costResult.spreadCrossBps.toFixed(2)}</td>
                      <td className="py-2 text-right">${costResult.spreadCrossUsdt.toFixed(2)}</td>
                    </tr>
                    <tr>
                      <td className="py-2 font-sans text-slate-700">{bi('基础市场滑点', 'Market Slippage')}</td>
                      <td className="py-2 text-right">{costResult.slippageBps.toFixed(2)}</td>
                      <td className="py-2 text-right">${costResult.slippageUsdt.toFixed(2)}</td>
                    </tr>
                    <tr>
                      <td className="py-2 font-sans text-slate-700">
                        {bi('无上限平方根冲击', 'Convex Square-Root Impact')}
                        {costResult.legacyCappedImpactBps !== null && (
                          <span className="text-slate-400 ml-1">
                            ({bi('旧版假封顶', 'Legacy cap')}: {costResult.legacyCappedImpactBps.toFixed(2)} bps)
                          </span>
                        )}
                      </td>
                      <td className="py-2 text-right font-semibold text-rose-700">
                        {costResult.impactBps.toFixed(2)}
                      </td>
                      <td className="py-2 text-right font-semibold text-rose-700">
                        ${costResult.impactUsdt.toFixed(2)}
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2 font-sans text-slate-700">
                        {bi('永续资金费率', 'Funding')} ({costResult.fundingIntervalsCrossed}{' '}
                        {bi('次整点结算', 'crossings')} ·{' '}
                        {costResult.fundingExactTimestampUsed
                          ? bi('精确 UTC 时间戳', 'exact UTC')
                          : bi('按时长整除', 'duration floor')}
                        )
                      </td>
                      <td className="py-2 text-right">{costResult.fundingBps.toFixed(2)}</td>
                      <td className="py-2 text-right">${costResult.fundingUsdt.toFixed(2)}</td>
                    </tr>
                  </tbody>
                </table>

                <div className="p-3.5 bg-blue-50/50 border border-blue-200 rounded-md text-xs text-slate-800 leading-relaxed">
                  <span className="font-semibold text-blue-950">
                    {bi('大白话解读：', 'Plain-Language Takeaway: ')}
                  </span>
                  {bi(
                    `这笔名义价值 $${costResult.notionalUsdt.toLocaleString('en-US', { maximumFractionDigits: 0 })} 的单子，来回一趟真实摩擦高达 ${costResult.totalBps.toFixed(2)} bps（$${costResult.totalUsdt.toFixed(2)}）。你的策略单笔预期收益必须稳稳高于 ${costResult.totalBps.toFixed(2)} bps 才有可能真正赚到钱！`,
                    `A $${costResult.notionalUsdt.toLocaleString('en-US', { maximumFractionDigits: 0 })} notional position costs ${costResult.totalBps.toFixed(2)} bps ($${costResult.totalUsdt.toFixed(2)}) in true friction. Any alpha edge smaller than ${costResult.totalBps.toFixed(2)} bps per trade loses money live.`
                  )}
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-500">
                {bi('点击左侧运行模拟。', 'Run the simulator to inspect costs.')}
              </p>
            )}
          </div>
        </div>
      )}

      {/* TOOL 4: HARDENED PIT LEAD-LAG QR-HAC LAB */}
      {tool === 'lead_lag' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <form
            onSubmit={runLeadLag}
            className="lg:col-span-5 bg-white border border-slate-200 rounded-lg p-6 space-y-4"
          >
            <h2 className="text-base font-semibold text-slate-900">
              {bi('防偷看未来 Householder QR + Andrews HAC 实验室', 'PIT-Safe Householder QR + Andrews HAC Lab')}
            </h2>
            <p className="text-xs text-slate-600 leading-relaxed">
              {bi(
                '用严格滞后控制变量、Householder QR 正交分解、Andrews 自动滞后带宽、精确 Student-t 分布与循环块自助法，彻底消除同期因子未来函数泄露。',
                'Replaces contemporaneous factor conditioning and Gauss-Jordan inversion with strictly lagged PIT controls, Householder QR, Andrews (1991) automatic HAC bandwidth, exact Student-t p-values, and Circular Block-Bootstrap CIs.'
              )}
            </p>

            {/* 1-Click Presets */}
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => {
                  setLlScenario('source_leads_target');
                  setLlFactorTiming('pit_lagged');
                  setLlBeta('0.18');
                  setLlFactor('1.40');
                  void runLeadLagDirect({
                    scenario: 'source_leads_target',
                    factorTiming: 'pit_lagged',
                    beta: 0.18,
                    commonFactorLoading: 1.4,
                  });
                }}
                className="px-2.5 py-1 text-[11px] font-medium text-amber-800 bg-amber-50 hover:bg-amber-100 rounded border border-amber-200"
              >
                {bi('揭穿「同期因子偷看未来」漏洞', 'Expose Lookahead Leak')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setLlScenario('common_factor');
                  setLlFactorTiming('pit_lagged');
                  setLlFactor('1.40');
                  void runLeadLagDirect({
                    scenario: 'common_factor',
                    factorTiming: 'pit_lagged',
                    commonFactorLoading: 1.4,
                  });
                }}
                className="px-2.5 py-1 text-[11px] font-medium text-emerald-800 bg-emerald-50 hover:bg-emerald-100 rounded border border-emerald-200"
              >
                {bi('纯大盘混淆（无真实传导）', 'Confounder Only (Null)')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setLlScenario('heavy_tail_garch');
                  setLlFactorTiming('pit_lagged');
                  void runLeadLagDirect({
                    scenario: 'heavy_tail_garch',
                    factorTiming: 'pit_lagged',
                  });
                }}
                className="px-2.5 py-1 text-[11px] font-medium text-blue-800 bg-blue-50 hover:bg-blue-100 rounded border border-blue-200"
              >
                {bi('暴涨暴跌厚尾 GARCH 检验', 'Heavy-Tail GARCH Stress')}
              </button>
            </div>

            <div>
              <label htmlFor="ll-scenario" className="block text-xs font-medium text-slate-700 mb-1">
                {bi('数据生成场景', 'Data-Generating Scenario')}
              </label>
              <select
                id="ll-scenario"
                value={llScenario}
                onChange={(e) => setLlScenario(e.target.value as SyntheticScenario)}
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white"
              >
                <option value="common_factor">
                  {bi('共同大盘混淆因子（其实没有因果领先）', 'Common Factor Confounder (no causal lag)')}
                </option>
                <option value="source_leads_target">
                  {bi('真实领先滞后传导（存在真实 β）', 'Source Leads Target (true β)')}
                </option>
                <option value="heavy_tail_garch">
                  {bi('高波动聚集厚尾 GARCH(1,1)', 'Heavy-Tail GARCH(1,1) Vol Clustering')}
                </option>
                <option value="regime_shift">
                  {bi('结构切换（仅前半段有效、后半段失效）', 'Regime Shift (active first half only)')}
                </option>
                <option value="null">
                  {bi('纯独立白噪声（检验是否乱报警）', 'Null (independent white noise)')}
                </option>
              </select>
            </div>

            <div>
              <label htmlFor="ll-timing" className="block text-xs font-medium text-slate-700 mb-1">
                {bi('共同因子控制变量时间对齐方式', 'Common-Factor Conditioning Timing')}
              </label>
              <select
                id="ll-timing"
                value={llFactorTiming}
                onChange={(e) => setLlFactorTiming(e.target.value as FactorTimingMode)}
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white"
              >
                <option value="pit_lagged">
                  {bi('严格 PIT 滞后 factor[t − lag]（防穿越安全）', 'Strict PIT-Lagged factor[t − lag] (Safe)')}
                </option>
                <option value="legacy_contemporaneous_leak">
                  {bi('旧版同期 factor[t]（故意演示未来函数泄露）', 'Legacy Contemporaneous factor[t] (Lookahead Audit)')}
                </option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="ll-obs" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('样本量', 'Observations')}
                </label>
                <input
                  id="ll-obs"
                  type="number"
                  min="100"
                  max="5000"
                  value={llObs}
                  onChange={(e) => setLlObs(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="ll-beta" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('真实传导强度 β', 'True β (lead effect)')}
                </label>
                <input
                  id="ll-beta"
                  type="number"
                  step="0.02"
                  value={llBeta}
                  onChange={(e) => setLlBeta(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="ll-factor" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('共同因子载荷', 'Factor Loading')}
                </label>
                <input
                  id="ll-factor"
                  type="number"
                  step="0.1"
                  value={llFactor}
                  onChange={(e) => setLlFactor(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="ll-hac" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('手动 HAC 滞后阶', 'Manual HAC Lag')}
                </label>
                <input
                  id="ll-hac"
                  type="number"
                  min="0"
                  max="20"
                  disabled={llAutoBw}
                  value={llHacLag}
                  onChange={(e) => setLlHacLag(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md disabled:bg-slate-100"
                />
              </div>
              <div>
                <label htmlFor="ll-lag" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('领先滞后步长', 'Lag Steps')}
                </label>
                <input
                  id="ll-lag"
                  type="number"
                  min="1"
                  max="10"
                  value={llLag}
                  onChange={(e) => setLlLag(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="ll-seed" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('随机种子', 'Deterministic Seed')}
                </label>
                <input
                  id="ll-seed"
                  type="number"
                  value={llSeed}
                  onChange={(e) => setLlSeed(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="flex items-center gap-2 text-xs text-slate-700">
                <input
                  type="checkbox"
                  checked={llControlFactor}
                  onChange={(e) => setLlControlFactor(e.target.checked)}
                />
                {bi('加入共同因子控制并对比 PIT vs. 偷看未来差异', 'Include common-factor control + PIT vs. Leak audit diff')}
              </label>
              <label className="flex items-center gap-2 text-xs text-slate-700">
                <input
                  type="checkbox"
                  checked={llAutoBw}
                  onChange={(e) => setLlAutoBw(e.target.checked)}
                />
                {bi('启用 Andrews (1991) 自适应 HAC 带宽', 'Andrews (1991) automatic AR(1) Bartlett HAC bandwidth')}
              </label>
            </div>

            {llError && <p className="text-xs text-rose-700">{llError}</p>}

            <button
              type="submit"
              className="px-4 py-2 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md transition-colors"
            >
              {bi('运行 Householder QR-HAC 检验', 'Run Householder QR-HAC Simulation')}
            </button>
          </form>

          <div className="lg:col-span-7 bg-white border border-slate-200 rounded-lg p-6 space-y-5">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-slate-900">
                {bi('小样本精确 QR-HAC 与块自助法估计结果', 'Finite-Sample QR-HAC & Block-Bootstrap Estimates')}
              </h3>
              {llResult && (
                <span className="text-xs font-mono text-slate-500">
                  κ(R) = {llResult.conditionNumber.toFixed(2)} · lag = {llResult.maxHacLag} (
                  {llResult.bandwidthMode === 'andrews_auto' ? 'Andrews' : 'Manual'})
                </span>
              )}
            </div>

            {llResult ? (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pb-4 border-b border-slate-200 text-xs">
                  <div>
                    <div className="text-slate-500">{bi('回归估计值 β̂', 'Estimated β̂')}</div>
                    <div className="text-lg font-bold font-mono tabular-nums text-slate-900 mt-0.5">
                      {llResult.coefficient.toFixed(4)}
                    </div>
                    <div className="font-mono text-slate-500">
                      HAC SE {llResult.standardError.toFixed(4)}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">
                      {bi(`Student-t 检验 (df=${llResult.degreesOfFreedom})`, `Student-t p-Value (df=${llResult.degreesOfFreedom})`)}
                    </div>
                    <div className="text-lg font-bold font-mono tabular-nums text-slate-900 mt-0.5">
                      t = {llResult.tStatistic.toFixed(2)}
                    </div>
                    <div
                      className={`font-mono ${
                        llResult.pValue < 0.05 ? 'text-emerald-700 font-medium' : 'text-slate-500'
                      }`}
                    >
                      p = {formatPValue(llResult.pValue)}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">{bi('偏 R² / 有效样本 Nₑff', 'Partial R² / Nₑff')}</div>
                    <div className="text-lg font-bold font-mono tabular-nums text-blue-700 mt-0.5">
                      {llResult.partialRSquared.toFixed(5)}
                    </div>
                    <div className="font-mono text-slate-500">
                      Nₑff = {llResult.effectiveSampleSize} / {llResult.observations}
                    </div>
                  </div>
                </div>

                {/* Circular Block-Bootstrap CI & PIT Lookahead Diff */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-md">
                    <div className="text-slate-500 font-medium">
                      {bi('循环块自助法 95% 置信区间', 'Circular Block-Bootstrap 95% CI')}
                    </div>
                    <div className="font-mono tabular-nums font-semibold text-slate-900 mt-1">
                      [{llResult.bootstrapCiLower.toFixed(4)}, {llResult.bootstrapCiUpper.toFixed(4)}]
                    </div>
                    <div className="font-mono text-[11px] text-slate-500 mt-0.5">
                      Boot p = {formatPValue(llResult.bootstrapPValue)} · ρ₁(e) ={' '}
                      {llResult.residualLag1Autocorr.toFixed(3)}
                    </div>
                  </div>

                  {llResult.lookaheadComparison && (
                    <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-md">
                      <div className="text-amber-900 font-medium">
                        {bi('防穿越 PIT vs. 偷看未来漏洞对比', 'PIT vs. Legacy Contemporaneous Leak Audit')}
                      </div>
                      <div className="font-mono tabular-nums text-amber-950 font-semibold mt-1">
                        PIT R² {llResult.lookaheadComparison.pitPartialRSquared.toFixed(4)} vs{' '}
                        {bi('偷看版', 'Leak')} {llResult.lookaheadComparison.leakedPartialRSquared.toFixed(4)}
                      </div>
                      <div className="font-mono text-[11px] text-amber-800 mt-0.5">
                        {bi('未来函数虚高倍数：', 'Leak inflation: ')}
                        {Number.isFinite(llResult.lookaheadComparison.partialRSquaredInflationRatio)
                          ? `${llResult.lookaheadComparison.partialRSquaredInflationRatio.toFixed(2)}×`
                          : '∞'}
                      </div>
                    </div>
                  )}
                </div>

                <div className="p-3.5 bg-blue-50/50 border border-blue-200 rounded-md text-xs text-slate-800 leading-relaxed">
                  <span className="font-semibold text-blue-950">
                    {bi('大白话解读：', 'Plain-Language Takeaway: ')}
                  </span>
                  {llResult.pValue < 0.05
                    ? bi(
                        `在严格防穿越控制下，领先效应仍然显著（p = ${formatPValue(llResult.pValue)}，自助法 95% 区间 [${llResult.bootstrapCiLower.toFixed(3)}, ${llResult.bootstrapCiUpper.toFixed(3)}]），矩阵条件数 κ(R) = ${llResult.conditionNumber.toFixed(2)} 非常健康，具备进一步测试交易成本的价值。`,
                        `Under strict PIT conditioning, the lead-lag signal remains significant (p = ${formatPValue(llResult.pValue)}, bootstrap 95% CI [${llResult.bootstrapCiLower.toFixed(3)}, ${llResult.bootstrapCiUpper.toFixed(3)}]) with healthy condition number κ(R) = ${llResult.conditionNumber.toFixed(2)}.`
                      )
                    : bi(
                        `在严格防穿越控制下，该信号并不显著（p = ${formatPValue(llResult.pValue)}），成功挡住了虚假关联！右上方黄色框展示了如果不小心用了旧版「同期控制因子」，偏 R² 会被未来信息凭空夸大。`,
                        `Under strict PIT conditioning, no spurious lead-lag signal passes (p = ${formatPValue(llResult.pValue)}). The amber audit card shows how legacy contemporaneous conditioning leaks future variance.`
                      )}
                </div>

                {/* Lightweight SVG Scatter Plot */}
                <div>
                  <div className="text-xs text-slate-500 mb-2">
                    {bi(
                      `滞后源信号 (x) vs. 目标资产收益 (y) — 抽样 ${llResult.samplePoints.length} 个观测点`,
                      `Lagged Source (x) vs. Target Return (y) — ${llResult.samplePoints.length} sampled observations`
                    )}
                  </div>
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-2">
                    <svg
                      viewBox="0 0 520 200"
                      className="w-full h-auto"
                      role="img"
                      aria-label="Scatter plot of lagged source versus target return"
                    >
                      <line x1="20" y1="100" x2="500" y2="100" stroke="#CBD5E1" strokeWidth="1" />
                      <line x1="260" y1="12" x2="260" y2="188" stroke="#CBD5E1" strokeWidth="1" />
                      {llResult.samplePoints.map((pt, idx) => {
                        const cx = Math.max(22, Math.min(498, 260 + pt.x * 55));
                        const cy = Math.max(14, Math.min(186, 100 - pt.y * 22));
                        return (
                          <circle
                            key={idx}
                            cx={cx}
                            cy={cy}
                            r="2.6"
                            fill="#1D4ED8"
                            opacity="0.55"
                          />
                        );
                      })}
                    </svg>
                  </div>
                </div>
              </>
            ) : (
              <p className="text-xs text-slate-500">
                {bi('点击左侧预设开始模拟。', 'Run a deterministic simulation to view estimates.')}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
