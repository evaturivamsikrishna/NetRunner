/* data/dashboard/assets/chart.js
   Clean, accessible chart rendering for NetRunner dashboard.
   Loads: data/dashboard/generated/metrics.json (single canonical file)
*/
const METRICS_URL = "/data/dashboard/generated/metrics.json";

const $id = id => document.getElementById(id);

function safeNum(n, dp = 2){ return (typeof n === "number") ? n.toFixed(dp) : (n || "--"); }

async function loadJSON(url){
  try {
    const r = await fetch(url, {cache: "no-store"});
    if(!r.ok) throw new Error("HTTP " + r.status);
    return await r.json();
  } catch (e) {
    console.warn("⚠️ Failed to load metrics:", e);
    return null;
  }
}

function setKPI(data){
  const latest = (data.locales && Object.values(data.locales).find(l=>l.summary)) || {};
  const s = latest.summary || {};
  if($id("latest-success")) $id("latest-success").textContent = safeNum(s.success_rate || data.global.overall_success_rate || 0) + "%";
  if($id("latest-duration")) $id("latest-duration").textContent = safeNum(s.duration_mins || 0,1);
  if($id("latest-total")) $id("latest-total").textContent = (s.total_links_found || "--");
  if($id("latest-broken")) $id("latest-broken").textContent = (s.broken_links || 0);
  if($id("overall-runs")) $id("overall-runs").textContent = (data.global.total_runs || 0);
  if($id("overall-links")) $id("overall-links").textContent = (data.global.total_links_checked || 0);
  if($id("overall-broken")) $id("overall-broken").textContent = (data.global.total_broken_links || 0);
  if($id("overall-success")) $id("overall-success").textContent = safeNum(data.global.overall_success_rate || 100) + "%";

  // Show count of locales verified in this run
  const verifiedCount = Object.values(data.locales || {}).filter(l=>l.summary).length;
  if($id("locales-verified")) $id("locales-verified").textContent = verifiedCount;
}

function makeLine(ctx, labels, dataSet, label, color){
  return new Chart(ctx, {
    type: 'line',
    data: { labels, datasets: [{ label, data: dataSet, borderColor: color, backgroundColor: "rgba(0,0,0,0)", tension: 0.25, pointRadius: 2 }]},
    options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}} , scales:{y:{beginAtZero:true}}}
  });
}

function makeBar(ctx, labels, dataSet, label, color){
  return new Chart(ctx, {
    type:'bar',
    data: { labels, datasets: [{ label, data: dataSet, backgroundColor: color, barThickness: 14 }]},
    options: { responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{y:{beginAtZero:true}}}
  });
}

function renderGlobalCharts(data){
  // success over locales (latest run)
  const locales = Object.keys(data.locales || {});
  const success = locales.map(l => (data.locales[l].summary || {}).success_rate || 0);
  const broken = locales.map(l => (data.locales[l].summary || {}).broken_links || 0);

  const ctxS = $id("chartSuccess")?.getContext("2d");
  const ctxB = $id("chartBroken")?.getContext("2d");
  const ctxE = $id("chartEff")?.getContext("2d");
  const ctxD = $id("chartDuration")?.getContext("2d");

  if(ctxS) makeLine(ctxS, locales, success, "Success %", "#1E6BD6");
  if(ctxB) makeBar(ctxB, locales, broken, "Broken", "#D03238");
  if(ctxE) {
    const eff = locales.map(l => (data.locales[l].summary || {}).crawler_efficiency || 0);
    makeBar(ctxE, locales, eff, "Efficiency %", "#4A8EF1");
  }
  if(ctxD) {
    const dur = locales.map(l => (data.locales[l].summary || {}).duration_mins || 0);
    makeLine(ctxD, locales, dur, "Duration (mins)", "#1E8E3E");
  }
}

function renderLocales(data){
  // the locale render script (locale_render.js) provides a hook: window.renderLocaleSections
  if(typeof window.renderLocaleSections === "function"){
    const created = window.renderLocaleSections(data);
    // for each locale that has series, call renderLocaleChartsFromSeries (provided by locale_render.js)
    const localeSeriesMap = {};
    Object.keys(data.locales || {}).forEach(loc=>{
      const ld = data.locales[loc];
      localeSeriesMap[loc] = (ld && ld.series) || [];
    });
    if(typeof window.renderLocaleChartsFromSeries === "function"){
      window.renderLocaleChartsFromSeries(localeSeriesMap);
    }
  }
}

(async function init(){
  const metrics = await loadJSON(METRICS_URL);
  if(!metrics) {
    // show message
    const el = $id("locales-container");
    if(el) el.innerHTML = "<p style='color:#D03238'>Metrics not found. Run the scanner and metrics_builder.</p>";
    return;
  }
  setKPI(metrics);
  renderGlobalCharts(metrics);
  renderLocales(metrics);
})();