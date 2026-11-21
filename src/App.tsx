import React, { useEffect, useState } from 'react';
import {
  BarChart3,
  BookOpen,
  Cpu,
  FileCheck2,
  Globe,
  Layers,
  Menu,
  Network,
  SlidersHorizontal,
  X,
} from 'lucide-react';
import type {
  DecisionRecordSummary,
  GraphPayload,
  OverviewPayload,
  SourcesAndPanelsPayload,
  StudyListItem,
} from './lib/types';
import { LanguageProvider, useI18n } from './lib/i18n';
import { OverviewView } from './components/OverviewView';
import { MarketGraphView } from './components/MarketGraphView';
import { StudiesView } from './components/StudiesView';
import { DecisionRecordsView } from './components/DecisionRecordsView';
import { StrategyEngineView, type EngineSubTab } from './components/StrategyEngineView';
import { QuantWorkbenchView, type WorkbenchSubTab } from './components/QuantWorkbenchView';
import { BeginnerModeView } from './components/BeginnerModeView';

export type TabId = 'overview' | 'graph' | 'studies' | 'decisions' | 'engine' | 'workbench';
type AppMode = 'simple' | 'pro';

const MODE_STORAGE_KEY = 'myquant_ui_mode_v1';

function readInitialMode(): AppMode {
  if (typeof window === 'undefined') return 'simple';
  try {
    const saved = window.localStorage.getItem(MODE_STORAGE_KEY);
    if (saved === 'pro' || saved === 'simple') return saved;
  } catch {
    // Ignore storage errors inside iframes
  }
  return 'simple';
}

interface NavItemConfig {
  id: TabId;
  labelZh: string;
  labelEn: string;
  breadcrumbZh: string;
  breadcrumbEn: string;
  icon: React.FC<{ className?: string }>;
}

const NAV_ITEMS: NavItemConfig[] = [
  {
    id: 'overview',
    labelZh: '实验室总览',
    labelEn: 'Lab Overview',
    breadcrumbZh: '实验室总览',
    breadcrumbEn: 'Overview',
    icon: BarChart3,
  },
  {
    id: 'engine',
    labelZh: '策略与风控引擎',
    labelEn: 'Strategy Engine',
    breadcrumbZh: '策略体检 · 撮合风控引擎',
    breadcrumbEn: 'Strategy & Execution Engine',
    icon: Cpu,
  },
  {
    id: 'workbench',
    labelZh: '量化检验工作台',
    labelEn: 'Quant Workbench',
    breadcrumbZh: '统计检验与成本工具箱',
    breadcrumbEn: 'Statistical & Cost Workbench',
    icon: SlidersHorizontal,
  },
  {
    id: 'graph',
    labelZh: '跨市场传导图谱',
    labelEn: 'Market Graph',
    breadcrumbZh: '市场图谱与关系边',
    breadcrumbEn: 'Market Graph & Edges',
    icon: Network,
  },
  {
    id: 'studies',
    labelZh: '实证研究报告',
    labelEn: 'Studies & Reports',
    breadcrumbZh: '13 项实证研究报告',
    breadcrumbEn: 'Empirical Studies',
    icon: BookOpen,
  },
  {
    id: 'decisions',
    labelZh: '决策记录与数据源',
    labelEn: 'Decision Records',
    breadcrumbZh: '研究决策与数据探针',
    breadcrumbEn: 'Decision Records & Provenance',
    icon: FileCheck2,
  },
];

