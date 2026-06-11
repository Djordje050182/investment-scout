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
    viewCrystal: document.getElementById("view-crystal"),
    meter: document.getElementById("buy-meter"),
    meterNum: document.getElementById("meter-num"),
    meterLabel: document.getElementById("meter-label"),
    meterFill: document.getElementById("meter-fill"),
    meterWhy: document.getElementById("meter-why"),
    cbAmount: document.getElementById("cb-amount"),
    cbHorizon: document.getElementById("cb-horizon"),
    cbRisk: document.getElementById("cb-risk"),
    cbOutput: document.getElementById("cb-output"),
    strategyFamily: document.getElementById("strategy-family"),
    aiMeta: document.getElementById("ai-meta"),
    aiPulse: document.getElementById("ai-pulse"),
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

  // ---- Plain-English term explainers --------------------------------------
  var GLOSS = {
    conviction: ["Conviction score", "Our 0–100 confidence that this is a lead worth researching. It blends the chart picture (technical) with the health of the business (fundamental). Higher = stronger lead. It is never a guarantee — think of it as how loudly the data is raising its hand."],
    tier: ["Signal tier", "WHY a name surfaced. Technical = the price chart looks good. Fundamental = the business looks good. High Conviction = both at once — a good company AND a sensible-looking moment, our top shelf."],
    both: ["High Conviction", "The chart and the business both look strong at the same time. Historically the best kind of setup: a quality company at a technically sensible moment."],
    technical: ["Technical signal", "Surfaced because of the price chart alone — patterns in price and volume. Says nothing about whether the business is good."],
    fundamental: ["Fundamental signal", "Surfaced because the business looks high-quality and reasonably priced — even if the chart isn't doing anything exciting yet."],
    rsi: ["RSI (momentum gauge)", "A 0–100 dial of how fast price has been rising or falling. Around 50 = calm. 50–70 = healthy climb. Above 70 = possibly overheated (be careful buying). Below 30 = beaten up (sometimes a bounce coming)."],
    macd: ["MACD", "A trend-change detector that compares a fast moving average with a slow one. When the fast line crosses above the slow one, momentum may be turning up — an early (but fallible) green shoot."],
    adx: ["ADX (trend strength)", "Measures how STRONG a trend is, ignoring direction. Above 25 = a real trend is underway. Below 20 = sideways chop where trend-following tends to fail."],
    stoch: ["Stochastic %K", "Where today's price sits inside its recent range, 0–100. Near 100 = pressing the top of the range; near 0 = scraping the bottom."],
    atr: ["ATR (daily wiggle)", "The average size of this asset's daily move — its noise level. We size stops and targets in ATRs so they sit outside normal wiggle. Higher ATR = bumpier ride."],
    vol_ratio: ["Volume ratio", "Today's trading volume versus the recent average. 2× means twice the usual shares changed hands — big volume behind a move suggests real conviction, not noise."],
    sma50: ["50-day average", "The average price of the last ~10 weeks, drawn as a smooth line. Price above a rising 50-day = healthy medium-term trend. Traders often watch it as a 'dip-buying' level."],
    sma200: ["200-day average", "The average price of the last ~10 months — the long-term health line. Above it: long-term uptrend. Below it: something is broken. Many big investors won't buy below it."],
    high52w: ["Distance from 52-week high", "How far price sits below its best level of the past year. Near the high = strength (strong stocks make new highs). Far below = either damaged or a potential recovery story."],
    rs: ["Relative strength (RS)", "This asset's return MINUS the market's return over the same period. +10% RS means it beat the benchmark by 10 points. Winners tend to keep beating; chronic laggards lag for a reason."],
    entry: ["Entry", "The price the plan is framed around — roughly where the asset trades now."],
    stop: ["Stop (exit if wrong)", "The pre-agreed 'I was wrong' price. If it falls here, the idea is invalidated and the plan says get out and keep the loss small. Set below normal daily wiggle so noise alone doesn't knock you out."],
    target: ["Targets", "Where the plan suggests taking profit. Target 1 is the modest first milestone; Target 2 is the fuller move if the pattern plays out."],
    rr: ["Risk : Reward (R:R)", "How much you stand to make at Target 1 versus lose at the stop. 2.0 means risking $1 to potentially make $2. Below 1.0 the math is against you."],
    cup_and_handle: ["Cup & Handle pattern", "Price carves a rounded dip and recovery (the cup), pauses with a small dip (the handle), then often breaks higher. The rounded shape suggests patient accumulation rather than panic."],
    breakout: ["Breakout", "Price pushes above a ceiling it kept failing at — on heavy volume. The ceiling-breakers often keep going, because everyone who wanted to sell there already has."],
    uptrend: ["Uptrend", "Price above its rising 50- and 200-day averages — the simplest definition of 'going up'. Trends persist more often than they reverse."],
    golden_cross: ["Golden cross", "The 50-day average crossing above the 200-day — a classic 'the tide has turned' signal that often marks the early innings of a long advance."],
    bull_flag: ["Bull flag", "A sharp rise (the pole) followed by a tight, calm drift (the flag). Often a rest stop, not a top — the move frequently continues by about the length of the pole."],
    double_bottom: ["Double bottom", "Price hits a low, bounces, retests the same low and holds — a 'W' shape. Two failures to go lower suggests sellers are exhausted."],
    bollinger_squeeze: ["Volatility squeeze", "The price's recent range has compressed to unusually tight levels. Quiet periods store energy — big moves often follow, in either direction."],
    obv_accumulation: ["Volume accumulation (OBV)", "Volume flowing in on up-days faster than out on down-days — a footprint of quiet, persistent buying that sometimes shows up before price moves."],
    pullback_to_trend: ["Pullback to trend", "A strong stock dips back to its 50-day average and steadies — the 'buy quality on a dip' setup, with the long-term trend intact."],
    oversold_reversal: ["Oversold bounce", "A long-term uptrend gets washed out short-term (RSI under 35), then hooks back up. Dips in strong stocks tend to get bought."],
    high_52w_momentum: ["Near 52-week highs", "Strength begets strength: stocks pressing their yearly highs with a real trend behind them tend to keep making new highs."],
    macd_bull_cross: ["MACD bullish cross", "The momentum gauge just flipped positive. Fired alone it's weak — we treat it as confirmation, not a reason to buy."],
    quality: ["Quality", "How good the business is at making money safely: high returns on shareholders' capital, fat margins, low debt, real cash flow."],
    value: ["Value", "Whether the price is reasonable for what you get — mainly the P/E ratio. A wonderful company at a silly price is still a bad deal."],
    moat: ["Moat", "A durable edge competitors can't easily copy — a brand, network effects, switching costs. Warren Buffett's favourite word. Moats keep profits fat."],
    management: ["Management", "Whether the people running it act like owners — we proxy it with share buybacks (shrinking share count = your slice grows)."],
    backing: ["Backing", "How much of the company big professional funds (and insiders) own. Heavy institutional ownership = the smart money has done its homework."],
    strength: ["Business strength", "One number blending quality, moat and value — how solid the underlying company is, separate from what the stock price is doing."],
    fwd_pe: ["Forward P/E", "Price divided by NEXT year's expected profit — how many years of future earnings you're paying upfront. Lower can mean cheap… or that the market doubts the forecast."],
    rev_growth: ["Revenue growth", "How fast sales grew versus a year ago. Sustained growth is the raw fuel of every great stock story."],
    upside: ["Analyst target upside", "How far Wall Street's average price target sits above today's price. Take with salt — analysts herd and chase — but big gaps are worth noticing."],
    ai_score: ["AI-chain score", "Our 0–100 blend for chain companies: momentum (40%), growth (35%), value-for-growth (25%). A ranking aid, not a verdict."],
    layer_heat: ["Layer heat", "How hot this slice of the supply chain is right now: median outperformance vs the chip index plus how many members are in uptrends. The AI build-out re-rates layer by layer — heat shows where the wave is."],
    catchup: ["Catch-up radar", "The pattern behind the great Micron trade: a layer turns hot, but one healthy member hasn't re-rated yet — growth intact, trend intact, not expensive vs peers. Rotation often reaches it next. Often ≠ always."],
    breadth: ["Breadth", "What fraction of everything we scan is above its own 50-day average. High breadth = a broad, healthy advance. Low breadth = a few generals, no army."],
    regime: ["Market regime", "The big-picture weather: Risk-On (benchmarks trending up, broad participation), Risk-Off (downtrends, hide), or Neutral. The same stock setup works far better in a rising tide."],
    fng: ["Fear & Greed index", "A 0–100 crowd-mood gauge for crypto. Extreme fear (low) historically marked better buying moments than extreme greed (high). A contrarian thermometer."],
    etf: ["ETF", "A single ticker that holds a whole basket of investments — one purchase, instant diversification, tiny fees. The sane default for most people most of the time."],
    preferred: ["Preferred share", "A hybrid between a share and a bond: it pays a fixed dividend and has priority over common stock, but usually little upside beyond that income. You're lending money, dressed as a share."],
    btc_treasury: ["Bitcoin treasury company", "A listed company whose main asset is a pile of bitcoin, often bought with borrowed money. The stock behaves like turbo-charged bitcoin — both directions."],
    neocloud: ["Neocloud", "A young cloud company that rents out raw AI computing power (GPUs) by the hour. Hypergrowth, heavy debt, big promises — high octane in both directions."],
    hyperscaler: ["Hyperscaler", "The giant clouds — Microsoft, Google, Amazon, Meta, Oracle. Their capital spending (hundreds of billions a year) funds the entire AI supply chain beneath them."],
    hbm: ["HBM (high-bandwidth memory)", "Special stacked memory chips bolted right next to AI processors so data arrives fast enough. The big 2025–26 bottleneck — demand outran supply and prices flew. Made by Micron, SK hynix, Samsung."],
    euv: ["EUV lithography", "The most precise machines ever built — they draw chip features with extreme ultraviolet light. One company on Earth makes them (ASML). No EUV, no advanced AI chips."],
    foundry: ["Foundry", "A factory that manufactures chips designed by others. TSMC makes the chips for Nvidia, AMD, Apple and nearly everyone — the single most indispensable company in the chain."],
    meter: ["Today's conditions meter", "A 0–100 read on whether TODAY is a friendly day to put new money to work, blending: market regime, breadth, benchmark momentum, and the quality of today's signals. It measures conditions, not your situation — and it is absolutely not a promise."],
    horizon: ["Time horizon", "When you might genuinely need this money back. The single most important input: money needed within a year should never ride in volatile assets, because you can be forced to sell at the worst moment."],
    risk_appetite: ["Risk appetite", "Honestly: how far can your investment fall before you panic-sell? Careful = a 15% drop would hurt. Balanced = can sit through 25%. Bold = can watch 40%+ vanish and not flinch. Be honest — overestimating this is the #1 amateur mistake."],
    spark: ["Sparkline", "A tiny 90-day price chart. Green = higher than 90 days ago, red = lower. Shape at a glance."],
    search_heat: ["Search interest (Google Trends)", "How often people are googling this layer's theme versus its 12-month normal. ×2.0 = double the usual curiosity. Attention often shows up in search before it shows up in price."],
    news_heat: ["News volume (GDELT)", "How much the world's news is covering this theme versus its recent baseline, from a free global news database. A sudden ×3 means the story is breaking out of the trade press into the mainstream."],
    pulse: ["Chain pulse", "TSMC and Foxconn report revenue EVERY MONTH (most companies only manage quarterly). Since nearly every AI chip passes through them, their monthly growth is the closest thing to a real-time meter on the whole chain's demand."],
    setup: ["Setup", "The strongest chart pattern currently present, with small credit for extra confirming patterns. The 'is there actually something to act on?' score."],
    trend: ["Trend", "The backdrop: moving-average structure and trend strength. Good setups in bad trends fail more."],
    momentum: ["Momentum", "Shorter-term push: RSI, MACD and the last month's pace."],
    volume_sub: ["Volume", "Whether trading activity supports the move — recent volume vs normal, and whether volume flows in on up-days."],
  };

  function termAttr(key) { return GLOSS[key] ? ' data-term="' + key + '"' : ""; }
  function termWrap(label, key) {
    if (!GLOSS[key]) return esc(label);
    return '<button type="button" class="t" data-term="' + key + '">' + esc(label) + "</button>";
  }

  var pop = {
    root: document.getElementById("termpop"),
    title: document.getElementById("termpop-title"),
    body: document.getElementById("termpop-body"),
  };
  function openTerm(key) {
    var def = GLOSS[key];
    if (!def) return;
    pop.title.textContent = def[0];
    pop.body.textContent = def[1];
    pop.root.hidden = false;
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-termpop-close]")) { pop.root.hidden = true; return; }
    var t = e.target.closest("[data-term]");
    if (t) { e.preventDefault(); e.stopPropagation(); openTerm(t.dataset.term); }
  }, true);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") pop.root.hidden = true;
  });

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
    // constant reading pace regardless of symbol count: ~28 px/s
    requestAnimationFrame(function () {
      var halfWidth = els.tape.scrollWidth / 2;
      if (halfWidth > 0) {
        els.tape.style.animationDuration = Math.max(60, Math.round(halfWidth / 28)) + "s";
      }
    });
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
  function indCell(key, val, hint, cls, termKey) {
    return '<div class="ind"><span class="ind__k">'
      + (termKey ? termWrap(key, termKey) : esc(key)) + "</span>"
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
      cells.push(indCell("RSI 14", snap.rsi14.toFixed(0), rhint, rcls, "rsi"));
    }
    if (snap.adx14 != null) {
      cells.push(indCell("ADX 14", snap.adx14.toFixed(0), snap.adx14 >= 25 ? "trending" : "chop", snap.adx14 >= 25 ? "up" : "", "adx"));
    }
    if (snap.macd_hist != null) {
      cells.push(indCell("MACD hist", (snap.macd_hist >= 0 ? "+" : "") + (snap.macd_hist * 100).toFixed(2),
        "% of price", snap.macd_hist >= 0 ? "up" : "down", "macd"));
    }
    if (snap.stoch_k != null) {
      cells.push(indCell("Stoch %K", snap.stoch_k.toFixed(0), snap.stoch_k > 80 ? "overbought" : snap.stoch_k < 20 ? "oversold" : "", "", "stoch"));
    }
    if (snap.atr_pct != null) {
      cells.push(indCell("ATR", fmtPct(snap.atr_pct), "daily range", "", "atr"));
    }
    if (snap.vol_ratio != null) {
      cells.push(indCell("Vol ×20d", snap.vol_ratio.toFixed(1) + "×", "", snap.vol_ratio >= 1.5 ? "up" : "", "vol_ratio"));
    }
    if (snap.sma50_dist != null) {
      cells.push(indCell("vs 50d", fmtPct(snap.sma50_dist, true), "", chgClass(snap.sma50_dist), "sma50"));
    }
    if (snap.sma200_dist != null) {
      cells.push(indCell("vs 200d", fmtPct(snap.sma200_dist, true), "", chgClass(snap.sma200_dist), "sma200"));
    }
    if (snap.high_52w_dist != null) {
      cells.push(indCell("vs 52w high", fmtPct(snap.high_52w_dist, true), "", snap.high_52w_dist > -0.05 ? "up" : "", "high52w"));
    }
    if (snap.ret_1m != null) cells.push(indCell("1M", fmtPct(snap.ret_1m, true), "", chgClass(snap.ret_1m)));
    if (snap.ret_3m != null) cells.push(indCell("3M", fmtPct(snap.ret_3m, true), "", chgClass(snap.ret_3m)));
    if (snap.ret_6m != null) cells.push(indCell("6M", fmtPct(snap.ret_6m, true), "", chgClass(snap.ret_6m)));
    if (snap.rel_1m != null) cells.push(indCell("RS 1M", fmtPct(snap.rel_1m, true), "vs " + benchName, chgClass(snap.rel_1m), "rs"));
    if (snap.rel_3m != null) cells.push(indCell("RS 3M", fmtPct(snap.rel_3m, true), "vs " + benchName, chgClass(snap.rel_3m), "rs"));
    return cells.join("");
  }

  function barRow(label, val, cls, termKey) {
    var v = Math.round(Math.max(0, Math.min(1, Number(val) || 0)) * 100);
    return '<div class="bar"><span class="bar__k">'
      + (termKey ? termWrap(label, termKey) : esc(label)) + "</span>"
      + '<span class="bar__track"><span class="bar__fill ' + (cls || "") + '" style="width:' + v + '%"></span></span>'
      + '<span class="bar__v">' + v + "</span></div>";
  }

  function planHtml(plan) {
    if (!plan) return "";
    return '<div class="dsec"><h3 class="dsec__title">Trade plan</h3>'
      + '<div class="plan">'
      + '<div class="plan__cell"><span class="plan__k">' + termWrap("Entry", "entry") + '</span><span class="plan__v">' + plan.entry + "</span></div>"
      + '<div class="plan__cell"><span class="plan__k">' + termWrap("Stop", "stop") + '</span><span class="plan__v stop">' + plan.stop + "</span></div>"
      + '<div class="plan__cell"><span class="plan__k">' + termWrap("Target 1", "target") + '</span><span class="plan__v target">' + plan.target1 + "</span></div>"
      + '<div class="plan__cell"><span class="plan__k">' + termWrap("Target 2", "target") + '</span><span class="plan__v target">' + plan.target2 + "</span></div>"
      + '<div class="plan__cell"><span class="plan__k">' + termWrap("R : R", "rr") + '</span><span class="plan__v rr">' + plan.rr + "</span></div>"
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
    if (typeof c.strength_score === "number") scoreBars += barRow("Strength", c.strength_score / 100, "", "strength");
    if (typeof c.backing_score === "number") scoreBars += barRow("Backing", c.backing_score / 100, "", "backing");
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
      +       '<span class="tierbadge tierbadge--' + esc(s.tier) + '" data-term="' + esc(s.tier) + '">' + esc(TIER_LABEL[s.tier] || s.tier) + "</span>"
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
      +   '<i style="margin-left:auto" data-term="conviction" class="t">Conviction ' + s.conviction + " / 100</i></div>"
      + "</div>"
      + planHtml(s.trade_plan)
      + '<div class="dsec"><h3 class="dsec__title">Indicators</h3><div class="igrid">' + indicatorGrid(s.snapshot, s.market) + "</div></div>"
      + (patterns ? '<div class="dsec"><h3 class="dsec__title">Patterns</h3><div class="ptags">' + patterns + "</div></div>" : "")
      + '<div class="dsec"><h3 class="dsec__title">Technical composition</h3><div class="bars">'
      +   barRow("Setup", d.setup, "tech", "setup") + barRow("Trend", d.trend, "tech", "trend")
      +   barRow("Momentum", d.momentum, "tech", "momentum") + barRow("Volume", d.volume, "tech", "volume_sub")
      + "</div></div>"
      + (s.market !== "Crypto"
        ? '<div class="dsec"><h3 class="dsec__title">Fundamentals</h3><div class="bars">'
          + barRow("Quality", f.quality, "fund", "quality") + barRow("Moat", f.moat, "fund", "moat")
          + barRow("Value", f.value, "fund", "value") + barRow("Management", f.management, "fund", "management")
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
    els.viewCrystal.hidden = view !== "crystal";
    document.querySelectorAll(".viewtab").forEach(function (b) {
      var active = b.dataset.view === view;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-pressed", String(active));
    });
    if (view === "ai" || view === "crystal") loadAI();   // crystal uses chain data too
    if (view === "crystal") renderCrystal();
    try {
      history.replaceState(null, "", view === "ai" ? "#ai" : view === "crystal" ? "#crystal" : "#");
    } catch (e) {}
  }

  document.querySelectorAll(".viewtab").forEach(function (b) {
    b.addEventListener("click", function () { switchView(b.dataset.view); });
  });

  function loadAI() {
    if (aiData || aiLoading) return;
    aiLoading = true;
    fetch("./data/ai_chain.json", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { aiData = j; renderAI(); renderCrystal(); })
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
    return '<span class="heat heat--' + esc(heat.label) + '" data-term="layer_heat">'
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

    // chain pulse: TWSE monthly revenue proxies (TSMC = chain demand)
    var twse = (aiData.pulse && aiData.pulse.twse) || {};
    var pulseChips = Object.keys(twse).map(function (code) {
      var p = twse[code];
      var month = p.month ? p.month.slice(2).replace("-", "/") : "";
      return '<span class="pulse__chip"><b>' + esc(p.name || code) + "</b> "
        + esc(month) + ' rev <span class="' + chgClass(p.yoy_pct) + '">'
        + (p.yoy_pct >= 0 ? "+" : "") + p.yoy_pct.toFixed(1) + "% YoY</span>"
        + '<span class="' + chgClass(p.ytd_yoy_pct) + '">'
        + (p.ytd_yoy_pct >= 0 ? "+" : "") + p.ytd_yoy_pct.toFixed(1) + "% YTD</span></span>";
    });
    els.aiPulse.hidden = pulseChips.length === 0;
    if (pulseChips.length) {
      els.aiPulse.innerHTML = '<span class="pulse__label t" data-term="pulse">Chain pulse</span>'
        + pulseChips.join("")
        + '<span class="pulse__src">monthly revenue · TWSE open data — the chain’s best free leading indicator</span>';
    }

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
        var edgarTip = c.edgar
          ? "SEC filings: " + c.edgar.form4_90d + " insider Form 4s in 90d"
            + (c.edgar.last_8k ? " · last 8-K " + c.edgar.last_8k : "")
          : "";
        return "<tr>"
          + '<td><span class="sym"' + (edgarTip ? ' title="' + esc(edgarTip) + '"' : "") + ">"
          +   esc(c.symbol.replace("-USD", ""))
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
      var att = l.attention || {};
      var attChips = "";
      function attChip(label, ratio, term) {
        if (ratio == null) return "";
        var cls = ratio >= 1.15 ? " att--hot" : ratio <= 0.85 ? " att--cool" : "";
        return '<span class="att' + cls + '" data-term="' + (label === "Search" ? "search_heat" : "news_heat") + '" title="' + esc('"' + term + '" vs its 12-month norm') + '">'
          + label + " <b>×" + ratio.toFixed(1) + "</b></span>";
      }
      attChips += attChip("Search", att.trends_ratio, att.trends_term || "");
      attChips += attChip("News", att.news_ratio, att.news_term || "");
      return '<section class="layer">'
        + '<div class="layer__head">'
        +   '<span class="layer__order">' + String(li + 1).padStart(2, "0") + "</span>"
        +   '<h3 class="layer__name">' + esc(l.name) + "</h3>"
        +   heatBadge(h)
        +   attChips
        +   '<span class="layer__stats">' + stats.map(esc).join("  ·  ") + "</span>"
        + "</div>"
        + '<p class="layer__role">' + esc(l.role) + "</p>"
        + '<p class="layer__watch"><b>Watch:</b> ' + esc(l.watch) + "</p>"
        + '<div class="ltable-wrap"><table class="ltable">'
        + '<thead><tr><th>Company</th><th>Last</th><th>1D</th><th>3M</th>'
        + "<th>" + termWrap("RS 3M", "rs") + "</th>"
        + "<th>" + termWrap("Rev growth", "rev_growth") + "</th>"
        + "<th>" + termWrap("Fwd P/E", "fwd_pe") + "</th>"
        + "<th>" + termWrap("Tgt upside", "upside") + "</th>"
        + "<th>" + termWrap("Score", "ai_score") + "</th>"
        + "<th>" + termWrap("90d", "spark") + "</th></tr></thead>"
        + "<tbody>" + rows + "</tbody></table></div>"
        + "</section>";
    }).join("");
    (aiData.layers || []).forEach(function (l, li) {
      (l.companies || []).forEach(function (c, ci) {
        drawSparkInto(document.querySelector('[data-l-spark="' + li + "-" + ci + '"]'), c.spark, 72, 24);
      });
    });
  }

  // ---- "Good buy today" conditions meter --------------------------------------
  function renderMeter() {
    if (!data) return;
    var m = data.market || {};
    var score = 0;
    var why = [];

    var regime = m.regime || "neutral";
    score += regime === "risk_on" ? 30 : regime === "neutral" ? 15 : 0;
    why.push({ risk_on: "market regime: risk-on", neutral: "market regime: neutral",
               risk_off: "market regime: risk-off" }[regime]);

    var b = m.breadth && m.breadth.pct_above_50dma;
    if (b != null) {
      score += Math.round(b * 25);
      why.push(Math.round(b * 100) + "% of scanned names above their 50-day");
    } else { score += 12; }

    var spy = m.benchmarks && m.benchmarks.SPY;
    var chg5 = spy && spy.chg_5d;
    if (chg5 != null) {
      score += Math.max(0, Math.min(15, Math.round((chg5 + 0.02) / 0.04 * 15)));
      why.push("S&P 500 " + fmtChg(chg5) + " over 5 days");
    } else { score += 7; }

    var sugs = data.suggestions || [];
    if (sugs.length) {
      var top3 = sugs.slice(0, 3).map(function (s) { return s.conviction; });
      var avg = top3.reduce(function (a, b2) { return a + b2; }, 0) / top3.length;
      score += Math.max(0, Math.min(20, Math.round((avg - 55) / 40 * 20)));
      why.push(sugs.length + " signal" + (sugs.length === 1 ? "" : "s")
        + " today, strongest " + sugs[0].conviction + "/100");
    } else {
      why.push("no signals cleared the bar today");
    }
    score += Math.min(10, sugs.filter(function (s) { return s.conviction >= 75; }).length * 2.5);

    score = Math.round(Math.max(0, Math.min(100, score)));
    var label = score >= 65 ? "Favourable" : score >= 40 ? "Mixed" : "Caution";
    var cls = score >= 65 ? "meter--good" : score >= 40 ? "meter--mixed" : "meter--caution";

    els.meter.hidden = false;
    els.meter.className = "meter " + cls;
    els.meterNum.textContent = score;
    els.meterLabel.textContent = label;
    els.meterFill.style.width = score + "%";
    els.meterWhy.innerHTML = why.map(function (w) { return "<span>" + esc(w) + "</span>"; }).join("");
  }

  // ---- Crystal Ball -------------------------------------------------------------
  var cb = { amount: 10000, horizon: "medium", risk: "balanced" };

  // Explicit allocation matrices per (risk, horizon) — percentages sum to 100.
  // Deliberately boring numbers; the fold explains the reasoning.
  var ALLOC = {
    careful: {
      short: { core: 30, income: 30, cash: 40 },
      medium: { core: 50, theme: 15, stocks: 10, income: 15, cash: 10 },
      long: { core: 55, theme: 20, stocks: 10, income: 10, cash: 5 },
    },
    balanced: {
      short: { core: 40, theme: 10, income: 25, cash: 25 },
      medium: { core: 35, theme: 25, stocks: 20, income: 10, spec: 5, cash: 5 },
      long: { core: 40, theme: 30, stocks: 20, spec: 5, cash: 5 },
    },
    bold: {
      short: { core: 40, theme: 20, stocks: 10, income: 10, cash: 20 },
      medium: { core: 20, theme: 30, stocks: 30, income: 5, spec: 10, cash: 5 },
      long: { core: 25, theme: 30, stocks: 30, spec: 12, cash: 3 },
    },
  };

  var BUCKET_META = {
    core: { name: "Core — the boring backbone", color: "#5aa9e6",
      why: "A broad index fund: one purchase, hundreds of companies. This is the part that quietly compounds while everything else makes noise." },
    theme: { name: "AI theme — ride the build-out", color: "#d2a85e",
      why: "Theme ETFs from the hottest layers of the AI supply chain. Concentrated, volatile, but diversified across a whole layer rather than one ticket." },
    stocks: { name: "Single stocks — today's strongest ideas", color: "#ecc987",
      why: "Pulled live from today's highest-conviction signals and the catch-up radar. Highest potential, highest risk — any single company can halve." },
    income: { name: "Income — get paid to wait", color: "#a18ae6",
      why: "Things that pay you: utilities riding AI power demand, and Strategy's high-yield preferred shares (with real caveats — read their cards below)." },
    spec: { name: "Speculative — small and honest about it", color: "#f25f5c",
      why: "Turbo-charged bets: bitcoin, its leveraged proxy MSTR, and a neocloud. Sized so that even going to zero wouldn't change your life." },
    cash: { name: "Cash — dry powder", color: "#4c5563",
      why: "Boring on purpose. Cash is an option on every future dip; the meter above tells you when conditions improve." },
  };

  function money(x) {
    return "$" + Math.round(x).toLocaleString();
  }

  function cbQuote(sym) {
    var q = live[sym] || quotes[sym];
    return q && q.price != null ? q.price : null;
  }

  function buildBucketItems(key) {
    var items = [];
    if (key === "core") {
      items.push({ sym: "VOO", why: "Vanguard S&P 500 ETF — a slice of America's 500 biggest companies for a 0.03% fee. Any broad index fund does the same job." });
    } else if (key === "theme") {
      items.push({ sym: "SMH", why: "The big semiconductor names (Nvidia, TSMC, Broadcom) in one ticket — the chain's engine room." });
      var hot = (aiData && aiData.radar && aiData.radar.hot_layers) || [];
      if (hot.indexOf("Memory & Storage") >= 0) {
        items.push({ sym: "DRAM", why: "Memory pure-play ETF — the layer the catch-up radar says is running hottest (the Micron trade in fund form)." });
      } else if (hot.indexOf("Power Generation & Grid") >= 0) {
        items.push({ sym: "AIPO", why: "AI × power ETF — the electricity bottleneck wrapped in one ticket." });
      } else {
        items.push({ sym: "AIQ", why: "Broad AI ETF — 80+ holdings across the whole theme, for when no single layer stands out." });
      }
    } else if (key === "stocks") {
      var seen = {};
      ((data && data.suggestions) || []).slice(0, 3).forEach(function (s) {
        seen[s.symbol] = true;
        items.push({ sym: s.symbol,
          whyText: "Today's signal — conviction " + s.conviction + "/100 ("
            + (TIER_LABEL[s.tier] || s.tier) + ")."
            + (s.reasons && s.reasons[0] ? " " + s.reasons[0] + "." : "") });
      });
      (((aiData || {}).radar || {}).catch_up || []).slice(0, 2).forEach(function (c) {
        if (seen[c.symbol]) return;
        items.push({ sym: c.symbol, whyText: c.thesis });
      });
      if (!items.length) items.push({ sym: "—", whyText: "No signals cleared the bar today — the honest answer is: wait." });
    } else if (key === "income") {
      items.push({ sym: "XLU", why: "Utilities ETF — the companies selling electricity to power-hungry AI data centres, with dividends." });
      items.push({ sym: "STRC", why: "Strategy 'Stretch' preferred — variable dividend, currently ~11.5%/yr paid MONTHLY, engineered to hug $100. The yield is real; so is the bitcoin-balance-sheet risk behind it." });
      items.push({ sym: "STRF", why: "Strategy 'Strife' preferred — 10% fixed dividend. Trading under $100 par, so the effective yield is higher. Same caveat: it's only as safe as Strategy's bitcoin pile." });
    } else if (key === "spec") {
      items.push({ sym: "BTC-USD", why: "Bitcoin itself — the cleanest way to own the idea, no company in between." });
      items.push({ sym: "MSTR", why: "Strategy — a software company turned giant bitcoin vault. Moves like bitcoin with the volume turned way up, both directions. Down hard over the past 8 months; that's the bet and the warning in one chart." });
      var neo = null;
      ((aiData && aiData.layers) || []).forEach(function (l) {
        if (l.key !== "datacenter_cloud") return;
        (l.companies || []).forEach(function (c) {
          if (["CRWV", "NBIS", "IREN", "APLD"].indexOf(c.symbol) >= 0
              && (!neo || (c.ai_score || 0) > (neo.ai_score || 0))) neo = c;
        });
      });
      if (neo) items.push({ sym: neo.symbol, why: "Best-scoring neocloud right now (" + (neo.ai_score || "—") + "/100) — rents raw GPU power by the hour. Hypergrowth, heavy debt, high octane." });
    } else if (key === "cash") {
      items.push({ sym: "CASH", why: "A high-interest savings account or money-market fund. Not dead money — it's your ticket to buy the next dip without selling anything." });
    }
    return items;
  }

  function renderCrystal() {
    if (!els.cbOutput || els.viewCrystal.hidden) { renderStrategyFamily(); return; }
    var alloc = (ALLOC[cb.risk] || {})[cb.horizon] || ALLOC.balanced.medium;
    alloc = JSON.parse(JSON.stringify(alloc));

    // regime adjustment: in a risk-off tape, pull risk down and hold more cash
    var regime = data && data.market && data.market.regime;
    var regimeNote = "";
    if (regime === "risk_off") {
      var taken = 0;
      ["spec", "stocks", "theme"].forEach(function (k) {
        if (alloc[k]) { var cut = Math.round(alloc[k] * 0.25); alloc[k] -= cut; taken += cut; }
      });
      alloc.cash = (alloc.cash || 0) + taken;
      regimeNote = "The market is risk-off right now, so this sketch holds " + taken + "pp more cash than usual.";
    } else if (regime === "risk_on") {
      regimeNote = "The market is risk-on right now — conditions are friendlier than average for this sketch.";
    }

    var amount = Math.max(0, Number(els.cbAmount.value) || 0);
    cb.amount = amount;

    var keys = Object.keys(alloc).filter(function (k) { return alloc[k] > 0; });
    var bar = keys.map(function (k) {
      return '<span style="width:' + alloc[k] + '%;background:' + BUCKET_META[k].color + '" title="'
        + esc(BUCKET_META[k].name + " " + alloc[k] + "%") + '"></span>';
    }).join("");

    var buckets = keys.map(function (k) {
      var meta = BUCKET_META[k];
      var dollars = amount * alloc[k] / 100;
      var items = buildBucketItems(k);
      var per = items.length ? dollars / items.length : 0;
      var rows = items.map(function (it) {
        var px = it.sym !== "CASH" && it.sym !== "—" ? cbQuote(it.sym) : null;
        var pxHtml = px != null
          ? '<span class="bitem__px">now ' + fmtPx(px, it.sym.endsWith("-USD") ? "Crypto" : "US") + "</span>" : "";
        return '<div class="bitem">'
          + '<span class="bitem__sym">' + esc(it.sym.replace("-USD", "")) + "</span>"
          + '<span class="bitem__amt">' + money(per) + "</span>"
          + pxHtml
          + '<span class="bitem__why">' + esc(it.whyText || it.why || "") + "</span>"
          + "</div>";
      }).join("");
      return '<div class="bucket">'
        + '<div class="bucket__head">'
        +   '<span class="bucket__dot" style="background:' + meta.color + '"></span>'
        +   '<span class="bucket__name">' + esc(meta.name) + "</span>"
        +   '<span class="bucket__amt">' + money(dollars) + "</span>"
        +   '<span class="bucket__pct">' + alloc[k] + "%</span>"
        +   '<span class="bucket__why">' + esc(meta.why) + "</span>"
        + "</div>"
        + '<div class="bucket__items">' + rows + "</div>"
        + "</div>";
    }).join("");

    var horizonLabel = { short: "under 1 year", medium: "1–3 years", long: "3+ years" }[cb.horizon];
    els.cbOutput.innerHTML =
      '<div class="cb-warn"><b>Before anything else:</b> this is an educational sketch built from'
      + " today's data and textbook allocation rules — not personal financial advice. It knows nothing about your"
      + ' debts, income, taxes or sleep quality. Nobody — human or machine — can promise "maximum returns."'
      + ' Anyone who does is selling something. If this money matters, talk to a licensed adviser.</div>'
      + '<div class="cb-summary"><span>' + money(amount) + " · " + esc(horizonLabel) + " · " + esc(cb.risk) + "</span>"
      + (regimeNote ? "<span>" + esc(regimeNote) + "</span>" : "")
      + "</div>"
      + '<div class="cb-bar">' + bar + "</div>"
      + buckets
      + '<p class="perf__note">Within each bucket, amounts are split evenly — precision beyond this is'
      + " false comfort. A sensible rhythm: invest in 2–3 chunks over a few weeks rather than all at once,"
      + " and rebalance once or twice a year. Tap any ticker term anywhere on this site for a plain-English"
      + " explanation.</p>";
    renderStrategyFamily();
  }

  var SFAMILY = [
    { sym: "MSTR", nick: "the mothership",
      desc: "Strategy (formerly MicroStrategy) — a software company that bet itself on bitcoin and now holds one of the world's largest BTC piles, much of it bought with borrowed money. The stock is effectively bitcoin with leverage: it rises faster and falls harder. It has fallen for 8 straight months as BTC cooled — high risk, high theatre." },
    { sym: "STRK", nick: "Strike — 8% convertible",
      desc: "A preferred share paying a fixed 8% yearly dividend, with a bonus: it can convert into MSTR stock if MSTR rises far enough. Think 'bond with a lottery ticket attached'. Trading well below its $100 par, the real yield is higher — because the market is pricing in real risk." },
    { sym: "STRF", nick: "Strife — 10% fixed",
      desc: "The straightforward one: 10% fixed dividend, no conversion frills, paid quarterly. Priced under par, so the effective yield is above 10%. You're lending money to a bitcoin treasury — the fat yield IS the risk warning." },
    { sym: "STRD", nick: "Stride — 10% non-cumulative",
      desc: "Also 10%, but 'non-cumulative': if Strategy ever skips a dividend, it never owes you the missed ones. That weaker protection is why it trades at the deepest discount — and therefore the juiciest (riskiest) effective yield of the family." },
    { sym: "STRC", nick: "Stretch — variable, paid monthly",
      desc: "Engineered to behave like a high-yield savings account: a variable dividend (currently ~11.5%/yr) paid monthly, with the rate tuned to keep the price hugging $100. The most stable of the family by design — but the income still depends entirely on Strategy staying solvent." },
  ];

  function renderStrategyFamily() {
    if (!els.strategyFamily) return;
    els.strategyFamily.innerHTML = SFAMILY.map(function (f) {
      var q = quotes[f.sym] || {};
      return '<div class="sfam">'
        + '<div class="sfam__head">'
        +   '<span class="sfam__sym">' + f.sym + "</span>"
        +   '<span class="sfam__nick">' + esc(f.nick) + "</span>"
        +   (q.price != null ? '<span class="sfam__px" data-live-px="' + f.sym + '">' + fmtPx(q.price, "US") + "</span>" : "")
        +   (q.chg_1d != null ? '<span class="sfam__chg ' + chgClass(q.chg_1d) + '">' + fmtChg(q.chg_1d) + "</span>" : "")
        + "</div>"
        + '<p class="sfam__desc">' + esc(f.desc) + " "
        + '<button type="button" class="t" data-term="' + (f.sym === "MSTR" ? "btc_treasury" : "preferred") + '">What kind of thing is this?</button></p>'
        + "</div>";
    }).join("");
  }

  function wireCrystal() {
    if (els.cbAmount) {
      els.cbAmount.addEventListener("input", function () { renderCrystal(); });
    }
    [["cbHorizon", "horizon"], ["cbRisk", "risk"]].forEach(function (pair) {
      var el = els[pair[0]];
      if (!el) return;
      el.addEventListener("click", function (e) {
        var btn = e.target.closest(".seg");
        if (!btn) return;
        cb[pair[1]] = btn.dataset.value;
        el.querySelectorAll(".seg").forEach(function (b) {
          var active = b === btn;
          b.classList.toggle("is-active", active);
          b.setAttribute("aria-pressed", String(active));
        });
        renderCrystal();
      });
    });
  }
  wireCrystal();

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
    renderMeter();
    loadPerf();
    setStatus("");
    // auto-select the top signal on desktop
    var first = visibleSuggestions()[0];
    if (first && window.matchMedia("(min-width: 1081px)").matches) select(first.symbol);
    startLive();
    pollQuotes();
    loadFearGreed();
    if (location.hash === "#ai") switchView("ai");
    if (location.hash === "#crystal") switchView("crystal");
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
