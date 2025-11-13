/* data/dashboard/assets/locale_render.js
   Locale renderer for NetRunner dashboard.
   Uses emoji flags. Accessible markup, simple structure.
*/
(function(){
  const LOCALE_DISPLAY = {
    "en":"English","es":"Spanish","de":"German","fr":"French","it":"Italian","ja":"Japanese",
    "ko":"Korean","zhcn":"Chinese (CN)","zhtw":"Chinese (TW)","ptbr":"Portuguese (BR)","ptpt":"Portuguese (PT)",
    "ru":"Russian","tr":"Turkish","uk":"Ukrainian","pl":"Polish","sv":"Swedish","nb":"Norwegian","da":"Danish","ar":"Arabic"
  };

  const LOCALE_FLAG = {
    "en":"🇬🇧","es":"🇪🇸","de":"🇩🇪","fr":"🇫🇷","it":"🇮🇹","ja":"🇯🇵","ko":"🇰🇷","zhcn":"🇨🇳","zhtw":"🇹🇼",
    "ptbr":"🇧🇷","ptpt":"🇵🇹","ru":"🇷🇺","tr":"🇹🇷","uk":"🇺🇦","pl":"🇵🇱","sv":"🇸🇪","nb":"🇳🇴","da":"🇩🇰","ar":"🇸🇦"
  };

  function createLocaleNode(code, summary){
    const name = LOCALE_DISPLAY[code] || code.toUpperCase();
    const flag = LOCALE_FLAG[code] || "🏳️";
    const latest = (summary && summary.latest_run) || "—";
    const total_links = (summary && summary.summary && summary.summary.total_links_found) || 0;
    const avg = (summary && summary.summary && summary.summary.success_rate) ? Number(summary.summary.success_rate).toFixed(2) : "—";

    const sec = document.createElement("section");
    sec.className = "locale-section";
    sec.setAttribute("data-locale", code);
    sec.innerHTML = `
      <div class="locale-header" role="group" aria-label="Locale ${name}">
        <div class="locale-title"><span class="flag">${flag}</span><div class="meta"><div class="locale-name">${name}</div><div class="locale-code">${code}</div></div></div>
        <div class="locale-kpis">
          <div class="mini"><div class="label">Latest</div><div class="val">${latest}</div></div>
          <div class="mini"><div class="label">Links</div><div class="val">${total_links}</div></div>
          <div class="mini"><div class="label">Success</div><div class="val">${avg}%</div></div>
        </div>
      </div>
      <div class="locale-charts">
        <div class="chart-card small"><h4>Success</h4><canvas id="locale_${code}_success"></canvas></div>
        <div class="chart-card small"><h4>Broken</h4><canvas id="locale_${code}_broken"></canvas></div>
      </div>
    `;
    return sec;
  }

  window.renderLocaleSections = function(metrics){
    const container = document.getElementById("locales-container");
    if(!container) return {};
    container.innerHTML = "";
    const locales = metrics && metrics.locales ? metrics.locales : {};
    const created = {};
    Object.keys(locales).sort().forEach(loc=>{
      const node = createLocaleNode(loc, locales[loc]);
      container.appendChild(node);
      created[loc] = { successCanvasId: `locale_${loc}_success`, brokenCanvasId: `locale_${loc}_broken`, summary: locales[loc].summary || {} };
    });
    // show verified count
    const verified = Object.keys(locales).length;
    const vEl = document.getElementById("locales-verified");
    if(vEl) vEl.textContent = verified;
    return created;
  };

  window.renderLocaleChartsFromSeries = function(localeSeries){
    Object.keys(localeSeries).forEach(loc => {
      const series = localeSeries[loc] || [];
      const labels = series.map(s => s.run_time || s.date || "");
      const success = series.map(s => Number(s.success_rate || 0));
      const broken = series.map(s => Number(s.broken_links || 0));
      const sEl = document.getElementById(`locale_${loc}_success`);
      const bEl = document.getElementById(`locale_${loc}_broken`);
      if(sEl && success.length){
        new Chart(sEl.getContext("2d"), { type: "line", data: { labels, datasets: [{ label: "Success", data: success, borderColor: "#1E6BD6", tension: 0.25 }]}, options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}, scales:{y:{beginAtZero:true, max:100}} }});
      }
      if(bEl && broken.length){
        new Chart(bEl.getContext("2d"), { type: "bar", data: { labels, datasets: [{ label: "Broken", data: broken, backgroundColor: "#D03238" }]}, options:{responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}}}});
      }
    });
  };

})();