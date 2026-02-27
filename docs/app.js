const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

let data = [];
let chart = null;
let athlete = "";
let exercise = "";
let chartMetric = "load_avg";
let todayMode = "top";

const $id = (id) => document.getElementById(id);
const $athlete = $id("athlete-select");
const $exercise = $id("exercise-select");

/* ════════════════════════════════════════════
   Init
   ════════════════════════════════════════════ */

async function init() {
    const res = await fetch("data.json");
    data = await res.json();
    fillAthletes();
    $athlete.addEventListener("change", onAthleteChange);
    $exercise.addEventListener("change", onExerciseChange);
    document.addEventListener("click", onGlobalClick);
}

/* ════════════════════════════════════════════
   Athletes
   ════════════════════════════════════════════ */

function fillAthletes() {
    [...new Set(data.map((r) => r.athlete))].sort().forEach((n) => {
        const o = document.createElement("option");
        o.value = n;
        o.textContent = n;
        $athlete.appendChild(o);
    });
}

function onAthleteChange() {
    athlete = $athlete.value;
    exercise = "";
    chartMetric = "load_avg";
    $exercise.value = "";
    $id("chart-area").classList.add("hidden");
    $id("history-table").innerHTML = "";

    if (!athlete) {
        $id("today-section").classList.add("hidden");
        $id("progression-section").classList.add("hidden");
        return;
    }

    renderToday();
    fillExercises();
    $id("progression-section").classList.remove("hidden");
}

/* ════════════════════════════════════════════
   Today section
   ════════════════════════════════════════════ */

function renderToday() {
    const today = DAYS[new Date().getDay()];
    const all = data.filter((r) => r.athlete === athlete);
    const dayRows = all
        .filter((r) => r.day_of_week === today)
        .sort((a, b) => a.date_only.localeCompare(b.date_only));

    const $title = $id("today-title");
    const $sub = $id("today-subtitle");
    const $toggle = $id("today-toggle");
    const $cards = $id("today-exercises");

    if (dayRows.length > 0) {
        const lastDate = dayRows[dayRows.length - 1].date_only;
        const session = dayRows.filter((r) => r.date_only === lastDate);
        $title.textContent = `Last ${today} — ${fmtDate(lastDate)}`;
        $sub.classList.add("hidden");
        $toggle.innerHTML = "";
        $cards.innerHTML = session.map((r) => buildCard(r)).join("");
    } else {
        $title.textContent = `${today} — No session recorded`;
        renderFallback(all, $sub, $toggle, $cards);
    }

    $id("today-section").classList.remove("hidden");
}

function renderFallback(allRows, $sub, $toggle, $cards) {
    $toggle.innerHTML = `<div class="toggle-group">
        <button class="toggle-btn view-btn ${todayMode === "top" ? "active" : ""}" data-view="top">Top Exercises</button>
        <button class="toggle-btn view-btn ${todayMode === "last" ? "active" : ""}" data-view="last">Last Workout</button>
    </div>`;

    if (todayMode === "top") {
        $sub.classList.add("hidden");
        $cards.innerHTML = buildTopCards(allRows);
    } else {
        const result = buildLastWorkoutCards(allRows);
        if (result.subtitle) {
            $sub.textContent = result.subtitle;
            $sub.classList.remove("hidden");
        } else {
            $sub.classList.add("hidden");
        }
        $cards.innerHTML = result.html;
    }
}

function buildTopCards(rows) {
    const counts = {};
    rows.forEach((r) => {
        counts[r.exercise] = (counts[r.exercise] || 0) + 1;
    });

    const top5 = Object.entries(counts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([name]) => name);

    if (!top5.length) return '<div class="empty-state">No data yet</div>';

    return top5
        .map((exName) => {
            const latest = rows
                .filter((r) => r.exercise === exName)
                .sort((a, b) => b.date_only.localeCompare(a.date_only))[0];
            return buildCard(latest);
        })
        .join("");
}

function buildLastWorkoutCards(rows) {
    const dates = [...new Set(rows.map((r) => r.date_only))].sort().reverse();
    if (!dates.length) return { html: '<div class="empty-state">No data yet</div>', subtitle: null };

    const lastDate = dates[0];
    const session = rows.filter((r) => r.date_only === lastDate);
    const day = session[0].day_of_week;

    return {
        html: session.map((r) => buildCard(r)).join(""),
        subtitle: `${fmtDate(lastDate)} — ${day}`,
    };
}

/* ════════════════════════════════════════════
   Exercise card
   ════════════════════════════════════════════ */

