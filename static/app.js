const $ = (id) => document.getElementById(id);
const COLORS = ["#2f6df6", "#e5864d", "#8a4df6", "#1faa59"];
let timer;

async function load() {
  try {
    const r = await fetch("/api/dashboard");
    if (!r.ok) throw new Error(r.status);
    render(await r.json());
    $("dot").classList.remove("err");
  } catch (e) {
    $("dot").classList.add("err");
    $("updated").textContent = "Connection problem – retrying…";
  }
}

function render(d) {
  $("updated").textContent =
    "Updated " + new Date(d.server_time).toLocaleTimeString();
  clearInterval(timer);
  timer = setInterval(load, d.refresh_sec * 1000);

  const need = d.bins.filter((b) => b.collection_required);
  const banner = $("banner");
  if (!need.length) {
    banner.className = "banner ok";
    banner.innerHTML =
      "✅ No bin needs collection<small>The van can stay at the depot.</small>";
  } else {
    banner.className = "banner alert";
    banner.innerHTML =
      "🚨 Collection required: " +
      need.map((b) => `${b.bin_id} (${Math.round(b.fill)}%)`).join(", ") +
      `<small>${d.bins.length - need.length} other bin(s) can wait.</small>`;
  }

  // route
  const steps = d.route.steps;
  $("routeCard").hidden = !steps.length;
  if (steps.length) {
    $("route").innerHTML =
      `<li><div class="badge start">🏁</div><div class="stop"><b>${d.depot}</b><span>Start</span></div></li>` +
      steps
        .map(
          (
            s,
            i,
          ) => `<li><div class="badge">${i + 1}</div><div class="stop"><b>${s.bin_id} – ${s.bin_name}</b>
        <span>${Math.round(s.fill)}% full · ${s.leg_km} km from previous stop</span></div></li>`,
        )
        .join("");
    $("routeKm").textContent =
      `Approx. total ${d.route.total_km} km (straight line)`;
  }

  // bins
  $("bins").innerHTML = d.bins.map(binCard).join("");
  drawChart(d.bins);
}

function binCard(b) {
  if (!b.has_data)
    return `<article class="card bin"><div class="bin-head"><h3>${b.bin_id} – ${b.bin_name}</h3></div><p class="note">No readings received yet.</p></article>`;
  const age =
    b.age_sec < 90 ? b.age_sec + " s" : Math.round(b.age_sec / 60) + " min";
  return `<article class="card bin ${b.status}">
    <div class="bin-head"><div><h3>${b.bin_id} – ${b.bin_name}</h3><small>updated ${age} ago</small></div>
      <span class="pill">${b.status}</span></div>
    <div class="gauge">
      <div class="ring" style="--p:${b.fill}"><div>${Math.round(b.fill)}<small>%</small></div></div>
      <div class="facts">
        <div><span>Estimated time to full</span><b>${b.eta_text}</b></div>
        <div><span>Fill rate</span><b>${b.rate_per_hour == null ? "–" : b.rate_per_hour.toFixed(1) + " %/hour"}</b></div>
      </div>
    </div>
    ${b.offline ? '<div class="warn">⚠ No recent data – check ESP32 / Wi-Fi.</div>' : ""}
    <p class="note">${b.note} Estimates are approximate.</p>
  </article>`;
}

function drawChart(bins) {
  const series = bins.filter((b) => b.history.length > 1);
  $("legend").innerHTML = series
    .map(
      (b, i) =>
        `<span><i style="background:${COLORS[i % 4]}"></i>${b.bin_id}</span>`,
    )
    .join("");
  if (!series.length) {
    $("chart").innerHTML = '<div class="empty">Not enough history yet.</div>';
    return;
  }

  const W = 800,
    H = 260,
    L = 38,
    R = 12,
    T = 12,
    B = 28;
  const all = series.flatMap((b) => b.history.map((p) => +new Date(p.t)));
  const t0 = Math.min(...all),
    t1 = Math.max(...all);
  const x = (t) => L + ((t - t0) / (t1 - t0 || 1)) * (W - L - R);
  const y = (v) => T + (1 - v / 100) * (H - T - B);

  let g = [0, 25, 50, 75, 100]
    .map(
      (v) =>
        `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="currentColor" opacity=".12"/>
     <text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="currentColor" opacity=".55">${v}</text>`,
    )
    .join("");
  g += [0, 0.5, 1]
    .map((f) => {
      const t = t0 + f * (t1 - t0);
      return `<text x="${x(t)}" y="${H - 8}" text-anchor="${f == 0 ? "start" : f == 1 ? "end" : "middle"}" font-size="11" fill="currentColor" opacity=".55">${new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</text>`;
    })
    .join("");
  const lines = series
    .map((b, i) => {
      const pts = b.history
        .map((p) => `${x(+new Date(p.t)).toFixed(1)},${y(p.v).toFixed(1)}`)
        .join(" ");
      return `<polyline points="${pts}" fill="none" stroke="${COLORS[i % 4]}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`;
    })
    .join("");
  $("chart").innerHTML =
    `<svg viewBox="0 0 ${W} ${H}" style="color:var(--ink)">${g}${lines}</svg>`;
}

load();
