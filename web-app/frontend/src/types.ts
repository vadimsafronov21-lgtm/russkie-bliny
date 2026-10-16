export interface Location {
  id: string;
  name: string;
  kind: string;
}
export interface User {
  id: string;
  username: string;
  name: string;
  role: string;
  locations: Location[];
}
export interface Ingredient {
  id: string;
  name: string;
  unit: string;
  pack: string;
}
export interface Catalog {
  ingredients: Ingredient[];
  menu: { id: string; name: string; price: string }[];
  today: string;
}
export interface Stock {
  ingredient_id: string;
  name: string;
  unit: string;
  quantity: string;
  reserved: string;
  available: string;
  negative: boolean;
}
export interface Order {
  id: string;
  number: string;
  point_id: string;
  warehouse_id: string;
  status: string;
  status_label: string;
  version: number;
  note: string;
  discrepancy: string;
  invoice_number: string | null;
  created_at: string;
  shipped_at: string | null;
  lines: { ingredient_id: string; quantity: string; received: string }[];
  receipts: {
    id: string;
    lines: Record<string, string>;
    note: string;
    created_at: string;
  }[];
}
export interface AnalyticItem {
  id: string;
  name: string;
  quantity: number;
  revenue: string;
  change: number | null;
  zero_days: number;
  known_days: number;
  attention: boolean;
  reason: string;
  explanation: string;
  share: number;
}
export interface Analytics {
  items: AnalyticItem[];
  daily: { day: string; quantity: number | null }[];
  quantity: number;
  revenue: string;
  period: string;
  availability: string;
}
export interface Forecast {
  origin: string;
  horizon: number;
  model: string;
  limitations: string;
  interval_note: string;
  weather: string;
  news: string;
  items: {
    item_id: string;
    name: string;
    total: number | null;
    daily: {
      day: string;
      quantity: number | null;
      interval: {
        lower: number;
        upper: number;
        calibration_n: number;
        method: string;
      } | null;
    }[];
  }[];
}
export interface Recommendation {
  lines: {
    ingredient_id: string;
    name: string;
    unit: string;
    stock: string;
    expected: string;
    safety: string;
    incoming: string;
    raw: string;
    quantity: string | null;
    risk: boolean;
    review_required: boolean;
    explanation: string;
  }[];
  notice: string;
}
export interface Notification {
  id: string;
  title: string;
  body: string;
  created_at: string;
  delivery_status: string;
  attempts: number;
  last_error: string | null;
}
export interface Audit {
  id: string;
  action: string;
  detail: string;
  created_at: string;
}
export interface System {
  database: string;
  one_c: string;
  last_successful_sync: string | null;
  weather: string;
  llm: string;
  news: string;
  email: string;
  limitations: string[];
}
export interface Evaluation {
  model: string;
  note: string;
  folds: {
    fold: number;
    origin: string;
    group: string;
    n: number;
    mae: number | null;
    wape: number | null;
    bias: number | null;
  }[];
}