const LanguageSegmentedToggle: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  const { lang, setLang } = useI18n();
  if (compact) {
    return (
      <div
        role="group"
        aria-label="Language switch"
        className="inline-flex bg-slate-100 border border-slate-200 rounded-md p-0.5 shrink-0"
      >
        <button
          type="button"
          onClick={() => setLang('zh')}
          aria-pressed={lang === 'zh'}
          className={`px-2 py-1 text-[11px] font-medium rounded transition-colors whitespace-nowrap ${
            lang === 'zh' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          中文
        </button>
        <button
          type="button"
          onClick={() => setLang('en')}
          aria-pressed={lang === 'en'}
          className={`px-2 py-1 text-[11px] font-medium rounded transition-colors whitespace-nowrap ${
            lang === 'en' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          EN
        </button>
      </div>
    );
  }

  return (
    <div
      role="group"
      aria-label="Language switch"
      className="flex items-center justify-between gap-2 px-3 py-2 bg-slate-50 border border-slate-200 rounded-md"
    >
      <span className="flex items-center gap-1.5 text-xs font-medium text-slate-600 whitespace-nowrap">
        <Globe className="w-3.5 h-3.5 text-slate-400 shrink-0" aria-hidden="true" />
        <span>{lang === 'zh' ? '界面语言' : 'Language'}</span>
      </span>
      <div className="inline-flex bg-white border border-slate-200 rounded p-0.5 shrink-0">
        <button
          type="button"
          onClick={() => setLang('zh')}
          aria-pressed={lang === 'zh'}
          className={`px-2 py-0.5 text-[11px] font-medium rounded transition-colors whitespace-nowrap ${
            lang === 'zh'
              ? 'bg-blue-700 text-white'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          中文
        </button>
        <button
          type="button"
          onClick={() => setLang('en')}
          aria-pressed={lang === 'en'}
          className={`px-2 py-0.5 text-[11px] font-medium rounded transition-colors whitespace-nowrap ${
            lang === 'en'
              ? 'bg-blue-700 text-white'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          EN
        </button>
      </div>
    </div>
  );
};

const ModeSegmentedToggle: React.FC<{
  mode: AppMode;
  onChangeMode: (next: AppMode) => void;
  compact?: boolean;
}> = ({ mode, onChangeMode, compact = false }) => {
  const { bi } = useI18n();
  if (compact) {
    return (
      <div
        role="group"
        aria-label={bi('版本模式切换', 'Experience mode switch')}
        className="inline-flex bg-slate-100 border border-slate-200 rounded-md p-0.5 shrink-0"
      >
        <button
          type="button"
          onClick={() => onChangeMode('simple')}
          aria-pressed={mode === 'simple'}
          className={`px-2 sm:px-2.5 py-1 text-[11px] sm:text-xs font-medium rounded transition-colors whitespace-nowrap ${
            mode === 'simple'
              ? 'bg-blue-700 text-white'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          {bi('小白简易版', 'Simple')}
        </button>
        <button
          type="button"
          onClick={() => onChangeMode('pro')}
          aria-pressed={mode === 'pro'}
          className={`px-2 sm:px-2.5 py-1 text-[11px] sm:text-xs font-medium rounded transition-colors whitespace-nowrap ${
            mode === 'pro'
              ? 'bg-blue-700 text-white'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          {bi('专业机构版', 'Pro Lab')}
        </button>
      </div>
    );
  }

  return (
    <div
      role="group"
      aria-label={bi('版本模式切换', 'Experience mode switch')}
      className="flex items-center justify-between gap-2 px-3 py-2 bg-slate-50 border border-slate-200 rounded-md"
    >
      <span className="flex items-center gap-1.5 text-xs font-medium text-slate-600 whitespace-nowrap">
        <Layers className="w-3.5 h-3.5 text-slate-400 shrink-0" aria-hidden="true" />
        <span>{bi('版本', 'Mode')}</span>
      </span>
      <div className="inline-flex bg-white border border-slate-200 rounded p-0.5 shrink-0">
        <button
          type="button"
          onClick={() => onChangeMode('simple')}
          aria-pressed={mode === 'simple'}
          className={`px-2 py-0.5 text-[11px] font-medium rounded transition-colors whitespace-nowrap ${
            mode === 'simple'
              ? 'bg-blue-700 text-white'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          {bi('小白版', 'Simple')}
        </button>
        <button
          type="button"
          onClick={() => onChangeMode('pro')}
          aria-pressed={mode === 'pro'}
          className={`px-2 py-0.5 text-[11px] font-medium rounded transition-colors whitespace-nowrap ${
            mode === 'pro'
              ? 'bg-blue-700 text-white'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          {bi('专业版', 'Pro')}
        </button>
      </div>
    </div>
  );
};

const AppShell: React.FC = () => {
  const { lang, bi } = useI18n();
  const [appMode, setAppModeState] = useState<AppMode>(readInitialMode);
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [selectedStudySlug, setSelectedStudySlug] = useState<string | null>(null);
  const [engineSubTab, setEngineSubTab] = useState<EngineSubTab>('arena');
  const [workbenchSubTab, setWorkbenchSubTab] = useState<WorkbenchSubTab>('lead_lag');

  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [studies, setStudies] = useState<StudyListItem[]>([]);
  const [records, setRecords] = useState<DecisionRecordSummary[]>([]);
  const [sources, setSources] = useState<SourcesAndPanelsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function setAppMode(next: AppMode) {
    setAppModeState(next);
    setMobileMenuOpen(false);
    try {
      window.localStorage.setItem(MODE_STORAGE_KEY, next);
    } catch {
      // Ignore storage errors
    }
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch('/api/lab/overview').then((r) => {
        if (!r.ok) throw new Error('Failed to load overview');
        return r.json() as Promise<OverviewPayload>;
      }),
      fetch('/api/graph').then((r) => {
        if (!r.ok) throw new Error('Failed to load market graph');
        return r.json() as Promise<GraphPayload>;
      }),
      fetch('/api/studies').then((r) => {
        if (!r.ok) throw new Error('Failed to load studies');
        return r.json() as Promise<StudyListItem[]>;
      }),
      fetch('/api/decision-records').then((r) => {
        if (!r.ok) throw new Error('Failed to load decision records');
        return r.json() as Promise<DecisionRecordSummary[]>;
      }),
      fetch('/api/sources').then((r) => {
        if (!r.ok) throw new Error('Failed to load data sources');
        return r.json() as Promise<SourcesAndPanelsPayload>;
      }),
    ])
      .then(([ov, gr, st, dr, src]) => {
        if (!cancelled) {
          setOverview(ov);
          setGraph(gr);
          setStudies(st);
          setRecords(dr);
          setSources(src);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unable to connect to MyQuant API');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  function openStudy(slug: string) {
    setSelectedStudySlug(slug);
    setActiveTab('studies');
    setMobileMenuOpen(false);
  }

  function handleNav(
    tab: TabId,
    options?: { engineSub?: EngineSubTab; workbenchSub?: WorkbenchSubTab }
  ) {
    if (options?.engineSub) setEngineSubTab(options.engineSub);
    if (options?.workbenchSub) setWorkbenchSubTab(options.workbenchSub);
    setActiveTab(tab);
    setMobileMenuOpen(false);
  }

  // Dedicated clean shell for Simple / Beginner Edition
  if (appMode === 'simple') {
    return (
      <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
        <header className="h-14 bg-white border-b border-slate-200 px-4 sm:px-6 lg:px-8 flex items-center justify-between gap-3 sticky top-0 z-20">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-base font-bold tracking-tight text-slate-900 whitespace-nowrap">
              {bi('MyQuant', 'MyQuant')}
            </span>
            <span className="hidden sm:inline text-xs text-slate-400">·</span>
            <span className="hidden sm:inline text-xs font-medium text-slate-500 whitespace-nowrap">
              {bi('小白简易版', 'Simple Edition')}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <ModeSegmentedToggle mode={appMode} onChangeMode={setAppMode} compact />
            <LanguageSegmentedToggle compact />
          </div>
        </header>

        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-[1040px] w-full mx-auto">
          <BeginnerModeView overview={overview} onOpenProMode={() => setAppMode('pro')} />
        </main>
      </div>
    );
  }

  const currentNav = NAV_ITEMS.find((n) => n.id === activeTab) ?? NAV_ITEMS[0];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex">
      {/* Desktop Sidebar (248px) */}
      <aside className="hidden lg:flex lg:flex-col w-[248px] shrink-0 bg-white border-r border-slate-200">
        <div className="h-14 px-5 flex items-center border-b border-slate-200">
          <a
            href="#overview"
            onClick={(e) => {
              e.preventDefault();
              handleNav('overview');
            }}
            className="text-base font-bold tracking-tight text-slate-900 whitespace-nowrap shrink-0"
          >
            {bi('MyQuant 量化实验室', 'MyQuant Lab')}
          </a>
        </div>

        <nav aria-label="Primary navigation" className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                aria-current={isActive ? 'page' : undefined}
                onClick={() => handleNav(item.id)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm rounded-md transition-colors whitespace-nowrap ${
                  isActive
                    ? 'bg-blue-50 text-blue-800 font-semibold'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/80 font-medium'
                }`}
              >
                <Icon className="w-4 h-4 shrink-0" aria-hidden="true" />
                <span>{lang === 'zh' ? item.labelZh : item.labelEn}</span>
              </button>
            );
          })}
        </nav>

        <div className="p-3 border-t border-slate-200 space-y-2.5">
          <ModeSegmentedToggle mode={appMode} onChangeMode={setAppMode} />
          <LanguageSegmentedToggle />
          <p className="px-1 text-[11px] text-slate-500 leading-relaxed">
            {bi(
              '仅限纸面仿真与严谨统计检验，不包含任何实盘下单或资金接口。',
              'Paper-only research workbench. No live brokerage or order execution.'
            )}
          </p>
        </div>
      </aside>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden flex">
          <div
            className="fixed inset-0 bg-slate-900/40"
            onClick={() => setMobileMenuOpen(false)}
            aria-hidden="true"
          />
          <aside className="relative z-50 w-64 max-w-[82vw] bg-white h-full border-r border-slate-200 flex flex-col">
            <div className="h-14 px-4 flex items-center justify-between border-b border-slate-200">
              <span className="text-base font-bold tracking-tight text-slate-900">
                {bi('MyQuant 量化实验室', 'MyQuant Lab')}
              </span>
              <button
                type="button"
                aria-label={bi('关闭导航菜单', 'Close navigation menu')}
                onClick={() => setMobileMenuOpen(false)}
                className="p-2 text-slate-600 hover:text-slate-900 rounded-md"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <nav aria-label="Mobile navigation" className="flex-1 p-3 space-y-1">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-current={isActive ? 'page' : undefined}
                    onClick={() => handleNav(item.id)}
                    className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-sm rounded-md transition-colors whitespace-nowrap ${
                      isActive
                        ? 'bg-blue-50 text-blue-800 font-semibold'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100 font-medium'
                    }`}
                  >
                    <Icon className="w-4 h-4 shrink-0" aria-hidden="true" />
                    <span>{lang === 'zh' ? item.labelZh : item.labelEn}</span>
                  </button>
                );
              })}
            </nav>
            <div className="p-3 border-t border-slate-200 space-y-2.5">
              <ModeSegmentedToggle mode={appMode} onChangeMode={setAppMode} />
              <LanguageSegmentedToggle />
            </div>
          </aside>
        </div>
      )}

      {/* Main Column */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Top Bar Contract: Breadcrumb on left, 1 primary action on right */}
        <header className="h-14 bg-white border-b border-slate-200 px-4 lg:px-8 flex items-center justify-between gap-4 sticky top-0 z-20">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              aria-label={bi('打开导航菜单', 'Open navigation menu')}
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-2 -ml-2 text-slate-600 hover:text-slate-900 rounded-md"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="text-sm text-slate-500 truncate">
              <span className="font-medium text-slate-900">MyQuant</span>
              <span className="mx-2 text-slate-300">/</span>
              <span>{lang === 'zh' ? currentNav.breadcrumbZh : currentNav.breadcrumbEn}</span>
            </div>
          </div>

          <button
            type="button"
            onClick={() =>
              handleNav(activeTab === 'engine' ? 'workbench' : 'engine', {
                engineSub: 'arena',
              })
            }
            className="px-4 py-2 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md transition-colors whitespace-nowrap shrink-0"
          >
            {activeTab === 'engine'
              ? bi('打开统计检验台', 'Open Quant Workbench')
              : bi('一键策略体检', 'Open Strategy Engine')}
          </button>
        </header>

        {/* Viewport Content */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-[1360px] w-full mx-auto">
          {loading ? (
            <div className="space-y-6">
              <div className="h-8 w-64 bg-slate-200/70 rounded animate-pulse" />
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {[1, 2, 3, 4].map((k) => (
                  <div
                    key={k}
                    className="h-28 bg-white border border-slate-200 rounded-lg animate-pulse"
                  />
                ))}
              </div>
              <div className="h-72 bg-white border border-slate-200 rounded-lg animate-pulse" />
            </div>
          ) : error ? (
            <div className="bg-white border border-rose-200 rounded-lg p-6">
              <h2 className="text-base font-semibold text-rose-800">
                {bi('无法加载实验室数据', 'Unable to load lab datasets')}
              </h2>
              <p className="text-sm text-slate-600 mt-1">{error}</p>
            </div>
          ) : (
            <>
              {activeTab === 'overview' && overview && (
                <OverviewView
                  data={overview}
                  onSelectStudy={openStudy}
                  onNavigate={handleNav}
                />
              )}
              {activeTab === 'graph' && graph && (
                <MarketGraphView data={graph} onSelectStudy={openStudy} />
              )}
              {activeTab === 'studies' && (
                <StudiesView studies={studies} initialSlug={selectedStudySlug} />
              )}
              {activeTab === 'decisions' && sources && (
                <DecisionRecordsView
                  records={records}
                  sourcesData={sources}
                  onSelectStudy={openStudy}
                />
              )}
              {activeTab === 'engine' && (
                <StrategyEngineView
                  activeSubTab={engineSubTab}
                  onChangeSubTab={setEngineSubTab}
                />
              )}
              {activeTab === 'workbench' && (
                <QuantWorkbenchView
                  activeSubTab={workbenchSubTab}
                  onChangeSubTab={setWorkbenchSubTab}
                />
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
};

export const App: React.FC = () => (
  <LanguageProvider>
    <AppShell />
  </LanguageProvider>
);
