export function formatPValue(p: number | null | undefined): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return '—';
  if (p < 0.0001) return p.toExponential(2);
  return p.toFixed(4);
}

export function formatNumber(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  if (Math.abs(v) > 0 && Math.abs(v) < 0.0001) return v.toExponential(2);
  return v.toFixed(digits);
}

export function formatInteger(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return Math.round(v).toLocaleString('en-US');
}

export function formatPercent(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return `${(v * 100).toFixed(digits)}%`;
}

export function formatShortDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return iso.slice(0, 10);
}

export function shortInstrumentLabel(instrumentId: string): string {
  const map: Record<string, string> = {
    'credit:baa-10y-spread': 'BAA10Y',
    'crypto:btc-usdt-perp': 'BTC-PERP',
    'crypto:eth-usdt-perp': 'ETH-PERP',
    'crypto:sol-usdt-perp': 'SOL-PERP',
    'index:btc-dvol': 'BTC DVOL',
    'index:eth-dvol': 'ETH DVOL',
    'index:sp500': 'SPX',
    'index:tyvix': 'TYVIX',
    'index:vix': 'VIX',
    'index:vxn': 'VXN',
    'macro:cpi-mom': 'CPI MoM',
    'rates:us-10y-yield': 'DGS10',
  };
  return map[instrumentId] ?? instrumentId;
}

export function formatStatusLabel(status: string): string {
  if (status === 'pending_forward') return 'Pending forward';
  return status.charAt(0).toUpperCase() + status.slice(1).replace(/_/g, ' ');
}

export function statusTextClass(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === 'supported' || normalized === 'pass' || normalized === 'fresh' || normalized === 'completed') {
    return 'text-emerald-700 font-medium';
  }
  if (normalized === 'rejected' || normalized === 'fail' || normalized === 'failed') {
    return 'text-rose-700 font-medium';
  }
  if (normalized === 'unverified' || normalized === 'stale' || normalized === 'pending_forward' || normalized === 'note') {
    return 'text-amber-700 font-medium';
  }
  return 'text-slate-600 font-medium';
}
