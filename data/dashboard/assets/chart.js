/* ============================================================
   🍏 Website Monitor Dashboard — Final Stable Apple Dark Theme
   ============================================================ */

const METRICS_URL = "./generated/metrics.json";
const BROKEN_CSV_FALLBACK = "../reports/broken_links_latest.csv";
const PAGE_SIZE = 25;
const chartCache = {};

// ------------------ Chart Defaults ------------------
Chart.register(window.ChartDataLabels);
Chart.defaults.color = "#e6e8ea";
Chart.defaults.borderColor = "rgba(255,255,255,0.1)";
Chart.defaults.font.family =
  '-apple-system, BlinkMacSystemFont, "SF Pro Text", Inter, Roboto, sans-serif';
Chart.defaults.font.size = 12;
Chart.defaults.plugins.legend.labels.color = "#b8c0c8";
Chart.defaults.plugins.tooltip.backgroundColor = "rgba(30,30,32,0.95)";
Chart.defaults.plugins.tooltip.borderColor = "rgba(52,199,89,0.3)";
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.titleColor = "#34c759";
Chart.defaults.plugins.tooltip.bodyColor = "#f5f5f5";

// ------------------ UTILITIES ------------------
const $id = (id) => document.getElementById(id);
const safeNum = (n) => Number(n || 0).toFixed(2);
const exists = (id) => !!document.getElementById(id);

async function loadJSON(url) {
  try {
    const r = await fetch(url + "?t=" + Date.now());
    if (!r.ok) throw new Error("HTTP " + r.status);
    return await r.json();
  } catch (e) {
    console.warn("⚠️ metrics.json load failed", e);
    return null;
  }
}

// ------------------ HEALTH BAR ------------------
function updateHealthBar(data) {
  const global = data.global || {};
  const latest = data.latest_run || {};
  const success = global.overall_success_rate || 0;

  const healthEl = $id("site-health");
  const currentEl = $id("current-status");
  const nextEl = $id("next-run");

  let status = "ok";
  let text = "Healthy";
  if (success < 80) {
    status = "err";
    text = "Critical";
  } else if (success < 95) {
    status = "warn";
    text = "Warning";
  }

  if (healthEl) {
    healthEl.textContent = text;
    healthEl.className = `health-status ${status}`;
  }

  if (currentEl) {
    const runNum = latest.run_number || global.total_runs || 0;
    const state = latest.state || "completed";
    const emoji =
      {
        running: "🟢",
        starting: "🟡",
        completed: "⚫",
        failed: "🔴",
      }[state] || "⚪";
    currentEl.textContent = `${emoji} Run #${runNum} — ${
      state.charAt(0).toUpperCase() + state.slice(1)
    }`;
  }

  if (nextEl) {
    try {
      const runTime = new Date(latest.time);
      const next = new Date(runTime.getTime() + 6 * 60 * 60 * 1000);
      nextEl.textContent = next.toLocaleString("en-GB", { hour12: false });
    } catch {
      nextEl.textContent = "Every 6 hours";
    }
  }
}

// ------------------ KPI ------------------
function updateKPI(data) {
  const latest = data.latest_run || {};
  const global = data.global || {};

  if ($id("latest-success"))
    $id("latest-success").textContent = safeNum(latest.success_rate) + "%";
  if ($id("latest-duration"))
    $id("latest-duration").textContent = ((latest.duration_sec || 0) / 60).toFixed(1);
  if ($id("latest-total"))
    $id("latest-total").textContent = latest.total_links || "--";
  if ($id("latest-broken"))
    $id("latest-broken").textContent = latest.broken_links || "--";

  if ($id("overall-runs"))
    $id("overall-runs").textContent = global.total_runs || "--";
  if ($id("overall-links"))
    $id("overall-links").textContent = global.total_links_checked || "--";
  if ($id("overall-broken"))
    $id("overall-broken").textContent = global.total_broken_links || "--";
  if ($id("overall-success"))
    $id("overall-success").textContent =
      safeNum(global.overall_success_rate) + "%";
}

