// assets/locales_render.js
// Enhanced Locales Renderer — dynamic tiers, flags, fallback-safe, chart-ready

(function globalLocalesRenderer() {
    const LOCALE_META = {
        // === TIER 1: TOP PRIORITY ===
        en: { name: "English (EN)", flag: "🇬🇧", tier: 1 },
        de: { name: "German (DE)", flag: "🇩🇪", tier: 1 },
        es: { name: "Spanish (ES)", flag: "🇪🇸", tier: 1 },
        it: { name: "Italian (IT)", flag: "🇮🇹", tier: 1 },
        no: { name: "Norwegian (NO)", flag: "🇳🇴", tier: 1 },
        pl: { name: "Polish (PL)", flag: "🇵🇱", tier: 1 },
        tr: { name: "Turkish (TR)", flag: "🇹🇷", tier: 1 },
        uk: { name: "Ukrainian (UK)", flag: "🇺🇦", tier: 1 },
        pt: { name: "Portuguese (PT)", flag: "🇵🇹", tier: 1 },
        sv: { name: "Swedish (SV)", flag: "🇸🇪", tier: 1 },

        // === TIER 2: MID PRIORITY ===
        th: { name: "Thai (TH)", flag: "🇹🇭", tier: 2 },
        fi: { name: "Finnish (FI)", flag: "🇫🇮", tier: 2 },
        nl: { name: "Dutch (NL)", flag: "🇳🇱", tier: 2 },
        "es-la": { name: "Spanish (Latin America)", flag: "🇲🇽", tier: 2 },

        // === TIER 3: LOW PRIORITY ===
        el: { name: "Greek (EL)", flag: "🇬🇷", tier: 3 },
        hu: { name: "Hungarian (HU)", flag: "🇭🇺", tier: 3 },
        id: { name: "Indonesian (ID)", flag: "🇮🇩", tier: 3 },
        cs: { name: "Czech (CS)", flag: "🇨🇿", tier: 3 },
        bg: { name: "Bulgarian (BG)", flag: "🇧🇬", tier: 3 },
        ro: { name: "Romanian (RO)", flag: "🇷🇴", tier: 3 },
        vi: { name: "Vietnamese (VI)", flag: "🇻🇳", tier: 3 },
    };

    // ===== Create one locale section =====
    function createLocaleSection(localeCode, summary) {
        const meta = LOCALE_META[localeCode] || { name: localeCode.toUpperCase(), flag: "🏳️", tier: 3 };
        if (meta.tier >= 3) return null; // skip low-tier locales visually

        const section = document.createElement("section");
        section.className = `locale-section locale-${localeCode}`;
        section.setAttribute("data-locale", localeCode);
        section.setAttribute("data-tier", meta.tier);

        const info = document.createElement("div");
        info.className = "locale-info";

        const title = document.createElement("div");
        title.className = "locale-title";
        title.innerHTML = `
            <span class="flag" aria-hidden="true">${meta.flag}</span>
            <div>
                <div style="font-weight:700">${localeCode.toUpperCase()}</div>
                <div class="locale-fullname">${meta.name}</div>
            </div>`;

        const smallKPIs = document.createElement("div");
        smallKPIs.style.marginTop = "8px";
        smallKPIs.innerHTML = `
            <div style="font-size:13px;color:var(--muted)">Latest run: 
                <strong style="color:var(--accent)">${summary.latest_run || "—"}</strong>
            </div>
            <div style="margin-top:6px;font-size:13px;color:var(--muted)">Total links: 
                <strong style="color:var(--accent)">${summary.total_links || 0}</strong>
            </div>
            <div style="margin-top:6px;font-size:13px;color:var(--muted)">Avg success: 
                <strong style="color:var(--accent)">${(summary.avg_success_rate || 0).toFixed(2)}%</strong>
            </div>`;

        info.appendChild(title);
        info.appendChild(smallKPIs);

        const chartsWrap = document.createElement("div");
        chartsWrap.className = "locale-charts";

        const cardA = document.createElement("div");
        cardA.className = "chart-card";
        cardA.innerHTML = `<h4>${meta.name} — Success %</h4><canvas id="locale_${localeCode}_success"></canvas>`;

        const cardB = document.createElement("div");
        cardB.className = "chart-card";
        cardB.innerHTML = `<h4>${meta.name} — Broken Links</h4><canvas id="locale_${localeCode}_broken"></canvas>`;

        chartsWrap.appendChild(cardA);
        chartsWrap.appendChild(cardB);

        section.appendChild(info);
        section.appendChild(chartsWrap);

        return { section, successCanvasId: `locale_${localeCode}_success`, brokenCanvasId: `locale_${localeCode}_broken` };
    }

    // ===== Render all locale sections into the dashboard =====
    window.renderLocaleSections = function renderLocaleSections(metrics) {
        const container = document.getElementById("locales-container");
        if (!container) return {};
        container.innerHTML = "";

        const locales = (metrics && metrics.locales) || {};
        const created = {};

        Object.keys(locales).forEach(loc => {
            const summary = locales[loc] || {};
            const built = createLocaleSection(loc, summary);
            if (!built) return;
            const { section, successCanvasId, brokenCanvasId } = built;

            section.setAttribute("data-locale-full", summary.latest_run || "");
            container.appendChild(section);
            created[loc] = { successCanvasId, brokenCanvasId, summary };
        });

        return created;
    };

    // ===== Render charts from per-locale data =====
    window.renderLocaleChartsFromSeries = function renderLocaleChartsFromSeries(localeSeriesMap = {}) {
        Object.keys(localeSeriesMap).forEach(loc => {
            const series = localeSeriesMap[loc] || [];
            const labels = series.map(s => s.date);
            const success = series.map(s => Number(s.success_rate || 0));
            const broken = series.map(s => Number(s.broken_links || 0));

            const sCtx = document.getElementById(`locale_${loc}_success`);
            const bCtx = document.getElementById(`locale_${loc}_broken`);

            if (!sCtx && !bCtx) return;

            if (sCtx) {
                new Chart(sCtx.getContext("2d"), {
                    type: "line",
                    data: { labels, datasets: [{ label: "Success %", data: success, borderColor: "#36a2eb", backgroundColor: "rgba(54,162,235,0.08)", tension: 0.25, pointRadius: 2 }] },
                    options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, max: 100 } }, plugins: { legend: { display: false } } }
                });
            }

            if (bCtx) {
                new Chart(bCtx.getContext("2d"), {
                    type: "bar",
                    data: { labels, datasets: [{ label: "Broken Links", data: broken, backgroundColor: "#ef4444", barThickness: 12 }] },
                    options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } }, plugins: { legend: { display: false }, tooltip: { mode: "index" } } }
                });
            }
        });
    };

    // Expose locale metadata globally
    window.LOCALE_META = LOCALE_META;
})();