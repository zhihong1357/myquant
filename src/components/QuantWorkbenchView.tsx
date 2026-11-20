import React, { useState } from 'react';
import { formatNumber, formatPValue } from '../lib/format';
import type { MultiplicityMethod } from '../lib/quant/multipleTesting';
import type { MinimumDetectableEffect } from '../lib/quant/power';
import type { PaperExecutionCostBreakdown } from '../lib/quant/executionCosts';
import type { LeadLagResult, SyntheticScenario } from '../lib/quant/leadLag';

interface MultiplicityResponse {
  method: MultiplicityMethod;
  alpha: number;
  familySize: number;
  rejections: number;
  results: Array<{
    originalIndex: number;
    label: string;
    rawPValue: number;
    adjustedPValue: number;
    reject: boolean;
  }>;
}

export const QuantWorkbenchView: React.FC = () => {
  const [tool, setTool] = useState<'multiplicity' | 'mde' | 'costs' | 'leadlag'>('multiplicity');

  // Tool 1: Multiple testing state
  const [mtMethod, setMtMethod] = useState<MultiplicityMethod>('holm');
  const [mtAlpha, setMtAlpha] = useState('0.05');
  const [mtInput, setMtInput] = useState('0.00017, 0.00290, 0.00982, 0.03999, 0.22690, 0.71779');
  const [mtResult, setMtResult] = useState<MultiplicityResponse | null>(null);
  const [mtError, setMtError] = useState<string | null>(null);
  const [mtLoading, setMtLoading] = useState(false);

  // Tool 2: MDE Power state
  const [mdeDesign, setMdeDesign] = useState<
    'lead_lag_ols' | 'event_study_car' | 'cohens_d' | 'mean_ratio'
  >('event_study_car');
  const [mdeObs, setMdeObs] = useState('135');
  const [mdeGroup2, setMdeGroup2] = useState('2009');
  const [mdeAlpha, setMdeAlpha] = useState('0.05');
  const [mdePower, setMdePower] = useState('0.80');
  const [mdeOneSided, setMdeOneSided] = useState(true);
  const [mdeBaseMean, setMdeBaseMean] = useState('0.025');
  const [mdeStdErr, setMdeStdErr] = useState('0.0018');
  const [mdeResult, setMdeResult] = useState<MinimumDetectableEffect | null>(null);
  const [mdeError, setMdeError] = useState<string | null>(null);

  // Tool 3: Paper Execution Cost state
  const [costPrice, setCostPrice] = useState('92000');
  const [costQty, setCostQty] = useState('25');
  const [costSide, setCostSide] = useState<'buy' | 'sell'>('buy');
  const [costRole, setCostRole] = useState<'taker' | 'maker'>('taker');
  const [costSpread, setCostSpread] = useState('1.5');
  const [costSlippage, setCostSlippage] = useState('1.0');
  const [costImpactCoeff, setCostImpactCoeff] = useState('5.0');
  const [costDepth, setCostDepth] = useState('120');
  const [costHoldHours, setCostHoldHours] = useState('24');
  const [costFundingBps, setCostFundingBps] = useState('1.0');
  const [costRoundTrip, setCostRoundTrip] = useState(true);
  const [costResult, setCostResult] = useState<PaperExecutionCostBreakdown | null>(null);
  const [costError, setCostError] = useState<string | null>(null);

  // Tool 4: Synthetic Lead-Lag state
  const [llScenario, setLlScenario] = useState<SyntheticScenario>('source_leads_target');
  const [llObs, setLlObs] = useState('1000');
  const [llBeta, setLlBeta] = useState('0.18');
  const [llFactor, setLlFactor] = useState('0.80');
  const [llLag, setLlLag] = useState('1');
  const [llHacLag, setLlHacLag] = useState('5');
  const [llControlFactor, setLlControlFactor] = useState(true);
  const [llSeed, setLlSeed] = useState('2026');
  const [llResult, setLlResult] = useState<LeadLagResult | null>(null);
  const [llError, setLlError] = useState<string | null>(null);

  async function runMultipleTesting(mode: 'custom' | 'lab_family') {
    setMtError(null);
    setMtLoading(true);
    try {
      const alphaNum = Number(mtAlpha);
      const payload: Record<string, unknown> = { mode, method: mtMethod, alpha: alphaNum };
      if (mode === 'custom') {
        const parsed = mtInput
          .split(/[\s,;]+/)
          .map((s) => s.trim())
          .filter(Boolean)
          .map(Number);
        if (parsed.length === 0 || parsed.some((v) => !Number.isFinite(v) || v < 0 || v > 1)) {
          throw new Error('Enter comma-separated p-values strictly between 0 and 1.');
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

  async function runMde(e: React.FormEvent) {
    e.preventDefault();
    setMdeError(null);
    try {
      const res = await fetch('/api/tools/mde', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          design: mdeDesign,
          observations: Number(mdeObs),
          groupSize2: Number(mdeGroup2),
          alpha: Number(mdeAlpha),
          power: Number(mdePower),
          oneSided: mdeOneSided,
          meanBaseline: Number(mdeBaseMean),
          standardError: Number(mdeStdErr),
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? 'MDE calculation failed');
      setMdeResult(json as MinimumDetectableEffect);
    } catch (err) {
      setMdeError(err instanceof Error ? err.message : 'Invalid MDE parameters');
    }
  }

  async function runCosts(e: React.FormEvent) {
    e.preventDefault();
    setCostError(null);
    try {
      const res = await fetch('/api/tools/execution-cost', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          price: Number(costPrice),
          quantityContracts: Number(costQty),
          contractValue: 0.01,
          side: costSide,
          executionRole: costRole,
          spreadBps: Number(costSpread),
          marketSlippageBps: Number(costSlippage),
          impactCoefficientBps: Number(costImpactCoeff),
          orderBookDepthContracts: costDepth.trim() === '' ? null : Number(costDepth),
          holdingHours: Number(costHoldHours),
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

  async function runLeadLag(e: React.FormEvent) {
    e.preventDefault();
    setLlError(null);
    try {
      const res = await fetch('/api/tools/synthetic-lead-lag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario: llScenario,
          observations: Number(llObs),
          beta: Number(llBeta),
          commonFactorLoading: Number(llFactor),
          lagSteps: Number(llLag),
          maxHacLag: Number(llHacLag),
          controlCommonFactor: llControlFactor,
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

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Deterministic Statistical &amp; Cost Workbench
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Interactive TypeScript ports of MyQuant&apos;s multiple-testing kernel, MDE power
            formulas, synthetic Newey-West HAC estimator, and paper-only execution cost model.
          </p>
        </div>
      </div>

      {/* Tool Selector */}
      <div className="flex flex-wrap items-center gap-1 p-1 bg-slate-100 rounded-lg self-start w-fit">
        {(
          [
            { id: 'multiplicity', label: 'Multiple Testing' },
            { id: 'mde', label: 'MDE Power Analyzer' },
            { id: 'costs', label: 'Paper Execution Costs' },
            { id: 'leadlag', label: 'Synthetic Lead-Lag HAC' },
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
            {item.label}
          </button>
        ))}
      </div>

      {/* TOOL 1: MULTIPLE TESTING */}
      {tool === 'multiplicity' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <div className="lg:col-span-5 bg-white border border-slate-200 rounded-lg p-6 space-y-4">
            <h2 className="text-base font-semibold text-slate-900">
              Family-Wise &amp; FDR Multiplicity Adjustment
            </h2>
            <p className="text-xs text-slate-600 leading-relaxed">
              Apply Bonferroni, Holm step-down FWER, or Benjamini–Hochberg FDR correction to a
              predeclared testing family or directly against all 42 tested lab edges.
            </p>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="mt-method" className="block text-xs font-medium text-slate-700 mb-1">
                  Correction Method
                </label>
                <select
                  id="mt-method"
                  value={mtMethod}
                  onChange={(e) => setMtMethod(e.target.value as MultiplicityMethod)}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white"
                >
                  <option value="holm">Holm (FWER)</option>
                  <option value="benjamini_hochberg">Benjamini–Hochberg (FDR)</option>
                  <option value="bonferroni">Bonferroni (FWER)</option>
                </select>
              </div>
              <div>
                <label htmlFor="mt-alpha" className="block text-xs font-medium text-slate-700 mb-1">
                  Target α
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

            <div>
              <label htmlFor="mt-pvalues" className="block text-xs font-medium text-slate-700 mb-1">
                Custom Raw p-Values (comma-separated)
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
                onClick={() => runMultipleTesting('custom')}
                className="px-4 py-2 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md transition-colors whitespace-nowrap"
              >
                Adjust Custom Family
              </button>
              <button
                type="button"
                disabled={mtLoading}
                onClick={() => runMultipleTesting('lab_family')}
                className="px-4 py-2 text-xs font-medium text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-md transition-colors whitespace-nowrap"
              >
                Audit Real 42-Edge Lab Family
              </button>
            </div>
          </div>

          <div className="lg:col-span-7 bg-white border border-slate-200 rounded-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-900">Adjustment Output</h3>
              {mtResult && (
                <span className="text-xs font-mono tabular-nums text-slate-600">
                  {mtResult.rejections} rejected of {mtResult.familySize} (α = {mtResult.alpha})
                </span>
              )}
            </div>
            {mtResult ? (
              <div className="overflow-x-auto max-h-[460px] overflow-y-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                      <th className="py-2.5 px-4 font-semibold">Test</th>
                      <th className="py-2.5 px-4 font-semibold text-right">Raw p</th>
                      <th className="py-2.5 px-4 font-semibold text-right">Adjusted p</th>
                      <th className="py-2.5 px-4 font-semibold">Decision</th>
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
                          {formatPValue(r.adjustedPValue)}
                        </td>
                        <td className="py-2 px-4 whitespace-nowrap">
                          {r.reject ? (
                            <span className="text-emerald-700 font-medium">Reject H₀</span>
                          ) : (
                            <span className="text-slate-500">Retain H₀</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-center text-xs text-slate-500">
                Run an adjustment on custom p-values or load the real 42-edge lab family to inspect
                adjusted p-values.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TOOL 2: MDE POWER ANALYZER */}
      {tool === 'mde' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <form
            onSubmit={runMde}
            className="lg:col-span-5 bg-white border border-slate-200 rounded-lg p-6 space-y-4"
          >
            <h2 className="text-base font-semibold text-slate-900">
              Minimum Detectable Effect (MDE) Calculator
            </h2>
            <p className="text-xs text-slate-600 leading-relaxed">
              Computes the smallest true effect detectable at target power (1 − β) and significance
              level α before touching holdout data.
            </p>

            <div>
              <label htmlFor="mde-design" className="block text-xs font-medium text-slate-700 mb-1">
                Study Design
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
                <option value="event_study_car">Event-Study Standardized Mean CAR (λ / √n)</option>
                <option value="lead_lag_ols">Lead-Lag OLS Partial R² (λ² / (λ² + n))</option>
                <option value="cohens_d">Two-Group Mean Comparison (Cohen&apos;s d)</option>
                <option value="mean_ratio">Window / Baseline Mean Ratio</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="mde-obs" className="block text-xs font-medium text-slate-700 mb-1">
                  {mdeDesign === 'cohens_d' ? 'Window Group (n₁)' : 'Observations (n)'}
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
                    Baseline Group (n₂)
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
                  Alpha (α)
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
                  Power (1 − β)
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
            </div>

            {mdeDesign === 'event_study_car' && (
              <label className="flex items-center gap-2 text-xs text-slate-700">
                <input
                  type="checkbox"
                  checked={mdeOneSided}
                  onChange={(e) => setMdeOneSided(e.target.checked)}
                />
                One-sided directional test (matches FOMC CAR design)
              </label>
            )}

            {mdeDesign === 'mean_ratio' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="mde-base" className="block text-xs font-medium text-slate-700 mb-1">
                    Baseline Mean
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
                    SE of Difference
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
              Compute MDE
            </button>
          </form>

          <div className="lg:col-span-7 bg-white border border-slate-200 rounded-lg p-6">
            <h3 className="text-sm font-semibold text-slate-900 mb-4">Design Detection Limit</h3>
            {mdeResult ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pb-4 border-b border-slate-200">
                  <div>
                    <div className="text-xs text-slate-500">Minimum Detectable Effect</div>
                    <div className="text-2xl font-bold font-mono tabular-nums text-blue-700 mt-1">
                      {formatNumber(mdeResult.minimumDetectableEffect, 6)}
                    </div>
                    <div className="text-[11px] font-mono text-slate-500 mt-0.5">
                      {mdeResult.effectMeasure}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Noncentrality (λ)</div>
                    <div className="text-xl font-semibold font-mono tabular-nums text-slate-900 mt-1">
                      {mdeResult.noncentrality.toFixed(4)}
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      {mdeResult.oneSided ? 'One-sided' : 'Two-sided'}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Sample Size</div>
                    <div className="text-xl font-semibold font-mono tabular-nums text-slate-900 mt-1">
                      {mdeResult.sampleSize.toLocaleString('en-US')}
                      {mdeResult.groupSize2 ? ` / ${mdeResult.groupSize2.toLocaleString('en-US')}` : ''}
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      α = {mdeResult.alpha} · power = {mdeResult.power}
                    </div>
                  </div>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">
                  Interpretation: An observed effect smaller than{' '}
                  <span className="font-mono font-semibold text-slate-900">
                    {formatNumber(mdeResult.minimumDetectableEffect, 5)}
                  </span>{' '}
                  sits below the 80%-power detection floor of this design; a null result does not
                  rule out smaller effects, and a significant result below the MDE carries
                  winner&apos;s-curse inflation risk.
                </p>
              </div>
            ) : (
              <p className="text-xs text-slate-500">
                Select a study design and click Compute MDE to calculate its analytic detection
                limit.
              </p>
            )}
          </div>
        </div>
      )}

      {/* TOOL 3: PAPER EXECUTION COST SIMULATOR */}
      {tool === 'costs' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <form
            onSubmit={runCosts}
            className="lg:col-span-5 bg-white border border-slate-200 rounded-lg p-6 space-y-4"
          >
            <div>
              <h2 className="text-base font-semibold text-slate-900">
                Paper Execution Cost Model (OKX Perpetuals)
              </h2>
              <p className="text-xs text-slate-600 mt-1">
                Paper-only economic gate (0.01 BTC/contract, Regular tier 2 bps maker / 5 bps taker,
                linear depth impact, 8-hour UTC funding settlements).
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="cost-price" className="block text-xs font-medium text-slate-700 mb-1">
                  Ref Price (USDT)
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
                  Contracts (0.01 BTC ea)
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
                  Position Side
                </label>
                <select
                  id="cost-side"
                  value={costSide}
                  onChange={(e) => setCostSide(e.target.value as 'buy' | 'sell')}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white"
                >
                  <option value="buy">Long (Buy)</option>
                  <option value="sell">Short (Sell)</option>
                </select>
              </div>
              <div>
                <label htmlFor="cost-role" className="block text-xs font-medium text-slate-700 mb-1">
                  Execution Role
                </label>
                <select
                  id="cost-role"
                  value={costRole}
                  onChange={(e) => setCostRole(e.target.value as 'taker' | 'maker')}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white"
                >
                  <option value="taker">Taker (5 bps)</option>
                  <option value="maker">Resting Maker (2 bps)</option>
                </select>
              </div>
              <div>
                <label htmlFor="cost-spread" className="block text-xs font-medium text-slate-700 mb-1">
                  Bid-Ask Spread (bps)
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
                  Slippage (bps/leg)
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
                  Impact Coeff (bps)
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
                  Top-5 Depth (contracts)
                </label>
                <input
                  id="cost-depth"
                  type="number"
                  value={costDepth}
                  onChange={(e) => setCostDepth(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="cost-hold" className="block text-xs font-medium text-slate-700 mb-1">
                  Holding Horizon (hrs)
                </label>
                <input
                  id="cost-hold"
                  type="number"
                  value={costHoldHours}
                  onChange={(e) => setCostHoldHours(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="cost-funding" className="block text-xs font-medium text-slate-700 mb-1">
                  Funding Rate (bps/8h)
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

            <label className="flex items-center gap-2 text-xs text-slate-700">
              <input
                type="checkbox"
                checked={costRoundTrip}
                onChange={(e) => setCostRoundTrip(e.target.checked)}
              />
              Round-trip trade (entry + exit leg)
            </label>

            {costError && <p className="text-xs text-rose-700">{costError}</p>}

            <button
              type="submit"
              className="px-4 py-2 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md transition-colors"
            >
              Simulate Paper Cost Breakdown
            </button>
          </form>

          <div className="lg:col-span-7 bg-white border border-slate-200 rounded-lg p-6">
            <h3 className="text-sm font-semibold text-slate-900 mb-4">
              Cost Gate &amp; Break-Even Breakdown
            </h3>
            {costResult ? (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4 pb-4 border-b border-slate-200">
                  <div>
                    <div className="text-xs text-slate-500">Notional Value</div>
                    <div className="text-lg font-bold font-mono tabular-nums text-slate-900 mt-1">
                      ${costResult.notionalUsdt.toLocaleString('en-US', { maximumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Total Cost (bps)</div>
                    <div className="text-lg font-bold font-mono tabular-nums text-rose-700 mt-1">
                      {costResult.totalBps.toFixed(2)} bps
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-500">Total Cost (USDT)</div>
                    <div className="text-lg font-bold font-mono tabular-nums text-slate-900 mt-1">
                      ${costResult.totalUsdt.toFixed(2)}
                    </div>
                  </div>
                </div>

                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-600">
                      <th className="py-2 font-semibold">Component</th>
                      <th className="py-2 font-semibold text-right">Basis Points</th>
                      <th className="py-2 font-semibold text-right">USDT</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono tabular-nums">
                    <tr>
                      <td className="py-2 font-sans text-slate-700">Exchange Fee</td>
                      <td className="py-2 text-right">{costResult.feeBps.toFixed(2)}</td>
                      <td className="py-2 text-right">${costResult.feeUsdt.toFixed(2)}</td>
                    </tr>
                    <tr>
                      <td className="py-2 font-sans text-slate-700">Half-Spread Crossing</td>
                      <td className="py-2 text-right">{costResult.spreadCrossBps.toFixed(2)}</td>
                      <td className="py-2 text-right">${costResult.spreadCrossUsdt.toFixed(2)}</td>
                    </tr>
                    <tr>
                      <td className="py-2 font-sans text-slate-700">Market Slippage</td>
                      <td className="py-2 text-right">{costResult.slippageBps.toFixed(2)}</td>
                      <td className="py-2 text-right">${costResult.slippageUsdt.toFixed(2)}</td>
                    </tr>
                    <tr>
                      <td className="py-2 font-sans text-slate-700">Linear Depth Impact</td>
                      <td className="py-2 text-right">
                        {costResult.impactBps !== null ? costResult.impactBps.toFixed(2) : 'Unknown'}
                      </td>
                      <td className="py-2 text-right">
                        {costResult.impactUsdt !== null ? `$${costResult.impactUsdt.toFixed(2)}` : 'Flagged'}
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2 font-sans text-slate-700">
                        Funding ({costResult.fundingIntervalsCrossed} × 8h settlements)
                      </td>
                      <td className="py-2 text-right">{costResult.fundingBps.toFixed(2)}</td>
                      <td className="py-2 text-right">${costResult.fundingUsdt.toFixed(2)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-slate-500">
                Configure paper order parameters and run the simulation to inspect fee, spread,
                slippage, impact, and 8-hour funding costs.
              </p>
            )}
          </div>
        </div>
      )}

      {/* TOOL 4: SYNTHETIC LEAD-LAG HAC LAB */}
      {tool === 'leadlag' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <form
            onSubmit={runLeadLag}
            className="lg:col-span-5 bg-white border border-slate-200 rounded-lg p-6 space-y-4"
          >
            <h2 className="text-base font-semibold text-slate-900">
              Synthetic Lead-Lag &amp; Newey-West HAC Lab
            </h2>
            <p className="text-xs text-slate-600 leading-relaxed">
              Test MyQuant&apos;s partial lead-lag OLS + Bartlett HAC inference under deterministic
              null, true transmission, common-factor confounder, or regime-shift panels.
            </p>

            <div>
              <label htmlFor="ll-scenario" className="block text-xs font-medium text-slate-700 mb-1">
                Data-Generating Scenario
              </label>
              <select
                id="ll-scenario"
                value={llScenario}
                onChange={(e) => setLlScenario(e.target.value as SyntheticScenario)}
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white"
              >
                <option value="source_leads_target">Source Leads Target (true β)</option>
                <option value="null">Null (independent white noise)</option>
                <option value="common_factor">Common Factor Confounder (no causal lag)</option>
                <option value="regime_shift">Regime Shift (active first half only)</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="ll-obs" className="block text-xs font-medium text-slate-700 mb-1">
                  Observations
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
                  True β (lead effect)
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
                  Factor Loading
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
                  Max HAC Lag
                </label>
                <input
                  id="ll-hac"
                  type="number"
                  min="0"
                  max="20"
                  value={llHacLag}
                  onChange={(e) => setLlHacLag(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="ll-lag" className="block text-xs font-medium text-slate-700 mb-1">
                  Lag Steps
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
                  Deterministic Seed
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

            <label className="flex items-center gap-2 text-xs text-slate-700">
              <input
                type="checkbox"
                checked={llControlFactor}
                onChange={(e) => setLlControlFactor(e.target.checked)}
              />
              Include contemporaneous common-factor control
            </label>

            {llError && <p className="text-xs text-rose-700">{llError}</p>}

            <button
              type="submit"
              className="px-4 py-2 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md transition-colors"
            >
              Run Deterministic Simulation
            </button>
          </form>

          <div className="lg:col-span-7 bg-white border border-slate-200 rounded-lg p-6 space-y-5">
            <h3 className="text-sm font-semibold text-slate-900">
              Partial Lead-Lag HAC Estimates
            </h3>
            {llResult ? (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pb-4 border-b border-slate-200 text-xs">
                  <div>
                    <div className="text-slate-500">Estimated β̂</div>
                    <div className="text-lg font-bold font-mono tabular-nums text-slate-900 mt-0.5">
                      {llResult.coefficient.toFixed(4)}
                    </div>
                    <div className="font-mono text-slate-500">
                      HAC SE {llResult.standardError.toFixed(4)}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">HAC t-Stat / p-Value</div>
                    <div className="text-lg font-bold font-mono tabular-nums text-slate-900 mt-0.5">
                      {llResult.tStatistic.toFixed(2)}
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
                    <div className="text-slate-500">Partial R²</div>
                    <div className="text-lg font-bold font-mono tabular-nums text-blue-700 mt-0.5">
                      {llResult.partialRSquared.toFixed(5)}
                    </div>
                    <div className="font-mono text-slate-500">
                      n = {llResult.observations.toLocaleString('en-US')}
                    </div>
                  </div>
                </div>

                {/* Lightweight SVG Scatter Plot */}
                <div>
                  <div className="text-xs text-slate-500 mb-2">
                    Lagged Source (x) vs. Target Return (y) — {llResult.samplePoints.length} sampled
                    observations
                  </div>
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-2">
                    <svg
                      viewBox="0 0 520 220"
                      className="w-full h-auto"
                      role="img"
                      aria-label="Scatter plot of lagged source versus target return"
                    >
                      <line x1="20" y1="110" x2="500" y2="110" stroke="#CBD5E1" strokeWidth="1" />
                      <line x1="260" y1="15" x2="260" y2="205" stroke="#CBD5E1" strokeWidth="1" />
                      {llResult.samplePoints.map((pt, idx) => {
                        const cx = Math.max(24, Math.min(496, 260 + pt.x * 55));
                        const cy = Math.max(18, Math.min(202, 110 - pt.y * 28));
                        return (
                          <circle
                            key={idx}
                            cx={cx}
                            cy={cy}
                            r="2.4"
                            fill="#1D4ED8"
                            opacity="0.55"
                          />
                        );
                      })}
                      {/* Regression slope line */}
                      <line
                        x1={260 - 3.5 * 55}
                        y1={110 - -3.5 * llResult.coefficient * 28}
                        x2={260 + 3.5 * 55}
                        y2={110 - 3.5 * llResult.coefficient * 28}
                        stroke="#0F172A"
                        strokeWidth="2"
                      />
                    </svg>
                  </div>
                </div>
              </>
            ) : (
              <p className="text-xs text-slate-500">
                Choose a scenario and click Run Deterministic Simulation to compute OLS + Newey-West
                HAC statistics and visualize the lagged relationship.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
