/** Typed mirror of the FastAPI schemas (app/schemas/link.py). */

export interface LinkOut {
  id: number;
  code: string;
  short_url: string;
  original_url: string;
  created_at: string;
  expires_at: string | null;
  utm_template: string | null;
  tags: string[];
  total_clicks: number;
  archived: boolean;
  archived_at: string | null;
}

export interface LinkPage {
  items: LinkOut[];
  total: number;
  limit: number;
  offset: number;
  status: string;
}

export interface RecentClick {
  clicked_at: string;
  ip_hash: string | null;
  user_agent: string | null;
  referrer: string | null;
  device: string;
}

export interface ReferrerStat {
  source: string;
  clicks: number;
  devices: Record<string, number>;
}

export interface DeviceStat {
  device: string;
  clicks: number;
}

export interface LinkDetail extends LinkOut {
  recent_clicks: RecentClick[];
  top_referrers: ReferrerStat[];
  device_breakdown: DeviceStat[];
  unique_clicks: number;
  daily_14d: number[];
}

export interface LinkPageEnv {
  items: LinkOut[];
  total: number;
  limit: number;
  offset: number;
  status: string;
}

export interface Stats {
  code: string;
  original_url: string;
  total_clicks: number;
  unique_clicks: number;
  created_at: string;
}

export interface DailyStats {
  code: string;
  window_days: number;
  total: number;
  items: { date: string; clicks: number }[];
}

export interface DeviceBreakdown {
  window_days: number;
  total: number;
  items: DeviceStat[];
}

export interface ReferrerWindow {
  code: string;
  window_days: number;
  total: number;
  items: ReferrerStat[];
}

export interface Hours {
  code: string;
  window_days: number;
  total: number;
  peak: number;
  cells: { dow: number; hour: number; clicks: number }[];
}

export interface Sparklines {
  window_days: number;
  items: { code: string; total_clicks: number; points: number[] }[];
}

export interface Activity {
  items: {
    code: string;
    clicked_at: string;
    device: string;
    referrer_host: string | null;
    ip_hash: string | null;
  }[];
  limit: number;
}

export interface TagRollup {
  window_days: number;
  total_clicks: number;
  items: { tag: string; links: number; clicks: number; unique_visitors: number }[];
}

export interface CompareResult {
  window_days: number;
  items: {
    code: string;
    original_url: string;
    total_clicks: number;
    unique_clicks: number;
    points: number[];
  }[];
}

export interface BulkActionOut {
  action: string;
  updated: number;
  not_found: number;
  results: { code: string; status: string }[];
}

export interface Health {
  status: string;
  database: boolean;
  redis: boolean | null;
  version: string;
  environment: string;
}

export interface ShortenBody {
  url: string;
  custom_code?: string;
  expires_at?: string | null;
  utm_template?: string | null;
  tags?: string[];
}

export interface PatchBody {
  url?: string;
  expires_at?: string | null;
  utm_template?: string | null;
  tags?: string[];
}
