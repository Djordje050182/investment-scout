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
    marketFilter: document.getElementById("market-filter"),
    minConviction: document.getElementById("min-conviction"),
    minConvictionValue: document.getElementById("min-conviction-value"),
  };

  // ---- State --------------------------------------------------------------
  let suggestions = [];                 // sorted, full list from the scan
  const filters = { tier: "all", market: "all", minConviction: 0 };

  const TIER_LABEL = {
    both: "High Conviction",
    technical: "Technical",
    fundamental: "Fundamental",
  };

  // Plain-English definitions surfaced as tooltips (and in the glossary).
  const GLOSSARY = {
    conviction: "Our 0–100 confidence score. It blends the technical (chart) and " +
      "fundamental (business) signals; when both line up the score gets a bonus. " +
      "Higher means a stronger lead — never a guarantee.",
    quality: "How good the business is: consistently high return on equity, healthy " +
      "profit margins, low debt, and positive free cash flow. A high-quality company " +
      "makes good money without taking big risks to do it.",
    value: "Whether the price looks reasonable for what you get — mainly the P/E ratio " +
      "(price relative to earnings). High value means you're not overpaying; a great " +
      "company at a silly price is not a great investment.",
    moat: "A durable competitive advantage that protects profits from competitors — " +
      "think a strong brand, network effects, or switching costs. We approximate it " +
      "with steady, high margins and returns over time. Warren Buffett's favourite trait.",
    both: "Both the chart setup and the business fundamentals look strong at the same " +
      "time — a great company AND a sensible entry point. Our highest-conviction tier.",
    technical: "Surfaced on the chart alone: price and volume patterns like a " +
      "cup-and-handle, a breakout, or an uptrend. (Crypto is always technical-only.)",
    fundamental: "Surfaced on the business alone: high quality and a reasonable price, " +
      "even if the chart isn't flashing a setup yet.",
    backing: "How strongly professional investors back this company — driven mainly " +
      "by the share owned by institutions (funds like BlackRock and Vanguard), with " +
      "a lift for insider ownership. High backing means the 'smart money' is in.",
    strength: "An overall read on how solid the business is, blending its quality, " +
      "moat, and value scores into one number. A high-strength company is a good " +
      "business — separate from whether the chart says now is a good time to buy.",
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

  // A small "?" affordance that reveals a plain-English definition on hover/focus.
  function infoTip(key) {
    const def = GLOSSARY[key];
    if (!def) return "";
    return `<button type="button" class="info" tabindex="0"
      aria-label="What does this mean?" data-tip="${escapeHtml(def)}">?</button>`;
  }

  // ---- Company section builder -------------------------------------------
  function buildCompany(company, isCrypto) {
    if (isCrypto) {
      return `<div class="block company">
        <h3 class="block__title">The company</h3>
        <p class="block__note">This is a cryptocurrency, not a company — there's no
        business, management, or institutional ownership behind it. The lead is
        based purely on its price action.</p>
      </div>`;
    }
    const c = company || {};
    if (!c.name && !c.description && c.backing_score == null) return "";

    const name = c.name ? `<p class="company__name">${escapeHtml(c.name)}</p>` : "";
    const desc = c.description
      ? `<p class="company__desc">${escapeHtml(c.description)}</p>` : "";

    // meta line: sector · industry · country · employees
    const bits = [];
    if (c.sector) bits.push(escapeHtml(c.sector));
    if (c.industry && c.industry !== c.sector) bits.push(escapeHtml(c.industry));
    if (c.country) bits.push(escapeHtml(c.country));
    if (typeof c.employees === "number" && c.employees > 0) {
      bits.push(c.employees.toLocaleString() + " employees");
    }
    const meta = bits.length
      ? `<p class="company__meta">${bits.join(" &middot; ")}</p>` : "";

    // two-score stat row (Backing + Strength), only what's available
    const stats = [];
    if (typeof c.backing_score === "number") {
      stats.push(statBlock("Backing", "backing", c.backing_score));
    }
    if (typeof c.strength_score === "number") {
      stats.push(statBlock("Strength", "strength", c.strength_score));
    }
    const statRow = stats.length
      ? `<div class="company__stats">${stats.join("")}</div>` : "";

    // named institutional backers
    const holders = Array.isArray(c.holders) ? c.holders : [];
    let backersHtml = "";
    if (holders.length) {
      const items = holders.map((h) => {
        const p = (typeof h.pct === "number")
          ? ` <span class="backer__pct">${(h.pct * 100).toFixed(1)}%</span>` : "";
        return `<li>${escapeHtml(h.name)}${p}</li>`;
      }).join("");
      backersHtml = `<div class="company__backers">
        <span class="company__backers-label">Top institutional backers${infoTip("backing")}</span>
        <ul class="backers">${items}</ul>
      </div>`;
    }

    if (!name && !desc && !meta && !statRow && !backersHtml) return "";

    return `<div class="block company">
      <h3 class="block__title">The company</h3>
      ${name}${meta}${desc}${statRow}${backersHtml}
    </div>`;
  }

  function statBlock(label, key, val) {
    const v = Math.max(0, Math.min(100, Math.round(Number(val) || 0)));
    return `<div class="stat">
      <span class="stat__label">${label}${infoTip(key)}</span>
      <span class="stat__bar"><span class="stat__fill" style="width:${v}%"></span></span>
      <span class="stat__val">${v}</span>
    </div>`;
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
    const scoreRow = (name, key, val) => {
      const v = pct(val);
      return `<div class="score">
        <span class="score__name">${name}${infoTip(key)}</span>
        <span class="score__track"><span class="score__fill" style="width:${v}%"></span></span>
        <span class="score__val">${v}</span>
      </div>`;
    };

    const summaryHtml = s.summary
      ? `<p class="card__summary">${escapeHtml(s.summary)}</p>`
      : "";

    // Crypto has no fundamentals — don't show an all-zero fundamental profile.
    const isCrypto = (s.market || "").toLowerCase() === "crypto";

    const techScore = pct(s.technical && s.technical.score);
    const fundScore = pct(s.fundamental && s.fundamental.score);

    const companyHtml = buildCompany(s.company, isCrypto);

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
          <span class="ring__label">Conviction${infoTip("conviction")}</span>
        </div>
      </div>

      <span class="badge badge--${tier}">${TIER_LABEL[tier]}${infoTip(tier)}</span>

      ${summaryHtml}

      ${companyHtml}

      <div class="block">
        <h3 class="block__title">Why it surfaced</h3>
        ${reasonsHtml}
      </div>

      <div class="block">
        <h3 class="block__title">Technical patterns</h3>
        <div class="patterns">${patternsHtml}</div>
      </div>

      ${isCrypto ? `
      <div class="block">
        <h3 class="block__title">Fundamental profile</h3>
        <p class="block__note">Crypto isn't a company, so there are no business
        fundamentals to screen — this lead is based on price action alone.</p>
      </div>` : `
      <div class="block">
        <h3 class="block__title">Fundamental profile</h3>
        <div class="scores">
          ${scoreRow("Quality", "quality", f.quality)}
          ${scoreRow("Value", "value", f.value)}
          ${scoreRow("Moat", "moat", f.moat)}
        </div>
      </div>`}

      <div class="card__foot">
        <span>Technical <b>${techScore}</b></span>
        <span>Fundamental <b>${isCrypto ? "—" : fundScore}</b></span>
      </div>
    `;
    return card;
  }

  // ---- Render with current filters ---------------------------------------
  function render() {
    const visible = suggestions.filter((s) => {
      const tierOk = filters.tier === "all" || s.tier === filters.tier;
      const marketOk = filters.market === "all" || s.market === filters.market;
      const convOk = (Number(s.conviction) || 0) >= filters.minConviction;
      return tierOk && marketOk && convOk;
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
  function wireSegmented(container, key) {
    if (!container) return;
    container.addEventListener("click", (e) => {
      const btn = e.target.closest(".seg");
      if (!btn) return;
      filters[key] = btn.dataset.value;
      container.querySelectorAll(".seg").forEach((b) => {
        const active = b === btn;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-pressed", String(active));
      });
      render();
    });
  }

  function setupControls() {
    wireSegmented(els.tierFilter, "tier");
    wireSegmented(els.marketFilter, "market");

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