function buildCard(row) {
    const prev = findPrevSession(row.exercise, row.date_only);
    const diff = getDiff(row.load_avg, prev?.load_avg);

    const weightText =
        row.load_avg != null ? fmtNum(row.load_avg) + " kg" + diff.arrow : "—";

    const stats = [];
    stats.push(mkStat(`${row.sets}\u00D7${fmtNum(row.reps_avg)}`, "Sets\u00D7Reps"));
    if (row.reps_total != null) stats.push(mkStat(fmtNum(row.reps_total), "Total Reps"));
    if (row.total_volume != null) stats.push(mkStat(fmtNum(row.total_volume), "Volume"));
    if (row.rpe != null) stats.push(mkStat(row.rpe, "RPE"));

    return `<div class="ex-card">
        <div class="ex-header">
            <div>
                <div class="ex-name">${esc(row.exercise)}</div>
                <div class="ex-date">${fmtDate(row.date_only)} · ${row.day_of_week}</div>
            </div>
            <button class="info-btn" data-row-id="${row.row_id}">i</button>
        </div>
        <div class="ex-hero">
            <span class="ex-weight ${diff.cls}">${weightText}</span>
            <span class="ex-weight-lbl">avg load</span>
        </div>
        <div class="ex-stats">${stats.join("")}</div>
        ${row.e1rm_avg != null ? `<div class="ex-secondary">e1RM ${fmtNum(row.e1rm_avg)} kg</div>` : ""}
        ${row.notes ? `<div class="ex-notes">${esc(row.notes)}</div>` : ""}
    </div>`;
}

function mkStat(val, label) {
    return `<div class="stat"><div class="stat-val">${val}</div><div class="stat-lbl">${label}</div></div>`;
}

function findPrevSession(exerciseName, beforeDate) {
    return (
        data
            .filter(
                (r) =>
                    r.athlete === athlete &&
                    r.exercise === exerciseName &&
                    r.date_only < beforeDate
            )
            .sort((a, b) => b.date_only.localeCompare(a.date_only))[0] || null
    );
}

function getDiff(current, previous) {
    if (current == null || previous == null) return { cls: "", arrow: "" };
    const d = current - previous;
    if (d > 0) return { cls: "change-up", arrow: " \u2191" };
    if (d < 0) return { cls: "change-down", arrow: " \u2193" };
    return { cls: "", arrow: "" };
}

/* ════════════════════════════════════════════
   Detail modal
   ════════════════════════════════════════════ */

function showDetail(rowId) {
    const row = data.find((r) => r.row_id === rowId);
    if (!row) return;

    $id("modal-title").textContent = row.exercise;

    const items = [
        ["Date", `${fmtDate(row.date_only)} (${row.day_of_week})`],
        ["Session", row.session_id],
        ["Sets", row.sets],
        ["Reps / set", row.reps_per_set || "\u2014"],
        ["Load / set", row.load_per_set ? row.load_per_set + " kg" : "\u2014"],
        ["Avg reps", fmtNum(row.reps_avg)],
        ["Avg load", row.load_avg != null ? fmtNum(row.load_avg) + " kg" : "\u2014"],
        ["Total reps", row.reps_total != null ? fmtNum(row.reps_total) : "\u2014"],
        [
            "Total volume",
            row.total_volume != null ? fmtNum(row.total_volume) + " kg" : "\u2014",
        ],
        [
            "Load range",
            row.load_min != null
                ? `${fmtNum(row.load_min)} \u2013 ${fmtNum(row.load_max)} kg`
                : "\u2014",
        ],
        ["RPE", row.rpe != null ? row.rpe : "\u2014"],
        ["Est. 1RM", row.e1rm_avg != null ? fmtNum(row.e1rm_avg) + " kg" : "\u2014"],
        ["Week", row.week_num],
        ["Notes", row.notes || "\u2014"],
    ];

    if (row.data_quality_flag) {
        items.push(["Flags", row.data_quality_flag]);
    }

    $id("modal-body").innerHTML = `<div class="detail-grid">${items
        .map(
            ([l, v]) =>
                `<div class="detail-label">${l}</div><div class="detail-value">${esc(String(v))}</div>`
        )
        .join("")}</div>`;

    $id("detail-modal").classList.remove("hidden");
}

function hideDetail() {
    $id("detail-modal").classList.add("hidden");
}

/* ════════════════════════════════════════════
   Exercise progression
   ════════════════════════════════════════════ */

function fillExercises() {
    const names = [
        ...new Set(data.filter((r) => r.athlete === athlete).map((r) => r.exercise)),
    ].sort();
    $exercise.innerHTML = '<option value="">Select Exercise</option>';
    names.forEach((n) => {
        const o = document.createElement("option");
        o.value = n;
        o.textContent = n;
        $exercise.appendChild(o);
    });
}

function onExerciseChange() {
    exercise = $exercise.value;
    if (!exercise) {
        $id("chart-area").classList.add("hidden");
        $id("history-table").innerHTML = "";
        return;
    }
    chartMetric = "load_avg";
    syncChartToggle();
    renderChart();
    renderHistory();
}

