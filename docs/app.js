/* =========================================================================
   SCOUT — Market Signal Terminal
   Vanilla JS. Data:
     ./data/signals.json  — daily scan (signals, radar, movers, market block)
     ./data/quotes.json   — intraday equity quotes (30-min Action refresh)
     Binance WebSocket    — live crypto prices, streamed in-browser
     alternative.me       — crypto Fear & Greed index
   Charts: TradingView lightweight-charts (CDN).
   ========================================================================= */

(function () {
  "use strict";

  // ---- DOM ------------------------------------------------------------
  var els = {
    benchStrip: document.getElementById("bench-strip"),
    regime: document.getElementById("regime-pill"),
    fng: document.getElementById("fng"),
    scannedAt: document.getElementById("scanned-at"),
    tape: document.getElementById("tape-track"),
    status: document.getElementById("status"),
    rows: document.getElementById("sigrows"),
    empty: document.getElementById("empty"),
    detail: document.getElementById("detail"),
    detailInner: document.getElementById("detail-inner"),
    leadCount: document.getElementById("lead-count"),
    marketFilter: document.getElementById("market-filter"),
    tierFilter: document.getElementById("tier-filter"),
    radar: document.getElementById("radar"),
    gainers: document.getElementById("gainers"),
    losers: document.getElementById("losers"),
    breadth: document.getElementById("breadth"),
    viewSignals: document.getElementById("view-signals"),
    viewAI: document.getElementById("view-ai"),
    aiMeta: document.getElementById("ai-meta"),
    catchup: document.getElementById("catchup"),
    leaders: document.getElementById("leaders"),
    etfs: document.getElementById("etfs"),
    aiLayers: document.getElementById("ai-layers"),
    watchlistPanel: document.getElementById("watchlist-panel"),
    watchlist: document.getElementById("watchlist"),
    recordPanel: document.getElementById("record-panel"),
    record: document.getElementById("record"),
    edgePanel: document.getElementById("edge-panel"),
    edge: document.getElementById("edge"),
  };

  // ---- State ----------------------------------------------------------
  var data = null;                  // signals.json payload
  var quotes = {};                  // symbol -> {price, chg_1d} from quotes.json
  var live = {};                    // symbol -> {price, chg} from Binance WS
  var filters = { market: "all", tier: "all" };
  var selected = null;              // selected suggestion symbol
  var chart = null;                 // lightweight-charts instance
  var ws = null;

  var TIER_LABEL = { both: "High Conviction", technical: "Technical", fundamental: "Fundamental" };

  var PATTERN_LABEL = {
    cup_and_handle: "Cup & Handle",
    breakout: "Breakout",
    uptrend: "Uptrend",
    golden_cross: "Golden Cross",
    pullback_to_trend: "Pullback to 50d",
    bull_flag: "Bull Flag",
    double_bottom: "Double Bottom",
    bollinger_squeeze: "BB Squeeze",
    obv_accumulation: "OBV Accumulation",
    high_52w_momentum: "Near 52w High",
    macd_bull_cross: "MACD Cross",
    oversold_reversal: "Oversold Reversal",
  };

  // ---- Watchlist (localStorage) -----------------------------------------
  var WL_KEY = "scout_watchlist_v1";

  function loadWL() {
    try { return JSON.parse(localStorage.getItem(WL_KEY)) || {}; }
    catch (e) { return {}; }
  }
  function saveWL(wl) {
    try { localStorage.setItem(WL_KEY, JSON.stringify(wl)); } catch (e) {}
  }
  function isStarred(sym) { return !!loadWL()[sym]; }
  function toggleStar(sym, market, price) {
    var wl = loadWL();
    if (wl[sym]) { delete wl[sym]; }
    else {
      wl[sym] = { market: market, priceAt: price, addedAt: new Date().toISOString().slice(0, 10) };
    }
    saveWL(wl);
    renderWatchlist();
    renderList();
    if (selected === sym) {
      var s = (data.suggestions || []).find(function (x) { return x.symbol === sym; });
      if (s) renderDetail(s);
    }
  }
  function starBtn(sym, market, price, extraClass) {
    var on = isStarred(sym);
    return '<button type="button" class="star ' + (extraClass || "") + (on ? " is-on" : "")
      + '" data-star="' + esc(sym) + '" data-star-market="' + esc(market || "US")
      + '" data-star-price="' + (price != null ? price : "") + '"'
      + ' aria-label="' + (on ? "Remove from" : "Add to") + ' watchlist" title="Watchlist">'
      + (on ? "★" : "☆") + "</button>";
  }
  // one delegated handler for every star on the page
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-star]");
    if (!btn) return;
    e.stopPropagation();
    e.preventDefault();
    toggleStar(btn.dataset.star, btn.dataset.starMarket,
      btn.dataset.starPrice ? Number(btn.dataset.starPrice) : null);
  }, true);

  // ---- Utils ----------------------------------------------------------
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function fmtPx(x, market) {
    if (x == null || isNaN(x)) return "—";
    var n = Number(x);
    var opts = n >= 1000 ? { maximumFractionDigits: 0 }
      : n >= 10 ? { minimumFractionDigits: 2, maximumFractionDigits: 2 }
      : { minimumFractionDigits: 2, maximumFractionDigits: 4 };
    var cur = market === "ASX" ? "A$" : "$";
    return cur + n.toLocaleString(undefined, opts);
  }

  function fmtChg(x) {
    if (x == null || isNaN(x)) return "";
    var pct = (Number(x) * 100);
    return (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%";
  }

  function chgClass(x) { return x == null ? "" : (Number(x) >= 0 ? "up" : "down"); }

  function fmtPct(x, signed) {
    if (x == null || isNaN(x)) return "—";
    var pct = Number(x) * 100;
    var s = (signed && pct >= 0 ? "+" : "") + pct.toFixed(1) + "%";
    return s;
  }

  function fmtTime(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return iso || "—";
    try {
      return new Intl.DateTimeFormat(undefined, {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      }).format(d);
    } catch (e) { return d.toUTCString(); }
  }

  function setStatus(msg, kind) {
    els.status.textContent = msg || "";
    els.status.className = "status" + (kind ? " status--" + kind : "");
  }

  function bestPrice(s) {
    // live (crypto WS) > intraday quote > scan-time price
    if (live[s.symbol]) return { px: live[s.symbol].price, chg: live[s.symbol].chg, src: "live" };
    var q = quotes[s.symbol];
    if (q && q.price != null) return { px: q.price, chg: q.chg_1d, src: "intraday" };
    return { px: s.price, chg: s.chg_1d, src: "close" };
  }

  // ---- Command bar ------------------------------------------------------
  function renderBenchmarks(market) {
    if (!market || !market.benchmarks) return;
    var order = ["SPY", "QQQ", "^AXJO", "BTC-USD"];
    var html = order.map(function (key) {
      var b = market.benchmarks[key];
      if (!b) return "";
      var arrow = b.trend === "uptrend" ? "▲" : b.trend === "downtrend" ? "▼" : "◆";
      return '<span class="bench" data-bench="' + esc(key) + '">'
        + '<span class="bench__trend ' + esc(b.trend) + '">' + arrow + "</span>"
        + '<span class="bench__name">' + esc(b.label) + "</span>"
        + '<span class="bench__px num">' + Number(b.price).toLocaleString() + "</span>"
        + '<span class="bench__chg ' + chgClass(b.chg_1d) + '">' + fmtChg(b.chg_1d) + "</span>"
        + "</span>";
    }).join("");
    els.benchStrip.innerHTML = html;
  }

  function renderRegime(market) {
    if (!market || !market.regime) return;
    var label = { risk_on: "Risk On", risk_off: "Risk Off", neutral: "Neutral" }[market.regime] || market.regime;
    els.regime.hidden = false;
    els.regime.className = "regime regime--" + market.regime;
    els.regime.querySelector(".regime__text").textContent = label;
    els.regime.title = "Market regime from benchmark trends + universe breadth";
  }

  function loadFearGreed() {
    fetch("https://api.alternative.me/fng/?limit=1")
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var d = j && j.data && j.data[0];
        if (!d) return;
        els.fng.hidden = false;
        els.fng.querySelector(".fng__val").textContent = d.value + " · " + d.value_classification;
      })
      .catch(function () { /* cosmetic; ignore */ });
  }

  // ---- Ticker tape ------------------------------------------------------
  function tapeSymbols() {
    var syms = [];
    var seen = {};
    function add(symbol, market) {
      if (seen[symbol]) return;
      seen[symbol] = true;
      syms.push({ symbol: symbol, market: market });
    }
    (data.suggestions || []).forEach(function (s) { add(s.symbol, s.market); });
    (data.radar || []).forEach(function (s) { add(s.symbol, s.market); });
    var m = data.movers || {};
    (m.gainers || []).concat(m.losers || []).forEach(function (s) { add(s.symbol, s.market); });
    Object.keys(quotes).forEach(function (sym) {
      add(sym, sym.endsWith("-USD") ? "Crypto" : sym.endsWith(".AX") ? "ASX" : "US");
    });
    var wl = loadWL();
    Object.keys(wl).forEach(function (sym) { add(sym, wl[sym].market || "US"); });
    return syms;
  }

  function renderTape() {
    var syms = tapeSymbols();
    if (!syms.length) return;
    var cell = function (s) {
      var p = bestPrice({ symbol: s.symbol, market: s.market, price: null, chg_1d: null });
      if (p.px == null) return "";
      return '<span class="tk" data-tape-sym="' + esc(s.symbol) + '">'
        + (p.src === "live" ? '<span class="tk__live"></span>' : "")
        + '<span class="tk__sym">' + esc(s.symbol.replace("-USD", "")) + "</span>"
        + '<span class="tk__px">' + fmtPx(p.px, s.market) + "</span>"
        + '<span class="tk__chg ' + chgClass(p.chg) + '">' + fmtChg(p.chg) + "</span>"
        + "</span>";
    };
    var row = syms.map(cell).join("");
    // duplicate for the seamless -50% loop
    els.tape.innerHTML = row + row;
  }

  // ---- Signal list ------------------------------------------------------
  function visibleSuggestions() {
    return (data.suggestions || []).filter(function (s) {
      return (filters.market === "all" || s.market === filters.market)
        && (filters.tier === "all" || s.tier === filters.tier);
    });
  }

  function drawSpark(canvas, closes) {
    if (!canvas || !closes || closes.length < 2) return;
    var dpr = window.devicePixelRatio || 1;
    var w = 76, h = 30;
    canvas.width = w * dpr; canvas.height = h * dpr;
    var ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    var vals = closes.filter(function (v) { return v != null; });
    var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    var range = max - min || 1;
    var up = vals[vals.length - 1] >= vals[0];
    ctx.strokeStyle = up ? "#2fd181" : "#f25f5c";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    closes.forEach(function (v, i) {
      if (v == null) return;
      var x = (i / (closes.length - 1)) * (w - 2) + 1;
      var y = h - 3 - ((v - min) / range) * (h - 6);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  function renderList() {
    var list = visibleSuggestions();
    els.leadCount.textContent = list.length + " signal" + (list.length === 1 ? "" : "s")
      + (data.scanned_at ? " · scan " + fmtTime(data.scanned_at) : "");
    els.rows.innerHTML = "";
    els.empty.hidden = list.length > 0;
    list.forEach(function (s, i) {
      var p = bestPrice(s);
      // div+role, not <button>: rows contain a nested star button, and
      // nested <button>s are invalid HTML the parser will split apart
      var row = document.createElement("div");
      row.setAttribute("role", "button");
      row.tabIndex = 0;
      row.className = "sigrow" + (s.symbol === selected ? " is-active" : "");
      row.setAttribute("data-sym", s.symbol);
      row.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(s.symbol); }
      });
      var name = (s.company && s.company.name) ? s.company.name : (s.market === "Crypto" ? "Cryptocurrency" : "");
      row.innerHTML =
        '<span class="col-rank">' + (i + 1) + "</span>"
        + '<span class="sigrow__sym">'
        +   '<span class="sigrow__ticker">' + esc(s.symbol.replace("-USD", ""))
        +     '<span class="mchip mchip--' + esc(s.market) + '">' + esc(s.market) + "</span>"
        +     starBtn(s.symbol, s.market, p.px)
        +   "</span>"
        +   '<span class="sigrow__name">' + esc(name) + "</span>"
        + "</span>"
        + '<span class="sigrow__price">'
        +   '<span class="sigrow__px" data-live-px="' + esc(s.symbol) + '">' + fmtPx(p.px, s.market) + "</span>"
        +   '<span class="sigrow__chg ' + chgClass(p.chg) + '" data-live-chg="' + esc(s.symbol) + '">' + fmtChg(p.chg) + "</span>"
        + "</span>"
        + '<canvas class="spark" width="76" height="30" aria-hidden="true"></canvas>'
        + '<span class="sigrow__conv">'
        +   '<span class="tierdot tierdot--' + esc(s.tier) + '" title="' + esc(TIER_LABEL[s.tier] || s.tier) + '"></span>'
        +   '<span class="convbar"><span class="convbar__fill" style="width:' + Math.min(100, s.conviction) + '%"></span></span>'
        +   '<span class="convnum">' + s.conviction + "</span>"
        + "</span>";
      row.addEventListener("click", function () { select(s.symbol); });
      els.rows.appendChild(row);
      if (s.chart && s.chart.close) drawSpark(row.querySelector(".spark"), s.chart.close);
    });
  }

  // ---- Detail panel -----------------------------------------------------
  function indCell(key, val, hint, cls) {
    return '<div class="ind"><span class="ind__k">' + esc(key) + "</span>"
      + '<span class="ind__v ' + (cls || "") + '">' + val + "</span>"
      + (hint ? '<span class="ind__hint">' + esc(hint) + "</span>" : "")
      + "</div>";
  }

  function indicatorGrid(snap, market) {
    if (!snap) return "";
    var benchName = market === "ASX" ? "ASX 200" : market === "Crypto" ? "BTC" : "SPY";
    var cells = [];
    if (snap.rsi14 != null) {
      var rcls = snap.rsi14 > 70 ? "warn" : snap.rsi14 >= 50 ? "up" : snap.rsi14 < 35 ? "down" : "";
      var rhint = snap.rsi14 > 70 ? "overbought" : snap.rsi14 >= 50 ? "bullish" : snap.rsi14 < 35 ? "oversold" : "neutral";
      cells.push(indCell("RSI 14", snap.rsi14.toFixed(0), rhint, rcls));
    }
    if (snap.adx14 != null) {
      cells.push(indCell("ADX 14", snap.adx14.toFixed(0), snap.adx14 >= 25 ? "trending" : "chop", snap.adx14 >= 25 ? "up" : ""));
    }
    if (snap.macd_hist != null) {
      cells.push(indCell("MACD hist", (snap.macd_hist >= 0 ? "+" : "") + (snap.macd_hist * 100).toFixed(2),
        "% of price", snap.macd_hist >= 0 ? "up" : "down"));
    }
    if (snap.stoch_k != null) {
      cells.push(indCell("Stoch %K", snap.stoch_k.toFixed(0), snap.stoch_k > 80 ? "overbought" : snap.stoch_k < 20 ? "oversold" : "", ""));
    }
    if (snap.atr_pct != null) {
      cells.push(indCell("ATR", fmtPct(snap.atr_pct), "daily range"));
    }
    if (snap.vol_ratio != null) {
      cells.push(indCell("Vol ×20d", snap.vol_ratio.toFixed(1) + "×", "", snap.vol_ratio >= 1.5 ? "up" : ""));
    }
    if (snap.sma50_dist != null) {
      cells.push(indCell("vs 50d", fmtPct(snap.sma50_dist, true), "", chgClass(snap.sma50_dist)));
    }
    if (snap.sma200_dist != null) {
      cells.push(indCell("vs 200d", fmtPct(snap.sma200_dist, true), "", chgClass(snap.sma200_dist)));
    }
    if (snap.high_52w_dist != null) {
      cells.push(indCell("vs 52w high", fmtPct(snap.high_52w_dist, true), "", snap.high_52w_dist > -0.05 ? "up" : ""));
    }
    if (snap.ret_1m != null) cells.push(indCell("1M", fmtPct(snap.ret_1m, true), "", chgClass(snap.ret_1m)));
    if (snap.ret_3m != null) cells.push(indCell("3M", fmtPct(snap.ret_3m, true), "", chgClass(snap.ret_3m)));
    if (snap.ret_6m != null) cells.push(indCell("6M", fmtPct(snap.ret_6m, true), "", chgClass(snap.ret_6m)));
    if (snap.rel_1m != null) cells.push(indCell("RS 1M", fmtPct(snap.rel_1m, true), "vs " + benchName, chgClass(snap.rel_1m)));
    if (snap.rel_3m != null) cells.push(indCell("RS 3M", fmtPct(snap.rel_3m, true), "vs " + benchName, chgClass(snap.rel_3m)));
    return cells.join("");
  }

  function barRow(label, val, cls) {
    var v = Math.round(Math.max(0, Math.min(1, Number(val) || 0)) * 100);
    return '<div class="bar"><span class="bar__k">' + esc(label) + "</span>"
      + '<span class="bar__track"><span class="bar__fill ' + (cls || "") + '" style="width:' + v + '%"></span></span>'
      + '<span class="bar__v">' + v + "</span></div>";
  }

  function planHtml(plan) {
    if (!plan) return "";
    return '<div class="dsec"><h3 class="dsec__title">Trade plan</h3>'
      + '<div class="plan">'
      + '<div class="plan__cell"><span class="plan__k">Entry</span><span class="plan__v">' + plan.entry + "</span></div>"
      + '<div class="plan__cell"><span class="plan__k">Stop</span><span class="plan__v stop">' + plan.stop + "</span></div>"
      + '<div class="plan__cell"><span class="plan__k">Target 1</span><span class="plan__v target">' + plan.target1 + "</span></div>"
      + '<div class="plan__cell"><span class="plan__k">Target 2</span><span class="plan__v target">' + plan.target2 + "</span></div>"
      + '<div class="plan__cell"><span class="plan__k">R : R</span><span class="plan__v rr">' + plan.rr + "</span></div>"
      + '<div class="plan__note">Stop: tighter of 20-day swing low / 2×ATR. Target 2: ' + esc(plan.method)
      + ". Levels frame the lead — not advice.</div>"
      + "</div></div>";
  }

  function companyHtml(s) {
    if (s.market === "Crypto") {
      return '<div class="dsec"><h3 class="dsec__title">Asset</h3>'
        + '<p class="codesc">Cryptocurrency — no company fundamentals exist; this lead is technical only.</p></div>';
    }
    var c = s.company || {};
    if (!c.name && !c.description) return "";
    var meta = [c.sector, c.industry !== c.sector ? c.industry : null, c.country,
      typeof c.employees === "number" ? c.employees.toLocaleString() + " employees" : null]
      .filter(Boolean).map(esc).join(" · ");
    var holders = (c.holders || []).map(function (h) {
      return "<li><span>" + esc(h.name) + '</span><span class="pct">' + (h.pct * 100).toFixed(1) + "%</span></li>";
    }).join("");
    var scoreBars = "";
    if (typeof c.strength_score === "number") scoreBars += barRow("Strength", c.strength_score / 100, "");
    if (typeof c.backing_score === "number") scoreBars += barRow("Backing", c.backing_score / 100, "");
    return '<div class="dsec"><h3 class="dsec__title">Company</h3>'
      + (meta ? '<p class="cometa">' + meta + "</p>" : "")
      + (c.description ? '<p class="codesc">' + esc(c.description) + "</p>" : "")
      + (scoreBars ? '<div class="bars">' + scoreBars + "</div>" : "")
      + (holders ? '<ul class="holders">' + holders + "</ul>" : "")
      + "</div>";
  }

  function renderDetail(s) {
    var p = bestPrice(s);
    var name = (s.company && s.company.name) || "";
    var patterns = ((s.technical && s.technical.patterns) || []).map(function (pt) {
      var strength = s.technical.strengths && s.technical.strengths[pt];
      return '<span class="ptag">' + esc(PATTERN_LABEL[pt] || pt)
        + (strength ? "<b>" + Math.round(strength * 100) + "</b>" : "") + "</span>";
    }).join("");
    var reasons = (s.reasons || []).map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("");
    var d = (s.technical && s.technical.detail) || {};
    var f = s.fundamental || {};
    var srcLabel = p.src === "live" ? '<span class="tk__live"></span> live · binance'
      : p.src === "intraday" ? "intraday · delayed" : "daily close";

    els.detailInner.innerHTML =
      '<button type="button" class="detail__close" id="detail-close">✕ &nbsp;Close</button>'
      + '<div class="dhead">'
      +   '<div class="dhead__id">'
      +     '<h2 class="dhead__sym">' + esc(s.symbol.replace("-USD", ""))
      +       '<span class="tierbadge tierbadge--' + esc(s.tier) + '">' + esc(TIER_LABEL[s.tier] || s.tier) + "</span>"
      +       starBtn(s.symbol, s.market, p.px)
      +     "</h2>"
      +     '<p class="dhead__name">' + esc(name || s.market)
      +       (s.earnings ? '<span class="echip">⚠ Earnings in ' + s.earnings.days + "d · " + esc(s.earnings.date) + "</span>" : "")
      +     "</p>"
      +   "</div>"
      +   '<div class="dhead__quote">'
      +     '<div class="dhead__px" data-live-px="' + esc(s.symbol) + '">' + fmtPx(p.px, s.market) + "</div>"
      +     '<div class="dhead__chg ' + chgClass(p.chg) + '" data-live-chg="' + esc(s.symbol) + '">' + fmtChg(p.chg) + "</div>"
      +     '<div class="dhead__src">' + srcLabel + "</div>"
      +   "</div>"
      + "</div>"
      + (s.summary ? '<p class="dsummary">' + esc(s.summary) + "</p>" : "")
      + '<div class="chartbox"><div id="chart"></div>'
      +   '<div class="chartlegend"><i class="lg-c">Price</i><i class="lg-50">SMA 50</i><i class="lg-200">SMA 200</i>'
      +   '<i style="margin-left:auto">Conviction ' + s.conviction + " / 100</i></div>"
      + "</div>"
      + planHtml(s.trade_plan)
      + '<div class="dsec"><h3 class="dsec__title">Indicators</h3><div class="igrid">' + indicatorGrid(s.snapshot, s.market) + "</div></div>"
      + (patterns ? '<div class="dsec"><h3 class="dsec__title">Patterns</h3><div class="ptags">' + patterns + "</div></div>" : "")
      + '<div class="dsec"><h3 class="dsec__title">Technical composition</h3><div class="bars">'
      +   barRow("Setup", d.setup, "tech") + barRow("Trend", d.trend, "tech")
      +   barRow("Momentum", d.momentum, "tech") + barRow("Volume", d.volume, "tech")
      + "</div></div>"
      + (s.market !== "Crypto"
        ? '<div class="dsec"><h3 class="dsec__title">Fundamentals</h3><div class="bars">'
          + barRow("Quality", f.quality, "fund") + barRow("Moat", f.moat, "fund")
          + barRow("Value", f.value, "fund") + barRow("Management", f.management, "fund")
          + "</div></div>"
        : "")
      + (reasons ? '<div class="dsec"><h3 class="dsec__title">Why it surfaced</h3><ul class="rlist">' + reasons + "</ul></div>" : "")
      + companyHtml(s);

    els.detail.hidden = false;
    var closeBtn = document.getElementById("detail-close");
    if (closeBtn) closeBtn.addEventListener("click", function () {
      els.detail.hidden = true;
      selected = null;
      renderList();
    });
    renderChart(s);
  }

  function renderChart(s) {
    var el = document.getElementById("chart");
    if (!el || !window.LightweightCharts || !s.chart || !s.chart.dates) return;
    if (chart) { try { chart.remove(); } catch (e) {} chart = null; }

    var c = s.chart;
    chart = LightweightCharts.createChart(el, {
      autoSize: true,
      height: 300,
      layout: { background: { color: "transparent" }, textColor: "#7c8694",
                fontFamily: "'JetBrains Mono', monospace", fontSize: 10 },
      grid: { vertLines: { color: "rgba(27,33,44,0.6)" }, horzLines: { color: "rgba(27,33,44,0.6)" } },
      rightPriceScale: { borderColor: "#1b212c" },
      timeScale: { borderColor: "#1b212c" },
      crosshair: { mode: 0 },
    });

    var candles = [];
    var vols = [];
    var sma50 = [];
    var sma200 = [];
    for (var i = 0; i < c.dates.length; i++) {
      if (c.open[i] == null || c.close[i] == null) continue;
      var t = c.dates[i];
      candles.push({ time: t, open: c.open[i], high: c.high[i], low: c.low[i], close: c.close[i] });
      var upBar = c.close[i] >= c.open[i];
      vols.push({ time: t, value: c.volume[i] || 0,
        color: upBar ? "rgba(47,209,129,0.25)" : "rgba(242,95,92,0.25)" });
      if (c.sma50 && c.sma50[i] != null) sma50.push({ time: t, value: c.sma50[i] });
      if (c.sma200 && c.sma200[i] != null) sma200.push({ time: t, value: c.sma200[i] });
    }

    var candleSeries = chart.addCandlestickSeries({
      upColor: "#2fd181", downColor: "#f25f5c",
      wickUpColor: "#2fd181", wickDownColor: "#f25f5c",
      borderVisible: false,
    });
    candleSeries.setData(candles);

    var volSeries = chart.addHistogramSeries({
      priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false,
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volSeries.setData(vols);

    if (sma50.length) {
      chart.addLineSeries({ color: "#5aa9e6", lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false }).setData(sma50);
    }
    if (sma200.length) {
      chart.addLineSeries({ color: "#a18ae6", lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false }).setData(sma200);
    }

    // trade-plan levels as price lines
    if (s.trade_plan) {
      var lines = [
        { price: s.trade_plan.stop, color: "#f25f5c", title: "stop" },
        { price: s.trade_plan.target1, color: "#2fd181", title: "T1" },
        { price: s.trade_plan.target2, color: "rgba(47,209,129,0.6)", title: "T2" },
      ];
      lines.forEach(function (l) {
        candleSeries.createPriceLine({
          price: l.price, color: l.color, lineWidth: 1,
          lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: l.title,
        });
      });
    }
    chart.timeScale().fitContent();
  }

  function select(symbol) {
    selected = symbol;
    var s = (data.suggestions || []).find(function (x) { return x.symbol === symbol; });
    if (!s) return;
    renderList();
    renderDetail(s);
    if (window.matchMedia("(min-width: 1081px)").matches) {
      // keep scroll position; panel is sticky
    } else {
      window.scrollTo({ top: 0 });
    }
  }

  // ---- Radar / movers / breadth ------------------------------------------
  function renderRadar() {
    var radar = data.radar || [];
    if (!radar.length) {
      els.radar.innerHTML = '<p class="radar__empty">Nothing close to the bar today.</p>';
      return;
    }
    els.radar.innerHTML = radar.slice(0, 12).map(function (r) {
      var pats = (r.patterns || []).map(function (p) { return PATTERN_LABEL[p] || p; }).join(", ");
      var snap = r.snapshot || {};
      var rsi = snap.rsi14 != null ? "RSI " + Math.round(snap.rsi14) : "";
      return '<div class="radar__row">'
        + '<span class="radar__sym">' + esc(r.symbol.replace("-USD", ""))
        +   '<span class="mchip mchip--' + esc(r.market) + '">' + esc(r.market) + "</span></span>"
        + '<span class="radar__px" data-live-px="' + esc(r.symbol) + '">' + fmtPx(bestPrice(r).px, r.market) + "</span>"
        + '<span class="radar__pat">' + esc(pats || "—") + "</span>"
        + '<span class="radar__rsi">' + esc(rsi) + "</span>"
        + '<span class="radar__conv">' + r.conviction + "</span>"
        + "</div>";
    }).join("");
  }

  function renderMovers() {
    var m = data.movers || {};
    function rows(list) {
      return (list || []).map(function (r) {
        return '<div class="mvr"><span class="mvr__sym">' + esc(r.symbol.replace("-USD", "")) + "</span>"
          + '<span class="mvr__chg ' + chgClass(r.chg_1d) + '">' + fmtChg(r.chg_1d) + "</span></div>";
      }).join("");
    }
    els.gainers.innerHTML = rows(m.gainers);
    els.losers.innerHTML = rows(m.losers);

    var b = data.market && data.market.breadth;
    if (b) {
      var cells = [];
      if (b.pct_above_50dma != null) cells.push(["Above 50-day", Math.round(b.pct_above_50dma * 100) + "%"]);
      if (b.pct_above_200dma != null) cells.push(["Above 200-day", Math.round(b.pct_above_200dma * 100) + "%"]);
      if (b.pct_rsi_bullish != null) cells.push(["RSI > 50", Math.round(b.pct_rsi_bullish * 100) + "%"]);
      if (b.symbols != null) cells.push(["Symbols scanned", b.symbols]);
      els.breadth.innerHTML = cells.map(function (c) {
        return '<div class="breadth__cell"><span class="breadth__k">' + c[0] + '</span><span class="breadth__v">' + c[1] + "</span></div>";
      }).join("");
    }
  }

  // ---- Watchlist panel ------------------------------------------------------
  function renderWatchlist() {
    var wl = loadWL();
    var syms = Object.keys(wl);
    els.watchlistPanel.hidden = false;
    if (!syms.length) {
      els.watchlist.innerHTML = '<p class="wl__empty">Tap ☆ on any signal to pin it here.</p>';
      return;
    }
    els.watchlist.innerHTML = syms.map(function (sym) {
      var w = wl[sym];
      var p = bestPrice({ symbol: sym, market: w.market, price: null, chg_1d: null });
      var since = (p.px != null && w.priceAt) ? p.px / w.priceAt - 1 : null;
      return '<div class="wl__row">'
        + '<span class="wl__sym">' + esc(sym.replace("-USD", ""))
        +   '<span class="wl__since">since ' + esc(w.addedAt || "?") + "</span></span>"
        + '<span class="wl__px">' + (w.priceAt != null ? fmtPx(w.priceAt, w.market) : "—") + "</span>"
        + '<span class="wl__px" data-live-px="' + esc(sym) + '">' + fmtPx(p.px, w.market) + "</span>"
        + '<span class="wl__chg ' + chgClass(since) + '">' + (since != null ? fmtChg(since) : "—") + "</span>"
        + '<button type="button" class="wl__rm" data-star="' + esc(sym) + '" aria-label="Remove">✕</button>'
        + "</div>";
    }).join("");
  }

  // ---- Performance panels (track record + backtest) --------------------------
  function fmtAvg(x) {
    if (x == null) return "—";
    return '<span class="' + (x >= 0 ? "up" : "down") + '">' + fmtPct(x, true) + "</span>";
  }
  function fmtWin(x) {
    if (x == null) return "—";
    return Math.round(x * 100) + "%";
  }

  function renderTrackRecord(tr) {
    if (!tr || !tr.aggregates) return;
    var o = tr.aggregates.overall || {};
    if (!o.episodes) return;
    els.recordPanel.hidden = false;
    var strip = '<div class="stat-strip">'
      + '<div class="breadth__cell"><span class="breadth__k">Leads tracked</span><span class="breadth__v">' + o.episodes + "</span></div>"
      + (o.win_rate_1w != null ? '<div class="breadth__cell"><span class="breadth__k">1w win rate</span><span class="breadth__v">' + fmtWin(o.win_rate_1w) + "</span></div>" : "")
      + (o.avg_1w != null ? '<div class="breadth__cell"><span class="breadth__k">1w avg</span><span class="breadth__v">' + fmtAvg(o.avg_1w) + "</span></div>" : "")
      + (o.win_rate_1m != null ? '<div class="breadth__cell"><span class="breadth__k">1m win rate</span><span class="breadth__v">' + fmtWin(o.win_rate_1m) + "</span></div>" : "")
      + (o.avg_1m != null ? '<div class="breadth__cell"><span class="breadth__k">1m avg</span><span class="breadth__v">' + fmtAvg(o.avg_1m) + "</span></div>" : "")
      + (o.target_rate != null ? '<div class="breadth__cell"><span class="breadth__k">Hit T1 first</span><span class="breadth__v">' + fmtWin(o.target_rate) + "</span></div>" : "")
      + "</div>";

    var tiers = tr.aggregates.by_tier || {};
    var rows = Object.keys(tiers).map(function (t) {
      var a = tiers[t];
      return "<tr><td>" + esc(TIER_LABEL[t] || t) + "</td><td>" + a.episodes + "</td><td>"
        + fmtWin(a.win_rate_1w != null ? a.win_rate_1w : a.win_rate_1m) + "</td><td>"
        + fmtAvg(a.avg_1w != null ? a.avg_1w : a.avg_1m) + "</td></tr>";
    }).join("");
    var table = rows
      ? '<table class="perf__table"><thead><tr><th>Tier</th><th>n</th><th>Win</th><th>Avg</th></tr></thead><tbody>' + rows + "</tbody></table>"
      : "";
    els.record.innerHTML = strip + table
      + '<p class="perf__note">Each lead is tracked from the day it first surfaced. Win/avg use the longest horizon with data (1-week early on, 1-month once mature). Updated daily after the scan.</p>';
  }

  function renderEdge(bt) {
    if (!bt || !bt.aggregates || !bt.aggregates.by_pattern) return;
    var base = (bt.aggregates.baseline || {}).r21 || {};
    var pats = bt.aggregates.by_pattern;
    var keys = Object.keys(pats).filter(function (k) { return pats[k].r21 && pats[k].r21.n >= 30; });
    if (!keys.length) return;
    keys.sort(function (a, b) { return (pats[b].r21.avg || 0) - (pats[a].r21.avg || 0); });
    els.edgePanel.hidden = false;
    var rows = keys.map(function (k) {
      var s = pats[k].r21;
      var edge = base.avg != null ? s.avg - base.avg : null;
      return "<tr><td>" + esc(PATTERN_LABEL[k] || k) + "</td><td>" + s.n + "</td><td>"
        + fmtWin(s.win_rate) + "</td><td>" + fmtAvg(s.avg) + "</td><td>"
        + (edge != null ? fmtAvg(edge) : "—") + "</td></tr>";
    }).join("");
    els.edge.innerHTML =
      '<table class="perf__table"><thead><tr><th>Pattern</th><th>n</th><th>Win</th><th>Avg 1m</th><th>vs base</th></tr></thead><tbody>'
      + rows + "</tbody></table>"
      + '<p class="perf__note">Walk-forward backtest: ' + esc(String(bt.years)) + "y of "
      + esc(bt.universe ? bt.universe.toUpperCase() : "US") + " data, weekly evaluation, "
      + Number(bt.eval_points).toLocaleString() + " points. Baseline 1m: "
      + fmtWin(base.win_rate) + " win, " + fmtAvg(base.avg)
      + ". Survivorship bias applies; no costs. A pattern needs a positive “vs base” to claim edge.</p>";
  }

  function loadPerf() {
    fetch("./data/track_record.json", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(renderTrackRecord)
      .catch(function () {});
    fetch("./data/backtest.json", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(renderEdge)
      .catch(function () {});
  }

  // ---- Live data: Binance WS + quotes polling ------------------------------
  function cryptoSymbols() {
    return tapeSymbols().filter(function (s) { return s.market === "Crypto"; })
      .map(function (s) { return s.symbol; });
  }

  function binanceStream(sym) {
    return sym.replace("-USD", "").toLowerCase() + "usdt@miniTicker";
  }

  function startLive() {
    var syms = cryptoSymbols();
    if (!syms.length || !window.WebSocket) return;
    var streams = syms.map(binanceStream).join("/");
    try {
      ws = new WebSocket("wss://stream.binance.com:9443/stream?streams=" + streams);
    } catch (e) { return; }
    ws.onmessage = function (ev) {
      try {
        var msg = JSON.parse(ev.data);
        var d = msg.data;
        if (!d || !d.s) return;
        var sym = d.s.replace("USDT", "") + "-USD";
        var price = Number(d.c);
        var open = Number(d.o);
        var chg = open > 0 ? price / open - 1 : null;
        var prev = live[sym] && live[sym].price;
        live[sym] = { price: price, chg: chg };
        updateLiveEls(sym, price, chg, prev);
      } catch (e) { /* ignore malformed frames */ }
    };
    ws.onclose = function () { setTimeout(startLive, 8000); };  // auto-reconnect
  }

  var tapeRefreshPending = false;
  function updateLiveEls(sym, price, chg, prev) {
    var market = "Crypto";
    document.querySelectorAll('[data-live-px="' + sym + '"]').forEach(function (el) {
      el.textContent = fmtPx(price, market);
      if (prev && el.classList.contains("dhead__px")) {
        el.classList.remove("live-up", "live-down");
        void el.offsetWidth;   // restart the flash transition
        el.classList.add(price >= prev ? "live-up" : "live-down");
      }
    });
    document.querySelectorAll('[data-live-chg="' + sym + '"]').forEach(function (el) {
      el.textContent = fmtChg(chg);
      el.className = el.className.replace(/\b(up|down)\b/g, "").trim() + " " + chgClass(chg);
    });
    // tape cells update in place
    document.querySelectorAll('[data-tape-sym="' + sym + '"]').forEach(function (el) {
      var px = el.querySelector(".tk__px"), ch = el.querySelector(".tk__chg");
      if (px) px.textContent = fmtPx(price, market);
      if (ch) { ch.textContent = fmtChg(chg); ch.className = "tk__chg " + chgClass(chg); }
      if (!el.querySelector(".tk__live")) {
        var dot = document.createElement("span");
        dot.className = "tk__live";
        el.insertBefore(dot, el.firstChild);
      }
    });
    if (!tapeRefreshPending) {
      tapeRefreshPending = true;
      setTimeout(function () { tapeRefreshPending = false; }, 1000);
    }
  }

  function loadQuotes() {
    return fetch("./data/quotes.json", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("no quotes"); return r.json(); })
      .then(function (j) {
        quotes = (j && j.quotes) || {};
      })
      .catch(function () { quotes = quotes || {}; });
  }

  function pollQuotes() {
    setInterval(function () {
      loadQuotes().then(function () {
        renderTape();
        renderList();
      });
    }, 5 * 60 * 1000);   // the Action refreshes every 30 min; poll lightly
  }

  // ---- AI Supply Chain view ---------------------------------------------------
  var aiData = null;
  var aiLoading = false;

  var CUR = { USD: "$", KRW: "₩", EUR: "€", GBP: "£", TWD: "NT$", JPY: "¥", AUD: "A$" };

  function fmtCur(x, currency) {
    if (x == null || isNaN(x)) return "—";
    var n = Number(x);
    var sym = CUR[currency || "USD"] || "$";
    var opts = n >= 1000 ? { maximumFractionDigits: 0 }
      : n >= 10 ? { minimumFractionDigits: 2, maximumFractionDigits: 2 }
      : { minimumFractionDigits: 2, maximumFractionDigits: 4 };
    return sym + n.toLocaleString(undefined, opts);
  }

  function switchView(view) {
    els.viewSignals.hidden = view !== "signals";
    els.viewAI.hidden = view !== "ai";
    document.querySelectorAll(".viewtab").forEach(function (b) {
      var active = b.dataset.view === view;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-pressed", String(active));
    });
    if (view === "ai") loadAI();
    try { history.replaceState(null, "", view === "ai" ? "#ai" : "#"); } catch (e) {}
  }

  document.querySelectorAll(".viewtab").forEach(function (b) {
    b.addEventListener("click", function () { switchView(b.dataset.view); });
  });

  function loadAI() {
    if (aiData || aiLoading) return;
    aiLoading = true;
    fetch("./data/ai_chain.json", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { aiData = j; renderAI(); })
      .catch(function (e) {
        console.error("SCOUT: ai_chain.json failed", e);
        aiLoading = false;
        els.aiLayers.innerHTML = '<p class="radar__empty">AI chain data not available yet — it generates with the daily scan.</p>';
      });
  }

  function drawSparkInto(canvas, closes, w, h) {
    if (!canvas || !closes || closes.length < 2) return;
    var dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr; canvas.height = h * dpr;
    var ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    var vals = closes.filter(function (v) { return v != null; });
    var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    var range = max - min || 1;
    var up = vals[vals.length - 1] >= vals[0];
    ctx.strokeStyle = up ? "#2fd181" : "#f25f5c";
    ctx.lineWidth = 1.3;
    ctx.beginPath();
    closes.forEach(function (v, i) {
      if (v == null) return;
      var x = (i / (closes.length - 1)) * (w - 2) + 1;
      var y = h - 2 - ((v - min) / range) * (h - 4);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  function heatBadge(heat) {
    if (!heat || heat.score == null) return "";
    return '<span class="heat heat--' + esc(heat.label) + '">'
      + esc(heat.label) + " " + heat.score
      + '<span class="heat__meter"><span class="heat__fill" style="width:' + heat.score + '%"></span></span>'
      + "</span>";
  }

  function scorePill(v) {
    if (v == null) return "—";
    var cls = v >= 70 ? "sp-hi" : v >= 45 ? "sp-mid" : "sp-lo";
    return '<span class="scorepill ' + cls + '">' + v + "</span>";
  }

  function renderAI() {
    if (!aiData) return;
    var hot = (aiData.radar && aiData.radar.hot_layers) || [];
    els.aiMeta.innerHTML = "updated " + esc(fmtTime(aiData.generated_at))
      + "<br>benchmark SMH 3m " + fmtChg(aiData.benchmark && aiData.benchmark.ret_3m)
      + (hot.length ? '<br><span class="hotlist">hot: ' + hot.map(esc).join(" · ") + "</span>" : "");

    // catch-up radar
    var cu = (aiData.radar && aiData.radar.catch_up) || [];
    els.catchup.innerHTML = cu.length ? cu.map(function (c) {
      return '<div class="cu">'
        + '<div class="cu__head"><span class="cu__sym">' + esc(c.symbol.replace("-USD", "")) + "</span>"
        + '<span class="cu__layer">' + esc(c.layer) + "</span>"
        + '<span class="cu__nums">'
        +   "<span>gap <b>" + Math.round((c.gap_to_layer || 0) * 100) + "pp</b></span>"
        +   "<span>growth <b>" + (c.growth_score != null ? c.growth_score : "—") + "</b></span>"
        +   (c.fwd_pe ? "<span>fwd P/E <b>" + c.fwd_pe.toFixed(1) + "</b></span>" : "")
        + "</span></div>"
        + '<p class="cu__thesis">' + esc(c.thesis || "") + "</p>"
        + "</div>";
    }).join("") : '<p class="cu__empty">No hot-layer laggards right now — the chain is either evenly priced or cooling.</p>';

    // leaders
    var ld = (aiData.radar && aiData.radar.leaders) || [];
    els.leaders.innerHTML = ld.length ? ld.map(function (l) {
      return '<div class="ldr"><span class="ldr__sym">' + esc(l.symbol) + "</span>"
        + '<span class="ldr__layer">' + esc(l.layer || "") + "</span>"
        + '<span>' + fmtCur(l.price, l.currency) + "</span>"
        + '<span class="' + chgClass(l.rel_3m) + '">' + fmtChg(l.rel_3m) + "</span>"
        + '<span class="ldr__score">' + (l.ai_score != null ? l.ai_score : "—") + "</span></div>";
    }).join("") : '<p class="cu__empty">No clear leaders at highs right now.</p>';

    // ETFs
    var etfs = aiData.etfs || [];
    var head = '<div class="etf etf--head"><span>Ticker</span><span>What it holds</span>'
      + "<span>Last</span><span>1M</span><span>3M</span><span>6M</span><span></span></div>";
    els.etfs.innerHTML = head + etfs.map(function (e, i) {
      return '<div class="etf"><span class="etf__sym">' + esc(e.symbol) + "</span>"
        + '<span class="etf__note">' + esc(e.note || "") + "</span>"
        + "<span>" + fmtCur(e.price) + "</span>"
        + '<span class="' + chgClass(e.ret_1m) + '">' + fmtChg(e.ret_1m) + "</span>"
        + '<span class="' + chgClass(e.ret_3m) + '">' + fmtChg(e.ret_3m) + "</span>"
        + '<span class="' + chgClass(e.ret_6m) + '">' + fmtChg(e.ret_6m) + "</span>"
        + '<canvas class="lspark" data-etf-spark="' + i + '" width="72" height="24"></canvas>'
        + "</div>";
    }).join("");
    etfs.forEach(function (e, i) {
      drawSparkInto(document.querySelector('[data-etf-spark="' + i + '"]'), e.spark, 72, 24);
    });

    // layers
    els.aiLayers.innerHTML = (aiData.layers || []).map(function (l, li) {
      var h = l.heat || {};
      var stats = [];
      if (h.median_rel_3m != null) stats.push("median RS3m " + fmtChg(h.median_rel_3m));
      if (h.pct_above_50dma != null) stats.push(Math.round(h.pct_above_50dma * 100) + "% above 50d");
      var rows = (l.companies || []).map(function (c, ci) {
        return "<tr>"
          + '<td><span class="sym">' + esc(c.symbol.replace("-USD", ""))
          +   (c.earnings ? '<span class="flag-e" title="Earnings ' + esc(c.earnings.date) + '">⚠E' + c.earnings.days + "d</span>" : "")
          + '</span><span class="nm">' + esc(c.note || c.name || "") + "</span></td>"
          + "<td>" + fmtCur(c.price, c.currency) + "</td>"
          + '<td class="' + chgClass(c.chg_1d) + '">' + fmtChg(c.chg_1d) + "</td>"
          + '<td class="' + chgClass(c.ret_3m) + '">' + fmtChg(c.ret_3m) + "</td>"
          + '<td class="' + chgClass(c.rel_3m) + '">' + fmtChg(c.rel_3m) + "</td>"
          + "<td>" + (c.rev_growth != null ? fmtPct(c.rev_growth, true) : "—") + "</td>"
          + "<td>" + (c.fwd_pe ? c.fwd_pe.toFixed(1) : "—") + "</td>"
          + "<td>" + (c.upside != null ? fmtPct(c.upside, true) : "—") + "</td>"
          + "<td>" + scorePill(c.ai_score) + "</td>"
          + '<td><canvas class="lspark" data-l-spark="' + li + "-" + ci + '" width="72" height="24"></canvas></td>'
          + "</tr>";
      }).join("");
      return '<section class="layer">'
        + '<div class="layer__head">'
        +   '<span class="layer__order">' + String(li + 1).padStart(2, "0") + "</span>"
        +   '<h3 class="layer__name">' + esc(l.name) + "</h3>"
        +   heatBadge(h)
        +   '<span class="layer__stats">' + stats.map(esc).join("  ·  ") + "</span>"
        + "</div>"
        + '<p class="layer__role">' + esc(l.role) + "</p>"
        + '<p class="layer__watch"><b>Watch:</b> ' + esc(l.watch) + "</p>"
        + '<div class="ltable-wrap"><table class="ltable">'
        + "<thead><tr><th>Company</th><th>Last</th><th>1D</th><th>3M</th><th>RS 3M</th>"
        + "<th>Rev growth</th><th>Fwd P/E</th><th>Tgt upside</th><th>Score</th><th>90d</th></tr></thead>"
        + "<tbody>" + rows + "</tbody></table></div>"
        + "</section>";
    }).join("");
    (aiData.layers || []).forEach(function (l, li) {
      (l.companies || []).forEach(function (c, ci) {
        drawSparkInto(document.querySelector('[data-l-spark="' + li + "-" + ci + '"]'), c.spark, 72, 24);
      });
    });
  }

  // ---- Filters --------------------------------------------------------------
  function wireSegmented(container, key) {
    if (!container) return;
    container.addEventListener("click", function (e) {
      var btn = e.target.closest(".seg");
      if (!btn) return;
      filters[key] = btn.dataset.value;
      container.querySelectorAll(".seg").forEach(function (b) {
        var active = b === btn;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-pressed", String(active));
      });
      renderList();
    });
  }

  // ---- Boot -------------------------------------------------------------------
  function init(payload) {
    data = payload;
    els.scannedAt.textContent = "scan " + fmtTime(payload.scanned_at);
    renderBenchmarks(payload.market);
    renderRegime(payload.market);
    renderTape();
    renderList();
    renderRadar();
    renderMovers();
    renderWatchlist();
    loadPerf();
    setStatus("");
    // auto-select the top signal on desktop
    var first = visibleSuggestions()[0];
    if (first && window.matchMedia("(min-width: 1081px)").matches) select(first.symbol);
    startLive();
    pollQuotes();
    loadFearGreed();
    if (location.hash === "#ai") switchView("ai");
  }

  wireSegmented(els.marketFilter, "market");
  wireSegmented(els.tierFilter, "tier");
  setStatus("Loading latest scan…");

  Promise.all([
    fetch("./data/signals.json", { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }),
    loadQuotes(),
  ])
    .then(function (results) { init(results[0]); })
    .catch(function (err) {
      console.error("SCOUT: failed to load signals.json", err);
      setStatus("Couldn't load the latest scan. Refresh to retry.", "error");
    });
})();
