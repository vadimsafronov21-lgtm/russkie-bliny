import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Boxes,
  Check,
  ChevronRight,
  ClipboardList,
  Clock3,
  Database,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  MapPin,
  Plus,
  Printer,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  TriangleAlert,
  Truck,
  X,
} from "lucide-react";
import { api, ApiError, mutate, setCsrf } from "./api";
import type {
  Analytics,
  Audit,
  Catalog,
  Evaluation,
  Forecast,
  Ingredient,
  Notification,
  Order,
  Recommendation,
  Stock,
  System,
  User,
} from "./types";

const ErrorContext = createContext("");
const number = (n: string | number | null) =>
  n === null
    ? "—"
    : Number(n).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
const date = (s: string) =>
  new Date(
    s.length === 10
      ? s + "T12:00:00"
      : /Z$|[+-]\d\d:\d\d$/.test(s)
        ? s
        : s + "Z",
  ).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
    timeZone: "Asia/Novosibirsk",
  });
const roles: Record<string, string> = {
  admin: "Администратор",
  analyst: "Аналитик",
  warehouse: "Кладовщик",
  point: "Сотрудник точки",
};
const tabs = [
  { id: "overview", label: "Обзор", icon: LayoutDashboard },
  { id: "stocks", label: "Остатки", icon: Boxes },
  { id: "orders", label: "Заявки и накладные", icon: ClipboardList },
  { id: "analytics", label: "Аналитика", icon: BarChart3 },
  { id: "forecast", label: "Прогноз спроса", icon: TrendingUp },
  { id: "audit", label: "Журнал действий", icon: Clock3 },
  { id: "system", label: "Система", icon: Database },
];
const titles: Record<string, [string, string]> = {
  overview: ["Всё под контролем", "Продажи, запасы и поставки вашей точки"],
  stocks: ["Остатки ингредиентов", "Собственный оперативный учёт приложения"],
  orders: ["Заявки и накладные", "От потребности точки до фактической приёмки"],
  analytics: [
    "Аналитика ассортимента",
    "Показатели, которые помогают задать правильные вопросы",
  ],
  forecast: ["Прогноз спроса", "Простой объяснимый прогноз количества продаж"],
  audit: ["Журнал действий", "История операций с документами и остатками"],
  system: [
    "Система и подключения",
    "Режим работы, доступы и ограничения этой версии",
  ],
};

function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <span />
        <span />
        <span />
      </span>
      <div>
        Русские блины<small>УПРАВЛЕНИЕ ЗАПАСАМИ</small>
      </div>
    </div>
  );
}
function Badge({ status, children }: { status: string; children: ReactNode }) {
  return (
    <span className={"badge " + status}>
      <i />
      {children}
    </span>
  );
}
function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <ClipboardList size={30} />
      <p>{children}</p>
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const error = useContext(ErrorContext);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className={wide ? "modal wide" : "modal"}
      onCancel={onClose}
    >
      <header>
        <h2>{title}</h2>
        <button className="icon-button" aria-label="Закрыть" onClick={onClose}>
          <X size={20} />
        </button>
      </header>
      {error && (
        <div className="notice danger" role="alert">
          {error}
        </div>
      )}
      {children}
    </dialog>
  );
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [username, setUsername] = useState("warehouse");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api<{ user: User; csrf: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setCsrf(r.csrf);
      onLogin(r.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка входа");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-shell">
      <section className="login-story">
        <Brand />
        <div>
          <span className="eyebrow light">ОТ ТОЧКИ ДО СКЛАДА</span>
          <h1>
            Нужные продукты.
            <br />В нужное время.
          </h1>
          <p>
            Прозрачные остатки, понятные заявки
            <br />и одна история каждой поставки.
          </p>
          <div className="login-flow">
            <Boxes />
            <span />
            <Truck />
            <span />
            <Check />
          </div>
        </div>
        <small>Учебный проект · версия 0.1</small>
      </section>
      <section className="login-panel">
        <div className="login-form">
          <span className="badge demo">
            <FlaskConical size={14} />
            Демонстрационный стенд
          </span>
          <h2>Добро пожаловать</h2>
          <p className="muted">
            Выберите роль и войдите в рабочее пространство.
          </p>
          <form onSubmit={submit}>
            <label>
              Учётная запись
              <select
                aria-label="Учётная запись"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              >
                <option value="warehouse">Кладовщик · обе точки</option>
                <option value="point1">Сотрудник · Центр</option>
                <option value="point2">Сотрудник · Парк</option>
                <option value="analyst">Аналитик</option>
                <option value="admin">Администратор</option>
              </select>
            </label>
            <label>
              Пароль
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <button className="button primary full" disabled={busy}>
              {busy ? "Входим…" : "Войти в приложение"}
              <ArrowRight size={17} />
            </button>
          </form>
          <div className="demo-access">
            <ShieldCheck size={19} />
            <div>
              <strong>Только синтетические данные</strong>
              <p>
                Пароль учебных аккаунтов: <code>Bliny-demo-2026!</code>
                <br />
                Если он изменён при установке — используйте новый.
              </p>
            </div>
          </div>
          <p className="fine">
            1С не подключена. Реальные продажи, остатки и качество прогнозов
            заказчика здесь не представлены.
          </p>
        </div>
      </section>
    </main>
  );
}

