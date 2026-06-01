/* =========================================================================
   Investment Scout — Signal Desk
   Vanilla JS. Fetches ./data/signals.json (relative for GH Pages subpaths),
   renders conviction-sorted cards, supports live tier + min-conviction filters.
   ========================================================================= */

(function () {
  "use strict";

  // ---- DOM handles --------------------------------------------------------
  const els = {
    scannedAt: document.getElementById("scanned-at"),
    universe: document.getElementById("universe"),
    count: document.getElementById("count"),
    cards: document.getElementById("cards"),
    empty: document.getElementById("empty"),
    status: document.getElementById("status"),
    tierFilter: document.getElementById("tier-filter"),
    minConviction: document.getElementById("min-conviction"),
    minConvictionValue: document.getElementById("min-conviction-value"),
  };

  // ---- State --------------------------------------------------------------
  let suggestions = [];                 // sorted, full list from the scan
  const filters = { tier: "all", minConviction: 0 };

  const TIER_LABEL = {
    both: "High Conviction",
    technical: "Technical",
    fundamental: "Fundamental",
  };

  // ---- Helpers ------------------------------------------------------------
  function setStatus(message, kind) {
    els.status.textContent = message || "";
    els.status.className = "status" + (kind ? " status--" + kind : "");
  }

  function formatTimestamp(iso) {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso || "unknown";
    try {
      return new Intl.DateTimeFormat(undefined, {
        weekday: "short", year: "numeric", month: "short", day: "numeric",
        hour: "2-digit", minute: "2-digit", timeZoneName: "short",
      }).format(d);
    } catch (e) {
      return d.toUTCString();
    }
  }

  function prettyPattern(p) {
    return String(p).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function pct(score) {
    const n = Math.max(0, Math.min(1, Number(score) || 0));
    return Math.round(n * 100);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  // ---- Card builder -------------------------------------------------------
  function buildCard(s) {
    const tier = TIER_LABEL[s.tier] ? s.tier : "fundamental";
    const conviction = Math.max(0, Math.min(100, Math.round(Number(s.conviction) || 0)));

    const card = document.createElement("article");
    card.className = "card card--" + tier;
    card.setAttribute("aria-label",
      `${s.symbol}, conviction ${conviction} out of 100, ${TIER_LABEL[tier]} signal`);

    // ring geometry
    const R = 36, C = 2 * Math.PI * R;
    const offset = C * (1 - conviction / 100);

    const reasons = Array.isArray(s.reasons) ? s.reasons : [];
    const reasonsHtml = reasons.length
      ? `<ul class="reasons">${reasons.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>`
      : `<ul class="reasons"><li>No reasons recorded.</li></ul>`;

    const patterns = (s.technical && Array.isArray(s.technical.patterns)) ? s.technical.patterns : [];
    const patternsHtml = patterns.length
      ? patterns.map((p) => `<span class="chip">${escapeHtml(prettyPattern(p))}</span>`).join("")
      : `<span class="chip chip--none">No patterns detected</span>`;

    const f = s.fundamental || {};
    const scoreRow = (name, val) => {
      const v = pct(val);
      return `<div class="score">
        <span class="score__name">${name}</span>
        <span class="score__track"><span class="score__fill" style="width:${v}%"></span></span>
        <span class="score__val">${v}</span>
      </div>`;
    };

    const techScore = pct(s.technical && s.technical.score);
    const fundScore = pct(s.fundamental && s.fundamental.score);

    card.innerHTML = `
      <div class="card__head">
        <div class="ticker">
          <div class="ticker__sym">${escapeHtml(s.symbol)}</div>
          <div class="ticker__row">
            <span class="ticker__market">${escapeHtml(s.market || "—")}</span>
            <span class="ticker__price">${Number(s.price).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          </div>
        </div>
        <div class="ring" role="img" aria-label="Conviction ${conviction} of 100">
          <svg width="86" height="86" viewBox="0 0 86 86">
            <circle class="ring__track" cx="43" cy="43" r="${R}" fill="none" stroke-width="7"/>
            <circle class="ring__value" cx="43" cy="43" r="${R}" fill="none" stroke-width="7"
              stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${offset.toFixed(1)}"/>
          </svg>
          <span class="ring__num">${conviction}</span>
          <span class="ring__label">Conviction</span>
        </div>
      </div>

      <span class="badge badge--${tier}">${TIER_LABEL[tier]}</span>

      <div class="block">
        <h3 class="block__title">Why it surfaced</h3>
        ${reasonsHtml}
      </div>

      <div class="block">
        <h3 class="block__title">Technical patterns</h3>
        <div class="patterns">${patternsHtml}</div>
      </div>

      <div class="block">
        <h3 class="block__title">Fundamental profile</h3>
        <div class="scores">
          ${scoreRow("Quality", f.quality)}
          ${scoreRow("Value", f.value)}
          ${scoreRow("Moat", f.moat)}
        </div>
      </div>

      <div class="card__foot">
        <span>Technical <b>${techScore}</b></span>
        <span>Fundamental <b>${fundScore}</b></span>
      </div>
    `;
    return card;
  }

  // ---- Render with current filters ---------------------------------------
  function render() {
    const visible = suggestions.filter((s) => {
      const tierOk = filters.tier === "all" || s.tier === filters.tier;
      const convOk = (Number(s.conviction) || 0) >= filters.minConviction;
      return tierOk && convOk;
    });

    els.cards.innerHTML = "";

    if (visible.length === 0) {
      els.empty.hidden = false;
      return;
    }

    els.empty.hidden = true;
    const frag = document.createDocumentFragment();
    visible.forEach((s, i) => {
      const card = buildCard(s);
      card.style.animationDelay = Math.min(i * 60, 360) + "ms";
      frag.appendChild(card);
    });
    els.cards.appendChild(frag);
  }

  // ---- Filter wiring ------------------------------------------------------
  function setupControls() {
    els.tierFilter.addEventListener("click", (e) => {
      const btn = e.target.closest(".seg");
      if (!btn) return;
      filters.tier = btn.dataset.tier;
      els.tierFilter.querySelectorAll(".seg").forEach((b) => {
        const active = b === btn;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-pressed", String(active));
      });
      render();
    });

    const onSlide = () => {
      const v = Number(els.minConviction.value);
      filters.minConviction = v;
      els.minConvictionValue.textContent = v;
      els.minConviction.style.setProperty("--fill", v + "%");
      render();
    };
    els.minConviction.addEventListener("input", onSlide);
    onSlide(); // initialise fill visual
  }

  // ---- Boot ---------------------------------------------------------------
  function init(data) {
    els.scannedAt.textContent = formatTimestamp(data.scanned_at);
    els.universe.textContent = data.universe || "—";

    const list = Array.isArray(data.suggestions) ? data.suggestions.slice() : [];
    list.sort((a, b) => (Number(b.conviction) || 0) - (Number(a.conviction) || 0));
    suggestions = list;

    const count = typeof data.count === "number" ? data.count : list.length;
    els.count.textContent = count;

    setStatus("");
    render();
  }

  setupControls();
  setStatus("Loading latest scan…", "loading");

  fetch("./data/signals.json", { cache: "no-store" })
    .then((res) => {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();
    })
    .then(init)
    .catch((err) => {
      console.error("Investment Scout: failed to load signals.json", err);
      suggestions = [];
      els.count.textContent = "—";
      els.scannedAt.textContent = "—";
      els.empty.hidden = true;
      els.cards.innerHTML = "";
      setStatus("Couldn't load the latest scan. Please refresh or try again later.", "error");
    });
})();
