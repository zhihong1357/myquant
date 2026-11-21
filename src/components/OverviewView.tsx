import React from 'react';
import { ArrowRight, Compass, Flame, ShieldCheck } from 'lucide-react';
import type { OverviewPayload } from '../lib/types';
import type { TabId } from '../App';
import type { EngineSubTab } from './StrategyEngineView';
import type { WorkbenchSubTab } from './QuantWorkbenchView';
import { formatInteger, formatNumber, formatPValue, formatShortDate } from '../lib/format';
import { useI18n } from '../lib/i18n';

interface OverviewViewProps {
  data: OverviewPayload;
  onSelectStudy: (slug: string) => void;
  onNavigate: (
    tab: TabId,
    options?: { engineSub?: EngineSubTab; workbenchSub?: WorkbenchSubTab }
  ) => void;
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  data,
  onSelectStudy,
  onNavigate,
}) => {
  const { bi } = useI18n();
  const { counts, audit, review, calibration, failed_trials } = data;

  return (
    <div className="space-y-8">
      {/* Header summary */}
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            {bi('MyQuant 量化研究与风控总览', 'Research Intelligence Overview')}
          </h1>
          <p className="text-sm text-slate-600 mt-1 max-w-3xl leading-relaxed">
            {bi(
              '独立、严谨、纯纸面仿真的跨市场量化研究系统。所有假设先预注册再验证，失败实验永久上链留痕，绝不隐瞒未来函数、高杠杆爆仓与大单滑点。',
              'Empirical cross-market expectation transmission ledger. Paper-only, point-in-time audited, and hash-chained across all preregistered hypotheses and failed trials.'
            )}
          </p>
        </div>
        <div className="text-xs text-slate-500 font-mono tabular-nums whitespace-nowrap">
          {bi('目录构建', 'Catalog built')} {formatShortDate(data.generated_at)} ·{' '}
          {bi('探针核验', 'Evidence probed')} {formatShortDate(data.evidence_probed_at)}
        </div>
      </div>

      {/* Beginner-Friendly 3-Step Guided Quick-Start Strip */}
      <section
        aria-label={bi('新手 3 步快速上手', '3-step quick start guide')}
        className="bg-white border border-slate-200 rounded-lg p-5 space-y-4"
      >
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">
              {bi(
                '新手 3 步快速上手：不用懂复杂公式，30 秒看懂机构级量化防坑逻辑',
                'Quick Start in 3 Clicks: Experience Institutional Quant Safeguards Instantly'
              )}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {bi(
                '点击下方任意卡片，系统已预填好典型测试场景，直接输出 0–100 分体检报告和大白话结论。',
                'Click any guided card below to launch pre-configured scenarios with live 0–100 health scorecards and plain-language diagnostics.'
              )}
            </p>
          </div>
          <span className="text-xs font-mono text-slate-500 whitespace-nowrap">
            {bi('纯纸面沙盒 · 零实盘风险', 'Paper-Only Sandbox')}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <button
            type="button"
            onClick={() => onNavigate('engine', { engineSub: 'arena' })}
            className="text-left p-4 rounded-lg border border-slate-200 hover:border-blue-300 hover:bg-blue-50/30 transition-colors flex flex-col justify-between gap-3 group"
          >
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="font-mono font-semibold text-blue-700">
                  {bi('第 1 步 · 核心体检', 'STEP 01 · ARENA')}
                </span>
                <ShieldCheck className="w-4 h-4 text-blue-700 shrink-0" aria-hidden="true" />
              </div>
              <div className="text-sm font-semibold text-slate-900">
                {bi('一键跑三策略盲测 PK', '1-Click 4-Way Walk-Forward Arena')}
              </div>
              <p className="text-xs text-slate-600 leading-relaxed">
                {bi(
                  '把 3 套可交易 QP 策略与「旧版满仓土法」拉出来同场盲测（带防泄密隔离带 Purge Gap），自动给出 0–100 分健康评分与红绿灯建议。',
                  'Benchmark all 3 tradable QP strategies against the Legacy Sign-Rule under Purged Walk-Forward folds, volatility regimes, and a 6-gate 0–100 scorecard.'
                )}
              </p>
            </div>
            <span className="inline-flex items-center gap-1 text-xs font-medium text-blue-700 group-hover:translate-x-0.5 transition-transform">
              {bi('立即开始体检', 'Launch Strategy Arena')}
              <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
            </span>
          </button>

          <button
            type="button"
            onClick={() => onNavigate('engine', { engineSub: 'execution' })}
            className="text-left p-4 rounded-lg border border-slate-200 hover:border-rose-300 hover:bg-rose-50/30 transition-colors flex flex-col justify-between gap-3 group"
          >
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="font-mono font-semibold text-rose-700">
                  {bi('第 2 步 · 实盘防爆', 'STEP 02 · STRESS TEST')}
                </span>
                <Flame className="w-4 h-4 text-rose-700 shrink-0" aria-hidden="true" />
              </div>
              <div className="text-sm font-semibold text-slate-900">
                {bi('亲眼看高杠杆插针强平与滑点', 'Simulate Flash-Wick Liquidation & L2 Sweep')}
              </div>
              <p className="text-xs text-slate-600 leading-relaxed">
                {bi(
                  '为什么回测赚翻、实盘却归零？一键对比普通回测的「无保证金幻觉」与 OKX 阶梯维持保证金强平、真实逐档吃单冲击成本。',
                  'Compare naive margin-free backtests against OKX tiered MMR forced liquidation on V-shaped flash wicks and unbounded square-root L2 book walking.'
                )}
              </p>
            </div>
            <span className="inline-flex items-center gap-1 text-xs font-medium text-rose-700 group-hover:translate-x-0.5 transition-transform">
              {bi('运行爆仓与滑点压测', 'Run Execution Stress')}
              <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
            </span>
          </button>

          <button
            type="button"
            onClick={() => onNavigate('workbench', { workbenchSub: 'lead_lag' })}
            className="text-left p-4 rounded-lg border border-slate-200 hover:border-emerald-300 hover:bg-emerald-50/30 transition-colors flex flex-col justify-between gap-3 group"
          >
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="font-mono font-semibold text-emerald-700">
                  {bi('第 3 步 · 排雷假信号', 'STEP 03 · PIT AUDIT')}
                </span>
                <Compass className="w-4 h-4 text-emerald-700 shrink-0" aria-hidden="true" />
              </div>
              <div className="text-sm font-semibold text-slate-900">
                {bi('揭穿「偷看未来」与假显著陷阱', 'Expose Lookahead Bias & False Discoveries')}
              </div>
              <p className="text-xs text-slate-600 leading-relaxed">
                {bi(
                  '体验同期因子如何把纯噪声放大成看似暴利的假 Alpha，并用 Householder QR、Andrews HAC 与有效样本量 Nₑff 把水分挤干。',
                  'See how contemporaneous common-factor leakage fabricates fake alpha, and audit signals with PIT-lagged Householder QR-HAC and effective-N MDE power.'
                )}
              </p>
            </div>
            <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 group-hover:translate-x-0.5 transition-transform">
              {bi('打开统计排雷工作台', 'Open PIT Audit Lab')}
              <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
            </span>
          </button>
        </div>
      </section>

      {/* Primary KPI Strip (single elevation, hairline dividers, zero pill clutter) */}
      <section aria-label="Laboratory metrics" className="bg-white border border-slate-200 rounded-lg">
        <div className="grid grid-cols-2 lg:grid-cols-4 divide-y lg:divide-y-0 lg:divide-x divide-slate-200">
          <div className="p-5">
            <div className="text-xs font-medium text-slate-500">
              {bi('实证研究报告', 'Empirical Studies')}
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-bold text-slate-900 font-mono tabular-nums">
                {counts.studies}
              </span>
              <span className="text-xs text-slate-500 font-mono tabular-nums">
                {bi(
                  `${counts.hypotheses} 项假设 · ${counts.trials_total} 次试验`,
                  `${counts.hypotheses} hypotheses · ${counts.trials_total} trials`
                )}
              </span>
            </div>
            <button
              type="button"
              onClick={() => onNavigate('studies')}
              className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-blue-700 hover:text-blue-800 whitespace-nowrap"
            >
              {bi('阅读完整研究报告', 'Inspect study reports')}{' '}
              <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
            </button>
          </div>

          <div className="p-5">
            <div className="text-xs font-medium text-slate-500">
              {bi('跨市场关系边', 'Market Graph Edges')}
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-bold text-slate-900 font-mono tabular-nums">
                {counts.edges_total}
              </span>
              <span className="text-xs text-slate-500 font-mono tabular-nums">
                {bi(
                  `${counts.edges_supported} 成立 · ${counts.edges_rejected} 证伪`,
                  `${counts.edges_supported} supported · ${counts.edges_rejected} rejected`
                )}
              </span>
            </div>
            <button
              type="button"
              onClick={() => onNavigate('graph')}
              className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-blue-700 hover:text-blue-800 whitespace-nowrap"
            >
              {bi(`查看 ${counts.nodes} 个资产节点`, `Explore ${counts.nodes} market nodes`)}{' '}
              <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
            </button>
          </div>

          <div className="p-5">
            <div className="text-xs font-medium text-slate-500">
              {bi('全实验室多重检验幸存边', 'Lab-Wide Multiple-Testing Survivors')}
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-bold text-emerald-700 font-mono tabular-nums">
                {audit.holm_survivors}
              </span>
              <span className="text-xs text-slate-500 font-mono tabular-nums">
                {bi(
                  `Holm · ${audit.bh_survivors} BH（共测 ${audit.family_size} 条）`,
                  `Holm · ${audit.bh_survivors} BH of ${audit.family_size} tested`
                )}
              </span>
            </div>
            <div className="mt-3 text-xs text-slate-500 font-mono tabular-nums">
              α = {audit.alpha} · {bi('未校正预期假阳性', 'E[FP uncorrected]')} ={' '}
              {audit.expected_false_positives_uncorrected}
            </div>
          </div>

          <div className="p-5">
            <div className="text-xs font-medium text-slate-500">
              {bi('对抗式独立复核 (Stage 6D)', 'Adversarial Review Audit')}
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-bold text-slate-900 font-mono tabular-nums">
                {review.counts.pass}
              </span>
              <span className="text-xs text-emerald-700 font-mono tabular-nums font-medium">
                {bi(
                  `通过 · ${review.counts.fail} 失败`,
                  `pass · ${review.counts.fail} fail`
                )}
              </span>
            </div>
            <div className="mt-3 text-xs text-slate-500 font-mono tabular-nums">
              {bi(
                `${review.counts.unverified} 未复验 · ${review.counts.note} 功效批注 · ${counts.broken_links} 断链`,
                `${review.counts.unverified} unverified · ${review.counts.note} MDE notes · ${counts.broken_links} broken links`
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Supported Edges Lab-Wide Audit Table */}
      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              {bi(
                '全实验室多重检验后真正「幸存」的统计规律（防数据挖掘过拟合）',
                'Supported Edges Under Lab-Wide Multiplicity Correction'
              )}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {bi(
                `对全部 ${audit.family_size} 条已测市场边统一做 Holm / BH 二次校正（Storey π₀ = ${formatNumber(audit.storey_pi0_lambda_0_5, 2)} · BH 假发现上界 = ${formatNumber(audit.bh_expected_false_discoveries_upper_bound, 2)} 条），防止「测 100 次总有几次碰巧显著」。`,
                `Post-hoc second-layer adjustment across all ${audit.family_size} tested market edges (Storey π₀ = ${formatNumber(audit.storey_pi0_lambda_0_5, 2)} · BH FDR upper bound = ${formatNumber(audit.bh_expected_false_discoveries_upper_bound, 2)} false discoveries).`
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onNavigate('workbench', { workbenchSub: 'multiplicity' })}
            className="text-xs font-medium text-blue-700 hover:text-blue-800 whitespace-nowrap shrink-0 self-start sm:self-auto"
          >
            {bi('去工作台用 Online LORD++ 重算', 'Recompute in Workbench')}
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs text-slate-600">
                <th className="py-2.5 px-4 font-semibold">{bi('边编号', 'Edge')}</th>
                <th className="py-2.5 px-4 font-semibold">{bi('所属研究 / 假设', 'Study / Hypothesis')}</th>
                <th className="py-2.5 px-4 font-semibold">{bi('检验设计', 'Design')}</th>
                <th className="py-2.5 px-4 font-semibold text-right">{bi('原始 p 值', 'Raw p')}</th>
                <th className="py-2.5 px-4 font-semibold text-right">{bi('Holm 校正 p', 'Holm adj. p')}</th>
                <th className="py-2.5 px-4 font-semibold text-right">{bi('BH 校正 p', 'BH adj. p')}</th>
                <th className="py-2.5 px-4 font-semibold">{bi('全局审核结论', 'Lab-Wide Status')}</th>
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
                        {bi('风险提示：', 'Caveat: ')}
                        {edge.caveat}
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
                      <span className="text-emerald-700 font-medium">
                        {bi('Holm + BH 双通过', 'Holm + BH survivor')}
                      </span>
                    ) : edge.bh_significant ? (
                      <span className="text-amber-700 font-medium">
                        {bi('仅 BH 通过 (Holm 筛掉)', 'BH only (Holm dropped)')}
                      </span>
                    ) : (
                      <span className="text-rose-700 font-medium">
                        {bi('全局多重检验淘汰', 'Dropped lab-wide')}
                      </span>
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
              {bi('统计内核蒙特卡洛校准体检 (Stage 2B)', 'Statistical Kernel Calibration (Stage 2B)')}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {bi(
                '在纯噪声和自相关环境下做上千次模拟，验证我们的检验工具本身不虚报、不漏报（目标 α=0.05 或 95% 置信区间覆盖率）。',
                'Monte Carlo validation of Newey-West HAC size, block-bootstrap coverage, and Holm FWER control under null and AR(1) / correlated settings.'
              )}
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                  <th className="py-2.5 px-4 font-semibold">{bi('校准项目', 'Diagnostic')}</th>
                  <th className="py-2.5 px-4 font-semibold text-right">{bi('理论目标', 'Target')}</th>
                  <th className="py-2.5 px-4 font-semibold text-right">{bi('实测值', 'Observed')}</th>
                  <th className="py-2.5 px-4 font-semibold text-right">{bi('蒙特卡洛误差', 'MC SE')}</th>
                  <th className="py-2.5 px-4 font-semibold text-right">{bi('模拟次数', 'Reps')}</th>
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
              {bi('永久保留的失败实验与账本异常', 'Retained Failed Trials & Ledger Exceptions')}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {bi(
                '机构级研究铁律：做砸了的实验绝不偷偷删掉，全部写入只增不改的哈希链账本，彻底杜绝幸存者偏差。',
                'Failed experiments are permanently recorded in append-only hash chains rather than deleted.'
              )}
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
                  {bi('缺失的可选完整性校验文件', 'Missing optional integrity file')}
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
