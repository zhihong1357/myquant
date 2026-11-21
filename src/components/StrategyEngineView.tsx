import React, { useEffect, useState } from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Sparkles } from 'lucide-react';
import { formatPValue } from '../lib/format';
import { useI18n } from '../lib/i18n';
import type { ExecutionSimPayload, LedgerOverviewPayload } from '../lib/types';
import type { UnifiedRunOutput, StrategyId } from '../lib/engine/unifiedPipeline';
import type { SignVsQpComparison } from '../lib/quant/portfolioOptimizer';
import type { BitemporalAuditDemoResult } from '../lib/engine/bitemporalStore';
import type { RecorderSnapshot } from '../lib/engine/marketRecorder';
import type { StrategyArenaReport, WalkForwardReport } from '../lib/quant/walkForward';

export type EngineSubTab = 'arena' | 'pipeline' | 'execution' | 'portfolio' | 'bitemporal';

interface StrategyEngineViewProps {
  activeSubTab?: EngineSubTab;
  onChangeSubTab?: (tab: EngineSubTab) => void;
}

function buildPolyline(
  values: number[],
  width: number,
  height: number,
  padX: number,
  padY: number,
  minVal: number,
  maxVal: number,
): string {
  if (values.length < 2) return '';
  const span = Math.max(1e-9, maxVal - minVal);
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;
  return values
    .map((v, i) => {
      const x = padX + (i / (values.length - 1)) * innerW;
      const y = height - padY - ((v - minVal) / span) * innerH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

const ARENA_COLORS = ['#1D4ED8', '#059669', '#D97706', '#94A3B8'];

export const StrategyEngineView: React.FC<StrategyEngineViewProps> = ({
  activeSubTab,
  onChangeSubTab,
}) => {
  const { bi } = useI18n();
  const [internalTab, setInternalTab] = useState<EngineSubTab>('arena');
  const subTab = activeSubTab ?? internalTab;
  const setSubTab = (next: EngineSubTab) => {
    setInternalTab(next);
    onChangeSubTab?.(next);
  };

  // Sub-tab 1 (NEW): Purged Walk-Forward Arena & 6-Gate Scorecard
  const [arenaVol, setArenaVol] = useState('0.14');
  const [arenaLev, setArenaLev] = useState('2.0');
  const [arenaCost, setArenaCost] = useState('6.5');
  const [arenaSeed, setArenaSeed] = useState('2026');
  const [arenaReport, setArenaReport] = useState<StrategyArenaReport | null>(null);
  const [wfReport, setWfReport] = useState<WalkForwardReport | null>(null);
  const [wfStrategy, setWfStrategy] = useState<StrategyId>('perp_carry_funding');
  const [wfMode, setWfMode] = useState<'qp_optimized' | 'legacy_sign_rule'>('qp_optimized');
  const [arenaBusy, setArenaBusy] = useState(false);

  // Sub-tab 2: Unified Strategy Pipeline & Merkle Ledger
  const [ledger, setLedger] = useState<LedgerOverviewPayload | null>(null);
  const [strategyId, setStrategyId] = useState<StrategyId>('perp_carry_funding');
  const [optimizerMode, setOptimizerMode] = useState<'qp_optimized' | 'legacy_sign_rule'>(
    'qp_optimized',
  );
  const [targetAnnualVol, setTargetAnnualVol] = useState('0.14');
  const [maxLeverage, setMaxLeverage] = useState('2.0');
  const [linearCostBps, setLinearCostBps] = useState('6.5');
  const [pipeSeed, setPipeSeed] = useState('2099');
  const [persistToLedger, setPersistToLedger] = useState(true);
  const [latestRun, setLatestRun] = useState<UnifiedRunOutput | null>(null);
  const [pipeBusy, setPipeBusy] = useState(false);
  const [pipeError, setPipeError] = useState<string | null>(null);

  // Sub-tab 3: Coupled L2 & OKX Margin Stress
  const [execMid, setExecMid] = useState('92000');
  const [execTopDepth, setExecTopDepth] = useState('35');
  const [execChildQty, setExecChildQty] = useState('140');
  const [execLeverage, setExecLeverage] = useState('10');
  const [execCrashPct, setExecCrashPct] = useState('12');
  const [execSide, setExecSide] = useState<'long' | 'short'>('long');
  const [execResult, setExecResult] = useState<ExecutionSimPayload | null>(null);
  const [execBusy, setExecBusy] = useState(false);

  // Sub-tab 4: QP Portfolio Optimizer
  const [qpPeriods, setQpPeriods] = useState('360');
  const [qpSignal, setQpSignal] = useState('0.09');
  const [qpCostBps, setQpCostBps] = useState('7.5');
  const [qpGamma, setQpGamma] = useState('5.0');
  const [qpTargetVol, setQpTargetVol] = useState('0.16');
  const [qpResult, setQpResult] = useState<SignVsQpComparison | null>(null);
  const [qpBusy, setQpBusy] = useState(false);

  // Sub-tab 5: Bitemporal ASOF & Public Recorder
  const [btSource, setBtSource] = useState<'fred' | 'deribit' | 'okx-public'>('fred');
  const [btResult, setBtResult] = useState<BitemporalAuditDemoResult | null>(null);
  const [recInst, setRecInst] = useState('crypto:btc-usdt-perp');
  const [recSnap, setRecSnap] = useState<RecorderSnapshot | null>(null);
  const [recBusy, setRecBusy] = useState(false);

  function strategyDisplayName(id: StrategyId, mode?: 'qp_optimized' | 'legacy_sign_rule') {
    if (mode === 'legacy_sign_rule') {
      return bi('旧版 100% 满仓符号法（反面基准）', 'Legacy 100% Sign-Rule Baseline');
    }
    if (id === 'perp_carry_funding') {
      return bi('1. 永续资金费率截面套利 (QP)', '1. Perpetual Carry & Funding (QP)');
    }
    if (id === 'volume_clock_ofi') {
      return bi('2. 成交量时钟订单流反转 (QP)', '2. Volume-Clock OFI Reversion (QP)');
    }
    return bi('3. 宏观窗口波动率风险溢价 (QP)', '3. Macro-Window VRP (QP)');
  }

  function gateTitle(id: string) {
    const map: Record<string, [string, string]> = {
      liquidation_survival: ['强平生存红线', 'Liquidation Survival'],
      oos_decay_guard: ['样本外盲测防衰减', 'Purged OOS Decay Guard'],
      deflated_sharpe: ['非正态缩水夏普 (DSR)', 'Non-Gaussian DSR'],
      turnover_cost_efficiency: ['换手与手续费效率', 'Cost & Turnover Efficiency'],
      stress_regime_drawdown: ['高波压力回撤控制', 'Stress Regime Drawdown'],
      oos_fold_consistency: ['多折盲测胜率稳定性', 'OOS Fold Consistency'],
    };
    const entry = map[id];
    return entry ? bi(entry[0], entry[1]) : id;
  }

  function gateObservedLocalized(gate: WalkForwardReport['gates'][number], report: WalkForwardReport) {
    if (bi('zh', 'en') === 'en') return gate.observedText;
    switch (gate.id) {
      case 'liquidation_survival':
        return report.liquidated
          ? `触发 OKX 盘中强平（出局）`
          : `全部盘中剧烈插针均存活（0 强平）`;
      case 'oos_decay_guard':
        return `盲测夏普 ${report.meanOosSharpe.toFixed(2)}（样本外保留率 ${(report.oosRetentionRatio * 100).toFixed(0)}%）`;
      case 'deflated_sharpe':
        return `缩水夏普概率 ${(report.deflatedSharpeRatio * 100).toFixed(1)}%`;
      case 'turnover_cost_efficiency':
        return `总磨损 -${report.totalCostDragPct.toFixed(2)}%（单期换手 ${report.avgDailyTurnoverPct.toFixed(1)}%）`;
      case 'stress_regime_drawdown': {
        const stressDd = report.regimes[2]?.maxDrawdownPct ?? 0;
        return `高波回撤 ${stressDd.toFixed(1)}% · 最大回撤 ${report.overallMaxDrawdownPct.toFixed(1)}%`;
      }
      case 'oos_fold_consistency':
        return `${report.oosProfitableFoldRatePct.toFixed(0)}% 盲测折实现正收益`;
      default:
        return gate.observedText;
    }
  }

  function gateThresholdLocalized(gate: WalkForwardReport['gates'][number]) {
    if (bi('zh', 'en') === 'en') return gate.thresholdText;
    switch (gate.id) {
      case 'liquidation_survival':
        return '0 次强制平仓';
      case 'oos_decay_guard':
        return '盲测夏普 >= 0.40 且保留率 >= 50%';
      case 'deflated_sharpe':
        return 'DSR >= 75%（已校正肥尾偏度）';
      case 'turnover_cost_efficiency':
        return '总磨损 <= 6.0% 且单期换手 <= 45%';
      case 'stress_regime_drawdown':
        return '高波回撤 <= 15% 且最大回撤 <= 20%';
      case 'oos_fold_consistency':
        return '至少 60% 盲测折为正收益';
      default:
        return gate.thresholdText;
    }
  }

  function regimeLabel(regime: 'calm_trend' | 'normal_chop' | 'high_vol_stress') {
    if (regime === 'calm_trend') return bi('低波顺势期 (前 33% 波动)', 'Calm Trend (Low Vol)');
    if (regime === 'normal_chop') return bi('常态震荡期 (中位波动)', 'Normal Chop (Mid Vol)');
    return bi('极端高波压力期 (前 25% 暴跌/暴涨)', 'High-Vol Stress (Top 25% Vol)');
  }

  function verdictLabel(verdict: 'paper_ready' | 'needs_tuning' | 'rejected') {
    if (verdict === 'paper_ready') {
      return bi('绿灯 · 可进入纸面观察', 'PAPER READY');
    }
    if (verdict === 'needs_tuning') {
      return bi('黄灯 · 需降杠杆或调参', 'NEEDS TUNING');
    }
    return bi('红灯 · 禁止上线', 'REJECTED');
  }

  function verdictColorClass(verdict: 'paper_ready' | 'needs_tuning' | 'rejected') {
    if (verdict === 'paper_ready') return 'text-emerald-700';
    if (verdict === 'needs_tuning') return 'text-amber-700';
    return 'text-rose-700';
  }

  async function runArenaAndWalkForward(override?: {
    vol?: number;
    lev?: number;
    cost?: number;
    seed?: number;
    focusStrategy?: StrategyId;
    focusMode?: 'qp_optimized' | 'legacy_sign_rule';
  }) {
    setArenaBusy(true);
    const vol = override?.vol ?? Number(arenaVol);
    const lev = override?.lev ?? Number(arenaLev);
    const cost = override?.cost ?? Number(arenaCost);
    const seed = override?.seed ?? Number(arenaSeed);

    try {
      const arenaRes = await fetch('/api/engine/arena', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          periods: 280,
          targetAnnualVol: vol,
          maxLeverage: lev,
          linearCostBps: cost,
          seed,
        }),
      });
      const arenaData = (await arenaRes.json()) as StrategyArenaReport;
      if (arenaRes.ok) {
        setArenaReport(arenaData);
        const top = arenaData.competitors[0];
        const targetStrat = override?.focusStrategy ?? top?.strategyId ?? wfStrategy;
        const targetMode = override?.focusMode ?? top?.optimizerMode ?? wfMode;
        setWfStrategy(targetStrat);
        setWfMode(targetMode);

        const wfRes = await fetch('/api/engine/walk-forward', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            strategyId: targetStrat,
            optimizerMode: targetMode,
            periods: 280,
            numFolds: 5,
            purgeGapBars: 6,
            embargoBars: 4,
            targetAnnualVol: vol,
            maxLeverage: lev,
            linearCostBps: cost,
            seed,
          }),
        });
        const wfData = (await wfRes.json()) as WalkForwardReport;
        if (wfRes.ok) setWfReport(wfData);
      }
    } finally {
      setArenaBusy(false);
    }
  }

  async function inspectCompetitorWalkForward(
    strat: StrategyId,
    mode: 'qp_optimized' | 'legacy_sign_rule',
  ) {
    setWfStrategy(strat);
    setWfMode(mode);
    setArenaBusy(true);
    try {
      const wfRes = await fetch('/api/engine/walk-forward', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategyId: strat,
          optimizerMode: mode,
          periods: 280,
          numFolds: 5,
          purgeGapBars: 6,
          embargoBars: 4,
          targetAnnualVol: Number(arenaVol),
          maxLeverage: Number(arenaLev),
          linearCostBps: Number(arenaCost),
          seed: Number(arenaSeed),
        }),
      });
      const wfData = (await wfRes.json()) as WalkForwardReport;
      if (wfRes.ok) setWfReport(wfData);
    } finally {
      setArenaBusy(false);
    }
  }

  // Initial load for Ledger + Arena
  useEffect(() => {
    let cancelled = false;
    fetch('/api/engine/ledger')
      .then((r) => r.json() as Promise<LedgerOverviewPayload>)
      .then((data) => {
        if (!cancelled) setLedger(data);
      })
      .catch(() => {});

    void runArenaAndWalkForward();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-populate other sub-tabs on first visit
  useEffect(() => {
    if (subTab === 'pipeline' && !latestRun) {
      void runStrategyDirect({
        strategyId: 'perp_carry_funding',
        optimizerMode: 'qp_optimized',
        targetAnnualVol: 0.14,
        maxLeverage: 2.0,
        linearCostBps: 6.5,
        seed: 2026,
        persistToLedger: false,
      });
    } else if (subTab === 'execution' && !execResult) {
      void runExecutionSim();
    } else if (subTab === 'portfolio' && !qpResult) {
      void runPortfolioQp();
    } else if (subTab === 'bitemporal') {
      if (!btResult) void runBitemporal('fred');
      if (!recSnap) void fetchRecorder('crypto:btc-usdt-perp');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subTab]);

  async function runStrategyDirect(params: {
    strategyId: StrategyId;
    optimizerMode: 'qp_optimized' | 'legacy_sign_rule';
    targetAnnualVol: number;
    maxLeverage: number;
    linearCostBps: number;
    seed: number;
    persistToLedger: boolean;
  }) {
    setPipeError(null);
    setPipeBusy(true);
    try {
      const res = await fetch('/api/engine/run-strategy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...params, periods: 240 }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? 'Strategy run failed');
      setLatestRun(json.run as UnifiedRunOutput);
      setLedger(json.ledger as LedgerOverviewPayload);
    } catch (err) {
      setPipeError(err instanceof Error ? err.message : 'Strategy run error');
    } finally {
      setPipeBusy(false);
    }
  }

  async function runStrategy(e: React.FormEvent) {
    e.preventDefault();
    await runStrategyDirect({
      strategyId,
      optimizerMode,
      targetAnnualVol: Number(targetAnnualVol),
      maxLeverage: Number(maxLeverage),
      linearCostBps: Number(linearCostBps),
      seed: Number(pipeSeed),
      persistToLedger,
    });
    setPipeSeed(String(Number(pipeSeed) + 7));
  }

  async function runExecutionSim(
    e?: React.FormEvent,
    override?: {
      midPrice: number;
      topLevelContracts: number;
      childContracts: number;
      leverage: number;
      crashDrawdownPct: number;
      side: 'long' | 'short';
    },
  ) {
    if (e) e.preventDefault();
    setExecBusy(true);
    try {
      const payload = override ?? {
        midPrice: Number(execMid),
        topLevelContracts: Number(execTopDepth),
        childContracts: Number(execChildQty),
        leverage: Number(execLeverage),
        crashDrawdownPct: Number(execCrashPct),
        side: execSide,
      };
      const res = await fetch('/api/tools/execution-sim', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (res.ok) setExecResult(json as ExecutionSimPayload);
    } finally {
      setExecBusy(false);
    }
  }

  async function runPortfolioQp(
    e?: React.FormEvent,
    override?: {
      periods: number;
      signalStrength: number;
      linearCostBps: number;
      riskAversion: number;
      targetAnnualVol: number;
    },
  ) {
    if (e) e.preventDefault();
    setQpBusy(true);
    try {
      const payload = override ?? {
        periods: Number(qpPeriods),
        signalStrength: Number(qpSignal),
        linearCostBps: Number(qpCostBps),
        riskAversion: Number(qpGamma),
        targetAnnualVol: Number(qpTargetVol),
      };
      const res = await fetch('/api/tools/portfolio-qp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, seed: 2026 }),
      });
      const json = await res.json();
      if (res.ok) setQpResult(json as SignVsQpComparison);
    } finally {
      setQpBusy(false);
    }
  }

  async function runBitemporal(source: 'fred' | 'deribit' | 'okx-public') {
    setBtSource(source);
    const res = await fetch('/api/engine/bitemporal-asof', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sourceId: source }),
    });
    const json = await res.json();
    if (res.ok) setBtResult(json as BitemporalAuditDemoResult);
  }

  async function fetchRecorder(inst: string) {
    setRecInst(inst);
    setRecBusy(true);
    try {
      const res = await fetch(`/api/engine/recorder/snapshot?inst=${encodeURIComponent(inst)}`);
      const json = await res.json();
      if (res.ok) setRecSnap(json as RecorderSnapshot);
    } finally {
      setRecBusy(false);
    }
  }

  const activeStrategyMeta =
    ledger?.strategies.find((s) => s.id === strategyId) ?? latestRun?.strategy ?? null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            {bi('机构级策略体检与撮合风控引擎', 'Institutional Strategy & Execution Engine')}
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            {bi(
              '集成了「去泄密滚动盲测 (Purged Walk-Forward)」、6 道上线闸门体检、Garleanu–Pedersen QP 组合优化、真实逐档吃单与 OKX 阶梯爆仓强平状态机。',
              'Unified deterministic research-to-paper pipeline with Purged Walk-Forward 6-gate scoring, Garleanu–Pedersen QP, coupled L2 book-walking, OKX tiered MMR liquidation, and O(1) Merkle CSCV-PBO.'
            )}
          </p>
        </div>
        {ledger && (
          <div className="text-xs font-mono text-slate-500 whitespace-nowrap">
            Merkle Root: {ledger.anchor.merkleRoot.slice(0, 12)}… ·{' '}
            <span
              className={
                ledger.integrity.valid
                  ? 'text-emerald-700 font-medium'
                  : 'text-rose-700 font-medium'
              }
            >
              {ledger.integrity.valid
                ? bi('哈希链已验证', 'Chain Verified')
                : bi('完整性告警', 'Integrity Alert')}
            </span>
          </div>
        )}
      </div>

      {/* Sub-tab navigation */}
      <div className="flex flex-wrap items-center gap-1 p-1 bg-slate-100 rounded-lg w-full sm:w-fit">
        {(
          [
            { id: 'arena', zh: '盲测体检 & 策略 PK', en: 'Walk-Forward Arena' },
            { id: 'pipeline', zh: '统一回测 & Merkle 账本', en: 'Unified Pipeline & PBO' },
            { id: 'execution', zh: 'L2 滑点 & 爆仓压测', en: 'Coupled L2 & Margin' },
            { id: 'portfolio', zh: 'QP 优化 vs 旧土法', en: 'QP Portfolio Optimizer' },
            { id: 'bitemporal', zh: '双时态防穿越 & 录盘', en: 'Bitemporal ASOF & Feed' },
          ] as const
        ).map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setSubTab(item.id)}
            className={`px-3.5 py-2 text-xs font-medium rounded-md transition-colors whitespace-nowrap shrink-0 ${
              subTab === item.id
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            {bi(item.zh, item.en)}
          </button>
        ))}
      </div>

      {/* ===================================================================== */}
      {/* SUB-TAB 1: PURGED WALK-FORWARD ARENA & 6-GATE SCORECARD               */}
      {/* ===================================================================== */}
      {subTab === 'arena' && (
        <div className="space-y-6">
          {/* Beginner 1-Click Scenario Presets + Parameters */}
          <section className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
            <div className="space-y-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">
                  {bi(
                    '一键选择测试场景（不用自己猜参数，点一下立刻跑完 4 套策略 PK）',
                    '1-Click Institutional Stress Scenarios (Benchmark All 4 Strategies Instantly)'
                  )}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {bi(
                    '采用 AFML 第 7 章去泄密隔离带 (Purge Gap = 6 bars) + 禁运区 (Embargo = 4 bars)，彻底阻断样本内外边界偷看。',
                    'Applies AFML Ch. 7 Purged (6-bar gap) & Embargoed (4-bar) Walk-Forward folds with 3-regime stress attribution.'
                  )}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={arenaBusy}
                  onClick={() => {
                    setArenaVol('0.14');
                    setArenaLev('2.0');
                    setArenaCost('6.5');
                    void runArenaAndWalkForward({ vol: 0.14, lev: 2.0, cost: 6.5 });
                  }}
                  className="px-3 py-1.5 text-xs font-medium text-blue-800 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-md whitespace-nowrap"
                >
                  {bi('推荐：标准机构 (14% 波动 · 2×)', 'Standard Institutional (14% Vol · 2×)')}
                </button>
                <button
                  type="button"
                  disabled={arenaBusy}
                  onClick={() => {
                    setArenaVol('0.10');
                    setArenaLev('1.5');
                    setArenaCost('5.0');
                    void runArenaAndWalkForward({ vol: 0.1, lev: 1.5, cost: 5.0 });
                  }}
                  className="px-3 py-1.5 text-xs font-medium text-emerald-800 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-md whitespace-nowrap"
                >
                  {bi('稳健防守 (10% 波动 · 1.5×)', 'Conservative (10% Vol · 1.5×)')}
                </button>
                <button
                  type="button"
                  disabled={arenaBusy}
                  onClick={() => {
                    setArenaVol('0.35');
                    setArenaLev('10.0');
                    setArenaCost('12.0');
                    void runArenaAndWalkForward({
                      vol: 0.35,
                      lev: 10.0,
                      cost: 12.0,
                      focusStrategy: 'perp_carry_funding',
                      focusMode: 'legacy_sign_rule',
                    });
                  }}
                  className="px-3 py-1.5 text-xs font-medium text-rose-800 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-md whitespace-nowrap"
                >
                  {bi('作死高压 (10× 高杠杆 · 12 bps 滑点)', 'High-Leverage Blowup (10× · 12 bps)')}
                </button>
              </div>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                void runArenaAndWalkForward();
              }}
              className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end pt-3 border-t border-slate-100"
            >
              <div>
                <label htmlFor="ar-vol" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('目标年化波动率', 'Target Annual Vol')}
                </label>
                <input
                  id="ar-vol"
                  type="number"
                  step="0.02"
                  min="0.05"
                  max="0.50"
                  value={arenaVol}
                  onChange={(e) => setArenaVol(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="ar-lev" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('最大总杠杆 (×)', 'Max Leverage (×)')}
                </label>
                <input
                  id="ar-lev"
                  type="number"
                  step="0.5"
                  min="0.5"
                  max="12"
                  value={arenaLev}
                  onChange={(e) => setArenaLev(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="ar-cost" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('单边摩擦费率 (bps)', 'Linear Cost (bps)')}
                </label>
                <input
                  id="ar-cost"
                  type="number"
                  step="0.5"
                  min="0"
                  max="30"
                  value={arenaCost}
                  onChange={(e) => setArenaCost(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="ar-seed" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('随机种子 (可复现)', 'Deterministic Seed')}
                </label>
                <input
                  id="ar-seed"
                  type="number"
                  value={arenaSeed}
                  onChange={(e) => setArenaSeed(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <button
                type="submit"
                disabled={arenaBusy}
                className="px-4 py-2 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md whitespace-nowrap disabled:opacity-60"
              >
                {arenaBusy
                  ? bi('正在盲测体检…', 'Running Arena…')
                  : bi('重新运行 4 策略 PK', 'Run 4-Way Arena')}
              </button>
            </form>
          </section>

          {/* Plain-Language Conclusion Banner */}
          {arenaReport && wfReport && (
            <section className="bg-blue-50/60 border border-blue-200 rounded-lg p-4 flex items-start gap-3">
              <Sparkles className="w-4 h-4 text-blue-700 shrink-0 mt-0.5" aria-hidden="true" />
              <div className="text-xs text-slate-800 leading-relaxed space-y-1">
                <div className="font-semibold text-blue-950">
                  {bi('大白话体检结论（根据本次真实盲测数据自动生成）', 'Plain-Language Verdict (Live Computed)')}
                </div>
                <p>
                  {(() => {
                    const winner = arenaReport.competitors[0];
                    const legacy = arenaReport.competitors.find(
                      (c) => c.optimizerMode === 'legacy_sign_rule',
                    );
                    if (bi('zh', 'en') === 'zh') {
                      return `本轮同场盲测冠军是「${strategyDisplayName(winner.strategyId, winner.optimizerMode)}」，综合健康分 ${winner.healthScore}/100（${verdictLabel(winner.releaseVerdict)}），样本外盲测夏普 ${winner.meanOosSharpe.toFixed(2)}，总交易磨损仅 -${winner.totalCostDragPct.toFixed(2)}%。相比之下，旧版满仓土法${legacy?.liquidated ? '直接触发 OKX 盘中插针强平归零！' : `健康分仅 ${legacy?.healthScore ?? 0}/100，交易磨损高达 -${(legacy?.totalCostDragPct ?? 0).toFixed(2)}%`}。点击下表任意策略行，可切换查看它的 6 道上线闸门明细。`;
                    }
                    return `Arena leader is "${strategyDisplayName(winner.strategyId, winner.optimizerMode)}" with ${winner.healthScore}/100 health score (${verdictLabel(winner.releaseVerdict)}), Purged OOS Sharpe ${winner.meanOosSharpe.toFixed(2)}, and only -${winner.totalCostDragPct.toFixed(2)}% fee/impact drag. By contrast, Legacy Sign-Rule ${legacy?.liquidated ? 'suffered forced OKX intraday liquidation!' : `scored ${legacy?.healthScore ?? 0}/100 with -${(legacy?.totalCostDragPct ?? 0).toFixed(2)}% cost drag`}. Click any row below to inspect its 6-gate Purged Walk-Forward scorecard.`;
                  })()}
                </p>
              </div>
            </section>
          )}

          {/* 4-Way Arena Leaderboard + Multi-Curve SVG */}
          {arenaReport && (
            <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
              <section className="xl:col-span-7 bg-white border border-slate-200 rounded-lg overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900">
                      {bi('四策略同场盲测排行榜（点击任意行查看深度体检）', '4-Way Strategy Arena Leaderboard (Click Row to Inspect)')}
                    </h3>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {bi(
                        '统一采用无上限平方根冲击成本 + OKX 阶梯维持保证金强平 + 5 折去泄密盲测。',
                        'Identical convex square-root impact, OKX tiered MMR liquidation, and 5-fold Purged Walk-Forward.'
                      )}
                    </p>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                        <th className="py-2.5 px-3 font-semibold whitespace-nowrap">#</th>
                        <th className="py-2.5 px-3 font-semibold whitespace-nowrap">{bi('策略名称', 'Strategy')}</th>
                        <th className="py-2.5 px-3 font-semibold text-right whitespace-nowrap">{bi('健康分', 'Score')}</th>
                        <th className="py-2.5 px-3 font-semibold text-right whitespace-nowrap">{bi('盲测夏普', 'OOS SR')}</th>
                        <th className="py-2.5 px-3 font-semibold text-right whitespace-nowrap">{bi('最大回撤', 'Max DD')}</th>
                        <th className="py-2.5 px-3 font-semibold text-right whitespace-nowrap">{bi('摩擦损耗', 'Cost Drag')}</th>
                        <th className="py-2.5 px-3 font-semibold whitespace-nowrap">{bi('上线建议', 'Verdict')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {arenaReport.competitors.map((comp, idx) => {
                        const isSelected =
                          comp.strategyId === wfStrategy && comp.optimizerMode === wfMode;
                        return (
                          <tr
                            key={`${comp.strategyId}-${comp.optimizerMode}`}
                            onClick={() =>
                              void inspectCompetitorWalkForward(comp.strategyId, comp.optimizerMode)
                            }
                            className={`cursor-pointer transition-colors ${
                              isSelected ? 'bg-blue-50/70' : 'hover:bg-slate-50'
                            }`}
                          >
                            <td className="py-2.5 px-3 font-mono font-semibold text-slate-500">
                              #{comp.rank}
                            </td>
                            <td className="py-2.5 px-3">
                              <div className="flex items-center gap-2">
                                <span
                                  className="w-2.5 h-2.5 rounded-full shrink-0"
                                  style={{ backgroundColor: ARENA_COLORS[idx % ARENA_COLORS.length] }}
                                />
                                <span className="font-medium text-slate-900">
                                  {strategyDisplayName(comp.strategyId, comp.optimizerMode)}
                                </span>
                              </div>
                            </td>
                            <td className="py-2.5 px-3 font-mono tabular-nums text-right font-bold text-slate-900">
                              {comp.healthScore}
                            </td>
                            <td className="py-2.5 px-3 font-mono tabular-nums text-right text-slate-800">
                              {comp.meanOosSharpe.toFixed(2)}
                            </td>
                            <td className="py-2.5 px-3 font-mono tabular-nums text-right text-slate-700">
                              {comp.overallMaxDrawdownPct.toFixed(1)}%
                            </td>
                            <td className="py-2.5 px-3 font-mono tabular-nums text-right text-rose-700">
                              -{comp.totalCostDragPct.toFixed(2)}%
                            </td>
                            <td
                              className={`py-2.5 px-3 font-medium whitespace-nowrap ${verdictColorClass(comp.releaseVerdict)}`}
                            >
                              {comp.liquidated
                                ? bi('爆仓淘汰', 'LIQUIDATED')
                                : verdictLabel(comp.releaseVerdict)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>

              {/* Multi-Curve Equity Comparison */}
              <section className="xl:col-span-5 bg-white border border-slate-200 rounded-lg p-5 space-y-3">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">
                    {bi('四策略净值曲线实时 PK（起始资金 $100,000）', '4-Way Equity Curves ($100,000 Start)')}
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {bi(
                      '实线为机构级 QP 组合，灰色虚线为旧版 100% 满仓土法。',
                      'Solid lines = Garleanu–Pedersen QP strategies; dashed gray = Legacy 100% Sign Rule.'
                    )}
                  </p>
                </div>

                {/* Legend placed cleanly ABOVE SVG so lines never overlap text */}
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px] font-mono">
                  {arenaReport.competitors.map((comp, idx) => (
                    <span key={`${comp.strategyId}-${comp.optimizerMode}`} className="inline-flex items-center gap-1.5 text-slate-700">
                      <span
                        className="w-3 h-0.5 inline-block"
                        style={{ backgroundColor: ARENA_COLORS[idx % ARENA_COLORS.length] }}
                      />
                      <span>
                        #{comp.rank} ({comp.healthScore}pts)
                      </span>
                    </span>
                  ))}
                </div>

                <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5">
                  {(() => {
                    const allVals = arenaReport.competitors.flatMap((c) => c.equityCurve);
                    const minV = Math.min(...allVals, 90_000);
                    const maxV = Math.max(...allVals, 108_000);
                    const baseY =
                      180 - 16 - ((100_000 - minV) / Math.max(1e-9, maxV - minV)) * (180 - 32);
                    return (
                      <svg
                        viewBox="0 0 460 180"
                        className="w-full h-auto"
                        role="img"
                        aria-label="4-way strategy arena equity curves"
                      >
                        <line
                          x1="20"
                          y1={baseY}
                          x2="440"
                          y2={baseY}
                          stroke="#CBD5E1"
                          strokeDasharray="4 3"
                        />
                        {arenaReport.competitors.map((comp, idx) => {
                          const pts = buildPolyline(comp.equityCurve, 460, 180, 20, 16, minV, maxV);
                          const isLegacy = comp.optimizerMode === 'legacy_sign_rule';
                          return (
                            <polyline
                              key={`${comp.strategyId}-${comp.optimizerMode}`}
                              fill="none"
                              stroke={ARENA_COLORS[idx % ARENA_COLORS.length]}
                              strokeWidth={isLegacy ? '1.8' : '2.3'}
                              strokeDasharray={isLegacy ? '5 4' : undefined}
                              points={pts}
                            />
                          );
                        })}
                      </svg>
                    );
                  })()}
                </div>
              </section>
            </div>
          )}

          {/* Selected Strategy: 6-Gate Institutional Scorecard + Purged Walk-Forward Folds + 3-Regime Attribution */}
          {wfReport && (
            <div className="space-y-6">
              {/* 6-Gate Institutional Scorecard */}
              <section className="bg-white border border-slate-200 rounded-lg p-6 space-y-5">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-slate-200">
                  <div>
                    <div className="text-xs font-mono text-slate-500">
                      {bi('当前深度体检对象', 'SELECTED STRATEGY AUDIT')}
                    </div>
                    <h3 className="text-base font-semibold text-slate-900 mt-0.5">
                      {strategyDisplayName(wfReport.strategyId, wfReport.optimizerMode)}
                    </h3>
                  </div>
                  <div className="flex items-center gap-5">
                    <div className="text-right">
                      <div className="text-xs text-slate-500">{bi('综合健康评分', 'Health Score')}</div>
                      <div className="text-2xl font-bold font-mono tabular-nums text-slate-900">
                        {wfReport.healthScore}
                        <span className="text-xs font-normal text-slate-400"> / 100</span>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-slate-500">{bi('机构风控判定', 'Release Gate')}</div>
                      <div
                        className={`text-sm font-bold mt-1 ${verdictColorClass(wfReport.releaseVerdict)}`}
                      >
                        {verdictLabel(wfReport.releaseVerdict)}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {wfReport.gates.map((gate) => (
                    <div
                      key={gate.id}
                      className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/50 space-y-1.5"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-slate-900">
                          {gateTitle(gate.id)}
                        </span>
                        {gate.severity === 'pass' ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" aria-hidden="true" />
                        ) : gate.severity === 'warn' ? (
                          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" aria-hidden="true" />
                        ) : (
                          <XCircle className="w-4 h-4 text-rose-600 shrink-0" aria-hidden="true" />
                        )}
                      </div>
                      <div className="text-xs font-mono text-slate-800">
                        {gateObservedLocalized(gate, wfReport)}
                      </div>
                      <div className="text-[11px] font-mono text-slate-500">
                        {bi('合格线：', 'Threshold: ')}
                        {gateThresholdLocalized(gate)}
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {/* Two-column lower: Purged Walk-Forward Fold Table + 3-Regime Stress Attribution */}
              <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
                <section className="xl:col-span-7 bg-white border border-slate-200 rounded-lg overflow-hidden">
                  <div className="px-5 py-4 border-b border-slate-200">
                    <h3 className="text-sm font-semibold text-slate-900">
                      {bi(
                        `去泄密滚动盲测逐折明细 (隔离带 Purge = ${wfReport.purgeGapBars} 根 · 禁运 Embargo = ${wfReport.embargoBars} 根)`,
                        `Purged & Embargoed Walk-Forward Folds (Purge = ${wfReport.purgeGapBars} · Embargo = ${wfReport.embargoBars})`
                      )}
                    </h3>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {bi(
                        `平均样本内夏普 ${wfReport.meanIsSharpe.toFixed(2)} → 样本外盲测夏普 ${wfReport.meanOosSharpe.toFixed(2)}（保留率 ${(wfReport.oosRetentionRatio * 100).toFixed(0)}%，正收益折占比 ${wfReport.oosProfitableFoldRatePct.toFixed(0)}%）。`,
                        `Mean IS Sharpe ${wfReport.meanIsSharpe.toFixed(2)} → Purged OOS Sharpe ${wfReport.meanOosSharpe.toFixed(2)} (${(wfReport.oosRetentionRatio * 100).toFixed(0)}% retention · ${wfReport.oosProfitableFoldRatePct.toFixed(0)}% positive folds).`
                      )}
                    </p>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                          <th className="py-2 px-3 font-semibold">{bi('折次', 'Fold')}</th>
                          <th className="py-2 px-3 font-semibold">{bi('训练集区间', 'Train Bars')}</th>
                          <th className="py-2 px-3 font-semibold">{bi('丢弃隔离带', 'Purged Gap')}</th>
                          <th className="py-2 px-3 font-semibold">{bi('盲测区间', 'OOS Test')}</th>
                          <th className="py-2 px-3 font-semibold text-right">{bi('样本内 SR', 'IS SR')}</th>
                          <th className="py-2 px-3 font-semibold text-right">{bi('盲测 SR', 'OOS SR')}</th>
                          <th className="py-2 px-3 font-semibold text-right">{bi('盲测收益', 'OOS Ret')}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 font-mono tabular-nums">
                        {wfReport.folds.map((f) => (
                          <tr key={f.foldIndex} className="hover:bg-slate-50">
                            <td className="py-2 px-3 font-semibold text-slate-900">#{f.foldIndex}</td>
                            <td className="py-2 px-3 text-slate-600">
                              [{f.trainStart}, {f.trainEnd})
                            </td>
                            <td className="py-2 px-3 text-amber-700">
                              [{f.purgeStart}, {f.purgeEnd})
                            </td>
                            <td className="py-2 px-3 text-blue-700">
                              [{f.testStart}, {f.testEnd})
                            </td>
                            <td className="py-2 px-3 text-right text-slate-600">
                              {f.isSharpe.toFixed(2)}
                            </td>
                            <td
                              className={`py-2 px-3 text-right font-semibold ${
                                f.oosSharpe > 0 ? 'text-emerald-700' : 'text-rose-700'
                              }`}
                            >
                              {f.oosSharpe.toFixed(2)}
                            </td>
                            <td
                              className={`py-2 px-3 text-right ${
                                f.oosReturnPct >= 0 ? 'text-emerald-700' : 'text-rose-700'
                              }`}
                            >
                              {f.oosReturnPct >= 0 ? '+' : ''}
                              {f.oosReturnPct.toFixed(2)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="xl:col-span-5 bg-white border border-slate-200 rounded-lg overflow-hidden">
                  <div className="px-5 py-4 border-b border-slate-200">
                    <h3 className="text-sm font-semibold text-slate-900">
                      {bi('不同行情环境（波动率状态）压力归因', 'Volatility Regime Stress Attribution')}
                    </h3>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {bi(
                        '把策略表现按行情平稳期、常态震荡期与暴跌高波期拆开体检，防止策略「平时赚小钱、暴跌一把亏光」。',
                        'Decomposes strategy performance across Calm, Normal, and High-Vol Stress regimes.'
                      )}
                    </p>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                          <th className="py-2 px-3 font-semibold">{bi('行情状态', 'Regime')}</th>
                          <th className="py-2 px-3 font-semibold text-right">{bi('占比', 'Share')}</th>
                          <th className="py-2 px-3 font-semibold text-right">{bi('夏普', 'Sharpe')}</th>
                          <th className="py-2 px-3 font-semibold text-right">{bi('回撤', 'Max DD')}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {wfReport.regimes.map((r) => (
                          <tr key={r.regime} className="hover:bg-slate-50">
                            <td className="py-2.5 px-3 text-slate-800 font-medium">
                              {regimeLabel(r.regime)}
                            </td>
                            <td className="py-2.5 px-3 font-mono tabular-nums text-right text-slate-600">
                              {r.sharePct.toFixed(0)}%
                            </td>
                            <td
                              className={`py-2.5 px-3 font-mono tabular-nums text-right font-semibold ${
                                r.sharpe >= 0 ? 'text-emerald-700' : 'text-rose-700'
                              }`}
                            >
                              {r.sharpe.toFixed(2)}
                            </td>
                            <td className="py-2.5 px-3 font-mono tabular-nums text-right text-slate-700">
                              {r.maxDrawdownPct.toFixed(1)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ===================================================================== */}
      {/* SUB-TAB 2: UNIFIED PIPELINE & MERKLE LEDGER CSCV-PBO                  */}
      {/* ===================================================================== */}
      {subTab === 'pipeline' && (
        <div className="space-y-6">
          {/* Top KPI Strip */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white border border-slate-200 rounded-lg p-5">
              <div className="text-xs font-medium text-slate-500">
                {bi('最新净夏普比率', 'Latest Run Net Sharpe')}
              </div>
              <div className="text-2xl font-bold font-mono tabular-nums text-slate-900 mt-1">
                {latestRun ? latestRun.metrics.netSharpe.toFixed(2) : '—'}
              </div>
              <div className="text-xs text-slate-500 mt-1 font-mono tabular-nums">
                {latestRun
                  ? `${bi('毛夏普', 'Gross')} ${latestRun.metrics.grossSharpe.toFixed(2)} · ${bi('回撤', 'DD')} ${latestRun.metrics.maxDrawdownPct.toFixed(1)}%`
                  : bi('等待运行', 'Waiting for simulation')}
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-lg p-5">
              <div className="text-xs font-medium text-slate-500">
                {bi('缩水夏普概率 (DSR)', 'Deflated Sharpe (DSR)')}
              </div>
              <div
                className={`text-2xl font-bold font-mono tabular-nums mt-1 ${
                  latestRun && latestRun.metrics.deflatedSharpeRatio >= 0.95
                    ? 'text-emerald-700'
                    : 'text-slate-900'
                }`}
              >
                {latestRun ? `${(latestRun.metrics.deflatedSharpeRatio * 100).toFixed(1)}%` : '—'}
              </div>
              <div className="text-xs text-slate-500 mt-1 font-mono tabular-nums">
                {latestRun
                  ? `${bi('偏度', 'Skew')} ${latestRun.metrics.skewness.toFixed(2)} · ${bi('峰度', 'Kurt')} ${latestRun.metrics.excessKurtosis.toFixed(2)}`
                  : bi('已校正非正态肥尾', 'Non-Gaussian moment adjusted')}
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-lg p-5">
              <div className="text-xs font-medium text-slate-500">
                {bi('全库过拟合概率 (CSCV-PBO)', 'Lab-Wide CSCV-PBO')}
              </div>
              <div
                className={`text-2xl font-bold font-mono tabular-nums mt-1 ${
                  ledger?.cscvPbo && ledger.cscvPbo.pbo <= 0.35
                    ? 'text-emerald-700'
                    : ledger?.cscvPbo && ledger.cscvPbo.pbo > 0.5
                      ? 'text-rose-700'
                      : 'text-amber-700'
                }`}
              >
                {ledger?.cscvPbo ? `${(ledger.cscvPbo.pbo * 100).toFixed(1)}%` : '—'}
              </div>
              <div className="text-xs text-slate-500 mt-1 font-mono tabular-nums">
                {ledger?.cscvPbo
                  ? bi(
                      `基于 ${ledger.cscvPbo.numStrategies} 次入链试验 · ${ledger.cscvPbo.combinationsEvaluated} 种组合切分`,
                      `${ledger.cscvPbo.numStrategies} persisted trials · ${ledger.cscvPbo.combinationsEvaluated} splits`
                    )
                  : bi('需至少 2 条账本记录', 'Requires >= 2 ledger trials')}
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-lg p-5">
              <div className="text-xs font-medium text-slate-500">
                {bi('在线 LORD++ 与 Merkle 证明', 'Online LORD++ & Merkle')}
              </div>
              <div className="text-2xl font-bold font-mono tabular-nums text-blue-700 mt-1">
                {ledger ? `${ledger.onlineLordRejections} / ${ledger.anchor.count}` : '—'}
              </div>
              <div className="text-xs text-slate-500 mt-1 font-mono tabular-nums">
                {ledger?.latestProof
                  ? bi(
                      `证明深度 ${ledger.latestProof.proofDepth} · ${ledger.latestProof.verified ? '验证通过' : '异常'}`,
                      `Proof depth ${ledger.latestProof.proofDepth} · ${ledger.latestProof.verified ? 'Verified' : 'Failed'}`
                    )
                  : bi('序列错误发现率控制', 'Sequential FDR control')}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Run Config Form */}
            <form
              onSubmit={runStrategy}
              className="lg:col-span-5 bg-white border border-slate-200 rounded-lg p-6 space-y-4"
            >
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  {bi('运行统一纸面策略试验（自动写入防篡改账本）', 'Run Unified Paper Strategy Trial')}
                </h2>
                <p className="text-xs text-slate-600 mt-1">
                  {bi(
                    '研究与仿真共用唯一代码路径：信号 → QP 权重优化 → 平方根滑点 → OKX 强平检验 → Merkle 链上存证。',
                    'Single code path for signal, QP optimization, convex square-root impact, OKX tiered MMR liquidation, and Merkle ledger persistence.'
                  )}
                </p>
              </div>

              {/* 1-Click Presets */}
              <div className="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    setStrategyId('perp_carry_funding');
                    setOptimizerMode('qp_optimized');
                    setTargetAnnualVol('0.14');
                    setMaxLeverage('2.0');
                    setLinearCostBps('6.5');
                  }}
                  className="px-2.5 py-1 text-[11px] font-medium text-blue-800 bg-blue-50 hover:bg-blue-100 rounded border border-blue-200"
                >
                  {bi('预设：稳健资金费率 QP', 'Preset: Carry QP')}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setStrategyId('volume_clock_ofi');
                    setOptimizerMode('qp_optimized');
                    setTargetAnnualVol('0.14');
                    setMaxLeverage('2.0');
                    setLinearCostBps('6.5');
                  }}
                  className="px-2.5 py-1 text-[11px] font-medium text-emerald-800 bg-emerald-50 hover:bg-emerald-100 rounded border border-emerald-200"
                >
                  {bi('预设：订单流反转 QP', 'Preset: Volume-Clock OFI')}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setStrategyId('perp_carry_funding');
                    setOptimizerMode('legacy_sign_rule');
                    setTargetAnnualVol('0.25');
                    setMaxLeverage('8.0');
                    setLinearCostBps('10.0');
                  }}
                  className="px-2.5 py-1 text-[11px] font-medium text-rose-800 bg-rose-50 hover:bg-rose-100 rounded border border-rose-200"
                >
                  {bi('预设：旧土法 8× 高杠杆反面教材', 'Preset: Legacy 8× Blowup')}
                </button>
              </div>

              <div>
                <label htmlFor="eng-strat" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('选择可交易策略原型', 'Tradable Strategy Archetype')}
                </label>
                <select
                  id="eng-strat"
                  value={strategyId}
                  onChange={(e) => setStrategyId(e.target.value as StrategyId)}
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white"
                >
                  <option value="perp_carry_funding">
                    {bi(
                      '1. 永续合约资金费率与基差截面套利 (BTC/ETH/SOL)',
                      '1. Perpetual Carry & Funding Cross-Section (BTC/ETH/SOL)'
                    )}
                  </option>
                  <option value="volume_clock_ofi">
                    {bi(
                      '2. 成交量时钟订单流失衡微观反转 (Volume-Clock OFI)',
                      '2. Volume-Clock OFI Microstructure Reversion'
                    )}
                  </option>
                  <option value="macro_event_vrp">
                    {bi(
                      '3. 宏观发布窗口波动率风险溢价 (VRP · Study 006)',
                      '3. Macro-Window Volatility Risk Premia (VRP · Study 006)'
                    )}
                  </option>
                </select>
              </div>

              {activeStrategyMeta && (
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-md text-xs space-y-1">
                  <div className="font-medium text-slate-800">{activeStrategyMeta.cadence}</div>
                  <div className="text-slate-600 leading-relaxed">{activeStrategyMeta.mechanism}</div>
                </div>
              )}

              <div>
                <label htmlFor="eng-opt" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('组合仓位构建器', 'Portfolio Construction Layer')}
                </label>
                <select
                  id="eng-opt"
                  value={optimizerMode}
                  onChange={(e) =>
                    setOptimizerMode(e.target.value as 'qp_optimized' | 'legacy_sign_rule')
                  }
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white"
                >
                  <option value="qp_optimized">
                    {bi(
                      '机构级 Garleanu–Pedersen QP + 协方差收缩 + 波动率目标',
                      'Garleanu–Pedersen QP + Ledoit-Wolf + Vol-Target'
                    )}
                  </option>
                  <option value="legacy_sign_rule">
                    {bi(
                      '旧版 100% 满仓符号法（无防抖动不交易缓冲区）',
                      'Legacy 100% Sign-Rule (No No-Trade Zone)'
                    )}
                  </option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="eng-vol" className="block text-xs font-medium text-slate-700 mb-1">
                    {bi('目标年化波动率', 'Target Annual Vol')}
                  </label>
                  <input
                    id="eng-vol"
                    type="number"
                    step="0.02"
                    min="0.04"
                    max="0.5"
                    value={targetAnnualVol}
                    onChange={(e) => setTargetAnnualVol(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                  />
                </div>
                <div>
                  <label htmlFor="eng-lev" className="block text-xs font-medium text-slate-700 mb-1">
                    {bi('最大总杠杆 (×)', 'Max Gross Leverage')}
                  </label>
                  <input
                    id="eng-lev"
                    type="number"
                    step="0.5"
                    min="0.5"
                    max="10"
                    value={maxLeverage}
                    onChange={(e) => setMaxLeverage(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                  />
                </div>
                <div>
                  <label htmlFor="eng-cost" className="block text-xs font-medium text-slate-700 mb-1">
                    {bi('单边费率 (bps)', 'Linear Cost (bps)')}
                  </label>
                  <input
                    id="eng-cost"
                    type="number"
                    step="0.5"
                    min="0"
                    max="40"
                    value={linearCostBps}
                    onChange={(e) => setLinearCostBps(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                  />
                </div>
                <div>
                  <label htmlFor="eng-seed" className="block text-xs font-medium text-slate-700 mb-1">
                    {bi('确定性随机种子', 'Deterministic Seed')}
                  </label>
                  <input
                    id="eng-seed"
                    type="number"
                    value={pipeSeed}
                    onChange={(e) => setPipeSeed(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                  />
                </div>
              </div>

              <label className="flex items-center gap-2 text-xs text-slate-700">
                <input
                  type="checkbox"
                  checked={persistToLedger}
                  onChange={(e) => setPersistToLedger(e.target.checked)}
                />
                {bi(
                  '将本次试验与完整净值序列永久写入 O(1) Merkle 账本',
                  'Append immutable trial + return stream to O(1) Merkle Ledger'
                )}
              </label>

              {pipeError && <p className="text-xs text-rose-700">{pipeError}</p>}

              <button
                type="submit"
                disabled={pipeBusy}
                className="w-full px-4 py-2.5 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md transition-colors disabled:opacity-60"
              >
                {pipeBusy
                  ? bi('正在运行统一引擎…', 'Running Unified Pipeline…')
                  : bi('运行纸面试验并刷新 CSCV-PBO', 'Execute Paper Trial & Update CSCV-PBO')}
              </button>
            </form>

            {/* Equity Curve & Diagnostics */}
            <div className="lg:col-span-7 bg-white border border-slate-200 rounded-lg p-6 space-y-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">
                    {bi('纸面净值曲线与风险归因', 'Paper Equity Curve & Risk Attribution')}
                  </h3>
                  {latestRun && (
                    <p className="text-xs text-slate-500 mt-0.5">
                      {latestRun.trialId} ·{' '}
                      {strategyDisplayName(latestRun.strategy.id, latestRun.optimizerMode)}
                    </p>
                  )}
                </div>
                {latestRun && (
                  <span
                    className={`text-xs font-mono font-semibold ${
                      latestRun.metrics.liquidated ? 'text-rose-700' : 'text-emerald-700'
                    }`}
                  >
                    {latestRun.metrics.liquidated
                      ? bi(
                          `第 ${latestRun.metrics.liquidationStep} 步爆仓强平`,
                          `LIQUIDATED @ Step ${latestRun.metrics.liquidationStep}`
                        )
                      : `${bi('净收益', 'Net')} ${latestRun.metrics.totalNetReturnPct >= 0 ? '+' : ''}${latestRun.metrics.totalNetReturnPct.toFixed(2)}%`}
                  </span>
                )}
              </div>

              {latestRun && latestRun.equityCurve.length > 1 && (
                <>
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                    {(() => {
                      const vals = latestRun.equityCurve.map((p) => p.equity);
                      const minV = Math.min(...vals, 95_000);
                      const maxV = Math.max(...vals, 105_000);
                      const pts = buildPolyline(vals, 560, 190, 28, 18, minV, maxV);
                      const baseY =
                        190 - 18 - ((100_000 - minV) / Math.max(1e-9, maxV - minV)) * (190 - 36);
                      return (
                        <svg
                          viewBox="0 0 560 190"
                          className="w-full h-auto"
                          role="img"
                          aria-label="Paper strategy equity curve"
                        >
                          <line
                            x1="28"
                            y1={baseY}
                            x2="532"
                            y2={baseY}
                            stroke="#CBD5E1"
                            strokeDasharray="4 3"
                          />
                          <polyline
                            fill="none"
                            stroke={latestRun.metrics.liquidated ? '#DC2626' : '#1D4ED8'}
                            strokeWidth="2.2"
                            points={pts}
                          />
                          <text x="30" y="14" fontSize="10" fill="#64748B" fontFamily="IBM Plex Mono">
                            Max ${Math.round(maxV).toLocaleString('en-US')}
                          </text>
                          <text x="30" y="182" fontSize="10" fill="#64748B" fontFamily="IBM Plex Mono">
                            Min ${Math.round(minV).toLocaleString('en-US')}
                          </text>
                          <text
                            x="530"
                            y={Math.max(16, Math.min(180, baseY - 4))}
                            textAnchor="end"
                            fontSize="9.5"
                            fill="#64748B"
                            fontFamily="IBM Plex Mono"
                          >
                            $100,000 Start
                          </text>
                        </svg>
                      );
                    })()}
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs pt-2 border-t border-slate-200">
                    <div>
                      <div className="text-slate-500">{bi('日均换手率', 'Avg Daily Turnover')}</div>
                      <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                        {(latestRun.metrics.avgDailyTurnover * 100).toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-slate-500">{bi('手续费与冲击损耗', 'Cost Drag')}</div>
                      <div className="font-mono tabular-nums font-semibold text-rose-700 mt-0.5">
                        -{latestRun.metrics.totalCostDragPct.toFixed(2)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-slate-500">{bi('资金费率净贡献', 'Funding Impact')}</div>
                      <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                        {latestRun.metrics.totalFundingImpactPct >= 0 ? '+' : ''}
                        {latestRun.metrics.totalFundingImpactPct.toFixed(2)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-slate-500">{bi('不交易缓冲拦截率', 'No-Trade Zone Hold')}</div>
                      <div className="font-mono tabular-nums font-semibold text-blue-700 mt-0.5">
                        {latestRun.metrics.noTradeHoldRatePct.toFixed(1)}%
                      </div>
                    </div>
                  </div>

                  {/* Dynamic Plain-Language Interpretation */}
                  <div className="p-3.5 bg-blue-50/50 border border-blue-200 rounded-md text-xs text-slate-800 leading-relaxed">
                    <span className="font-semibold text-blue-950">
                      {bi('大白话解读：', 'Plain-Language Takeaway: ')}
                    </span>
                    {latestRun.metrics.liquidated
                      ? bi(
                          `高杠杆在第 ${latestRun.metrics.liquidationStep} 步被盘中剧烈波动直接击穿 OKX 维持保证金线，账户被强制平仓。即便后面行情反弹，真金白银也早已出局。`,
                          `Excess leverage breached OKX maintenance margin at step ${latestRun.metrics.liquidationStep}, causing forced liquidation before any recovery.`
                        )
                      : bi(
                          `本次试验在不交易缓冲区帮助下拦截了 ${latestRun.metrics.noTradeHoldRatePct.toFixed(1)}% 的无效抖动调仓，手续费与滑点总损耗控制在 -${latestRun.metrics.totalCostDragPct.toFixed(2)}%，扣除多重试错惩罚后的缩水夏普概率 DSR 为 ${(latestRun.metrics.deflatedSharpeRatio * 100).toFixed(1)}%。`,
                          `The L1 No-Trade Zone suppressed ${latestRun.metrics.noTradeHoldRatePct.toFixed(1)}% of noisy rebalances, keeping total friction at -${latestRun.metrics.totalCostDragPct.toFixed(2)}% with a non-Gaussian Deflated Sharpe probability of ${(latestRun.metrics.deflatedSharpeRatio * 100).toFixed(1)}%.`
                        )}
                  </div>

                  <div className="pt-2 border-t border-slate-200">
                    <div className="text-xs font-medium text-slate-700 mb-2">
                      {bi('期末目标组合仓位权重', 'Final Target Portfolio Weights')}
                    </div>
                    <div className="grid grid-cols-3 gap-3 text-xs font-mono tabular-nums">
                      {latestRun.latestWeights.map((w) => (
                        <div
                          key={w.instrument}
                          className="p-2.5 bg-slate-50 border border-slate-200 rounded-md"
                        >
                          <div className="text-[11px] text-slate-500 truncate">{w.instrument}</div>
                          <div
                            className={`text-sm font-semibold mt-0.5 ${
                              w.weight > 0
                                ? 'text-emerald-700'
                                : w.weight < 0
                                  ? 'text-rose-700'
                                  : 'text-slate-600'
                            }`}
                          >
                            {w.weight >= 0 ? '+' : ''}
                            {(w.weight * 100).toFixed(1)}%
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Persisted Merkle Ledger Table */}
          {ledger && (
            <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">
                    {bi('O(1) 增量 Merkle 不可篡改实验账本', 'O(1) Append-Only Merkle Experiment Ledger')}
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {bi(
                      '每次纸面回测都会把完整净收益序列写入本地哈希链，实时驱动全库 CSCV-PBO 过拟合检验与 Online LORD++ 动态门槛。',
                      'Every trial appends a full net-return stream to feed live lab-wide CSCV-PBO, DSR, and Online LORD++ sequential FDR control.'
                    )}
                  </p>
                </div>
                <div className="text-xs font-mono text-slate-600 whitespace-nowrap">
                  {ledger.anchor.count} {bi('条记录', 'trials')} · Tip{' '}
                  {ledger.anchor.latestChainHash.slice(0, 10)}…
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                      <th className="py-2.5 px-4 font-semibold">{bi('试验号', 'Trial')}</th>
                      <th className="py-2.5 px-4 font-semibold">{bi('策略与优化器', 'Strategy & Optimizer')}</th>
                      <th className="py-2.5 px-4 font-semibold text-right">{bi('净夏普', 'Net Sharpe')}</th>
                      <th className="py-2.5 px-4 font-semibold text-right">DSR</th>
                      <th className="py-2.5 px-4 font-semibold text-right">{bi('日均换手', 'Turnover')}</th>
                      <th className="py-2.5 px-4 font-semibold text-right">{bi('原始 p', 'Raw p')}</th>
                      <th className="py-2.5 px-4 font-semibold">{bi('在线 LORD++ 判决', 'Online LORD++')}</th>
                      <th className="py-2.5 px-4 font-semibold">{bi('叶子哈希', 'Leaf SHA-256')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {[...ledger.entries].reverse().map((row) => (
                      <tr key={row.trialId} className="hover:bg-slate-50">
                        <td className="py-2.5 px-4 font-mono font-semibold text-slate-900 whitespace-nowrap">
                          {row.trialId}
                        </td>
                        <td className="py-2.5 px-4 text-slate-700">
                          <div className="font-medium text-slate-900">
                            {strategyDisplayName(row.strategyId as StrategyId, row.mode)}
                          </div>
                          <div className="text-[11px] text-slate-500 font-mono">
                            {row.mode === 'qp_optimized' ? 'QP + VolTarget' : 'Legacy Sign Rule'} ·
                            seed {row.seed}
                          </div>
                        </td>
                        <td className="py-2.5 px-4 font-mono tabular-nums text-right font-semibold text-slate-900">
                          {row.netSharpe.toFixed(2)}
                        </td>
                        <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-700">
                          {(row.deflatedSharpeRatio * 100).toFixed(1)}%
                        </td>
                        <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-600">
                          {(row.avgDailyTurnover * 100).toFixed(1)}%
                        </td>
                        <td className="py-2.5 px-4 font-mono tabular-nums text-right text-slate-700">
                          {formatPValue(row.rawPValue)}
                        </td>
                        <td className="py-2.5 px-4 whitespace-nowrap">
                          {row.liquidated ? (
                            <span className="text-rose-700 font-semibold">
                              {bi('已爆仓', 'Liquidated')}
                            </span>
                          ) : row.lordAccepted ? (
                            <span className="text-emerald-700 font-medium">
                              {bi('通过', 'Accepted')} (αₜ={formatPValue(row.lordAlphaThreshold)})
                            </span>
                          ) : (
                            <span className="text-slate-500">
                              {bi('暂不采纳', 'Retained')} (αₜ={formatPValue(row.lordAlphaThreshold)})
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-4 font-mono text-slate-500 whitespace-nowrap">
                          {row.leafHash.slice(0, 12)}…
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      )}

      {/* ===================================================================== */}
      {/* SUB-TAB 3: COUPLED L2 BOOK-WALK & OKX TIERED MARGIN STRESS            */}
      {/* ===================================================================== */}
      {subTab === 'execution' && (
        <div className="space-y-6">
          <div className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs font-semibold text-slate-800">
                {bi('一键切换极端压测场景：', '1-Click Execution Stress Presets:')}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setExecMid('92000');
                    setExecTopDepth('35');
                    setExecChildQty('140');
                    setExecLeverage('10');
                    setExecCrashPct('12');
                    setExecSide('long');
                    void runExecutionSim(undefined, {
                      midPrice: 92000,
                      topLevelContracts: 35,
                      childContracts: 140,
                      leverage: 10,
                      crashDrawdownPct: 12,
                      side: 'long',
                    });
                  }}
                  className="px-3 py-1 text-xs font-medium text-rose-800 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-md"
                >
                  {bi('10× 高杠杆遇 12% 闪崩插针（强平演示）', '10× Leverage · 12% Flash Wick (Liquidation)')}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setExecMid('92000');
                    setExecTopDepth('35');
                    setExecChildQty('80');
                    setExecLeverage('3');
                    setExecCrashPct('12');
                    setExecSide('long');
                    void runExecutionSim(undefined, {
                      midPrice: 92000,
                      topLevelContracts: 35,
                      childContracts: 80,
                      leverage: 3,
                      crashDrawdownPct: 12,
                      side: 'long',
                    });
                  }}
                  className="px-3 py-1 text-xs font-medium text-emerald-800 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-md"
                >
                  {bi('3× 机构低杠杆抗住 12% 插针（存活演示）', '3× Low Leverage · Survives 12% Wick')}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setExecMid('92000');
                    setExecTopDepth('20');
                    setExecChildQty('240');
                    setExecLeverage('5');
                    setExecCrashPct('15');
                    setExecSide('long');
                    void runExecutionSim(undefined, {
                      midPrice: 92000,
                      topLevelContracts: 20,
                      childContracts: 240,
                      leverage: 5,
                      crashDrawdownPct: 15,
                      side: 'long',
                    });
                  }}
                  className="px-3 py-1 text-xs font-medium text-amber-800 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-md"
                >
                  {bi('薄盘口连砸 3 笔 240 张大单（流动性枯竭）', 'Thin Book · 3× 240-Contract Sweep')}
                </button>
              </div>
            </div>

            <form
              onSubmit={runExecutionSim}
              className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end pt-3 border-t border-slate-100"
            >
              <div>
                <label htmlFor="ex-mid" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('参考中间价 (USDT)', 'Mid Price (USDT)')}
                </label>
                <input
                  id="ex-mid"
                  type="number"
                  value={execMid}
                  onChange={(e) => setExecMid(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="ex-depth" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('买一/卖一深度 (张)', 'L1 Depth (cts)')}
                </label>
                <input
                  id="ex-depth"
                  type="number"
                  value={execTopDepth}
                  onChange={(e) => setExecTopDepth(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="ex-child" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('单笔子单量 (张)', 'Child Qty (cts)')}
                </label>
                <input
                  id="ex-child"
                  type="number"
                  value={execChildQty}
                  onChange={(e) => setExecChildQty(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="ex-lev" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('永续杠杆倍数 (×)', 'Perp Leverage (×)')}
                </label>
                <input
                  id="ex-lev"
                  type="number"
                  min="1"
                  max="20"
                  value={execLeverage}
                  onChange={(e) => setExecLeverage(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="ex-crash" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('盘中插针跌幅 (%)', 'Intraday Wick (%)')}
                </label>
                <input
                  id="ex-crash"
                  type="number"
                  min="2"
                  max="40"
                  value={execCrashPct}
                  onChange={(e) => setExecCrashPct(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div className="flex gap-2">
                <select
                  aria-label="Position direction"
                  value={execSide}
                  onChange={(e) => setExecSide(e.target.value as 'long' | 'short')}
                  className="px-2.5 py-2 text-xs border border-slate-300 rounded-md bg-white"
                >
                  <option value="long">{bi('做多', 'Long')}</option>
                  <option value="short">{bi('做空', 'Short')}</option>
                </select>
                <button
                  type="submit"
                  disabled={execBusy}
                  className="flex-1 px-3 py-2 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md whitespace-nowrap"
                >
                  {execBusy ? bi('计算中…', 'Running…') : bi('开始压测', 'Simulate')}
                </button>
              </div>
            </form>
          </div>

          {execResult && (
            <>
              <div className="p-4 bg-blue-50/60 border border-blue-200 rounded-lg text-xs text-slate-800 leading-relaxed">
                <span className="font-semibold text-blue-950">
                  {bi('大白话风险提示：', 'Plain-Language Takeaway: ')}
                </span>
                {execResult.marginStress.liquidated
                  ? bi(
                      `同样遇到 ${execCrashPct}% 的 V 型深插针，普通不算保证金的回测以为最后还赚到 $${Math.round(execResult.marginStress.naiveNoMarginFinalEquity).toLocaleString('en-US')}；但真实 OKX 阶梯保证金状态机在盘中直接触发强平，最终账户只剩 $${Math.round(execResult.marginStress.finalEquity).toLocaleString('en-US')}！同时，连续吃单把盘口打穿后，第 3 笔子单滑点升至 ${execResult.childFills[2]?.totalEffectiveCostBps.toFixed(1)} bps。`,
                      `On a ${execCrashPct}% V-shaped flash wick, a naive margin-free backtest pretends equity ends at $${Math.round(execResult.marginStress.naiveNoMarginFinalEquity).toLocaleString('en-US')}, whereas the realistic OKX tiered MMR engine liquidates intraday leaving $${Math.round(execResult.marginStress.finalEquity).toLocaleString('en-US')}. Meanwhile, coupled book depletion pushes child order #3 total cost to ${execResult.childFills[2]?.totalEffectiveCostBps.toFixed(1)} bps.`
                    )
                  : bi(
                      `在当前 ${execLeverage}× 低杠杆下，账户成功扛住了 ${execCrashPct}% 的盘中闪崩插针没有爆仓，期末净值 $${Math.round(execResult.marginStress.finalEquity).toLocaleString('en-US')}。但注意如果下单量达到前 5 档深度的 10 倍，无上限平方根冲击成本会飙升至 ${Math.max(...execResult.impactCurve.map((p) => p.squareRootBps)).toFixed(1)} bps（旧模型却错误封顶在 5.0 bps）。`,
                      `At ${execLeverage}× leverage, the account survives the ${execCrashPct}% intraday wick without forced liquidation (final equity $${Math.round(execResult.marginStress.finalEquity).toLocaleString('en-US')}). Note that at 10× top-5 depth, true square-root impact reaches ${Math.max(...execResult.impactCurve.map((p) => p.squareRootBps)).toFixed(1)} bps vs. the broken 5.0 bps legacy cap.`
                    )}
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Unbounded Square-Root Impact vs Legacy 5 bps Cap */}
                <div className="lg:col-span-6 bg-white border border-slate-200 rounded-lg p-6 space-y-4">
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900">
                      {bi(
                        '无上限平方根冲击成本 vs. 旧版 5 bps 假上限',
                        'Unbounded Square-Root Impact vs. Legacy 5 bps Cap'
                      )}
                    </h2>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {bi(
                        `旧代码把超大单滑点偷偷封死在 5.0 bps（超过前 5 档深度 ${execResult.initialTop5Depth.toFixed(0)} 张就不再涨）；新模型真实刻画流动性悬崖。`,
                        `Legacy linear impact silently froze at 5.0 bps above 1× Top-5 depth (${execResult.initialTop5Depth.toFixed(0)} cts). Convex square-root sweep captures true liquidity cliff.`
                      )}
                    </p>
                  </div>

                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono">
                      <span className="text-rose-700 font-medium">
                        — {bi('平方根真实冲击 (10× 深度峰值', 'Square-Root (Peak')}{' '}
                        {Math.max(...execResult.impactCurve.map((p) => p.squareRootBps)).toFixed(1)}{' '}
                        bps)
                      </span>
                      <span className="text-slate-500">
                        --- {bi('旧版假封顶 (死锁 5.0 bps)', 'Legacy Cap (Frozen @ 5.0 bps)')}
                      </span>
                    </div>
                    {(() => {
                      const sqVals = execResult.impactCurve.map((p) => p.squareRootBps);
                      const legVals = execResult.impactCurve.map((p) => p.legacyCappedBps);
                      const maxBps = Math.max(...sqVals, 10);
                      const sqPts = buildPolyline(sqVals, 480, 155, 24, 14, 0, maxBps);
                      const legPts = buildPolyline(legVals, 480, 155, 24, 14, 0, maxBps);
                      return (
                        <svg
                          viewBox="0 0 480 155"
                          className="w-full h-auto"
                          role="img"
                          aria-label="Square-root impact versus legacy 5 bps cap"
                        >
                          <line x1="24" y1="141" x2="456" y2="141" stroke="#CBD5E1" />
                          <polyline
                            fill="none"
                            stroke="#94A3B8"
                            strokeWidth="2"
                            strokeDasharray="5 4"
                            points={legPts}
                          />
                          <polyline fill="none" stroke="#DC2626" strokeWidth="2.4" points={sqPts} />
                        </svg>
                      );
                    })()}
                  </div>

                  <div>
                    <h3 className="text-xs font-semibold text-slate-800 mb-2">
                      {bi(
                        '状态耦合 L2 逐档吃单（连续 3 笔子单消耗同一盘口）',
                        'Coupled Sequential L2 Book-Walk (3 Consecutive Child Orders)'
                      )}
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="border-b border-slate-200 text-slate-600">
                            <th className="py-1.5 pr-2 font-semibold">{bi('子单', 'Child')}</th>
                            <th className="py-1.5 px-2 font-semibold text-right">
                              {bi('均价成交', 'VWAP Fill')}
                            </th>
                            <th className="py-1.5 px-2 font-semibold text-right">
                              {bi('打穿档位', 'Levels')}
                            </th>
                            <th className="py-1.5 px-2 font-semibold text-right">
                              {bi('吃单滑点', 'Walk Slip')}
                            </th>
                            <th className="py-1.5 pl-2 font-semibold text-right">
                              {bi('总冲击成本', 'Total Cost')}
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 font-mono tabular-nums">
                          {execResult.childFills.map((c) => (
                            <tr key={c.childIndex}>
                              <td className="py-1.5 pr-2 text-slate-800">#{c.childIndex}</td>
                              <td className="py-1.5 px-2 text-right">${c.vwapFillPrice.toFixed(2)}</td>
                              <td className="py-1.5 px-2 text-right">{c.levelsSwept}</td>
                              <td className="py-1.5 px-2 text-right text-amber-700">
                                {c.bookWalkSlippageBps.toFixed(2)} bps
                              </td>
                              <td className="py-1.5 pl-2 text-right font-semibold text-rose-700">
                                {c.totalEffectiveCostBps.toFixed(2)} bps
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>

                {/* OKX Tiered Margin Liquidation & Passive Markout */}
                <div className="lg:col-span-6 bg-white border border-slate-200 rounded-lg p-6 space-y-4">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h2 className="text-sm font-semibold text-slate-900">
                        {bi(
                          'OKX 阶梯保证金盘中强平 vs. 无保证金幻觉',
                          'OKX Tiered MMR Intraday Forced Liquidation vs. Margin-Free'
                        )}
                      </h2>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {bi(
                          `测试 ${execLeverage}× 杠杆遭遇 -${execCrashPct}% 盘中闪崩插针后 V 型反弹的真实命运。`,
                          `Tests a -${execCrashPct}% flash wick followed by V-shaped recovery at ${execLeverage}× leverage.`
                        )}
                      </p>
                    </div>
                    <span
                      className={`text-xs font-mono font-semibold whitespace-nowrap ${
                        execResult.marginStress.liquidated ? 'text-rose-700' : 'text-emerald-700'
                      }`}
                    >
                      {execResult.marginStress.liquidated
                        ? bi('已触发强平', 'FORCED LIQUIDATION')
                        : bi('成功存活', 'SURVIVED WICK')}
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-3 text-xs pb-3 border-b border-slate-200">
                    <div>
                      <div className="text-slate-500">{bi('真实期末资金', 'Realistic Final Equity')}</div>
                      <div
                        className={`text-base font-bold font-mono tabular-nums mt-0.5 ${
                          execResult.marginStress.liquidated ? 'text-rose-700' : 'text-slate-900'
                        }`}
                      >
                        ${Math.round(execResult.marginStress.finalEquity).toLocaleString('en-US')}
                      </div>
                    </div>
                    <div>
                      <div className="text-slate-500">{bi('普通回测假象', 'Legacy Margin-Free')}</div>
                      <div className="text-base font-bold font-mono tabular-nums text-slate-500 mt-0.5">
                        $
                        {Math.round(
                          execResult.marginStress.naiveNoMarginFinalEquity,
                        ).toLocaleString('en-US')}
                      </div>
                    </div>
                    <div>
                      <div className="text-slate-500">{bi('强平触发价', 'Liquidation Price')}</div>
                      <div className="text-base font-bold font-mono tabular-nums text-slate-900 mt-0.5">
                        {execResult.marginStress.liquidationPrice
                          ? `$${Math.round(execResult.marginStress.liquidationPrice).toLocaleString('en-US')}`
                          : bi('未触发', 'None')}
                      </div>
                    </div>
                  </div>

                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono">
                      <span
                        className={
                          execResult.marginStress.liquidated
                            ? 'text-rose-700 font-medium'
                            : 'text-blue-700 font-medium'
                        }
                      >
                        — {bi('OKX 阶梯保证金状态机', 'OKX Tiered MMR State Machine')}
                      </span>
                      <span className="text-slate-500">
                        --- {bi('旧版无保证金回测', 'Legacy Margin-Free')}
                      </span>
                    </div>
                    {(() => {
                      const realEq = execResult.marginStress.equityCurve.map((p) => p.equity);
                      const naiveEq = execResult.marginStress.equityCurve.map((p) => p.naiveEquity);
                      const minEq = Math.min(...realEq, ...naiveEq, 0);
                      const maxEq = Math.max(...realEq, ...naiveEq, 110_000);
                      const realPts = buildPolyline(realEq, 480, 130, 24, 14, minEq, maxEq);
                      const naivePts = buildPolyline(naiveEq, 480, 130, 24, 14, minEq, maxEq);
                      return (
                        <svg
                          viewBox="0 0 480 130"
                          className="w-full h-auto"
                          role="img"
                          aria-label="Margin liquidation equity versus naive margin-free equity"
                        >
                          <polyline
                            fill="none"
                            stroke="#94A3B8"
                            strokeWidth="2"
                            strokeDasharray="4 3"
                            points={naivePts}
                          />
                          <polyline
                            fill="none"
                            stroke={execResult.marginStress.liquidated ? '#DC2626' : '#1D4ED8'}
                            strokeWidth="2.4"
                            points={realPts}
                          />
                        </svg>
                      );
                    })()}
                  </div>

                  {/* Passive Limit Adverse Selection Markout */}
                  <div className="pt-2 border-t border-slate-200 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-slate-800">
                        {bi(
                          '被动挂单排队与逆向选择毒流亏损 (Markout)',
                          'Passive Limit Queue & Adverse Selection Markout'
                        )}
                      </span>
                      <span className="font-mono text-amber-700">
                        {execResult.passiveMarkout.adverseSelectionDetected
                          ? bi('检出逆向选择毒流', 'Adverse Selection Detected')
                          : bi('正常成交', 'Clean Fill')}
                      </span>
                    </div>
                    <div className="grid grid-cols-4 gap-2 text-xs font-mono tabular-nums bg-slate-50 border border-slate-200 rounded-md p-3">
                      <div>
                        <div className="font-sans text-[11px] text-slate-500">
                          {bi('保守队首兜底', 'Queue Fallback')}
                        </div>
                        <div className="font-semibold text-slate-900">
                          {execResult.passiveMarkout.queueAheadUsed.toFixed(1)} cts
                        </div>
                      </div>
                      <div>
                        <div className="font-sans text-[11px] text-slate-500">
                          {bi('成交后 1 秒', 'Markout 1s')}
                        </div>
                        <div className="font-semibold text-rose-700">
                          {execResult.passiveMarkout.markout1sBps?.toFixed(2) ?? '—'} bps
                        </div>
                      </div>
                      <div>
                        <div className="font-sans text-[11px] text-slate-500">
                          {bi('成交后 10 秒', 'Markout 10s')}
                        </div>
                        <div className="font-semibold text-rose-700">
                          {execResult.passiveMarkout.markout10sBps?.toFixed(2) ?? '—'} bps
                        </div>
                      </div>
                      <div>
                        <div className="font-sans text-[11px] text-slate-500">
                          {bi('成交后 60 秒', 'Markout 60s')}
                        </div>
                        <div className="font-semibold text-rose-700">
                          {execResult.passiveMarkout.markout60sBps?.toFixed(2) ?? '—'} bps
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ===================================================================== */}
      {/* SUB-TAB 4: GARLEANU-PEDERSEN QP PORTFOLIO OPTIMIZER                   */}
      {/* ===================================================================== */}
      {subTab === 'portfolio' && (
        <div className="space-y-6">
          <div className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs font-semibold text-slate-800">
                {bi('一键对比不同交易成本下的 QP 降维优势：', '1-Click Cost & Signal Presets:')}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setQpCostBps('7.5');
                    setQpSignal('0.09');
                    setQpGamma('5.0');
                    setQpTargetVol('0.16');
                    void runPortfolioQp(undefined, {
                      periods: 360,
                      signalStrength: 0.09,
                      linearCostBps: 7.5,
                      riskAversion: 5.0,
                      targetAnnualVol: 0.16,
                    });
                  }}
                  className="px-3 py-1 text-xs font-medium text-blue-800 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-md"
                >
                  {bi('标准永续费率 (7.5 bps)', 'Standard Perp (7.5 bps)')}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setQpCostBps('14.0');
                    setQpSignal('0.08');
                    setQpGamma('6.0');
                    setQpTargetVol('0.14');
                    void runPortfolioQp(undefined, {
                      periods: 360,
                      signalStrength: 0.08,
                      linearCostBps: 14.0,
                      riskAversion: 6.0,
                      targetAnnualVol: 0.14,
                    });
                  }}
                  className="px-3 py-1 text-xs font-medium text-amber-800 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-md"
                >
                  {bi('高滑点小币种 (14 bps · 碾压旧土法)', 'High Friction (14 bps · Huge QP Edge)')}
                </button>
              </div>
            </div>

            <form
              onSubmit={runPortfolioQp}
              className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end pt-3 border-t border-slate-100"
            >
              <div>
                <label htmlFor="qp-per" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('回测期数', 'Periods')}
                </label>
                <input
                  id="qp-per"
                  type="number"
                  value={qpPeriods}
                  onChange={(e) => setQpPeriods(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="qp-sig" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('Alpha 信号强度', 'Signal Strength')}
                </label>
                <input
                  id="qp-sig"
                  type="number"
                  step="0.01"
                  value={qpSignal}
                  onChange={(e) => setQpSignal(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="qp-cost" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('换手成本 (bps)', 'Cost (bps/turn)')}
                </label>
                <input
                  id="qp-cost"
                  type="number"
                  step="0.5"
                  value={qpCostBps}
                  onChange={(e) => setQpCostBps(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="qp-gamma" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('风险厌恶系数 γ', 'Risk Aversion (γ)')}
                </label>
                <input
                  id="qp-gamma"
                  type="number"
                  step="0.5"
                  value={qpGamma}
                  onChange={(e) => setQpGamma(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <div>
                <label htmlFor="qp-vol" className="block text-xs font-medium text-slate-700 mb-1">
                  {bi('目标年化波动率', 'Target Annual Vol')}
                </label>
                <input
                  id="qp-vol"
                  type="number"
                  step="0.02"
                  value={qpTargetVol}
                  onChange={(e) => setQpTargetVol(e.target.value)}
                  className="w-full px-3 py-2 text-xs font-mono border border-slate-300 rounded-md"
                />
              </div>
              <button
                type="submit"
                disabled={qpBusy}
                className="px-4 py-2 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md whitespace-nowrap"
              >
                {qpBusy ? bi('求解 QP 中…', 'Solving QP…') : bi('开始对比求解', 'Compare QP vs Sign')}
              </button>
            </form>
          </div>

          {qpResult && (
            <>
              <div className="p-4 bg-blue-50/60 border border-blue-200 rounded-lg text-xs text-slate-800 leading-relaxed">
                <span className="font-semibold text-blue-950">
                  {bi('大白话结论：', 'Plain-Language Takeaway: ')}
                </span>
                {bi(
                  `旧版「信号正就满仓做多、信号负就满仓反手」的方法，在信号围绕 0 抖动时疯狂反手了 ${qpResult.signRule.totalFlipCount} 次，白白交掉 -${qpResult.signRule.totalCostDragPct.toFixed(2)}% 手续费！机构级 Garleanu–Pedersen QP 自动画出「不交易缓冲区」，直接砍掉 ${qpResult.turnoverReductionPct.toFixed(1)}% 的无谓换手，把净夏普从 ${qpResult.signRule.netSharpe.toFixed(2)} 拉升到 ${qpResult.qpOptimized.netSharpe.toFixed(2)}。`,
                  `The naive Sign Rule flipped ${qpResult.signRule.totalFlipCount} times on signal noise, bleeding -${qpResult.signRule.totalCostDragPct.toFixed(2)}% in transaction costs. Garleanu–Pedersen QP's L1 No-Trade Zone cut turnover by ${qpResult.turnoverReductionPct.toFixed(1)}% and lifted Net Sharpe from ${qpResult.signRule.netSharpe.toFixed(2)} to ${qpResult.qpOptimized.netSharpe.toFixed(2)}.`
                )}
              </div>

              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-white border border-slate-200 rounded-lg p-5">
                  <div className="text-xs font-medium text-slate-500">
                    {bi('无谓换手率下降', 'Turnover Reduction')}
                  </div>
                  <div className="text-2xl font-bold font-mono tabular-nums text-emerald-700 mt-1">
                    -{qpResult.turnoverReductionPct.toFixed(1)}%
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {bi('L1 软阈值不交易缓冲区生效', 'Via L₁ soft-thresholding No-Trade Zone')}
                  </div>
                </div>
                <div className="bg-white border border-slate-200 rounded-lg p-5">
                  <div className="text-xs font-medium text-slate-500">
                    {bi('净夏普比率提升', 'Net Sharpe Improvement')}
                  </div>
                  <div className="text-2xl font-bold font-mono tabular-nums text-blue-700 mt-1">
                    {qpResult.sharpeImprovement >= 0 ? '+' : ''}
                    {qpResult.sharpeImprovement.toFixed(2)}
                  </div>
                  <div className="text-xs text-slate-500 mt-1 font-mono tabular-nums">
                    QP {qpResult.qpOptimized.netSharpe.toFixed(2)} vs{' '}
                    {bi('旧法', 'Sign')} {qpResult.signRule.netSharpe.toFixed(2)}
                  </div>
                </div>
                <div className="bg-white border border-slate-200 rounded-lg p-5">
                  <div className="text-xs font-medium text-slate-500">
                    {bi('不交易缓冲拦截比例', 'No-Trade Zone Hold Rate')}
                  </div>
                  <div className="text-2xl font-bold font-mono tabular-nums text-slate-900 mt-1">
                    {qpResult.qpOptimized.noTradeHoldRatePct.toFixed(1)}%
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {bi(
                      `旧法盲目反手 ${qpResult.signRule.totalFlipCount} 次`,
                      `Sign Rule flipped ${qpResult.signRule.totalFlipCount} times`
                    )}
                  </div>
                </div>
                <div className="bg-white border border-slate-200 rounded-lg p-5">
                  <div className="text-xs font-medium text-slate-500">
                    {bi('Ledoit-Wolf 收缩强度 δ*', 'Ledoit-Wolf Shrinkage δ*')}
                  </div>
                  <div className="text-2xl font-bold font-mono tabular-nums text-slate-900 mt-1">
                    {qpResult.shrinkageIntensity.toFixed(3)}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {bi('解析半正定协方差去噪', 'Analytical PSD covariance regularization')}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-7 bg-white border border-slate-200 rounded-lg p-6 space-y-3">
                  <h3 className="text-sm font-semibold text-slate-900">
                    {bi(
                      '累计净值曲线：机构级 QP 优化 vs. 旧版 100% 满仓符号法',
                      'Cumulative Net Equity: Garleanu–Pedersen QP vs. Legacy 100% Sign Rule'
                    )}
                  </h3>
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono">
                      <span className="text-blue-700 font-medium">
                        — {bi('Garleanu–Pedersen QP + 协方差收缩 + 波动率目标', 'Garleanu–Pedersen QP + Ledoit-Wolf + Vol-Target')}
                      </span>
                      <span className="text-slate-500">
                        --- {bi('旧版 100% 满仓符号法', 'Legacy 100% Sign Rule')}
                      </span>
                    </div>
                    {(() => {
                      const qEq = qpResult.qpOptimized.equityCurve;
                      const sEq = qpResult.signRule.equityCurve;
                      const minV = Math.min(...qEq, ...sEq);
                      const maxV = Math.max(...qEq, ...sEq);
                      const qPts = buildPolyline(qEq, 540, 190, 24, 14, minV, maxV);
                      const sPts = buildPolyline(sEq, 540, 190, 24, 14, minV, maxV);
                      return (
                        <svg
                          viewBox="0 0 540 190"
                          className="w-full h-auto"
                          role="img"
                          aria-label="QP optimized versus sign rule equity curves"
                        >
                          <polyline
                            fill="none"
                            stroke="#94A3B8"
                            strokeWidth="2"
                            strokeDasharray="5 4"
                            points={sPts}
                          />
                          <polyline fill="none" stroke="#1D4ED8" strokeWidth="2.4" points={qPts} />
                        </svg>
                      );
                    })()}
                  </div>
                </div>

                <div className="lg:col-span-5 bg-white border border-slate-200 rounded-lg p-6">
                  <h3 className="text-sm font-semibold text-slate-900 mb-3">
                    {bi('同条件核心指标正面 PK', 'Head-to-Head Attribution Table')}
                  </h3>
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-600">
                        <th className="py-2 font-semibold">{bi('指标', 'Metric')}</th>
                        <th className="py-2 font-semibold text-right">{bi('旧版符号法', 'Sign Rule')}</th>
                        <th className="py-2 font-semibold text-right text-blue-700">
                          {bi('QP + 波动率目标', 'QP + VolTarget')}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-mono tabular-nums">
                      <tr>
                        <td className="py-2 font-sans text-slate-700">{bi('净夏普比率', 'Net Sharpe')}</td>
                        <td className="py-2 text-right">{qpResult.signRule.netSharpe.toFixed(2)}</td>
                        <td className="py-2 text-right font-semibold text-blue-700">
                          {qpResult.qpOptimized.netSharpe.toFixed(2)}
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2 font-sans text-slate-700">{bi('毛夏普比率', 'Gross Sharpe')}</td>
                        <td className="py-2 text-right">{qpResult.signRule.grossSharpe.toFixed(2)}</td>
                        <td className="py-2 text-right">
                          {qpResult.qpOptimized.grossSharpe.toFixed(2)}
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2 font-sans text-slate-700">{bi('累计净收益', 'Total Net Return')}</td>
                        <td className="py-2 text-right">
                          {qpResult.signRule.totalNetReturnPct.toFixed(2)}%
                        </td>
                        <td className="py-2 text-right font-semibold">
                          {qpResult.qpOptimized.totalNetReturnPct.toFixed(2)}%
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2 font-sans text-slate-700">{bi('实际年化波动', 'Realized Annual Vol')}</td>
                        <td className="py-2 text-right">
                          {qpResult.signRule.annualizedVolPct.toFixed(1)}%
                        </td>
                        <td className="py-2 text-right">
                          {qpResult.qpOptimized.annualizedVolPct.toFixed(1)}%
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2 font-sans text-slate-700">{bi('最大回撤', 'Max Drawdown')}</td>
                        <td className="py-2 text-right text-rose-700">
                          {qpResult.signRule.maxDrawdownPct.toFixed(1)}%
                        </td>
                        <td className="py-2 text-right">
                          {qpResult.qpOptimized.maxDrawdownPct.toFixed(1)}%
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2 font-sans text-slate-700">{bi('日均换手率', 'Avg Daily Turnover')}</td>
                        <td className="py-2 text-right">
                          {(qpResult.signRule.averageDailyTurnover * 100).toFixed(1)}%
                        </td>
                        <td className="py-2 text-right text-emerald-700 font-semibold">
                          {(qpResult.qpOptimized.averageDailyTurnover * 100).toFixed(1)}%
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2 font-sans text-slate-700">{bi('总交易磨损', 'Total Cost Drag')}</td>
                        <td className="py-2 text-right text-rose-700">
                          -{qpResult.signRule.totalCostDragPct.toFixed(2)}%
                        </td>
                        <td className="py-2 text-right text-emerald-700 font-semibold">
                          -{qpResult.qpOptimized.totalCostDragPct.toFixed(2)}%
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ===================================================================== */}
      {/* SUB-TAB 5: BITEMPORAL ASOF STORE & PUBLIC OKX RECORDER                */}
      {/* ===================================================================== */}
      {subTab === 'bitemporal' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Bitemporal Write-Time Guard & Strict ASOF Diff */}
          <div className="lg:col-span-7 bg-white border border-slate-200 rounded-lg p-6 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">
                  {bi('双时态列式存储内核与严格 ASOF JOIN 审计', 'Bitemporal Storage Kernel & Strict ASOF JOIN Audit')}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {bi(
                    '在数据写入层硬拦截伪造可用时间，确保回测只能用到当时真正已发布的数据 (knowledgeTs ≤ decisionTs)。',
                    'Enforces source publication lags at write time and compares strict knowledgeTs <= decisionTs vs. naive event-time joins.'
                  )}
                </p>
              </div>
              <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-md">
                {(
                  [
                    { id: 'fred', label: 'FRED BAA10Y (48h)' },
                    { id: 'deribit', label: 'Deribit DVOL (24h)' },
                    { id: 'okx-public', label: 'OKX Real-Time (0h)' },
                  ] as const
                ).map((src) => (
                  <button
                    key={src.id}
                    type="button"
                    onClick={() => void runBitemporal(src.id)}
                    className={`px-2.5 py-1 text-xs font-medium rounded whitespace-nowrap ${
                      btSource === src.id
                        ? 'bg-white text-slate-900 shadow-xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {src.label}
                  </button>
                ))}
              </div>
            </div>

            {btResult && (
              <>
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-md text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-800">
                      {bi(
                        '写入期硬防线测试（尝试伪造 knowledgeTs === eventTs）',
                        'Write-Time Guard Check (Attempting knowledgeTs === eventTs)'
                      )}
                    </span>
                    <span
                      className={`font-mono font-semibold ${
                        btResult.fakePitWriteBlocked ? 'text-emerald-700' : 'text-slate-600'
                      }`}
                    >
                      {btResult.fakePitWriteBlocked
                        ? bi('内核已硬拦截', 'BLOCKED AT KERNEL')
                        : bi('实时源允许零延迟', 'ZERO-LAG ALLOWED')}
                    </span>
                  </div>
                  <div className="font-mono text-[11px] text-slate-600">
                    {btResult.blockedErrorMessage}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div className="p-3 border border-slate-200 rounded-md">
                    <div className="text-slate-500">{bi('强制最小发布延迟', 'Enforced Min Lag')}</div>
                    <div className="text-base font-bold font-mono tabular-nums text-slate-900 mt-0.5">
                      {btResult.enforcedLagHours}h
                    </div>
                  </div>
                  <div className="p-3 border border-slate-200 rounded-md">
                    <div className="text-slate-500">{bi('传统拼接穿越行数', 'Naive Rows Leaked')}</div>
                    <div
                      className={`text-base font-bold font-mono tabular-nums mt-0.5 ${
                        btResult.rowsWithLookaheadLeak > 0 ? 'text-rose-700' : 'text-emerald-700'
                      }`}
                    >
                      {btResult.rowsWithLookaheadLeak} / {btResult.rowsEvaluated}
                    </div>
                  </div>
                  <div className="p-3 border border-slate-200 rounded-md">
                    <div className="text-slate-500">{bi('平均偷看未来时长', 'Mean Leak Horizon')}</div>
                    <div className="text-base font-bold font-mono tabular-nums text-slate-900 mt-0.5">
                      {btResult.meanLookaheadHoursLeaked.toFixed(0)}h
                    </div>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                        <th className="py-2 px-3 font-semibold">{bi('交易决策日', 'Decision Date')}</th>
                        <th className="py-2 px-3 font-semibold">{bi('严格 ASOF (真实可见)', 'Strict ASOF (Event Date)')}</th>
                        <th className="py-2 px-3 font-semibold">{bi('传统按日期拼接', 'Naive Join (Event Date)')}</th>
                        <th className="py-2 px-3 font-semibold">{bi('审计判定', 'Audit')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-mono tabular-nums">
                      {btResult.sampleRows.map((row) => (
                        <tr key={row.decisionDate}>
                          <td className="py-1.5 px-3 text-slate-800">{row.decisionDate}</td>
                          <td className="py-1.5 px-3 text-slate-700">
                            {row.strictAsofValue !== null
                              ? `${row.strictAsofValue.toFixed(2)} (${row.strictEventDate})`
                              : bi('NULL（尚未发布）', 'NULL (not published)')}
                          </td>
                          <td className="py-1.5 px-3 text-slate-600">
                            {row.naiveEventValue !== null
                              ? `${row.naiveEventValue.toFixed(2)} (${row.naiveEventDate})`
                              : '—'}
                          </td>
                          <td className="py-1.5 px-3 font-sans">
                            {row.leakedFutureData ? (
                              <span className="text-rose-700 font-medium">
                                {bi('偷看未来', 'Future Leaked')}
                              </span>
                            ) : (
                              <span className="text-emerald-700 font-medium">
                                {bi('时间合规', 'PIT Clean')}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>

          {/* Public Read-Only OKX L2 & Funding Recorder */}
          <div className="lg:col-span-5 bg-white border border-slate-200 rounded-lg p-6 space-y-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">
                  {bi('公开只读 L2 盘口与资金费率录盘器', 'Public Read-Only Market Recorder')}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {bi(
                    '无需 API Key · 自动校验单调序列号与倒挂盘口异常。',
                    'Zero credentials · monotonic seqId & crossed-book validation.'
                  )}
                </p>
              </div>
              <button
                type="button"
                disabled={recBusy}
                onClick={() => void fetchRecorder(recInst)}
                className="px-3 py-1.5 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md whitespace-nowrap"
              >
                {recBusy ? bi('抓取中…', 'Capturing…') : bi('抓取快照', 'Capture Snapshot')}
              </button>
            </div>

            <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-md w-fit">
              {[
                { id: 'crypto:btc-usdt-perp', label: 'BTC-SWAP' },
                { id: 'crypto:eth-usdt-perp', label: 'ETH-SWAP' },
                { id: 'crypto:sol-usdt-perp', label: 'SOL-SWAP' },
              ].map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => void fetchRecorder(item.id)}
                  className={`px-2.5 py-1 text-xs font-medium rounded whitespace-nowrap ${
                    recInst === item.id
                      ? 'bg-white text-slate-900 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>

            {recSnap && (
              <>
                <div className="grid grid-cols-2 gap-3 text-xs pt-2 border-t border-slate-200">
                  <div>
                    <div className="text-slate-500">{bi('采集模式', 'Capture Mode')}</div>
                    <div
                      className={`font-mono font-semibold mt-0.5 ${
                        recSnap.captureMode === 'live_okx_public'
                          ? 'text-emerald-700'
                          : 'text-amber-700'
                      }`}
                    >
                      {recSnap.captureMode === 'live_okx_public'
                        ? bi('实时 OKX 公开盘口', 'Live OKX Public')
                        : bi('已校验离线快照兜底', 'Verified Offline Capture')}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">{bi('单调序列号', 'Sequence ID')}</div>
                    <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                      {recSnap.seqId}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">{bi('中间价 / 微观加权价', 'Mid / Microprice')}</div>
                    <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                      ${recSnap.midPrice.toFixed(2)} · ${recSnap.microprice.toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">{bi('点差 / 8h 资金费率', 'Spread / 8h Funding')}</div>
                    <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                      {recSnap.spreadBps.toFixed(2)} bps · {recSnap.fundingRateBps8h.toFixed(2)} bps
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">{bi('前 5 档盘口失衡度', 'Top-5 Imbalance')}</div>
                    <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                      {(recSnap.depthImbalanceTop5 * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">{bi('标记价格', 'Mark Price')}</div>
                    <div className="font-mono tabular-nums font-semibold text-slate-900 mt-0.5">
                      ${recSnap.markPrice.toFixed(2)}
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-2 border-t border-slate-200 text-xs font-mono tabular-nums">
                  <div>
                    <div className="font-sans text-[11px] font-semibold text-emerald-700 mb-1">
                      {bi('买盘前 5 档 (价格 / 数量)', 'Top 5 Bids (Price / Size)')}
                    </div>
                    <div className="space-y-1">
                      {recSnap.bids.slice(0, 5).map((b, i) => (
                        <div key={i} className="flex justify-between text-slate-700">
                          <span>${b.price.toFixed(2)}</span>
                          <span className="text-slate-500">{b.size.toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="font-sans text-[11px] font-semibold text-rose-700 mb-1">
                      {bi('卖盘前 5 档 (价格 / 数量)', 'Top 5 Asks (Price / Size)')}
                    </div>
                    <div className="space-y-1">
                      {recSnap.asks.slice(0, 5).map((a, i) => (
                        <div key={i} className="flex justify-between text-slate-700">
                          <span>${a.price.toFixed(2)}</span>
                          <span className="text-slate-500">{a.size.toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <p className="text-[11px] text-slate-500 leading-relaxed pt-2 border-t border-slate-200">
                  {recSnap.note}
                </p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
