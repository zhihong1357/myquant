import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Flame,
  GraduationCap,
  ShieldCheck,
  Sparkles,
  XCircle,
} from 'lucide-react';
import { useI18n } from '../lib/i18n';
import type { ExecutionSimPayload, OverviewPayload } from '../lib/types';
import type { StrategyArenaReport, WalkForwardReport } from '../lib/quant/walkForward';
import type { BitemporalAuditDemoResult } from '../lib/engine/bitemporalStore';
import type { PaperExecutionCostBreakdown } from '../lib/quant/executionCosts';
import type { StrategyId } from '../lib/engine/unifiedPipeline';

interface BeginnerModeViewProps {
  overview: OverviewPayload | null;
  onOpenProMode: () => void;
}

type SimpleTab = 'checkup' | 'liquidation' | 'pitfalls';
type RiskProfile = 'safe' | 'balanced' | 'aggressive';

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

const RISK_CONFIGS: Record<
  RiskProfile,
  {
    vol: number;
    lev: number;
    cost: number;
    titleZh: string;
    titleEn: string;
    descZh: string;
    descEn: string;
    badgeZh: string;
    badgeEn: string;
  }
> = {
  safe: {
    vol: 0.1,
    lev: 1.5,
    cost: 5.0,
    titleZh: '稳健防守型（推荐新手）',
    titleEn: 'Conservative (Best for Beginners)',
    descZh: '小仓位慢慢赚，最多 1.5 倍杠杆，尽量避免大起大落。',
    descEn: 'Small risk budget, max 1.5× leverage, prioritizes capital safety.',
    badgeZh: '1.5× 低杠杆',
    badgeEn: '1.5× Low Lev',
  },
  balanced: {
    vol: 0.14,
    lev: 2.0,
    cost: 6.5,
    titleZh: '标准机构型',
    titleEn: 'Institutional Standard',
    descZh: '专业量化常用配置，2 倍杠杆，在收益与回撤之间求平衡。',
    descEn: 'Balanced institutional 2× leverage and 14% volatility target.',
    badgeZh: '2× 均衡杠杆',
    badgeEn: '2× Balanced',
  },
  aggressive: {
    vol: 0.35,
    lev: 10.0,
    cost: 12.0,
    titleZh: '高危重仓试错型（警示演示）',
    titleEn: 'High-Leverage Stress (Danger Demo)',
    descZh: '体验 10 倍高杠杆遇上剧烈波动时，普通满仓土法如何直接爆仓。',
    descEn: 'See how 10× leverage wipes out naive strategies under real exchange rules.',
    badgeZh: '10× 高危演示',
    badgeEn: '10× Danger',
  },
};

