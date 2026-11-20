import React, { useEffect, useState } from 'react';
import {
  BarChart3,
  BookOpen,
  FileCheck2,
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
import { OverviewView } from './components/OverviewView';
import { MarketGraphView } from './components/MarketGraphView';
import { StudiesView } from './components/StudiesView';
import { DecisionRecordsView } from './components/DecisionRecordsView';
import { QuantWorkbenchView } from './components/QuantWorkbenchView';

type TabId = 'overview' | 'graph' | 'studies' | 'decisions' | 'workbench';

const NAV_ITEMS: Array<{
  id: TabId;
  label: string;
  breadcrumb: string;
  icon: React.FC<{ className?: string }>;
}> = [
  { id: 'overview', label: 'Lab Overview', breadcrumb: 'Overview', icon: BarChart3 },
  { id: 'graph', label: 'Market Graph', breadcrumb: 'Market Graph & Edges', icon: Network },
  { id: 'studies', label: 'Studies & Reports', breadcrumb: 'Empirical Studies', icon: BookOpen },
  {
    id: 'decisions',
    label: 'Decision Records',
    breadcrumb: 'Decision Records & Provenance',
    icon: FileCheck2,
  },
  {
    id: 'workbench',
    label: 'Quant Workbench',
    breadcrumb: 'Statistical & Cost Workbench',
    icon: SlidersHorizontal,
  },
];

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [selectedStudySlug, setSelectedStudySlug] = useState<string | null>(null);

  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [graph, setGraph] = useState<GraphPayload | null>(null);
  const [studies, setStudies] = useState<StudyListItem[]>([]);
  const [records, setRecords] = useState<DecisionRecordSummary[]>([]);
  const [sources, setSources] = useState<SourcesAndPanelsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  function handleNav(tab: TabId) {
    setActiveTab(tab);
    setMobileMenuOpen(false);
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
            MyQuant Lab
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
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-200 text-xs text-slate-500 leading-relaxed">
          Paper-only research workbench. No live brokerage or order execution.
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
          <aside className="relative z-50 w-64 max-w-[80vw] bg-white h-full border-r border-slate-200 flex flex-col">
            <div className="h-14 px-4 flex items-center justify-between border-b border-slate-200">
              <span className="text-base font-bold tracking-tight text-slate-900">
                MyQuant Lab
              </span>
              <button
                type="button"
                aria-label="Close navigation menu"
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
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </nav>
          </aside>
        </div>
      )}

      {/* Main Column */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Top Bar Contract: Breadcrumb on left, 1 primary action on right */}
        <header className="h-14 bg-white border-b border-slate-200 px-4 lg:px-8 flex items-center justify-between gap-6 sticky top-0 z-20">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              aria-label="Open navigation menu"
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-2 -ml-2 text-slate-600 hover:text-slate-900 rounded-md"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="text-sm text-slate-500 truncate">
              <span className="font-medium text-slate-900">MyQuant</span>
              <span className="mx-2 text-slate-300">/</span>
              <span>{currentNav.breadcrumb}</span>
            </div>
          </div>

          <button
            type="button"
            onClick={() => handleNav(activeTab === 'workbench' ? 'overview' : 'workbench')}
            className="px-4 py-2 text-xs font-medium text-white bg-blue-700 hover:bg-blue-800 rounded-md transition-colors whitespace-nowrap shrink-0"
          >
            {activeTab === 'workbench' ? 'Back to Overview' : 'Open Quant Workbench'}
          </button>
        </header>

        {/* Viewport Content */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-[1360px] w-full mx-auto">
          {loading ? (
            <div className="space-y-6">
              <div className="h-8 w-64 bg-slate-200/70 rounded animate-pulse" />
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {[1, 2, 3, 4].map((k) => (
                  <div key={k} className="h-28 bg-white border border-slate-200 rounded-lg animate-pulse" />
                ))}
              </div>
              <div className="h-72 bg-white border border-slate-200 rounded-lg animate-pulse" />
            </div>
          ) : error ? (
            <div className="bg-white border border-rose-200 rounded-lg p-6">
              <h2 className="text-base font-semibold text-rose-800">Unable to load lab datasets</h2>
              <p className="text-sm text-slate-600 mt-1">{error}</p>
            </div>
          ) : (
            <>
              {activeTab === 'overview' && overview && (
                <OverviewView
                  data={overview}
                  onSelectStudy={openStudy}
                  onNavigate={(tab) => handleNav(tab)}
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
              {activeTab === 'workbench' && <QuantWorkbenchView />}
            </>
          )}
        </main>
      </div>
    </div>
  );
};