/* ════════════════════════════════════════════
   Chart
   ════════════════════════════════════════════ */

function renderChart() {
    const rows = data
        .filter(
            (r) =>
                r.athlete === athlete &&
                r.exercise === exercise &&
                r[chartMetric] != null
        )
        .sort((a, b) => a.date_only.localeCompare(b.date_only));

    if (!rows.length) {
        $id("chart-area").classList.add("hidden");
        return;
    }

    if (chart) chart.destroy();

    const isVolume = chartMetric === "total_volume";
    const label = isVolume ? "Total Volume (kg)" : "Avg Load (kg)";
    const color = isVolume ? "#3fb950" : "#7c5cfc";

    const ctx = $id("progression-chart").getContext("2d");
    chart = new Chart(ctx, {
        type: "line",
        data: {
            labels: rows.map((r) => fmtDate(r.date_only)),
            datasets: [
                {
                    label,
                    data: rows.map((r) => r[chartMetric]),
                    borderColor: color,
                    backgroundColor: color + "14",
                    fill: true,
                    tension: 0.25,
                    pointRadius: 4,
                    pointBackgroundColor: color,
                    pointHoverRadius: 7,
                    borderWidth: 2,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: "index" },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: "#161b22",
                    borderColor: "#30363d",
                    borderWidth: 1,
                    titleColor: "#e6edf3",
                    bodyColor: "#8b949e",
                    padding: 10,
                    displayColors: false,
                    callbacks: {
                        label: (c) =>
                            isVolume
                                ? `Volume: ${c.parsed.y.toLocaleString()} kg`
                                : `Avg Load: ${c.parsed.y} kg`,
                    },
                },
            },
            scales: {
                x: {
                    ticks: { color: "#484f58", font: { size: 11 } },
                    grid: { color: "rgba(48,54,61,0.5)" },
                },
                y: {
                    ticks: {
                        color: "#484f58",
                        font: { size: 11 },
                        callback: (v) => v.toLocaleString(),
                    },
                    grid: { color: "rgba(48,54,61,0.5)" },
                },
            },
        },
    });

    $id("chart-area").classList.remove("hidden");
}

function syncChartToggle() {
    document.querySelectorAll(".chart-toggle .toggle-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.metric === chartMetric);
    });
}

/* ════════════════════════════════════════════
   History table
   ════════════════════════════════════════════ */

function renderHistory() {
    const rows = data
        .filter((r) => r.athlete === athlete && r.exercise === exercise)
        .sort((a, b) => b.date_only.localeCompare(a.date_only));

    if (!rows.length) {
        $id("history-table").innerHTML = '<div class="empty-state">No data</div>';
        return;
    }

    let html = `<div class="h-row h-head">
        <div>Date</div><div>Detail</div><div>e1RM</div><div></div>
    </div>`;

    rows.forEach((r) => {
        html += `<div class="h-row">
            <div class="h-date">${fmtDateShort(r.date_only)}</div>
            <div class="h-detail">${r.sets}\u00D7${fmtNum(r.reps_avg)} @ ${fmtNum(r.load_avg)} kg</div>
            <div class="h-e1rm">${r.e1rm_avg != null ? fmtNum(r.e1rm_avg) : "\u2014"}</div>
            <div class="h-info"><button class="info-btn" data-row-id="${r.row_id}">i</button></div>
        </div>`;
        if (r.notes) {
            html += `<div class="h-notes">${esc(r.notes)}</div>`;
        }
    });

    $id("history-table").innerHTML = html;
}

/* ════════════════════════════════════════════
   Global click delegation
   ════════════════════════════════════════════ */

function onGlobalClick(e) {
    const info = e.target.closest(".info-btn");
    if (info) {
        showDetail(Number(info.dataset.rowId));
        return;
    }

    if (e.target.closest(".modal-backdrop") || e.target.closest(".modal-close")) {
        hideDetail();
        return;
    }

    const viewBtn = e.target.closest(".view-btn");
    if (viewBtn) {
        todayMode = viewBtn.dataset.view;
        renderToday();
        return;
    }

    const chartBtn = e.target.closest(".chart-toggle .toggle-btn");
    if (chartBtn) {
        chartMetric = chartBtn.dataset.metric;
        syncChartToggle();
        renderChart();
        return;
    }
}

/* ════════════════════════════════════════════
   Helpers
   ════════════════════════════════════════════ */

function fmtNum(n) {
    if (n == null) return "\u2014";
    return Number.isInteger(n) ? String(n) : parseFloat(n.toFixed(1));
}

function fmtDate(s) {
    return new Date(s + "T00:00:00").toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
    });
}

function fmtDateShort(s) {
    return new Date(s + "T00:00:00").toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
    });
}

function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}

init();
