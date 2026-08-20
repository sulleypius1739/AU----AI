import { useEffect, useRef, useState, useCallback } from "react";
import axios from "axios";
import {
  Search, TrendingUp, TrendingDown, Activity, Crosshair, Minus, Slash,
  Square, Ruler, Type, Pencil, MousePointer2, Zap, Newspaper, Shield,
  BarChart3, BookOpen, Server, Bot, CheckCircle2, XCircle, Clock, Target,
  Bell, BellOff, Play, Pause, SkipForward, RotateCcw,
} from "lucide-react";
import "./App.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function beep(up) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.connect(g); g.connect(ctx.destination);
    o.type = "sine"; o.frequency.value = up ? 880 : 440;
    g.gain.setValueAtTime(0.001, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    o.start(); o.stop(ctx.currentTime + 0.5);
  } catch (e) { /* audio not available */ }
}
const TIMEFRAMES = ["5M", "10M", "15M", "1H", "4H", "1D"];
const C = { bull: "#16A085", bear: "#EF5350", blue: "#2962FF", gold: "#C79235", grid: "#EDF0F3" };

const TOOLS = [
  { icon: MousePointer2, name: "Cursor" }, { icon: Crosshair, name: "Crosshair" },
  { icon: Slash, name: "Trendline" }, { icon: Minus, name: "Horizontal" },
  { icon: Square, name: "Rectangle" }, { icon: Ruler, name: "Measure" },
  { icon: Type, name: "Text" }, { icon: Pencil, name: "Brush" },
];

function StatusBadge({ status }) {
  const map = {
    "A+ BUY": "bg-emerald-100 text-emerald-700 border-emerald-300",
    "A+ SELL": "bg-red-100 text-red-700 border-red-300",
    WAIT: "bg-slate-100 text-slate-500 border-slate-200",
    WATCH: "bg-amber-50 text-amber-700 border-amber-200",
    ARMED: "bg-blue-50 text-blue-700 border-blue-200",
    CONFIRMED: "bg-indigo-50 text-indigo-700 border-indigo-200",
    INVALIDATED: "bg-rose-50 text-rose-600 border-rose-200",
  };
  return (
    <span data-testid="signal-status-badge"
      className={`px-3 py-1 rounded-full text-xs font-bold border tracking-wide ${map[status] || map.WAIT}`}>
      {status}
    </span>
  );
}

function Chart({ candles, signal }) {
  const ref = useRef(null);
  useEffect(() => {
    const cv = ref.current; if (!cv || !candles.length) return;
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth, h = cv.clientHeight;
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext("2d"); ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);
    const data = candles.slice(-160);
    const hi = Math.max(...data.map((d) => d.high));
    const lo = Math.min(...data.map((d) => d.low));
    const pad = (hi - lo) * 0.08 || 1;
    const top = hi + pad, bot = lo - pad;
    const padR = 64, padB = 22;
    const cw = (w - padR) / data.length;
    const y = (p) => ((top - p) / (top - bot)) * (h - padB);
    ctx.strokeStyle = C.grid; ctx.lineWidth = 1; ctx.font = "10px ui-monospace,monospace";
    ctx.fillStyle = "#8a94a6";
    for (let i = 0; i <= 5; i++) {
      const yy = (i / 5) * (h - padB);
      ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(w - padR, yy); ctx.stroke();
      const price = top - (i / 5) * (top - bot);
      ctx.fillText(price.toFixed(price > 100 ? 2 : 5), w - padR + 4, yy + 3);
    }
    data.forEach((d, i) => {
      const x = i * cw + cw / 2;
      const up = d.close >= d.open;
      ctx.strokeStyle = up ? C.bull : C.bear;
      ctx.fillStyle = up ? C.bull : C.bear;
      ctx.beginPath(); ctx.moveTo(x, y(d.high)); ctx.lineTo(x, y(d.low)); ctx.stroke();
      const bw = Math.max(cw * 0.6, 1);
      const yo = y(d.open), yc = y(d.close);
      ctx.fillRect(x - bw / 2, Math.min(yo, yc), bw, Math.max(Math.abs(yc - yo), 1));
    });
    // AUREUS annotations from real engine
    if (signal?.trade_plan) {
      const p = signal.trade_plan;
      const line = (price, color, label) => {
        ctx.strokeStyle = color; ctx.setLineDash([5, 4]); ctx.beginPath();
        ctx.moveTo(0, y(price)); ctx.lineTo(w - padR, y(price)); ctx.stroke();
        ctx.setLineDash([]); ctx.fillStyle = color;
        ctx.fillText(label, 4, y(price) - 3);
      };
      if (p.entry <= top && p.entry >= bot) line(p.entry, C.blue, `ENTRY ${p.entry}`);
      if (p.stop <= top && p.stop >= bot) line(p.stop, C.bear, `STOP ${p.stop}`);
      if (p.target <= top && p.target >= bot) line(p.target, C.bull, `TARGET ${p.target}`);
    }
    if (signal?.poi) {
      const poi = signal.poi;
      ctx.fillStyle = "rgba(199,146,53,0.14)";
      ctx.fillRect(0, y(poi.high), w - padR, y(poi.low) - y(poi.high));
    }
  }, [candles, signal]);
  return <canvas ref={ref} data-testid="price-chart" className="w-full h-full" />;
}