// ------------------ CHART HELPERS ------------------
function makeLineConfig(labels, datasets, opts = {}) {
  return {
    type: "line",
    data: { labels, datasets },
    options: Object.assign(
      {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 10, left: 5, right: 5, bottom: 5 } },
        plugins: {
          legend: { position: "top" },
          datalabels: {
            color: "#34c759",
            font: { weight: "500", size: 11 },
            align: "top",
            formatter: (v) => {
              const n = typeof v === "number" ? v : parseFloat(v);
              return Number.isFinite(n) ? n.toFixed(1) : "";
            },
          },
        },
        scales: { y: { beginAtZero: true } },
      },
      opts
    ),
  };
}

function makeBarConfig(labels, datasets, maxY = null) { 
  return {
    type: "bar",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 10, bottom: 5 } },
      scales: {
        y: { beginAtZero: true, max: maxY ? maxY * 1.5 : undefined, grace: "10%" },
        x: { grid: { display: false } },
      },
      plugins: {
        legend: { display: false },
        datalabels: {
          color: "#34c759",
          font: { weight: "600", size: 11 },
          anchor: "end",
          align: "top",
          formatter: (v) => {
            const n = typeof v === "number" ? v : parseFloat(v);
            return Number.isFinite(n) ? String(Math.round(n)) : "";
          },
        },
      },
    },
  };
}


function updateChart(id, config) {
  const ctx = $id(id)?.getContext("2d");
  if (!ctx) return;
  if (chartCache[id]) {
    chartCache[id].data = config.data;
    chartCache[id].update();
  } else {
    chartCache[id] = new Chart(ctx, config);
  }
}

// ------------------ GLOBAL CHARTS ------------------
function renderGlobalCharts(data) {
  const trend = data.weekly_trend || [];
  const labels = trend.map((x) => x.date);
  const success = trend.map((x) => Number(x.success_rate || 0));
  const eff = trend.map((x) => Number(x.crawler_efficiency || 0));
  const broken = trend.map((x) => Number(x.broken_links || 0));

  const avgDuration = (data.global.average_duration_sec || 0) / 60;
  const durations = trend.map((x) =>
    x.duration_sec ? (x.duration_sec / 60).toFixed(2) : avgDuration.toFixed(2)
  );

  // Efficiency
  updateChart(
    "chartEff",
    makeBarConfig(labels, [
      {
        label: "Efficiency %",
        data: eff,
        backgroundColor: "#0a84ff",
        barThickness: 24,
      },
    ])
  );

  // Broken
  updateChart(
    "chartBroken",
    makeBarConfig(labels, [
      {
        label: "Broken",
        data: broken,
        backgroundColor: "#ff453a",
        barThickness: 24,
      },
    ])
  );

  // Duration
  updateChart(
    "chartDuration",
    makeLineConfig(labels, [
      {
        label: "Duration (mins)",
        data: durations,
        borderColor: "#ffd60a",
        tension: 0.3,
      },
    ])
  );

  // Success
  updateChart(
    "chartSuccess",
    makeLineConfig(labels, [
      { label: "Success %", data: success, borderColor: "#34c759", tension: 0.3 },
    ])
  );

  // Placeholder Error Chart (if no CSV yet)
  updateChart("chartError", {
    type: "pie",
    data: { labels: ["Loading..."], datasets: [{ data: [1], backgroundColor: ["#333"] }] },
  });

  // Valid vs Broken Pie
  const latest = data.latest_run || {};
  const brokenNow = Number(latest.broken_links || 0);
  const totalNow = Number(latest.total_links || 0);
  const valid = Math.max(totalNow - brokenNow, 0);

  updateChart("chartValidBroken", {
    type: "pie",
    data: {
      labels: ["Valid", "Broken"],
      datasets: [
        { data: [valid, brokenNow], backgroundColor: ["#34c759", "#ff453a"] },
      ],
    },
    options: {
      plugins: {
        legend: { position: "bottom" },
        datalabels: {
          color: "#fff",
          font: { size: 13, weight: "600" },
          formatter: (v, ctx) =>
            ctx.chart.data.labels[ctx.dataIndex] + ": " + v,
        },
      },
    },
  });
}