interface Data {
  catalog: Catalog;
  stocks: Stock[];
  orders: Order[];
  analysis: Analytics;
  forecast: Forecast;
  rec: Recommendation;
  notifications: Notification[];
  audit: Audit[];
  system: System;
  evaluation: Evaluation;
  warehouse: Stock[];
}
export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [point, setPoint] = useState("");
  const [tab, setTab] = useState("overview");
  const [data, setData] = useState<Data | null>(null);
  const [horizon, setHorizon] = useState(7);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [modal, setModal] = useState<
    "new" | "recommend" | "sale" | "notifications" | null
  >(null);
  const [selected, setSelected] = useState<Order | null>(null);
  const [search, setSearch] = useState("");
  const [attention, setAttention] = useState(true);
  const [status, setStatus] = useState("all");
  const loadId = useRef(0);
  function acceptUser(u: User) {
    setUser(u);
    setPoint(u.locations.find((x) => x.kind === "point")?.id || "");
    setData(null);
    setTab("overview");
  }
  useEffect(() => {
    api<{ user: User; csrf: string }>("/auth/me")
      .then((r) => {
        setCsrf(r.csrf);
        acceptUser(r.user);
      })
      .catch(() => {})
      .finally(() => setAuthLoading(false));
  }, []);
  const load = useCallback(async () => {
    if (!user || !point) return;
    const id = ++loadId.current;
    setRefreshing(true);
    try {
      const p = "?point_id=" + encodeURIComponent(point);
      const [
        catalog,
        stocks,
        orders,
        analysis,
        forecast,
        rec,
        notifications,
        audit,
        system,
        evaluation,
        warehouse,
      ] = await Promise.all([
        api<Catalog>("/catalog"),
        api<Stock[]>("/stocks?location_id=" + point),
        api<Order[]>("/requests" + p),
        api<Analytics>("/analytics" + p),
        api<Forecast>("/forecast" + p + "&horizon=" + horizon),
        api<Recommendation>("/recommendations" + p),
        api<Notification[]>("/notifications"),
        api<Audit[]>("/audit"),
        api<System>("/system"),
        api<Evaluation>("/forecast/evaluation" + p),
        user.locations.some((x) => x.id === "warehouse")
          ? api<Stock[]>("/stocks?location_id=warehouse")
          : Promise.resolve([]),
      ]);
      if (id === loadId.current) {
        setData({
          catalog,
          stocks,
          orders,
          analysis,
          forecast,
          rec,
          notifications,
          audit,
          system,
          evaluation,
          warehouse,
        });
        setSelected((prev) =>
          prev ? orders.find((x) => x.id === prev.id) || null : null,
        );
      }
    } catch (err) {
      if (id === loadId.current) {
        if (err instanceof ApiError && err.status === 401) {
          setUser(null);
          setData(null);
        }
        setError(
          err instanceof Error ? err.message : "Не удалось загрузить данные.",
        );
      }
    } finally {
      if (id === loadId.current) setRefreshing(false);
    }
  }, [user, point, horizon]);
  useEffect(() => {
    setData(null);
    setSelected(null);
    void load();
    return () => {
      loadId.current++;
    };
  }, [load]);
  async function action(job: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await job();
      setSuccess(message);
      await load();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка операции.");
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    if (
      await action(
        () => api("/auth/logout", { method: "POST" }),
        "Вы вышли из приложения",
      )
    ) {
      setCsrf("");
      setUser(null);
      setData(null);
      setSelected(null);
      setModal(null);
      setError("");
      setSuccess("");
    }
  }
  if (authLoading)
    return (
      <div className="loading-screen">
        <Brand />
        <p>Открываем рабочее пространство…</p>
      </div>
    );
  if (!user) return <Login onLogin={acceptUser} />;
  const location = user.locations.find((x) => x.id === point);
  const canCreate = user.role === "point" || user.role === "warehouse";
  const activeOrders =
    data?.orders.filter((x) => !["received", "cancelled"].includes(x.status)) ||
    [];
  const risks = data?.rec.lines.filter((x) => x.risk) || [];
  const displayOrders =
    data?.orders.filter(
      (x) =>
        (status === "all" || x.status === status) &&
        (x.number.toLowerCase().includes(search.toLowerCase()) ||
          x.note.toLowerCase().includes(search.toLowerCase())),
    ) || [];
  const names = (id: string) =>
    data?.catalog.ingredients.find((i) => i.id === id);
  const actionStatus = async (order: Order, next: string) =>
    action(
      () =>
        mutate(`/requests/${order.id}/transition`, {
          version: order.version,
          status: next,
        }),
      "Статус документа обновлён.",
    );
  const orderTable = (orders: Order[]) =>
    orders.length ? (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Заявка</th>
              <th>Состав</th>
              <th>Создана</th>
              <th>Статус</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id}>
                <td>
                  <button
                    className="text-button strong"
                    onClick={() => setSelected(o)}
                  >
                    {o.number}
                  </button>
                  <small>
                    {o.invoice_number || "Накладная ещё не создана"}
                  </small>
                </td>
                <td>
                  {o.lines.map((l) => names(l.ingredient_id)?.name).join(", ")}
                  <small>
                    {o.lines.length} поз. ·{" "}
                    {o.receipts.length ? "Есть приёмка" : "Без приёмки"}
                  </small>
                </td>
                <td>{date(o.created_at)}</td>
                <td>
                  <Badge status={o.status}>
                    {o.status_label}
                    {o.status === "sent" && o.receipts.length
                      ? " · частично принята"
                      : ""}
                  </Badge>
                </td>
                <td>
                  <button
                    className="icon-button"
                    aria-label={"Открыть " + o.number}
                    onClick={() => setSelected(o)}
                  >
                    <ChevronRight size={18} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <Empty>В этом списке пока нет заявок.</Empty>
    );
  return (
    <ErrorContext.Provider value={error}>
      <div className="app-shell">
        <aside className="sidebar">
          <Brand />
          <div className="workspace-caption">РАБОЧЕЕ ПРОСТРАНСТВО</div>
          <nav aria-label="Основная навигация">
            {tabs.map((t) => (
              <button
                key={t.id}
                className={tab === t.id ? "nav-item active" : "nav-item"}
                onClick={() => {
                  setTab(t.id);
                  setSearch("");
                }}
              >
                <t.icon size={19} />
                <span>{t.label}</span>
                {t.id === "orders" && activeOrders.length > 0 && (
                  <b>{activeOrders.length}</b>
                )}
              </button>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="mode-card">
              <span className="status-dot" />
              <strong>Самостоятельный учёт</strong>
              <p>
                Остатки приложения.
                <br />
                Без подключения к 1С.
              </p>
            </div>
            <button
              className="profile"
              onClick={logout}
              disabled={busy}
              title="Выйти"
            >
              <span className="avatar">{user.name[0]}</span>
              <span>
                <strong>{user.name}</strong>
                <small>{roles[user.role]}</small>
              </span>
              <LogOut size={16} />
            </button>
          </div>
        </aside>
        <div className="main-shell">
          <header className="topbar">
            <div className="breadcrumb">
              Рабочее пространство <ChevronRight size={13} />
              <strong>{tabs.find((x) => x.id === tab)?.label}</strong>
            </div>
            <div className="topbar-actions">
              <label className="point-picker">
                <MapPin size={16} />
                <select
                  aria-label="Торговая точка"
                  value={point}
                  onChange={(e) => {
                    setPoint(e.target.value);
                    setError("");
                    setSuccess("");
                  }}
                >
                  {user.locations
                    .filter((x) => x.kind === "point")
                    .map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.name}
                      </option>
                    ))}
                </select>
              </label>
              <button
                className="icon-button bell"
                aria-label="Уведомления"
                onClick={() => setModal("notifications")}
              >
                <Bell size={20} />
                {!!data?.notifications.length && <i />}
              </button>
            </div>
          </header>
          <div className="demo-strip">
            <FlaskConical size={15} />
            <span>
              <strong>Демонстрационный режим</strong>
              <span className="strip-separator">·</span>Синтетические данные, не
              показатели заказчика
            </span>
            <span className="demo-version">MVP / 0.1</span>
          </div>
          <main className="content">
            <div className="page-heading">
              <div>
                <span className="eyebrow">
                  {location?.name.replace("Учебная точка · ", "").toUpperCase()}{" "}
                  / {data ? date(data.catalog.today) : "ДЕМО"}
                </span>
                <h1>{titles[tab][0]}</h1>
                <p>{titles[tab][1]}</p>
              </div>
              <div className="heading-actions">
                <button
                  className="button secondary compact"
                  aria-label="Обновить данные"
                  onClick={() => void load()}
                  disabled={refreshing}
                >
                  <RefreshCw size={16} className={refreshing ? "spin" : ""} />
                  <span>Обновить</span>
                </button>
                {canCreate &&
                  ["overview", "orders", "stocks"].includes(tab) && (
                    <button
                      className="button primary"
                      onClick={() => setModal("new")}
                    >
                      <Plus size={17} />
                      Новая заявка
                    </button>
                  )}
              </div>
            </div>
            {error && (
              <div className="notice danger" role="alert">
                <TriangleAlert size={18} />
                <span>{error}</span>
                <button aria-label="Скрыть ошибку" onClick={() => setError("")}>
                  <X size={16} />
                </button>
              </div>
            )}
            {success && (
              <div className="notice success" role="status">
                <Check size={18} />
                <span>{success}</span>
                <button
                  aria-label="Скрыть сообщение"
                  onClick={() => setSuccess("")}
                >
                  <X size={16} />
                </button>
              </div>
            )}
            {!data ? (
              <div className="loading-panel">
                <RefreshCw className="spin" />
                <p>
                  {error
                    ? "Данные не загружены. Нажмите «Обновить»."
                    : "Загружаем данные…"}
                </p>
              </div>
            ) : (
              <>
                {tab === "overview" && (
                  <>
                    <div className="metrics">
                      <Metric
                        label="Выручка за 28 дней"
                        value={number(data.analysis.revenue) + " ₽"}
                        icon={<BarChart3 />}
                        note="После финансовых возвратов"
                      />
                      <Metric
                        label="Продано порций"
                        value={number(data.analysis.quantity)}
                        icon={<TrendingUp />}
                        note="Последние 28 полных дней"
                      />
                      <Metric
                        label="Активные заявки"
                        value={String(activeOrders.length)}
                        icon={<Truck />}
                        note="Ожидают обработки или приёмки"
                      />
                      <Metric
                        label="Требуют проверки"
                        value={String(risks.length)}
                        icon={<TriangleAlert />}
                        note="Ингредиенты по черновому расчёту"
                        warning={risks.length > 0}
                      />
                    </div>
                    <div className="overview-grid">
                      <section className="panel">
                        <div className="panel-heading">
                          <div>
                            <h2>Динамика продаж</h2>
                            <p>Порции по дням · последние 14 дней</p>
                          </div>
                          <span className="chart-legend">
                            <i /> Продажи
                          </span>
                        </div>
                        <SalesChart daily={data.analysis.daily} />
                      </section>
                      <section className="panel attention-panel">
                        <div className="panel-heading">
                          <div className="section-icon warning">
                            <TriangleAlert size={18} />
                          </div>
                          <div>
                            <h2>На что обратить внимание</h2>
                            <p>Проверьте запас перед заказом</p>
                          </div>
                        </div>
                        <div className="risk-list">
                          {risks.slice(0, 3).map((r) => (
                            <div key={r.ingredient_id}>
                              <span className="ingredient-icon">
                                <Boxes size={18} />
                              </span>
                              <div>
                                <strong>{r.name}</strong>
                                <small>
                                  Остаток {number(r.stock)} {r.unit} · расход{" "}
                                  {number(r.expected)} {r.unit}
                                </small>
                              </div>
                              <span className="badge attention">Проверить</span>
                            </div>
                          ))}
                          {!risks.length && (
                            <p className="muted">
                              По условному расчёту пополнение не требуется.
                            </p>
                          )}
                        </div>
                        <button
                          className="button secondary full"
                          onClick={() => setTab("stocks")}
                        >
                          Посмотреть расчёт <ArrowRight size={16} />
                        </button>
                        <p className="fine">
                          Сроки годности и вместимость неизвестны.
                        </p>
                      </section>
                    </div>
                    <section className="panel">
                      <div className="panel-heading">
                        <div>
                          <h2>
                            Заявки в работе{" "}
                            <span className="count">{activeOrders.length}</span>
                          </h2>
                          <p>Последние документы выбранной точки</p>
                        </div>
                        <button
                          className="text-button"
                          onClick={() => setTab("orders")}
                        >
                          Все заявки <ArrowRight size={15} />
                        </button>
                      </div>
                      {orderTable(activeOrders.slice(0, 4))}
                    </section>
                    <div className="context-card">
                      <div>
                        <FlaskConical size={22} />
                        <div>
                          <strong>Прозрачная демонстрация полного пути</strong>
                          <p>
                            {user.role === "point"
                              ? "Создайте продажу: расход будет рассчитан по версии рецептуры."
                              : "Создайте накладную из принятой заявки. Затем войдите сотрудником точки для приёмки."}
                          </p>
                        </div>
                      </div>
                      {user.role === "point" ? (
                        <button
                          className="button secondary"
                          onClick={() => setModal("sale")}
                        >
                          Демо-продажа <ArrowRight size={15} />
                        </button>
                      ) : (
                        <span className="badge demo">1С не подключена</span>
                      )}
                    </div>
                  </>
                )}
                {tab === "stocks" && (
                  <>
                    <div className="notice info">
                      <ShieldCheck size={18} />
                      <span>
                        Это остаток приложения. Последняя успешная синхронизация
                        с 1С: отсутствует — интеграция не подключена.
                      </span>
                    </div>
                    <section className="panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Запас на точке</h2>
                          <p>
                            Отрицательные значения сохраняются и требуют
                            проверки
                          </p>
                        </div>
                        {user.role === "point" && (
                          <button
                            className="button secondary"
                            onClick={() => setModal("sale")}
                          >
                            <FlaskConical size={16} />
                            Демо-продажа
                          </button>
                        )}
                      </div>
                      <StockTable stocks={data.stocks} />
                    </section>
                    <section className="panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Черновая корзина пополнения</h2>
                          <p>
                            Ожидаемый расход + страховой запас − остаток −
                            подтверждённые поступления
                          </p>
                        </div>
                        {canCreate && (
                          <button
                            className="button primary"
                            onClick={() => setModal("recommend")}
                            disabled={!risks.length}
                          >
                            Проверить и создать <ArrowRight size={16} />
                          </button>
                        )}
                      </div>
                      <p className="panel-note amber">{data.rec.notice}</p>
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>Ингредиент</th>
                              <th>Расход / 3 дня</th>
                              <th>Страховой запас</th>
                              <th>В пути / принято складом</th>
                              <th>Черновое количество</th>
                            </tr>
                          </thead>
                          <tbody>
                            {data.rec.lines.map((r) => (
                              <tr key={r.ingredient_id}>
                                <td>
                                  <strong>{r.name}</strong>
                                  <small>{r.explanation}</small>
                                </td>
                                <td>
                                  {number(r.expected)} {r.unit}
                                </td>
                                <td>
                                  {number(r.safety)} {r.unit}
                                </td>
                                <td>
                                  {number(r.incoming)} {r.unit}
                                </td>
                                <td>
                                  <strong className={r.risk ? "red" : ""}>
                                    {number(r.quantity)} {r.unit}
                                  </strong>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </section>
                    {data.warehouse.length > 0 && (
                      <section className="panel">
                        <div className="panel-heading">
                          <div>
                            <h2>Учебный склад</h2>
                            <p>
                              Резерв создаётся при принятии заявки и снимается
                              при отправке или отмене
                            </p>
                          </div>
                        </div>
                        <StockTable stocks={data.warehouse} />
                      </section>
                    )}
                  </>
                )}
                {tab === "orders" && (
                  <section className="panel">
                    <div className="filter-bar">
                      <label className="search-input">
                        <Search size={17} />
                        <input
                          placeholder="Найти заявку…"
                          aria-label="Найти заявку"
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                        />
                      </label>
                      <select
                        aria-label="Статус заявки"
                        value={status}
                        onChange={(e) => setStatus(e.target.value)}
                      >
                        <option value="all">Все статусы</option>
                        {Object.entries({
                          new: "Новая",
                          accepted: "Принята",
                          packing: "Комплектуется",
                          sent: "Отправлена",
                          received: "Получена",
                          cancelled: "Отменена",
                        }).map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </select>
                      <span className="muted">
                        {displayOrders.length} документов
                      </span>
                    </div>
                    {orderTable(displayOrders)}
                  </section>
                )}
                {tab === "analytics" && (
                  <>
                    <div className="notice info">
                      <BarChart3 size={18} />
                      <span>
                        {data.analysis.availability} Низкие продажи не
                        доказывают отсутствие спроса.
                      </span>
                    </div>
                    <section className="panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Ассортимент</h2>
                          <p>
                            {data.analysis.period} · предыдущие 28 дней для
                            сравнения
                          </p>
                        </div>
                        <div className="segmented">
                          <button
                            className={attention ? "active" : ""}
                            onClick={() => setAttention(true)}
                          >
                            Требуют внимания
                          </button>
                          <button
                            className={!attention ? "active" : ""}
                            onClick={() => setAttention(false)}
                          >
                            Все позиции
                          </button>
                        </div>
                      </div>
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>Позиция меню</th>
                              <th>Порции</th>
                              <th>Выручка</th>
                              <th>Динамика</th>
                              <th>Доля</th>
                              <th>Дней без продаж</th>
                              <th>Сигнал</th>
                            </tr>
                          </thead>
                          <tbody>
                            {data.analysis.items
                              .filter((i) => !attention || i.attention)
                              .map((i) => (
                                <tr key={i.id}>
                                  <td>
                                    <strong>{i.name}</strong>
                                  </td>
                                  <td>{number(i.quantity)}</td>
                                  <td>{number(i.revenue)} ₽</td>
                                  <td>
                                    <span
                                      className={
                                        (i.change || 0) < 0
                                          ? "trend down"
                                          : "trend up"
                                      }
                                    >
                                      {(i.change || 0) < 0 ? (
                                        <ArrowDownRight size={14} />
                                      ) : (
                                        <ArrowUpRight size={14} />
                                      )}{" "}
                                      {number(i.change)}%
                                    </span>
                                  </td>
                                  <td>{i.share}%</td>
                                  <td>
                                    {i.zero_days} / {i.known_days}
                                  </td>
                                  <td>
                                    <Badge
                                      status={
                                        i.attention ? "attention" : "received"
                                      }
                                    >
                                      {i.reason}
                                    </Badge>
                                  </td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                      <p className="panel-note">
                        Демо-правило: менее 3 порций в день при ≥14 наблюдениях
                        либо снижение &gt;15%. Причины нужно исследовать.
                        Себестоимость, маржинальность и стоимость списаний
                        недоступны.
                      </p>
                    </section>
                    <section className="panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Продажи по дням</h2>
                          <p>
                            Для сравнения доступных точек используйте
                            переключатель вверху
                          </p>
                        </div>
                      </div>
                      <SalesChart daily={data.analysis.daily} />
                    </section>
                  </>
                )}
                {tab === "forecast" && (
                  <>
                    <div className="forecast-toolbar">
                      <div className="model-label">
                        <Sparkles size={18} />
                        <div>
                          <strong>{data.forecast.model}</strong>
                          <small>
                            Сформирован на {date(data.forecast.origin)} · без
                            погоды и новостей
                          </small>
                        </div>
                      </div>
                      <div className="segmented">
                        {[1, 7, 14].map((h) => (
                          <button
                            key={h}
                            className={horizon === h ? "active" : ""}
                            onClick={() => setHorizon(h)}
                          >
                            {h} {h === 1 ? "день" : "дней"}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="notice info">
                      <FlaskConical size={18} />
                      <span>
                        {data.forecast.limitations}{" "}
                        {data.forecast.interval_note}
                      </span>
                    </div>
                    <section className="panel">
                      <div className="table-wrap">
                        <table className="forecast-table">
                          <thead>
                            <tr>
                              <th>Позиция</th>
                              {data.forecast.items[0]?.daily.map((d) => (
                                <th key={d.day}>{date(d.day)}</th>
                              ))}
                              <th>Всего</th>
                            </tr>
                          </thead>
                          <tbody>
                            {data.forecast.items.map((item) => (
                              <tr key={item.item_id}>
                                <td>
                                  <strong>{item.name}</strong>
                                </td>
                                {item.daily.map((d) => (
                                  <td key={d.day}>
                                    {number(d.quantity)}
                                    {d.interval && (
                                      <small title={d.interval.method}>
                                        {number(d.interval.lower)}–
                                        {number(d.interval.upper)}*
                                      </small>
                                    )}
                                  </td>
                                ))}
                                <td>
                                  <strong>{number(item.total)}</strong>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <p className="panel-note">
                        Количество в порциях. * Эмпирический диапазон с
                        номинальным уровнем 80% для первого дня; фактическое
                        покрытие ещё не оценено.
                      </p>
                    </section>
                    <section className="panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Временная проверка baseline</h2>
                          <p>
                            Рассчитано на синтетической истории, не на данных
                            заказчика
                          </p>
                        </div>
                        <Badge status="demo">3 последовательных периода</Badge>
                      </div>
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>Период</th>
                              <th>Группа</th>
                              <th>Наблюдения</th>
                              <th>MAE, порции</th>
                              <th>WAPE</th>
                              <th>Смещение</th>
                            </tr>
                          </thead>
                          <tbody>
                            {data.evaluation.folds.map((f, i) => (
                              <tr key={i}>
                                <td>
                                  {date(f.origin)} · №{f.fold}
                                </td>
                                <td>{f.group}</td>
                                <td>{f.n}</td>
                                <td>{number(f.mae)}</td>
                                <td>
                                  {f.wape === null
                                    ? "N/A"
                                    : number(f.wape * 100) + "%"}
                                </td>
                                <td>{number(f.bias)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <p className="panel-note">
                        {data.evaluation.note} Положительное смещение означает
                        завышение.
                      </p>
                    </section>
                  </>
                )}
                {tab === "audit" && (
                  <section className="panel">
                    <div className="panel-heading">
                      <div>
                        <h2>Последние действия</h2>
                        <p>Только операции доступных вам точек</p>
                      </div>
                    </div>
                    <div className="activity-list">
                      {data.audit.map((a) => (
                        <div key={a.id}>
                          <span className="activity-dot" />
                          <div>
                            <strong>{a.detail}</strong>
                            <small>{a.action}</small>
                          </div>
                          <time>{date(a.created_at)}</time>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
                {tab === "system" && (
                  <>
                    <section className="panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Состояние стенда</h2>
                          <p>
                            Самостоятельный журнал приложения · синтетические
                            данные
                          </p>
                        </div>
                        <Badge status="demo">Учебный режим</Badge>
                      </div>
                      <div className="system-grid">
                        {[
                          [
                            "Хранилище",
                            data.system.database === "sqlite"
                              ? "SQLite · локальный просмотр"
                              : "PostgreSQL",
                          ],
                          ["1С", data.system.one_c],
                          ["Погода", data.system.weather],
                          ["Новости", data.system.news],
                          ["LLM", data.system.llm],
                          ["Email", data.system.email],
                        ].map(([label, value]) => (
                          <div key={label}>
                            <span>{label}</span>
                            <strong>{value}</strong>
                          </div>
                        ))}
                      </div>
                    </section>
                    <section className="panel">
                      <div className="panel-heading">
                        <div>
                          <h2>Что ещё предстоит</h2>
                          <p>
                            Эта версия — первый работающий этап, не завершённая
                            система
                          </p>
                        </div>
                      </div>
                      <ul className="limitations">
                        {data.system.limitations.map((x) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ul>
                      <p className="panel-note">
                        Резервные копии и инструкция запуска находятся в папке
                        проекта. API-документация:{" "}
                        <a href="/docs" target="_blank" rel="noreferrer">
                          открыть Swagger
                        </a>
                        .
                      </p>
                    </section>
                  </>
                )}
                <footer className="page-footer">
                  <span>
                    <span className="status-dot" />
                    Данные приложения · {location?.name}
                  </span>
                  <span>Русские блины / Учебный стенд</span>
                </footer>
              </>
            )}
          </main>
        </div>
        {data && (modal === "new" || modal === "recommend") && (
          <RequestModal
            ingredients={data.catalog.ingredients}
            initial={
              modal === "recommend"
                ? Object.fromEntries(
                    data.rec.lines
                      .filter((x) => x.risk && x.quantity)
                      .map((x) => [x.ingredient_id, x.quantity!]),
                  )
                : {}
            }
            notice={modal === "recommend" ? data.rec.notice : undefined}
            busy={busy}
            onClose={() => setModal(null)}
            onSubmit={async (lines, note) => {
              if (
                await action(
                  () => mutate("/requests", { point_id: point, lines, note }),
                  "Заявка создана и передана кладовщику.",
                )
              )
                setModal(null);
            }}
          />
        )}
        {data && modal === "sale" && (
          <SaleModal
            catalog={data.catalog}
            busy={busy}
            onClose={() => setModal(null)}
            onSubmit={async (item, quantity, eventId) => {
              if (
                await action(
                  () =>
                    mutate("/demo/sales", {
                      point_id: point,
                      item_id: item,
                      quantity,
                      event_id: eventId,
                      day: data.catalog.today,
                    }),
                  "Демонстрационная продажа учтена. Остатки обновлены по рецептуре.",
                )
              )
                setModal(null);
            }}
          />
        )}
        {data && modal === "notifications" && (
          <Modal title="Уведомления" onClose={() => setModal(null)}>
            <div className="notification-list">
              {data.notifications.map((n) => (
                <article key={n.id}>
                  <strong>{n.title}</strong>
                  <p>{n.body}</p>
                  <small>
                    {date(n.created_at)} · Email:{" "}
                    {(
                      {
                        pending: "ожидает обработки",
                        local_sink: "сохранён в локальный sink",
                        sent_demo: "отправлен в demo SMTP",
                        retry: "повтор доставки",
                        failed: "ошибка доставки",
                      } as Record<string, string>
                    )[n.delivery_status] || n.delivery_status}
                  </small>
                  {n.last_error && (
                    <p className="red">
                      {n.last_error} Попыток: {n.attempts}
                    </p>
                  )}
                </article>
              ))}
            </div>
          </Modal>
        )}
        {data && selected && (
          <OrderModal
            order={selected}
            ingredients={data.catalog.ingredients}
            pointName={location?.name || ""}
            user={user}
            busy={busy}
            onClose={() => setSelected(null)}
            onTransition={(next) => actionStatus(selected, next)}
            onReceive={async (lines, note) => {
              await action(
                () =>
                  mutate(`/requests/${selected.id}/receive`, {
                    version: selected.version,
                    lines,
                    note,
                  }),
                "Приёмка сохранена. Остаток увеличен только на принятое количество.",
              );
            }}
          />
        )}
      </div>
    </ErrorContext.Provider>
  );
}

function Metric({
  label,
  value,
  note,
  icon,
  warning = false,
}: {
  label: string;
  value: string;
  note: string;
  icon: ReactNode;
  warning?: boolean;
}) {
  return (
    <section className={"metric " + (warning ? "warning-metric" : "")}>
      <div>
        <span>{label}</span>
        <span className="metric-icon">{icon}</span>
      </div>
      <strong>{value}</strong>
      <small>{note}</small>
    </section>
  );
}
function SalesChart({ daily }: { daily: Analytics["daily"] }) {
  const max = Math.max(...daily.map((x) => x.quantity ?? 0), 1);
  return (
    <div
      className="chart"
      role="img"
      aria-label="Продажи в порциях за последние 14 дней"
    >
      <div className="chart-axis">
        <span>{max}</span>
        <span>{Math.round(max / 2)}</span>
        <span>0</span>
      </div>
      <div className="chart-bars">
        {daily.map((d, i) => (
          <div className="bar-column" key={d.day}>
            <span className="bar-value">
              {d.quantity === null ? "н/д" : d.quantity}
            </span>
            <div
              className={
                "bar " +
                (d.quantity === null
                  ? "missing"
                  : i === daily.length - 1
                    ? "latest"
                    : "")
              }
              style={{
                height: Math.max(2, ((d.quantity ?? 0) / max) * 146) + "px",
              }}
              title={`${date(d.day)}: ${d.quantity === null ? "Нет данных" : d.quantity + " порций"}`}
            />
            <small>{new Date(d.day).getDate()}</small>
          </div>
        ))}
      </div>
    </div>
  );
}
function StockTable({ stocks }: { stocks: Stock[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Ингредиент</th>
            <th>Остаток</th>
            <th>Резерв</th>
            <th>Свободно</th>
            <th>Состояние данных</th>
          </tr>
        </thead>
        <tbody>
          {stocks.map((s) => (
            <tr key={s.ingredient_id}>
              <td>
                <strong>{s.name}</strong>
              </td>
              <td>
                {number(s.quantity)} {s.unit}
              </td>
              <td>
                {number(s.reserved)} {s.unit}
              </td>
              <td className={s.negative ? "red" : ""}>
                {number(s.available)} {s.unit}
              </td>
              <td>
                <Badge status={s.negative ? "attention" : "received"}>
                  {s.negative ? "Отрицательный остаток" : "Остаток приложения"}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
type Lines = { ingredient_id: string; quantity: string }[];
function RequestModal({
  ingredients,
  initial,
  notice,
  busy,
  onClose,
  onSubmit,
}: {
  ingredients: Ingredient[];
  initial: Record<string, string>;
  notice?: string;
  busy: boolean;
  onClose: () => void;
  onSubmit: (lines: Lines, note: string) => Promise<void>;
}) {
  const [quantities, setQuantities] = useState(initial);
  const [note, setNote] = useState("");
  const lines = ingredients
    .filter((i) => Number(quantities[i.id]) > 0)
    .map((i) => ({ ingredient_id: i.id, quantity: quantities[i.id] }));
  return (
    <Modal title="Новая заявка на пополнение" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void onSubmit(lines, note);
        }}
      >
        {notice && <p className="notice amber">{notice}</p>}
        <p className="muted">
          Укажите количество в базовых единицах. Пустые строки не включаются в
          заявку.
        </p>
        <div className="quantity-form">
          {ingredients.map((i) => (
            <label key={i.id}>
              <span>
                {i.name}
                <small>
                  Упаковка {number(i.pack)} {i.unit} · условное значение
                </small>
              </span>
              <div>
                <input
                  aria-label={i.name}
                  type="number"
                  min="0"
                  max="1000000"
                  step="0.001"
                  value={quantities[i.id] || ""}
                  placeholder="0"
                  onChange={(e) =>
                    setQuantities({ ...quantities, [i.id]: e.target.value })
                  }
                />
                <span>{i.unit}</span>
              </div>
            </label>
          ))}
        </div>
        <label>
          Комментарий
          <textarea
            value={note}
            maxLength={500}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Например, к утренней поставке"
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Отмена
          </button>
          <button className="button primary" disabled={busy || !lines.length}>
            {busy ? "Сохраняем…" : "Создать заявку"}
            <ArrowRight size={16} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
function SaleModal({
  catalog,
  busy,
  onClose,
  onSubmit,
}: {
  catalog: Catalog;
  busy: boolean;
  onClose: () => void;
  onSubmit: (id: string, q: number, eventId: string) => Promise<void>;
}) {
  const [item, setItem] = useState("curd-pancake");
  const [quantity, setQuantity] = useState(10);
  const [eventId] = useState(() => crypto.randomUUID());
  return (
    <Modal title="Демонстрационная продажа" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void onSubmit(item, quantity, eventId);
        }}
      >
        <p className="notice info">
          Это генератор синтетического события, а не касса и не импорт реальной
          продажи.
        </p>
        <label>
          Позиция меню
          <select value={item} onChange={(e) => setItem(e.target.value)}>
            {catalog.menu.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Количество порций
          <input
            aria-label="Количество порций"
            type="number"
            min="1"
            max="1000"
            required
            value={quantity}
            onChange={(e) => setQuantity(Number(e.target.value))}
          />
        </label>
        <p className="fine">
          Для блина с творогом: 30 г творога на порцию. 10 порций спишут 300 г
          творога, а также муку и молоко по рецепту.
        </p>
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Отмена
          </button>
          <button className="button primary" disabled={busy}>
            Учесть демо-продажу
          </button>
        </div>
      </form>
    </Modal>
  );
}
function OrderModal({
  order,
  ingredients,
  pointName,
  user,
  busy,
  onClose,
  onTransition,
  onReceive,
}: {
  order: Order;
  ingredients: Ingredient[];
  pointName: string;
  user: User;
  busy: boolean;
  onClose: () => void;
  onTransition: (status: string) => Promise<unknown>;
  onReceive: (lines: Lines, note: string) => Promise<void>;
}) {
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const name = (id: string) => ingredients.find((i) => i.id === id);
  useEffect(() => {
    setQuantities({});
    setNote("");
  }, [order.version]);
  const receivedLines = order.lines
    .filter((l) => Number(quantities[l.ingredient_id]) > 0)
    .map((l) => ({
      ingredient_id: l.ingredient_id,
      quantity: quantities[l.ingredient_id],
    }));
  return (
    <Modal title={order.number} onClose={onClose} wide>
      <div className="invoice-content">
        <div className="invoice-heading">
          <div>
            <span className="eyebrow">
              ВНУТРЕННИЙ ДОКУМЕНТ · СИНТЕТИЧЕСКИЕ ДАННЫЕ
            </span>
            <h2>
              {order.invoice_number
                ? "Накладная " + order.invoice_number
                : "Заявка на пополнение"}
            </h2>
            <p>Учебный склад → {pointName}</p>
            <p className="fine">
              Создана {date(order.created_at)}
              {order.shipped_at
                ? " · Отправлена " + date(order.shipped_at)
                : ""}{" "}
              · Не документ 1С
            </p>
          </div>
          <Badge status={order.status}>{order.status_label}</Badge>
        </div>
        {order.note && <p className="notice info">{order.note}</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ингредиент</th>
                <th>По накладной</th>
                <th>Принято</th>
                <th>Осталось</th>
              </tr>
            </thead>
            <tbody>
              {order.lines.map((l) => (
                <tr key={l.ingredient_id}>
                  <td>{name(l.ingredient_id)?.name}</td>
                  <td>
                    {number(l.quantity)} {name(l.ingredient_id)?.unit}
                  </td>
                  <td>{number(l.received)}</td>
                  <td>{number(Number(l.quantity) - Number(l.received))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {order.discrepancy && (
          <p className="notice amber">
            Расхождение / примечание: {order.discrepancy}
          </p>
        )}
        {!!order.receipts.length && (
          <div className="receipt-history">
            <h3>История приёмки</h3>
            {order.receipts.map((r) => (
              <p key={r.id}>
                {date(r.created_at)} ·{" "}
                {Object.entries(r.lines)
                  .map(
                    ([id, q]) =>
                      `${name(id)?.name}: ${number(q)} ${name(id)?.unit}`,
                  )
                  .join("; ")}
                {r.note ? " · " + r.note : ""}
              </p>
            ))}
          </div>
        )}
      </div>
      {user.role === "point" && order.status === "sent" && (
        <form
          className="receipt-form"
          onSubmit={(e) => {
            e.preventDefault();
            void onReceive(receivedLines, note);
          }}
        >
          <h3>Подтвердить фактическую приёмку</h3>
          <p className="fine">
            Введите только полученное сейчас. Непринятое количество останется в
            ожидании.
          </p>
          <div className="quantity-form">
            {order.lines
              .filter((l) => Number(l.quantity) > Number(l.received))
              .map((l) => (
                <label key={l.ingredient_id}>
                  <span>{name(l.ingredient_id)?.name}</span>
                  <div>
                    <input
                      aria-label={"Принято: " + name(l.ingredient_id)?.name}
                      type="number"
                      min="0"
                      max={Number(l.quantity) - Number(l.received)}
                      step="0.001"
                      placeholder="0"
                      value={quantities[l.ingredient_id] || ""}
                      onChange={(e) =>
                        setQuantities({
                          ...quantities,
                          [l.ingredient_id]: e.target.value,
                        })
                      }
                    />
                    <span>{name(l.ingredient_id)?.unit}</span>
                  </div>
                </label>
              ))}
          </div>
          <label>
            Расхождения / комментарий
            <textarea
              value={note}
              maxLength={500}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <button
            className="button primary"
            disabled={busy || !receivedLines.length}
          >
            <Check size={16} />
            Подтвердить приёмку
          </button>
        </form>
      )}
      <div className="modal-actions">
        <button className="button secondary" onClick={onClose}>
          Закрыть
        </button>
        {order.invoice_number && (
          <button className="button secondary" onClick={() => window.print()}>
            <Printer size={16} />
            Печать
          </button>
        )}
        {user.role === "warehouse" &&
          ["new", "accepted", "packing"].includes(order.status) && (
            <button
              className="button primary"
              disabled={busy}
              onClick={() =>
                void onTransition(
                  (
                    {
                      new: "accepted",
                      accepted: "packing",
                      packing: "sent",
                    } as Record<string, string>
                  )[order.status],
                )
              }
            >
              {
                (
                  {
                    new: "Принять заявку",
                    accepted: "Создать накладную",
                    packing: "Подтвердить отправку",
                  } as Record<string, string>
                )[order.status]
              }
              <ArrowRight size={16} />
            </button>
          )}
        {((user.role === "warehouse" &&
          ["new", "accepted", "packing"].includes(order.status)) ||
          (user.role === "point" && order.status === "new")) && (
          <button
            className="text-button red"
            disabled={busy}
            onClick={() => void onTransition("cancelled")}
          >
            Отменить заявку
          </button>
        )}
      </div>
    </Modal>
  );
}