export const BeginnerModeView: React.FC<BeginnerModeViewProps> = ({
  overview,
  onOpenProMode,
}) => {
  const { bi } = useI18n();
  const [tab, setTab] = useState<SimpleTab>('checkup');

  // Section 1: 1-Click Checkup state
  const [riskProfile, setRiskProfile] = useState<RiskProfile>('safe');
  const [virtualCapital, setVirtualCapital] = useState<number>(10_000);
  const [arena, setArena] = useState<StrategyArenaReport | null>(null);
  const [wf, setWf] = useState<WalkForwardReport | null>(null);
  const [checkupBusy, setCheckupBusy] = useState(false);

  // Section 2: Liquidation Simulator state
  const [simLev, setSimLev] = useState<number>(10);
  const [simDrop, setSimDrop] = useState<number>(12);
  const [simResult, setSimResult] = useState<ExecutionSimPayload | null>(null);
  const [simBusy, setSimBusy] = useState(false);

  // Section 3: Pitfalls Interactive Lab state
  const [btDemo, setBtDemo] = useState<BitemporalAuditDemoResult | null>(null);
  const [costDemo, setCostDemo] = useState<PaperExecutionCostBreakdown | null>(null);
  const [pitfallBusy, setPitfallBusy] = useState(false);

  function friendlyStrategyName(id: StrategyId, mode: 'qp_optimized' | 'legacy_sign_rule') {
    if (mode === 'legacy_sign_rule') {
      return bi('普通散户满仓乱冲法（对照组）', 'Naive 100% All-In Rule (Baseline)');
    }
    if (id === 'perp_carry_funding') {
      return bi('稳健策略 A：永续资金费率套利', 'Strategy A: Perpetual Funding Carry');
    }
    if (id === 'volume_clock_ofi') {
      return bi('稳健策略 B：大单资金流反转', 'Strategy B: Order-Flow Reversion');
    }
    return bi('稳健策略 C：宏观事件波动率套利', 'Strategy C: Macro Volatility Premia');
  }

  function friendlyGateQuestion(
    gate: WalkForwardReport['gates'][number],
    report: WalkForwardReport,
  ): { question: string; answer: string } {
    switch (gate.id) {
      case 'liquidation_survival':
        return {
          question: bi('半夜突然暴跌插针，会不会爆仓归零？', 'Will a sudden flash crash liquidate me?'),
          answer: report.liquidated
            ? bi('会！测试中已经触发交易所强制平仓，绝不能用。', 'Yes! Liquidated during stress test — do not use.')
            : bi('不会，所有剧烈插针都安全扛住了，0 次爆仓。', 'No — survived every intraday flash wick with 0 liquidations.'),
        };
      case 'oos_decay_guard':
        return {
          question: bi('拿到从未见过的未来行情里，还灵不灵？', 'Does it still work on unseen future data?'),
          answer:
            gate.severity === 'pass'
              ? bi(
                  `表现扎实，盲测夏普 ${report.meanOosSharpe.toFixed(2)}，没有明显失效。`,
                  `Solid unseen performance (OOS Sharpe ${report.meanOosSharpe.toFixed(2)}).`
                )
              : bi(
                  `样本外有衰减（盲测夏普 ${report.meanOosSharpe.toFixed(2)}），建议先纸面观察别急着重仓。`,
                  `Noticeable decay on unseen data (OOS Sharpe ${report.meanOosSharpe.toFixed(2)}); keep in paper testing.`
                ),
        };
      case 'deflated_sharpe':
        return {
          question: bi('赚钱是真本事，还是撞大运蒙的？', 'Is the return real skill or just luck?'),
          answer:
            gate.severity === 'pass'
              ? bi(
                  `可信度高达 ${(report.deflatedSharpeRatio * 100).toFixed(0)}%，经得起多重试错检验。`,
                  `High statistical confidence (${(report.deflatedSharpeRatio * 100).toFixed(0)}% DSR).`
                )
              : bi(
                  `扣除多次试错运气成分后可信度为 ${(report.deflatedSharpeRatio * 100).toFixed(0)}%，还需更多数据验证。`,
                  `After adjusting for trial luck, confidence is ${(report.deflatedSharpeRatio * 100).toFixed(0)}% — needs more data.`
                ),
        };
      case 'turnover_cost_efficiency':
        return {
          question: bi('手续费和滑点有没有把利润全吃光？', 'Do fees and slippage eat all the profit?'),
          answer:
            gate.severity === 'pass'
              ? bi(
                  `控制得很好！整个周期总交易磨损仅 -${report.totalCostDragPct.toFixed(2)}%。`,
                  `Well controlled — total trading friction is only -${report.totalCostDragPct.toFixed(2)}%.`
                )
              : bi(
                  `交易磨损达到 -${report.totalCostDragPct.toFixed(2)}%，换手偏频，需要降低调仓频率。`,
                  `Total trading friction reached -${report.totalCostDragPct.toFixed(2)}% — too much turnover.`
                ),
        };
      case 'stress_regime_drawdown':
        return {
          question: bi('遇到极端大跌行情，最惨会亏多少？', 'How bad is the worst crash drawdown?'),
          answer: bi(
            `历史上从最高点最多回撤过 ${report.overallMaxDrawdownPct.toFixed(1)}%（合格线 ≤ 20%）。`,
            `Worst peak-to-trough drop was ${report.overallMaxDrawdownPct.toFixed(1)}% (limit <= 20%).`
          ),
        };
      case 'oos_fold_consistency':
        return {
          question: bi('把时间切成 5 段盲测，有几段是赚钱的？', 'How many of the 5 unseen time slices were profitable?'),
          answer: bi(
            `5 段独立盲测里有 ${report.oosProfitableFoldRatePct.toFixed(0)}% 的时段赚到了钱。`,
            `${report.oosProfitableFoldRatePct.toFixed(0)}% of unseen chronological slices finished positive.`
          ),
        };
      default:
        return { question: gate.id, answer: gate.observedText };
    }
  }

  async function runCheckup(profile: RiskProfile) {
    setRiskProfile(profile);
    setCheckupBusy(true);
    const cfg = RISK_CONFIGS[profile];
    try {
      const aRes = await fetch('/api/engine/arena', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          periods: 280,
          targetAnnualVol: cfg.vol,
          maxLeverage: cfg.lev,
          linearCostBps: cfg.cost,
          seed: 2026,
        }),
      });
      const aData = (await aRes.json()) as StrategyArenaReport;
      if (aRes.ok) {
        setArena(aData);
        const top = aData.competitors[0];
        if (top) {
          const wRes = await fetch('/api/engine/walk-forward', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              strategyId: top.strategyId,
              optimizerMode: top.optimizerMode,
              periods: 280,
              numFolds: 5,
              purgeGapBars: 6,
              embargoBars: 4,
              targetAnnualVol: cfg.vol,
              maxLeverage: cfg.lev,
              linearCostBps: cfg.cost,
              seed: 2026,
            }),
          });
          const wData = (await wRes.json()) as WalkForwardReport;
          if (wRes.ok) setWf(wData);
        }
      }
    } finally {
      setCheckupBusy(false);
    }
  }

  async function runLiquidationCheck(lev: number, drop: number) {
    setSimLev(lev);
    setSimDrop(drop);
    setSimBusy(true);
    try {
      const res = await fetch('/api/tools/execution-sim', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          midPrice: 92000,
          topLevelContracts: 35,
          childContracts: 120,
          leverage: lev,
          crashDrawdownPct: drop,
          side: 'long',
        }),
      });
      const data = (await res.json()) as ExecutionSimPayload;
      if (res.ok) setSimResult(data);
    } finally {
      setSimBusy(false);
    }
  }

  async function loadPitfallDemos() {
    setPitfallBusy(true);
    try {
      const [btRes, costRes] = await Promise.all([
        fetch('/api/engine/bitemporal-asof', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sourceId: 'fred' }),
        }),
        fetch('/api/tools/execution-cost', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            price: 92000,
            quantityContracts: 500,
            contractValue: 0.01,
            side: 'buy',
            executionRole: 'taker',
            spreadBps: 1.5,
            marketSlippageBps: 1.0,
            impactCoefficientBps: 5.0,
            orderBookDepthContracts: 120,
            dailyVolBps: 320,
            advContracts: 500000,
            holdingHours: 0.5,
            entryTimestampIso: '2026-11-18T07:45:00Z',
            fundingRateBpsPer8h: 1.0,
            roundTrip: true,
          }),
        }),
      ]);
      if (btRes.ok) setBtDemo((await btRes.json()) as BitemporalAuditDemoResult);
      if (costRes.ok) setCostDemo((await costRes.json()) as PaperExecutionCostBreakdown);
    } finally {
      setPitfallBusy(false);
    }
  }

  useEffect(() => {
    void runCheckup('safe');
  }, []);

  useEffect(() => {
    if (tab === 'liquidation' && !simResult) {
      void runLiquidationCheck(10, 12);
    } else if (tab === 'pitfalls' && (!btDemo || !costDemo)) {
      void loadPitfallDemos();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const capitalScale = virtualCapital / 100_000;
  const winner = arena?.competitors[0] ?? null;
  const baseline =
    arena?.competitors.find((c) => c.optimizerMode === 'legacy_sign_rule') ?? null;

  return (
    <div className="space-y-6">
      {/* Friendly Hero Header */}
      <section className="bg-white border border-slate-200 rounded-xl p-5 sm:p-6">
        <div className="space-y-1.5 max-w-3xl">
          <div className="text-xs font-semibold text-blue-700">
            {bi('MyQuant 小白简易版 · 纯模拟零风险', 'MyQuant Simple Mode · Paper-Only Sandbox')}
          </div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
            {bi('不懂量化公式，也能 1 分钟看懂策略靠不靠谱', 'Understand Quant Risk in 60 Seconds — Zero Math Jargon')}
          </h1>
          <p className="text-sm text-slate-600 leading-relaxed">
            {bi(
              '底层跑的是同一套机构级防爆仓、防偷看未来、真滑点引擎，只是把晦涩术语全部翻译成大白话和红绿灯评分，帮你在真正投入一分钱前先排雷。',
              'Powered by the exact same institutional liquidation, lookahead-guard, and order-book engine — translated into plain language and traffic-light scores.'
            )}
          </p>
        </div>
      </section>

      {/* 3 Big Clear Tabs */}
      <nav
        aria-label={bi('简易版功能导航', 'Simple mode navigation')}
        className="grid grid-cols-1 sm:grid-cols-3 gap-3"
      >
        {(
          [
            {
              id: 'checkup',
              icon: ShieldCheck,
              titleZh: '① 策略体检室',
              titleEn: '1. Strategy Checkup',
              subZh: '选风险偏好，自动比出最稳方案',
              subEn: 'Pick risk level, get a 0–100 score',
            },
            {
              id: 'liquidation',
              icon: Flame,
              titleZh: '② 爆仓体验馆',
              titleEn: '2. Liquidation Simulator',
              subZh: '调杠杆看插针为什么会瞬间归零',
              subEn: 'See why high leverage wipes accounts',
            },
            {
              id: 'pitfalls',
              icon: GraduationCap,
              titleZh: '③ 3 分钟避坑课',
              titleEn: '3. 3-Min Quant Pitfalls',
              subZh: '实测偷看未来、幸存者偏差与大单滑点',
              subEn: 'Live demos of 3 classic quant traps',
            },
          ] as const
        ).map((item) => {
          const Icon = item.icon;
          const active = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              aria-current={active ? 'page' : undefined}
              onClick={() => setTab(item.id)}
              className={`text-left p-4 rounded-xl border transition-colors flex items-start gap-3 ${
                active
                  ? 'bg-blue-50/70 border-blue-300 ring-1 ring-blue-200'
                  : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/70'
              }`}
            >
              <Icon
                className={`w-5 h-5 shrink-0 mt-0.5 ${active ? 'text-blue-700' : 'text-slate-400'}`}
                aria-hidden="true"
              />
              <div>
                <div
                  className={`text-sm font-semibold ${active ? 'text-blue-900' : 'text-slate-900'}`}
                >
                  {bi(item.titleZh, item.titleEn)}
                </div>
                <div className="text-xs text-slate-600 mt-0.5">{bi(item.subZh, item.subEn)}</div>
              </div>
            </button>
          );
        })}
      </nav>

      {/* ===================================================================== */}
      {/* TAB 1: 策略体检室                                                     */}
      {/* ===================================================================== */}
      {tab === 'checkup' && (
        <div className="space-y-6">
          {/* Step 1: Pick risk profile & virtual money */}
          <section className="bg-white border border-slate-200 rounded-xl p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  {bi('第一步：选择你的风格与模拟本金', 'Step 1: Choose Your Risk Style & Virtual Capital')}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {bi(
                    '点一下卡片，系统会自动在真实滑点与强平规则下跑完 4 套策略并打出体检分。',
                    'Click a risk profile to benchmark 4 strategies under realistic slippage and liquidation rules.'
                  )}
                </p>
              </div>
              <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-lg self-start">
                {[10_000, 50_000, 100_000].map((amt) => (
                  <button
                    key={amt}
                    type="button"
                    onClick={() => setVirtualCapital(amt)}
                    className={`px-3 py-1.5 text-xs font-mono font-medium rounded-md transition-colors whitespace-nowrap ${
                      virtualCapital === amt
                        ? 'bg-white text-slate-900 shadow-xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    ${amt.toLocaleString('en-US')}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {(['safe', 'balanced', 'aggressive'] as const).map((key) => {
                const cfg = RISK_CONFIGS[key];
                const selected = riskProfile === key;
                return (
                  <button
                    key={key}
                    type="button"
                    disabled={checkupBusy}
                    onClick={() => void runCheckup(key)}
                    className={`text-left p-4 rounded-lg border transition-colors space-y-2 ${
                      selected
                        ? key === 'aggressive'
                          ? 'bg-rose-50/60 border-rose-300 ring-1 ring-rose-200'
                          : 'bg-blue-50/60 border-blue-300 ring-1 ring-blue-200'
                        : 'bg-slate-50/50 border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-slate-900">
                        {bi(cfg.titleZh, cfg.titleEn)}
                      </span>
                      <span
                        className={`text-[11px] font-mono font-semibold whitespace-nowrap ${
                          key === 'aggressive'
                            ? 'text-rose-700'
                            : key === 'safe'
                              ? 'text-emerald-700'
                              : 'text-blue-700'
                        }`}
                      >
                        {bi(cfg.badgeZh, cfg.badgeEn)}
                      </span>
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed">
                      {bi(cfg.descZh, cfg.descEn)}
                    </p>
                  </button>
                );
              })}
            </div>
          </section>

          {/* Step 2: Big Plain-Language Result & Side-by-Side Comparison */}
          {checkupBusy && (!winner || !wf) && (
            <section className="bg-white border border-slate-200 rounded-xl p-6 space-y-4 animate-pulse">
              <div className="h-5 w-52 bg-slate-200 rounded" />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="h-28 bg-slate-100 rounded-lg" />
                <div className="h-28 bg-slate-100 rounded-lg" />
              </div>
              <div className="text-xs text-slate-500">
                {bi('正在用机构风控引擎实时盲测 4 套策略…', 'Benchmarking 4 strategies on real risk engine…')}
              </div>
            </section>
          )}

          {winner && wf && (
            <>
              <section className={`bg-white border border-slate-200 rounded-xl p-6 space-y-6 transition-opacity ${checkupBusy ? 'opacity-65' : 'opacity-100'}`}>
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-5 border-b border-slate-200">
                  <div className="space-y-1">
                    <div className="text-xs font-medium text-slate-500">
                      {bi('系统自动筛选出的本轮最稳方案', 'TOP-SCORING STRATEGY FOR THIS PROFILE')}
                    </div>
                    <h2 className="text-xl font-bold text-slate-900">
                      {friendlyStrategyName(winner.strategyId, winner.optimizerMode)}
                    </h2>
                  </div>

                  <div className="flex items-center gap-6">
                    <div>
                      <div className="text-xs text-slate-500">{bi('安全健康评分', 'Safety Score')}</div>
                      <div className="text-3xl font-bold font-mono tabular-nums text-slate-900">
                        {winner.healthScore}
                        <span className="text-sm font-normal text-slate-400"> / 100</span>
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">{bi('红绿灯建议', 'Recommendation')}</div>
                      <div
                        className={`text-base font-bold mt-1 ${
                          winner.releaseVerdict === 'paper_ready'
                            ? 'text-emerald-700'
                            : winner.releaseVerdict === 'needs_tuning'
                              ? 'text-amber-700'
                              : 'text-rose-700'
                        }`}
                      >
                        {winner.releaseVerdict === 'paper_ready'
                          ? bi('绿灯 · 可纸面跟单观察', 'GREEN · Paper Ready')
                          : winner.releaseVerdict === 'needs_tuning'
                            ? bi('黄灯 · 建议继续模拟观察', 'YELLOW · Keep in Paper')
                            : bi('红灯 · 风险过高禁止使用', 'RED · Do Not Use')}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Human-readable Money Summary Cards: Institutional Winner vs Naive All-In */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {(() => {
                    const winEnd =
                      (winner.equityCurve[winner.equityCurve.length - 1] ?? 100_000) * capitalScale;
                    const winPnl = winEnd - virtualCapital;
                    const baseEnd = baseline
                      ? (baseline.equityCurve[baseline.equityCurve.length - 1] ?? 100_000) *
                        capitalScale
                      : virtualCapital;
                    const basePnl = baseEnd - virtualCapital;

                    return (
                      <>
                        <div className="p-5 rounded-lg bg-blue-50/40 border border-blue-200 space-y-3">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-blue-900">
                              {bi('机构稳健方案（自动控仓 + 防无效折腾）', 'Institutional QP Strategy (Recommended)')}
                            </span>
                            <span className="font-mono font-semibold text-emerald-700">
                              {winner.liquidated ? bi('爆仓', 'Liquidated') : bi('0 爆仓', '0 Liquidations')}
                            </span>
                          </div>
                          <div className="flex items-baseline gap-3">
                            <span className="text-2xl font-bold font-mono tabular-nums text-slate-900">
                              ${Math.round(winEnd).toLocaleString('en-US')}
                            </span>
                            <span
                              className={`text-sm font-mono font-semibold ${
                                winPnl >= 0 ? 'text-emerald-700' : 'text-rose-700'
                              }`}
                            >
                              {winPnl >= 0 ? '+' : '-'}$
                              {Math.abs(Math.round(winPnl)).toLocaleString('en-US')}
                            </span>
                          </div>
                          <div className="text-xs text-slate-600 space-y-1">
                            <div>
                              {bi(
                                `最惨回撤：-${winner.overallMaxDrawdownPct.toFixed(1)}% · 手续费总损耗：-${winner.totalCostDragPct.toFixed(2)}%`,
                                `Worst Drawdown: -${winner.overallMaxDrawdownPct.toFixed(1)}% · Total Fees: -${winner.totalCostDragPct.toFixed(2)}%`
                              )}
                            </div>
                          </div>
                        </div>

                        <div className="p-5 rounded-lg bg-slate-50 border border-slate-200 space-y-3">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-slate-700">
                              {bi('对照组：普通满仓反手土法（不做仓位管理）', 'Baseline: Naive 100% All-In Sign Rule')}
                            </span>
                            <span
                              className={`font-mono font-semibold ${
                                baseline?.liquidated ? 'text-rose-700' : 'text-amber-700'
                              }`}
                            >
                              {baseline?.liquidated
                                ? bi('已爆仓归零！', 'LIQUIDATED!')
                                : bi('高磨损', 'High Cost')}
                            </span>
                          </div>
                          <div className="flex items-baseline gap-3">
                            <span
                              className={`text-2xl font-bold font-mono tabular-nums ${
                                baseline?.liquidated ? 'text-rose-700' : 'text-slate-700'
                              }`}
                            >
                              ${Math.round(baseEnd).toLocaleString('en-US')}
                            </span>
                            <span
                              className={`text-sm font-mono font-semibold ${
                                basePnl >= 0 ? 'text-emerald-700' : 'text-rose-700'
                              }`}
                            >
                              {basePnl >= 0 ? '+' : '-'}$
                              {Math.abs(Math.round(basePnl)).toLocaleString('en-US')}
                            </span>
                          </div>
                          <div className="text-xs text-slate-600">
                            {baseline
                              ? bi(
                                  `最惨回撤：-${baseline.overallMaxDrawdownPct.toFixed(1)}% · 光手续费和滑点就白交了 -${baseline.totalCostDragPct.toFixed(2)}%`,
                                  `Worst Drawdown: -${baseline.overallMaxDrawdownPct.toFixed(1)}% · Bleeds -${baseline.totalCostDragPct.toFixed(2)}% in fees & impact`
                                )
                              : '—'}
                          </div>
                        </div>
                      </>
                    );
                  })()}
                </div>

                {/* Simple 2-line Virtual Money Chart */}
                {baseline && (
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span className="font-semibold text-slate-800">
                        {bi(
                          `假设投入 $${virtualCapital.toLocaleString('en-US')} 虚拟本金的资金走势对比`,
                          `Virtual $${virtualCapital.toLocaleString('en-US')} Account Trajectory`
                        )}
                      </span>
                      <div className="flex items-center gap-4 text-[11px] font-mono">
                        <span className="text-blue-700 font-medium">
                          — {bi('机构稳健方案', 'Institutional QP')}
                        </span>
                        <span className="text-slate-500">
                          --- {bi('普通满仓乱冲法', 'Naive All-In Rule')}
                        </span>
                      </div>
                    </div>
                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                      {(() => {
                        const winCurve = winner.equityCurve.map((v) => v * capitalScale);
                        const baseCurve = baseline.equityCurve.map((v) => v * capitalScale);
                        const minV = Math.min(...winCurve, ...baseCurve, virtualCapital * 0.85);
                        const maxV = Math.max(...winCurve, ...baseCurve, virtualCapital * 1.05);
                        const startY =
                          170 -
                          16 -
                          ((virtualCapital - minV) / Math.max(1e-9, maxV - minV)) * (170 - 32);
                        return (
                          <svg
                            viewBox="0 0 600 170"
                            className="w-full h-auto"
                            role="img"
                            aria-label="Simple mode equity comparison"
                          >
                            <line
                              x1="20"
                              y1={startY}
                              x2="580"
                              y2={startY}
                              stroke="#CBD5E1"
                              strokeDasharray="3 3"
                            />
                            <polyline
                              fill="none"
                              stroke="#94A3B8"
                              strokeWidth="2"
                              strokeDasharray="5 4"
                              points={buildPolyline(baseCurve, 600, 170, 20, 16, minV, maxV)}
                            />
                            <polyline
                              fill="none"
                              stroke="#1D4ED8"
                              strokeWidth="2.6"
                              points={buildPolyline(winCurve, 600, 170, 20, 16, minV, maxV)}
                            />
                          </svg>
                        );
                      })()}
                    </div>
                  </div>
                )}

                {/* 6 Plain-Language Q&A Health Check Cards */}
                <div className="space-y-3 pt-2">
                  <h3 className="text-sm font-semibold text-slate-900">
                    {bi('6 个大白话体检问题（帮你逐条排雷）', '6 Plain-Language Safety Checks')}
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {wf.gates.map((gate) => {
                      const qa = friendlyGateQuestion(gate, wf);
                      return (
                        <div
                          key={gate.id}
                          className="p-4 rounded-lg border border-slate-200 bg-slate-50/40 flex items-start gap-3"
                        >
                          {gate.severity === 'pass' ? (
                            <CheckCircle2
                              className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5"
                              aria-hidden="true"
                            />
                          ) : gate.severity === 'warn' ? (
                            <AlertTriangle
                              className="w-4 h-4 text-amber-600 shrink-0 mt-0.5"
                              aria-hidden="true"
                            />
                          ) : (
                            <XCircle
                              className="w-4 h-4 text-rose-600 shrink-0 mt-0.5"
                              aria-hidden="true"
                            />
                          )}
                          <div className="space-y-1 text-xs">
                            <div className="font-semibold text-slate-900">{qa.question}</div>
                            <div className="text-slate-600 leading-relaxed">{qa.answer}</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </section>
            </>
          )}
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB 2: 爆仓体验馆                                                     */}
      {/* ===================================================================== */}
      {tab === 'liquidation' && (
        <div className="space-y-6">
          <section className="bg-white border border-slate-200 rounded-xl p-6 space-y-5">
            <div>
              <h2 className="text-base font-semibold text-slate-900">
                {bi('为什么「看对了大方向」还是会爆仓？动手试一下就明白', 'Why High Leverage Wipes You Out Even When Price Recovers')}
              </h2>
              <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                {bi(
                  '下面模拟一个真实的币圈行情：先突然往下急跌插针，随后 V 型反弹创出新高。选一下你的杠杆倍数和插针深度，看看真实交易所强平机制和「不靠谱回测软件」的天壤之别。',
                  'Simulates a realistic V-shaped flash crash followed by a full rebound. Pick leverage and flash-wick size to compare real OKX forced liquidation vs. naive backtests.'
                )}
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-2">
              <div className="space-y-2">
                <div className="text-xs font-semibold text-slate-800">
                  {bi('1. 你开几倍杠杆？', '1. Choose Leverage')}
                </div>
                <div className="grid grid-cols-4 gap-2">
                  {[2, 5, 10, 15].map((lv) => (
                    <button
                      key={lv}
                      type="button"
                      disabled={simBusy}
                      onClick={() => void runLiquidationCheck(lv, simDrop)}
                      className={`py-2.5 text-xs font-mono font-semibold rounded-lg border transition-colors ${
                        simLev === lv
                          ? lv >= 10
                            ? 'bg-rose-600 text-white border-rose-600'
                            : 'bg-blue-700 text-white border-blue-700'
                          : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                      }`}
                    >
                      {lv}×
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-xs font-semibold text-slate-800">
                  {bi('2. 盘中突然急跌插针多少？', '2. Intraday Flash-Wick Drop')}
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {[6, 12, 18].map((dp) => (
                    <button
                      key={dp}
                      type="button"
                      disabled={simBusy}
                      onClick={() => void runLiquidationCheck(simLev, dp)}
                      className={`py-2.5 text-xs font-mono font-semibold rounded-lg border transition-colors ${
                        simDrop === dp
                          ? 'bg-slate-900 text-white border-slate-900'
                          : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                      }`}
                    >
                      -{dp}%
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {simBusy && !simResult && (
            <section className="bg-white border border-slate-200 rounded-xl p-6 space-y-4 animate-pulse">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="h-28 bg-slate-100 rounded-lg" />
                <div className="h-28 bg-slate-100 rounded-lg" />
              </div>
              <div className="text-xs text-slate-500">
                {bi('正在按 OKX 梯度保证金规则模拟盘中插针…', 'Simulating intraday flash crash under OKX tiered margin…')}
              </div>
            </section>
          )}

          {simResult && (
            <section className={`bg-white border border-slate-200 rounded-xl p-6 space-y-5 transition-opacity ${simBusy ? 'opacity-65' : 'opacity-100'}`}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div
                  className={`p-5 rounded-lg border space-y-2 ${
                    simResult.marginStress.liquidated
                      ? 'bg-rose-50/70 border-rose-200'
                      : 'bg-emerald-50/60 border-emerald-200'
                  }`}
                >
                  <div className="text-xs font-semibold text-slate-800">
                    {bi('真实交易所结果（OKX 阶梯保证金强平规则）', 'Real Exchange Outcome (OKX Tiered Margin)')}
                  </div>
                  <div
                    className={`text-3xl font-bold font-mono tabular-nums ${
                      simResult.marginStress.liquidated ? 'text-rose-700' : 'text-emerald-700'
                    }`}
                  >
                    $
                    {Math.round(simResult.marginStress.finalEquity * capitalScale).toLocaleString(
                      'en-US',
                    )}
                  </div>
                  <p className="text-xs text-slate-700 leading-relaxed">
                    {simResult.marginStress.liquidated
                      ? bi(
                          `悲剧！开 ${simLev}× 杠杆遇到 -${simDrop}% 插针直接被强平出局，哪怕后面行情暴涨也和你毫无关系了。`,
                          `Wiped out! At ${simLev}× leverage, a -${simDrop}% flash wick triggers forced liquidation before the market rebounds.`
                        )
                      : bi(
                          `安全过关！${simLev}× 杠杆的保证金足够厚，成功扛过 -${simDrop}% 插针并吃到了后续反弹。`,
                          `Survived! ${simLev}× leverage maintained enough margin buffer to survive the -${simDrop}% wick and capture the rebound.`
                        )}
                  </p>
                </div>

                <div className="p-5 rounded-lg border border-slate-200 bg-slate-50 space-y-2">
                  <div className="text-xs font-semibold text-slate-600">
                    {bi('市面上「普通回测软件」骗你的假结果', 'Fake Result Shown by Naive Backtesters')}
                  </div>
                  <div className="text-3xl font-bold font-mono tabular-nums text-slate-700">
                    $
                    {Math.round(
                      simResult.marginStress.naiveNoMarginFinalEquity * capitalScale,
                    ).toLocaleString('en-US')}
                  </div>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    {bi(
                      '普通回测只看收盘价、不算盘中保证金，所以它以为你完美扛过了大跌还大赚一笔——这就是为什么很多人「回测赚翻、实盘归零」。',
                      'Naive backtests ignore intraday maintenance margin and assume you held through the crash — creating dangerous false confidence.'
                    )}
                  </p>
                </div>
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono">
                  <span
                    className={
                      simResult.marginStress.liquidated
                        ? 'text-rose-700 font-semibold'
                        : 'text-emerald-700 font-semibold'
                    }
                  >
                    — {bi('真实账户余额（含强平）', 'Real Account (With Liquidation)')}
                  </span>
                  <span className="text-slate-500">
                    --- {bi('普通回测假象曲线', 'Naive Backtest Illusion')}
                  </span>
                </div>
                {(() => {
                  const realEq = simResult.marginStress.equityCurve.map((p) => p.equity);
                  const naiveEq = simResult.marginStress.equityCurve.map((p) => p.naiveEquity);
                  const minEq = Math.min(...realEq, ...naiveEq, 0);
                  const maxEq = Math.max(...realEq, ...naiveEq, 110_000);
                  return (
                    <svg
                      viewBox="0 0 560 150"
                      className="w-full h-auto"
                      role="img"
                      aria-label="Simple liquidation comparison chart"
                    >
                      <polyline
                        fill="none"
                        stroke="#94A3B8"
                        strokeWidth="2"
                        strokeDasharray="5 4"
                        points={buildPolyline(naiveEq, 560, 150, 20, 14, minEq, maxEq)}
                      />
                      <polyline
                        fill="none"
                        stroke={simResult.marginStress.liquidated ? '#DC2626' : '#059669'}
                        strokeWidth="2.6"
                        points={buildPolyline(realEq, 560, 150, 20, 14, minEq, maxEq)}
                      />
                    </svg>
                  );
                })()}
              </div>
            </section>
          )}
        </div>
      )}

      {/* ===================================================================== */}
      {/* TAB 3: 3 分钟避坑课                                                   */}
      {/* ===================================================================== */}
      {tab === 'pitfalls' && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Pitfall 1: Lookahead Bias */}
          <article className="bg-white border border-slate-200 rounded-xl p-6 flex flex-col justify-between gap-4">
            <div className="space-y-3">
              <div className="text-xs font-mono font-semibold text-rose-700">
                {bi('大坑 #1 · 偷看未来', 'TRAP #1 · LOOKAHEAD')}
              </div>
              <h3 className="text-base font-bold text-slate-900">
                {bi('用「明天的报纸」炒今天的股', 'Trading Today With Tomorrow’s Data')}
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                {bi(
                  '美联储 FRED 的信用利差等宏观数据要延迟 48 小时才公布。如果直接按日期对齐，回测就在偷偷用「当时根本还没发布」的数据赚钱。',
                  'Macro data like FRED credit spreads post 48 hours late. Naive date joins accidentally use data that was not public yet.'
                )}
              </p>
            </div>

            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-1">
              <div className="text-slate-500">{bi('本系统实测结果（FRED 真实延迟）：', 'Live Kernel Audit (FRED):')}</div>
              <div className="font-mono font-bold text-rose-700">
                {btDemo
                  ? bi(
                      `传统拼接 ${btDemo.rowsWithLookaheadLeak}/${btDemo.rowsEvaluated} 天全部偷看了未来！`,
                      `Naive join leaked future data on ${btDemo.rowsWithLookaheadLeak}/${btDemo.rowsEvaluated} days!`
                    )
                  : pitfallBusy
                    ? bi('正在实测…', 'Auditing…')
                    : '—'}
              </div>
              <div className="text-emerald-700 font-medium">
                {bi('本系统防线：写入时强制锁定 48h 延迟，彻底堵死。', 'Our Fix: Kernel blocks fake zero-lag writes at storage layer.')}
              </div>
            </div>
          </article>

          {/* Pitfall 2: Survivorship & Data Mining */}
          <article className="bg-white border border-slate-200 rounded-xl p-6 flex flex-col justify-between gap-4">
            <div className="space-y-3">
              <div className="text-xs font-mono font-semibold text-amber-700">
                {bi('大坑 #2 · 幸存者偏差', 'TRAP #2 · DATA MINING')}
              </div>
              <h3 className="text-base font-bold text-slate-900">
                {bi('试 100 次总有 5 次碰巧赚钱', 'Test 100 Random Ideas, 5 Look Lucky')}
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                {bi(
                  '很多人跑 50 组参数，把亏钱的 49 组偷偷删掉，只晒最赚钱的那 1 组。一旦真金白银跟进去立刻亏钱。',
                  'Deleting failed experiments makes random luck look like alpha. Every single failed trial must count against your significance bar.'
                )}
              </p>
            </div>

            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-1">
              <div className="text-slate-500">{bi('本实验室真实统计数据：', 'Real Lab Audit Stats:')}</div>
              <div className="font-mono font-bold text-slate-900">
                {overview
                  ? bi(
                      `共实测 ${overview.audit.family_size} 条跨市场规律 → 严审后仅 ${overview.audit.holm_survivors} 条过关`,
                      `${overview.audit.family_size} edges tested → only ${overview.audit.holm_survivors} survived Holm`
                    )
                  : '—'}
              </div>
              <div className="text-emerald-700 font-medium">
                {bi('本系统防线：所有失败试验永久上链，绝不隐瞒。', 'Our Fix: Append-only Merkle ledger + Online LORD++ FDR.')}
              </div>
            </div>
          </article>

          {/* Pitfall 3: Hidden Big-Order Slippage */}
          <article className="bg-white border border-slate-200 rounded-xl p-6 flex flex-col justify-between gap-4">
            <div className="space-y-3">
              <div className="text-xs font-mono font-semibold text-blue-700">
                {bi('大坑 #3 · 隐形滑点黑洞', 'TRAP #3 · LIQUIDITY CLIFF')}
              </div>
              <h3 className="text-base font-bold text-slate-900">
                {bi('大单砸穿盘口，手续费翻倍暴涨', 'Big Orders Smash Through Thin Order Books')}
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                {bi(
                  '小钱买 1 张不会影响价格，但一次性买 500 张会瞬间把卖一到卖十全吃光，成交价远远差于屏幕上的挂单价。',
                  'Small orders pay minimal spread, but a 500-contract sweep eats multiple book levels and drives true slippage far above a fixed 5 bps estimate.'
                )}
              </p>
            </div>

            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-1">
              <div className="text-slate-500">{bi('本系统实测（500 张砸 120 张盘口）：', 'Live Cost Audit (500 cts vs 120 Depth):')}</div>
              <div className="font-mono font-bold text-rose-700">
                {costDemo
                  ? bi(
                      `真实总磨损 ${costDemo.totalBps.toFixed(1)} bps（单笔白亏 $${costDemo.totalUsdt.toFixed(0)}）`,
                      `True total drag ${costDemo.totalBps.toFixed(1)} bps ($${costDemo.totalUsdt.toFixed(0)} cost)`
                    )
                  : pitfallBusy
                    ? bi('正在实测…', 'Auditing…')
                    : '—'}
              </div>
              <div className="text-emerald-700 font-medium">
                {bi('本系统防线：无上限平方根冲击 + 缺深度自动惩罚。', 'Our Fix: Unbounded square-root sweep + fail-closed penalty.')}
              </div>
            </div>
          </article>
        </div>
      )}

      {/* Bottom Friendly Reminder Banner */}
      <div className="p-4 bg-slate-100/80 border border-slate-200 rounded-xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-xs text-slate-600">
        <div className="flex items-start gap-2">
          <Sparkles className="w-4 h-4 text-blue-700 shrink-0 mt-0.5" aria-hidden="true" />
          <span>
            {bi(
              '想看背后的数学细节、13 篇完整实证研究报告、市场传导图谱或 Merkle 加密哈希链？随时一键切到专业机构版。',
              'Want the underlying math, all 13 empirical study reports, market graph, and Merkle ledger? Switch to Pro Mode anytime.'
            )}
          </span>
        </div>
        <button
          type="button"
          onClick={onOpenProMode}
          className="text-blue-700 hover:text-blue-800 font-semibold whitespace-nowrap self-start sm:self-center"
        >
          {bi('进入专业机构版 →', 'Open Pro Mode →')}
        </button>
      </div>
    </div>
  );
};