function Check({ ok, label, detail }) {
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-slate-100 last:border-0">
      {ok ? <CheckCircle2 size={15} className="text-emerald-500 mt-0.5 shrink-0" />
        : <XCircle size={15} className="text-slate-300 mt-0.5 shrink-0" />}
      <div>
        <div className={`text-xs font-semibold ${ok ? "text-slate-700" : "text-slate-400"}`}>{label}</div>
        <div className="text-[11px] text-slate-400">{detail}</div>
      </div>
    </div>
  );
}

export default function App() {
  const [symbol, setSymbol] = useState("XAU/USD");
  const [tf, setTf] = useState("15M");
  const [candles, setCandles] = useState([]);
  const [state, setState] = useState("REAL-TIME");
  const [signal, setSignal] = useState(null);
  const [watch, setWatch] = useState([]);
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [tab, setTab] = useState("signal");
  const [lower, setLower] = useState("backtest");
  const [tool, setTool] = useState("Cursor");
  const [news, setNews] = useState(null);
  const [funda, setFunda] = useState(null);
  const [risk, setRisk] = useState(null);
  const [validation, setValidation] = useState(null);
  const [backtest, setBacktest] = useState(null);
  const [report, setReport] = useState(null);
  const [alertsOn, setAlertsOn] = useState(true);
  const [alertBanner, setAlertBanner] = useState(null);
  const lastAlertRef = useRef(null);
  const [replayOn, setReplayOn] = useState(false);
  const [replayData, setReplayData] = useState([]);
  const [replayIdx, setReplayIdx] = useState(60);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [admin, setAdmin] = useState(null);
  const [ai, setAi] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [riskForm, setRiskForm] = useState({ equity: 10000, risk_pct: 1, entry: 2000, stop: 1990, target: 2025 });
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadChart = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/candles`, { params: { symbol, timeframe: tf, limit: 300 } });
      setCandles(data.candles); setState(data.state); setErr(null);
    } catch (e) {
      setErr(`DATA FEED ERROR — ${e.response?.status || "NETWORK"}: ${e.message}`);
    } finally { setLoading(false); }
  }, [symbol, tf]);

  const loadSignal = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/signal`, { params: { symbol } });
      setSignal(data);
    } catch (e) {
      setErr(`SIGNAL ENGINE ERROR: ${e.message}`);
    }
  }, [symbol]);

  useEffect(() => { loadChart(); }, [loadChart]);
  useEffect(() => { loadSignal(); }, [loadSignal]);
  useEffect(() => {
    axios.get(`${API}/watchlist`).then((r) => setWatch(r.data.items));
    axios.get(`${API}/validation`).then((r) => setValidation(r.data));
    axios.get(`${API}/admin/status`).then((r) => setAdmin(r.data));
    axios.get(`${API}/backtest/report`).then((r) => setReport(r.data)).catch(() => {});
  }, []);
  useEffect(() => {
    axios.get(`${API}/news`, { params: { symbol } }).then((r) => setNews(r.data));
    axios.get(`${API}/fundamentals`, { params: { symbol } }).then((r) => setFunda(r.data));
  }, [symbol]);
  // live tick simulation on active candle
  useEffect(() => {
    const id = setInterval(() => setCandles((cs) => {
      if (!cs.length) return cs;
      const c = [...cs]; const last = { ...c[c.length - 1] };
      const drift = (Math.random() - 0.5) * last.close * 0.0006;
      last.close = +(last.close + drift).toFixed(5);
      last.high = Math.max(last.high, last.close); last.low = Math.min(last.low, last.close);
      c[c.length - 1] = last; return c;
    }), 2000);
    return () => clearInterval(id);
  }, []);

  // A+ alerts: on-screen banner + sound + browser notification
  useEffect(() => {
    if (!signal || !alertsOn) return;
    const st = signal.status;
    if ((st === "A+ BUY" || st === "A+ SELL")) {
      const key = `${signal.symbol}:${st}`;
      if (lastAlertRef.current !== key) {
        lastAlertRef.current = key;
        const msg = `${signal.symbol} — AUREUS ${st} detected`;
        setAlertBanner(msg);
        beep(st === "A+ BUY");
        if ("Notification" in window && Notification.permission === "granted") {
          new Notification("AUREUS AI", { body: msg });
        }
        setTimeout(() => setAlertBanner(null), 8000);
      }
    } else {
      lastAlertRef.current = null;
    }
  }, [signal, alertsOn]);

  // Replay playback
  useEffect(() => {
    if (!replayOn || !replayPlaying) return;
    const id = setInterval(() => setReplayIdx((x) => Math.min(x + 1, replayData.length)), 500);
    return () => clearInterval(id);
  }, [replayOn, replayPlaying, replayData.length]);

  const toggleReplay = async () => {
    if (replayOn) { setReplayOn(false); setReplayPlaying(false); return; }
    const { data } = await axios.get(`${API}/candles`, { params: { symbol, timeframe: tf, limit: 300 } });
    setReplayData(data.candles); setReplayIdx(60); setReplayPlaying(false); setReplayOn(true);
  };
  const enableNotifications = () => {
    setAlertsOn((v) => !v);
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  };

  const doSearch = async (v) => {
    setQ(v);
    const { data } = await axios.get(`${API}/instruments`, { params: { q: v } });
    setResults(v ? data.results.slice(0, 8) : []);
  };
  const pick = (s) => { setSymbol(s); setResults([]); setQ(""); };

  const runBacktest = async () => {
    setLower("backtest"); setBacktest({ loading: true });
    const { data } = await axios.get(`${API}/backtest`, { params: { symbol, candles: 6000 } });
    setBacktest(data);
  };
  const calcRisk = async () => {
    const { data } = await axios.post(`${API}/risk`, riskForm); setRisk(data);
  };
  const askAi = async () => {
    setAiLoading(true); setAi(null);
    const dir = signal?.direction === "bearish" ? "bearish" : "bullish";
    const { data } = await axios.post(`${API}/ai/explain`, { symbol, direction: dir });
    setAi(data); setAiLoading(false);
  };

  const shownCandles = replayOn ? replayData.slice(0, replayIdx) : candles;

  return (
    <div className="h-screen w-screen flex flex-col bg-white text-slate-800 overflow-hidden aureus">
      {/* Header */}
      <header className="h-12 flex items-center gap-3 px-3 border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-2 pr-3 border-r border-slate-200">
          <div className="w-7 h-7 rounded flex items-center justify-center font-black text-white" style={{ background: C.gold }}>A</div>
          <span className="font-black tracking-tight text-sm">AUREUS <span style={{ color: C.gold }}>AI</span></span>
        </div>
        <div className="relative">
          <div className="flex items-center gap-2 px-3 h-8 rounded bg-slate-50 border border-slate-200 min-w-[220px]">
            <Search size={14} className="text-slate-400" />
            <input data-testid="symbol-search-input" value={q || symbol}
              onChange={(e) => doSearch(e.target.value)} onFocus={() => setQ("")}
              className="bg-transparent outline-none text-sm font-bold flex-1" placeholder="Search markets..." />
          </div>
          {results.length > 0 && (
            <div className="absolute z-30 mt-1 w-80 bg-white border border-slate-200 rounded shadow-xl">
              {results.map((r) => (
                <button key={r.symbol} data-testid={`search-result-${r.symbol}`} onClick={() => pick(r.symbol)}
                  className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-50 text-left">
                  <div><div className="text-sm font-bold">{r.symbol}</div><div className="text-[11px] text-slate-400">{r.name}</div></div>
                  <span className="text-[10px] uppercase text-slate-400">{r.asset_class}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1">
          {TIMEFRAMES.map((t) => (
            <button key={t} data-testid={`tf-${t}`} onClick={() => setTf(t)}
              className={`px-2.5 h-8 rounded text-xs font-bold ${tf === t ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-slate-100"}`}>{t}</button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2 text-xs">
          <button data-testid="alerts-toggle" onClick={enableNotifications} title="A+ alerts"
            className={`w-8 h-8 rounded flex items-center justify-center ${alertsOn ? "bg-amber-50 text-amber-600" : "text-slate-400 hover:bg-slate-100"}`}>
            {alertsOn ? <Bell size={15} /> : <BellOff size={15} />}
          </button>
          <button data-testid="replay-toggle" onClick={toggleReplay} title="Replay mode"
            className={`px-2.5 h-8 rounded text-xs font-bold flex items-center gap-1 ${replayOn ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-slate-100"}`}>
            <RotateCcw size={13} /> Replay
          </button>
          <span className="flex items-center gap-1 px-2 py-1 rounded font-semibold"
            style={replayOn ? { background: "#eef2ff", color: C.blue } : { background: "#ecfdf5", color: C.bull }}>
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: replayOn ? C.blue : C.bull }} />
            {replayOn ? "REPLAY" : state}
          </span>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Toolbar */}
        <div className="w-11 border-r border-slate-200 flex flex-col items-center py-2 gap-1 shrink-0">
          {TOOLS.map((t) => (
            <button key={t.name} data-testid={`tool-${t.name}`} title={t.name} onClick={() => setTool(t.name)}
              className={`w-8 h-8 rounded flex items-center justify-center ${tool === t.name ? "bg-slate-800 text-white" : "text-slate-500 hover:bg-slate-100"}`}>
              <t.icon size={16} />
            </button>
          ))}
        </div>

        {/* Center */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex items-center gap-3 px-4 h-9 border-b border-slate-100 text-sm">
            <span className="font-black">{symbol}</span>
            <span className="text-slate-400">·{tf}</span>
            {shownCandles.length > 0 && <span className="font-bold" style={{ color: shownCandles.at(-1).close >= shownCandles.at(-1).open ? C.bull : C.bear }}>
              {shownCandles.at(-1).close}</span>}
            {signal && !replayOn && <StatusBadge status={signal.status} />}
            {replayOn && (
              <div data-testid="replay-controls" className="ml-auto flex items-center gap-1">
                <button data-testid="replay-play" onClick={() => setReplayPlaying((p) => !p)}
                  className="w-7 h-7 rounded flex items-center justify-center bg-slate-100 hover:bg-slate-200">
                  {replayPlaying ? <Pause size={13} /> : <Play size={13} />}</button>
                <button data-testid="replay-step" onClick={() => setReplayIdx((x) => Math.min(x + 1, replayData.length))}
                  className="w-7 h-7 rounded flex items-center justify-center bg-slate-100 hover:bg-slate-200"><SkipForward size={13} /></button>
                <button data-testid="replay-reset" onClick={() => { setReplayIdx(60); setReplayPlaying(false); }}
                  className="w-7 h-7 rounded flex items-center justify-center bg-slate-100 hover:bg-slate-200"><RotateCcw size={13} /></button>
                <span className="text-[11px] text-slate-400 ml-1">bar {replayIdx}/{replayData.length} · no look-ahead</span>
              </div>
            )}
          </div>
          <div className="flex-1 relative">
            {alertBanner && (
              <div data-testid="alert-banner" className="absolute top-2 left-1/2 -translate-x-1/2 z-30 px-4 py-2 rounded-lg shadow-lg text-white text-xs font-bold flex items-center gap-2 animate-pulse" style={{ background: C.gold }}>
                <Bell size={14} /> {alertBanner}
              </div>
            )}
            {err && (
              <div data-testid="data-feed-error" className="absolute top-2 left-1/2 -translate-x-1/2 z-20 px-4 py-2 rounded bg-red-50 border border-red-200 text-red-600 text-xs font-bold">
                {err}
              </div>
            )}
            {loading && candles.length === 0 && !err && (
              <div className="absolute inset-0 flex items-center justify-center text-slate-400 text-sm">Loading market data…</div>
            )}
            <Chart candles={shownCandles} signal={replayOn ? null : signal} />
          </div>
          {/* Lower dock */}
          <div className="h-56 border-t border-slate-200 flex flex-col shrink-0">
            <div className="flex items-center gap-1 px-2 h-9 border-b border-slate-100">
              {[["backtest", BarChart3, "Backtest"], ["journal", BookOpen, "Journal"],
                ["validation", CheckCircle2, "V4 Validation"], ["admin", Server, "President"]].map(([k, Icon, lbl]) => (
                <button key={k} data-testid={`lower-tab-${k}`} onClick={() => setLower(k)}
                  className={`flex items-center gap-1.5 px-3 h-7 rounded text-xs font-semibold ${lower === k ? "bg-slate-100 text-slate-800" : "text-slate-500"}`}>
                  <Icon size={13} />{lbl}</button>
              ))}
            </div>
            <div className="flex-1 overflow-auto p-3 text-xs">
              {lower === "backtest" && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <button data-testid="run-backtest-btn" onClick={runBacktest} className="px-3 py-1.5 rounded text-white text-xs font-bold" style={{ background: C.blue }}>
                      Run backtest ({symbol})</button>
                    {report?.status === "READY" && <span className="text-[11px] text-slate-400">4Y report generated {report.generated_at}</span>}
                    {report?.status === "PENDING" && <span className="text-[11px] text-amber-600">4Y report generating…</span>}
                  </div>
                  {backtest?.loading && <p className="text-slate-400">Running walk-forward backtest…</p>}
                  {backtest?.metrics && (
                    <div className="grid grid-cols-4 gap-2 mb-3">
                      {Object.entries({ Trades: backtest.metrics.total_trades, "Win %": backtest.metrics.win_rate,
                        "Profit Factor": backtest.metrics.profit_factor, "Net R": backtest.metrics.net_r,
                        "Avg R": backtest.metrics.average_r, Expectancy: backtest.metrics.expectancy,
                        "Max DD (R)": backtest.metrics.max_drawdown_r, "A+ count": backtest.metrics.a_plus_count })
                        .map(([k, v]) => (
                          <div key={k} className="bg-slate-50 rounded p-2 border border-slate-100">
                            <div className="text-[10px] text-slate-400 uppercase">{k}</div>
                            <div className="text-sm font-black">{v ?? "—"}</div></div>
                        ))}
                    </div>
                  )}
                  {report?.status === "READY" && <Report4Y report={report} />}
                </div>
              )}
              {lower === "journal" && <JournalPanel />}
              {lower === "validation" && validation && (
                <div>
                  <div className={`inline-flex items-center gap-1 px-2 py-1 rounded mb-2 font-bold ${validation.all_pass ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-600"}`}>
                    {validation.all_pass ? <CheckCircle2 size={13} /> : <XCircle size={13} />} Suite {validation.all_pass ? "PASS" : "FAIL"}</div>
                  <div className="grid grid-cols-2 gap-1">
                    <Row k="Golden Bullish" v={validation.results.golden_bullish.status} ok={validation.results.golden_bullish.pass} />
                    <Row k="Golden Bearish" v={validation.results.golden_bearish.status} ok={validation.results.golden_bearish.pass} />
                    {Object.entries(validation.results.negatives).map(([k, val]) => (
                      <Row key={k} k={k} v={val.status} ok={val.pass} />))}
                  </div>
                </div>
              )}
              {lower === "admin" && admin && (
                <div className="grid grid-cols-4 gap-2">
                  {Object.entries(admin).filter(([k]) => k.endsWith("engine") || k.endsWith("feed") || k === "database" || k === "signal_engine" || k === "risk_engine").map(([k, v]) => (
                    <div key={k} className="bg-slate-50 rounded p-2 border border-slate-100">
                      <div className="text-[10px] text-slate-400 uppercase">{k.replace(/_/g, " ")}</div>
                      <div className={`text-xs font-black ${String(v).includes("ONLINE") || String(v).includes("READY") ? "text-emerald-600" : "text-amber-600"}`}>{String(v)}</div></div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right panel */}
        <div className="w-80 border-l border-slate-200 flex flex-col shrink-0">
          <div className="flex border-b border-slate-200">
            {[["signal", Zap], ["watch", Activity], ["risk", Shield], ["news", Newspaper], ["ai", Bot]].map(([k, Icon]) => (
              <button key={k} data-testid={`panel-tab-${k}`} onClick={() => setTab(k)}
                className={`flex-1 h-9 flex items-center justify-center ${tab === k ? "border-b-2 text-slate-800" : "text-slate-400"}`}
                style={tab === k ? { borderColor: C.gold } : {}}><Icon size={15} /></button>
            ))}
          </div>
          <div className="flex-1 overflow-auto p-3">
            {tab === "signal" && signal && (
              <div data-testid="signal-panel">
                {replayOn && (
                  <div className="text-[10px] font-bold text-blue-600 bg-blue-50 border border-blue-100 rounded px-2 py-1 mb-2">
                    LIVE signal — not synced to replay bars
                  </div>
                )}
                <div className="flex items-center justify-between mb-2">
                  <div><div className="text-[11px] text-slate-400 uppercase">AUREUS AI · {signal.symbol}</div>
                    <div className="flex items-center gap-1 font-black text-sm">
                      {signal.direction === "bullish" ? <TrendingUp size={15} className="text-emerald-500" /> : <TrendingDown size={15} className="text-red-500" />}
                      {signal.direction.toUpperCase()}</div></div>
                  <StatusBadge status={signal.status} />
                </div>
                <div className="bg-slate-50 rounded p-2 mb-2">
                  <Check ok={signal.checks.htf_direction.passed} label="4H Direction" detail={signal.checks.htf_direction.detail} />
                  <Check ok={signal.checks.poi.passed} label="1H Fresh POI" detail={signal.checks.poi.detail} />
                  <Check ok={signal.checks.market_shift.passed} label="15M Market Shift" detail={signal.checks.market_shift.detail} />
                  <Check ok={signal.checks.liquidity_sweep.passed} label="15M Liquidity Sweep" detail={signal.checks.liquidity_sweep.detail} />
                  <Check ok={signal.checks.ltf_confirmation.passed} label="10M Confirmation" detail={signal.checks.ltf_confirmation.detail} />
                  <Check ok={signal.checks.poi_mitigation.passed} label="POI Mitigation" detail={signal.checks.poi_mitigation.detail} />
                  <Check ok={signal.checks.rr.passed} label="R:R (2R–5R)" detail={signal.checks.rr.detail} />
                </div>
                {signal.trade_plan ? (
                  <div>
                    {!signal.actionable && (
                      <div data-testid="hypothetical-plan-label" className="text-[10px] font-bold text-amber-600 mb-1 flex items-center gap-1">
                        <Clock size={11} /> HYPOTHETICAL PLAN — {signal.missing || "sequence incomplete"}
                      </div>
                    )}
                    <div className="grid grid-cols-3 gap-1 text-center">
                      {[["Entry", signal.trade_plan.entry], ["Stop", signal.trade_plan.stop], ["Target", signal.trade_plan.target],
                        ["Risk", "$" + signal.trade_plan.risk_amount], ["Reward", "$" + signal.trade_plan.potential_profit], ["R:R", signal.trade_plan.rr + "R"]]
                        .map(([k, v]) => (<div key={k} className="bg-white border border-slate-100 rounded p-1.5">
                          <div className="text-[10px] text-slate-400">{k}</div><div className="text-xs font-black">{v}</div></div>))}
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 bg-amber-50 border border-amber-100 rounded p-2 flex items-start gap-1">
                    <Clock size={13} className="mt-0.5 shrink-0" />{signal.missing}</div>
                )}
                <p className="text-[10px] text-slate-400 italic mt-3">{signal.philosophy}</p>
              </div>
            )}
            {tab === "watch" && (
              <div data-testid="watchlist-panel">
                {watch.map((w) => (
                  <button key={w.symbol} data-testid={`watch-${w.symbol}`} onClick={() => setSymbol(w.symbol)}
                    className="w-full flex items-center justify-between px-2 py-2 rounded hover:bg-slate-50 text-left">
                    <span className="text-sm font-bold">{w.symbol}</span>
                    <div className="text-right"><div className="text-xs font-bold">{w.last}</div>
                      <div className="text-[11px] font-semibold" style={{ color: w.change >= 0 ? C.bull : C.bear }}>
                        {w.change >= 0 ? "+" : ""}{w.change_pct}%</div></div>
                  </button>
                ))}
              </div>
            )}
            {tab === "risk" && (
              <div data-testid="risk-panel" className="space-y-2">
                {["equity", "risk_pct", "entry", "stop", "target"].map((f) => (
                  <div key={f}><label className="text-[11px] text-slate-400 uppercase">{f.replace("_", " ")}</label>
                    <input data-testid={`risk-${f}`} type="number" value={riskForm[f]}
                      onChange={(e) => setRiskForm({ ...riskForm, [f]: +e.target.value })}
                      className="w-full h-8 px-2 rounded bg-slate-50 border border-slate-200 text-sm font-bold" /></div>
                ))}
                <button data-testid="calc-risk-btn" onClick={calcRisk} className="w-full h-8 rounded text-white text-xs font-bold" style={{ background: C.blue }}>Calculate</button>
                {risk && (
                  <div className={`grid grid-cols-2 gap-1 text-center ${risk.rr_valid ? "" : "opacity-90"}`}>
                    {[["Position", risk.position_size], ["R:R", risk.rr + "R"], ["Profit", "$" + risk.potential_profit], ["Loss", "$" + risk.potential_loss]]
                      .map(([k, v]) => (<div key={k} className="bg-slate-50 border border-slate-100 rounded p-1.5"><div className="text-[10px] text-slate-400">{k}</div><div className="text-xs font-black">{v}</div></div>))}
                    <div className={`col-span-2 rounded p-1.5 font-bold ${risk.rr_valid ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-600"}`}>
                      {risk.rr_valid ? "VALID (2R–5R)" : "REJECT — outside 2R–5R"}</div>
                  </div>
                )}
              </div>
            )}
            {tab === "news" && (
              <div data-testid="news-panel">
                {news && (<>
                  {news.events.map((e, i) => (
                    <div key={i} className="py-2 border-b border-slate-100">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold">{e.headline}</span>
                        <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${e.importance === "HIGH" ? "bg-red-100 text-red-600" : e.importance === "MEDIUM" ? "bg-amber-100 text-amber-600" : "bg-slate-100 text-slate-500"}`}>{e.importance}</span>
                      </div>
                      <div className="text-[11px] text-slate-400">{e.interpretation}</div>
                    </div>
                  ))}
                </>)}
                {funda && (
                  <div className="mt-3 bg-slate-50 rounded p-2">
                    <div className="text-[11px] text-slate-400 uppercase mb-1">Fundamental Bias</div>
                    <div className="text-xs font-bold mb-2">{funda.fundamental_bias}</div>
                    <p className="text-[10px] text-slate-400 italic">{funda.note}</p>
                  </div>
                )}
              </div>
            )}
            {tab === "ai" && (
              <div data-testid="ai-panel">
                <button data-testid="ask-ai-btn" onClick={askAi} disabled={aiLoading}
                  className="w-full h-9 rounded text-white text-xs font-bold flex items-center justify-center gap-1 disabled:opacity-50" style={{ background: C.gold }}>
                  <Bot size={14} />{aiLoading ? "AUREUS is analysing…" : "Explain this setup"}</button>
                {ai && (
                  <div className="mt-3">
                    <div className={`text-[10px] font-bold mb-1 ${ai.ai_connected ? "text-emerald-600" : "text-amber-600"}`}>AI: {ai.status}</div>
                    <div className="text-xs whitespace-pre-wrap leading-relaxed text-slate-700">{ai.explanation}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Report4Y({ report }) {
  const e = report.eurusd || {};
  if (!e.after_tp_beyond_swing) return <p className="text-slate-400 text-xs">Report generating…</p>;
  const before = e.before_tp_at_swing || {};
  const after = e.after_tp_beyond_swing || {};
  const managed = e.after_with_management || {};
  const ab = e.matched_ab || {};
  const abAt = ab.tp_at_swing || {};
  const abBey = ab.tp_beyond_swing || {};
  const dist = after.rr_distribution || {};
  const maxBucket = Math.max(1, ...Object.values(dist));
  const cmp = [
    ["Win rate %", before.win_rate, after.win_rate, managed.win_rate],
    ["Profit factor", before.profit_factor, after.profit_factor, managed.profit_factor],
    ["Net R", before.net_r, after.net_r, managed.net_r],
    ["Avg R", before.average_r, after.average_r, managed.average_r],
    ["Max DD (R)", before.max_drawdown_r, after.max_drawdown_r, managed.max_drawdown_r],
    ["SL→TP (premature)", `${before.sl_hit_then_tp_would_fill}/${before.sl_before_tp_count}`,
      `${after.sl_hit_then_tp_would_fill}/${after.sl_before_tp_count}`, "—"],
  ];
  return (
    <div data-testid="report-4y" className="space-y-3">
      <div className="text-[11px] text-amber-700 bg-amber-50 border border-amber-100 rounded px-2 py-1">
        {report.window_years}Y · {report.primary_dataset} · {(report.bars_tested || 0).toLocaleString()} bars ·
        <b> {report.data_source}</b>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-[10px] text-slate-400 uppercase mb-1">Before vs After · TP placement</div>
          <table className="w-full text-[11px]">
            <thead><tr className="text-slate-400 text-left">
              <th></th><th>TP@swing</th><th>TP beyond</th><th>+ Mgmt</th></tr></thead>
            <tbody>{cmp.map(([k, a, b, c]) => (
              <tr key={k} className="border-t border-slate-100">
                <td className="py-1 font-semibold text-slate-600">{k}</td>
                <td>{a ?? "—"}</td><td className="font-bold">{b ?? "—"}</td><td>{c ?? "—"}</td></tr>))}
            </tbody>
          </table>
          <p className="text-[10px] text-slate-400 mt-1 italic">
            Matched A/B (same entries) shows TP-beyond-swing leaves win rate essentially
            unchanged — placement alone is not the edge. Break-even + 50% partial at +1R is
            what lifts win rate materially.
          </p>
          {ab.matched_trades ? (
            <div data-testid="matched-ab-block" className="mt-2 border-t border-slate-100 pt-2">
              <div className="text-[10px] text-slate-400 uppercase mb-1">Matched A/B · {ab.matched_trades} identical entries</div>
              <table data-testid="matched-ab-table" className="w-full text-[11px]">
                <thead><tr className="text-slate-400 text-left"><th></th><th>TP@swing</th><th>TP beyond</th></tr></thead>
                <tbody>
                  <tr className="border-t border-slate-100"><td className="py-1 font-semibold text-slate-600">Win rate %</td><td>{abAt.win_rate}</td><td className="font-bold">{abBey.win_rate}</td></tr>
                  <tr className="border-t border-slate-100"><td className="py-1 font-semibold text-slate-600">Avg R</td><td>{abAt.average_r}</td><td className="font-bold">{abBey.average_r}</td></tr>
                  <tr className="border-t border-slate-100"><td className="py-1 font-semibold text-slate-600">SL→TP premature</td><td>{abAt.sl_hit_then_tp_would_fill}/{abAt.sl_before_tp_count}</td><td className="font-bold">{abBey.sl_hit_then_tp_would_fill}/{abBey.sl_before_tp_count}</td></tr>
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
        <div>
          <div className="text-[10px] text-slate-400 uppercase mb-1">RR distribution (TP beyond)</div>
          {Object.entries(dist).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2 mb-0.5">
              <span className="text-[10px] w-14 text-slate-500">{k}</span>
              <div className="flex-1 bg-slate-100 rounded h-3 overflow-hidden">
                <div className="h-3 rounded" style={{ width: `${(v / maxBucket) * 100}%`, background: k.includes("-") || k === "0..1R" ? C.bear : C.bull }} /></div>
              <span className="text-[10px] w-6 text-right font-bold">{v}</span>
            </div>
          ))}
        </div>
      </div>
      <div>
        <div className="text-[10px] text-slate-400 uppercase mb-1">Per-instrument (1Y, TP beyond)</div>
        <div className="grid grid-cols-4 gap-1">
          {(report.per_instrument || []).map((p) => (
            <div key={p.symbol} className="bg-slate-50 border border-slate-100 rounded p-1.5">
              <div className="text-[11px] font-bold">{p.symbol}</div>
              <div className="text-[10px] text-slate-400">{p.trades} trades</div>
              <div className="text-xs font-black" style={{ color: p.win_rate >= 50 ? C.bull : C.bear }}>{p.win_rate}% win</div>
              <div className="text-[10px] text-slate-500">PF {p.profit_factor} · {p.net_r}R</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Row({ k, v, ok }) {
  return (
    <div className="flex items-center justify-between bg-slate-50 rounded px-2 py-1 border border-slate-100">
      <span className="text-[11px] font-semibold text-slate-600 truncate">{k}</span>
      <span className="flex items-center gap-1">{ok ? <CheckCircle2 size={12} className="text-emerald-500" /> : <XCircle size={12} className="text-red-500" />}
        <span className="text-[10px] font-bold text-slate-500">{v}</span></span>
    </div>
  );
}

function JournalPanel() {
  const [user, setUser] = useState(null);
  const [entries, setEntries] = useState([]);
  const [creds, setCreds] = useState({ email: "president@aureus.ai", password: "Aureus2020!" });
  const [form, setForm] = useState({ symbol: "XAU/USD", direction: "bullish", entry: 2000, stop: 1990, target: 2025, result: "open" });

  const cfg = { withCredentials: true };
  const load = async () => { try { const r = await axios.get(`${API}/journal`, cfg); setEntries(r.data); } catch { } };
  useEffect(() => { axios.get(`${API}/auth/me`, cfg).then((r) => { setUser(r.data); load(); }).catch(() => { }); }, []);
  const login = async () => { const r = await axios.post(`${API}/auth/login`, creds, cfg); setUser(r.data); load(); };
  const add = async () => { await axios.post(`${API}/journal`, form, cfg); load(); };

  if (!user) return (
    <div data-testid="journal-login" className="flex items-center gap-2">
      <input data-testid="login-email" value={creds.email} onChange={(e) => setCreds({ ...creds, email: e.target.value })} className="h-8 px-2 rounded bg-slate-50 border border-slate-200 text-xs" placeholder="email" />
      <input data-testid="login-password" type="password" value={creds.password} onChange={(e) => setCreds({ ...creds, password: e.target.value })} className="h-8 px-2 rounded bg-slate-50 border border-slate-200 text-xs" placeholder="password" />
      <button data-testid="login-btn" onClick={login} className="h-8 px-3 rounded text-white text-xs font-bold" style={{ background: C.blue }}>Login</button>
    </div>
  );
  return (
    <div data-testid="journal-panel">
      <div className="flex items-center gap-1 mb-2 flex-wrap">
        {["symbol", "direction", "entry", "stop", "target"].map((f) => (
          <input key={f} data-testid={`journal-${f}`} value={form[f]} onChange={(e) => setForm({ ...form, [f]: e.target.value })}
            className="h-7 px-2 rounded bg-slate-50 border border-slate-200 text-xs w-24" placeholder={f} />))}
        <button data-testid="add-journal-btn" onClick={add} className="h-7 px-3 rounded text-white text-xs font-bold" style={{ background: C.bull }}>+ Log Trade</button>
      </div>
      <table className="w-full text-[11px]">
        <thead><tr className="text-slate-400 text-left">{["Symbol", "Dir", "Entry", "Stop", "Target", "RR", "Result"].map((h) => <th key={h} className="py-1">{h}</th>)}</tr></thead>
        <tbody>{entries.map((e) => (
          <tr key={e.id} className="border-t border-slate-100"><td className="py-1 font-bold">{e.symbol}</td><td>{e.direction}</td>
            <td>{e.entry}</td><td>{e.stop}</td><td>{e.target}</td><td className="font-bold">{e.rr}R</td><td>{e.result}</td></tr>))}</tbody>
      </table>
      {entries.length === 0 && <p className="text-slate-400">No trades logged yet.</p>}
    </div>
  );
}