// ------------------ LOCALE CHARTS ------------------
function renderLocaleCharts(metrics) {
  const localeSections = window.renderLocaleSections
    ? window.renderLocaleSections(metrics)
    : {};
  Object.keys(localeSections).forEach((loc) => {
    const csvUrl = `../reports/summary_history_${loc}.csv?t=${Date.now()}`;
    fetch(csvUrl)
      .then((r) => r.text())
      .then((txt) => {
        const parsed = Papa.parse(txt, { header: true, skipEmptyLines: true }).data;
        if (!parsed.length) return;
        parsed.sort((a, b) => new Date(a.run_time) - new Date(b.run_time));

        const series = parsed.map((r) => {
          const broken = Number(r.broken_links || 0);
          const total = Math.max(Number(r.total_links_found || 1), 1);
          const successRate = 100 - (broken / total) * 100;
          return {
            date: r.run_time?.split(" ")[0],
            success_rate: successRate,
            broken_links: r.status_code === "999" ? 0 : broken, // exclude 999
          };
        });

        const brokenMax = Math.max(...series.map((s) => s.broken_links)) || 0;
        updateChart(
          `locale_${loc}_success`,
          makeLineConfig(series.map((s) => s.date), [
            { label: "Success %", data: series.map((s) => s.success_rate) },
          ])
        );
        updateChart(
          `locale_${loc}_broken`,
          makeBarConfig(
            series.map((s) => s.date),
            [
              {
                label: "Broken",
                data: series.map((s) => s.broken_links),
                backgroundColor: "#ff453a",
                barThickness: 24,
              },
            ],
            brokenMax
          )
        );
      })
      .catch(() => {});
  });
}

// ------------------ ERROR BREAKDOWN (from CSV) ------------------
function renderErrorBreakdownFromCSV() {
  fetch("../reports/broken_links_latest.csv?t=" + Date.now())
    .then((r) => r.text())
    .then((txt) => {
      const parsed = Papa.parse(txt, { header: true, skipEmptyLines: true }).data;
      const counts = {};
      parsed.forEach((r) => {
        const code = r.status_code || "000";
        if (code !== "999") counts[code] = (counts[code] || 0) + 1;
      });

      const labels = Object.keys(counts).length ? Object.keys(counts) : ["No Errors"];
      const dataVals = Object.keys(counts).length ? Object.values(counts) : [1];
      const colorMap = { 404: "#f97316", 403: "#facc15", 500: "#ef4444", 999: "#94a3b8" };
      const colors = labels.map((l) => colorMap[l] || "#3b82f6");

      updateChart("chartError", {
        type: "pie",
        data: { labels, datasets: [{ data: dataVals, backgroundColor: colors }] },
        options: {
          plugins: {
            legend: { position: "bottom" },
            datalabels: {
              color: "#fff",
              font: { size: 12, weight: "600" },
              formatter: (v, ctx) =>
                `${ctx.chart.data.labels[ctx.dataIndex]}: ${v}`,
            },
          },
        },
      });
    })
    .catch(() => {});
}

// ------------------ BROKEN LINKS TABLE ------------------
async function loadBrokenTable(metrics) {
  const res = await fetch(BROKEN_CSV_FALLBACK + "?t=" + Date.now());
  if (!res.ok) return;
  const txt = await res.text();
  const parsed = Papa.parse(txt, { header: true, skipEmptyLines: true }).data;

  const rows = parsed.map((r, i) => ({
    id: i + 1,
    locale: (r.locale || "GLOBAL").toUpperCase(),
    url: r.url || "—",
    source_page: r.source_page || "—",
    status_code: r.status_code || "000",
    reason: r.reason || "Unknown",
    snippet: r.snippet || "",
  }));

  const tbody = document.querySelector("#broken-table tbody");
  tbody.innerHTML = rows
    .map(
      (r) => `
      <tr>
        <td>${r.id}</td>
        <td>${r.locale}</td>
        <td><a href="${r.source_page}" target="_blank">${r.source_page}</a></td>
        <td><a href="${r.url}" target="_blank">${r.url}</a></td>
        <td>${r.status_code}</td>
        <td>${r.reason}</td>
        <td>${r.snippet.slice(0, 100)}</td>
      </tr>`
    )
    .join("");
}

// ------------------ MAIN ------------------
(async function main() {
  const metrics = await loadJSON(METRICS_URL);
  if (!metrics) return;
  updateHealthBar(metrics);
  updateKPI(metrics);
  renderGlobalCharts(metrics);
  renderLocaleCharts(metrics);
  await loadBrokenTable(metrics);
  renderErrorBreakdownFromCSV();
})();