"use strict";

const state = {
  document: null,
  city: "",
  disease: "",
  range: "14",
  points: [],
  chartPoints: [],
};

const elements = {
  city: document.querySelector("#city-select"),
  disease: document.querySelector("#disease-select"),
  range: document.querySelector("#range-options"),
  status: document.querySelector("#status"),
  dashboard: document.querySelector("#dashboard"),
  updatedAt: document.querySelector("#updated-at"),
  coverage: document.querySelector("#coverage"),
  latestValue: document.querySelector("#latest-value"),
  latestDate: document.querySelector("#latest-date"),
  periodChange: document.querySelector("#period-change"),
  periodChangeDetail: document.querySelector("#period-change-detail"),
  peakValue: document.querySelector("#peak-value"),
  peakDate: document.querySelector("#peak-date"),
  historyDays: document.querySelector("#history-days"),
  chartKicker: document.querySelector("#chart-kicker"),
  chartTitle: document.querySelector("#chart-title"),
  canvas: document.querySelector("#trend-chart"),
  tooltip: document.querySelector("#chart-tooltip"),
  table: document.querySelector("#data-table"),
  download: document.querySelector("#download-csv"),
};

const formatValue = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
const formatDate = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "short",
  day: "numeric",
});
const formatShortDate = new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" });

function parseDate(date) {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function displayDate(date) {
  return formatDate.format(parseDate(date));
}

function unique(values) {
  return [...new Set(values)];
}

function showError(message) {
  elements.status.textContent = message;
  elements.status.hidden = false;
  elements.dashboard.hidden = true;
}

function fillSelect(select, options, selected) {
  select.replaceChildren(
    ...options.map((option) => {
      const element = document.createElement("option");
      element.value = option;
      element.textContent = option;
      element.selected = option === selected;
      return element;
    }),
  );
}

function selectedSeries() {
  return state.document.series.find(
    (item) => item.city === state.city && item.disease === state.disease,
  );
}

function visiblePoints(series) {
  if (!series) return [];
  if (state.range === "all") return series.points;
  return series.points.slice(-Number(state.range));
}

function syncUrl() {
  const url = new URL(window.location.href);
  url.searchParams.set("city", state.city.replace(/市$/, ""));
  url.searchParams.set("disease", state.disease);
  url.searchParams.set("range", state.range);
  history.replaceState(null, "", url);
}

function renderMetrics(series, points) {
  const latest = points.at(-1);
  const first = points[0];
  const peak = points.reduce((best, point) => (point[1] > best[1] ? point : best), points[0]);
  const difference = latest[1] - first[1];
  const percentage = first[1] === 0 ? null : (difference / first[1]) * 100;

  elements.latestValue.textContent = formatValue.format(latest[1]);
  elements.latestDate.textContent = displayDate(latest[0]);
  elements.periodChange.textContent = `${difference > 0 ? "+" : ""}${formatValue.format(difference)}`;
  elements.periodChange.classList.toggle("positive", difference > 0);
  elements.periodChange.classList.toggle("negative", difference < 0);
  elements.periodChangeDetail.textContent = percentage === null
    ? `${displayDate(first[0])} 至今`
    : `${percentage > 0 ? "+" : ""}${percentage.toFixed(1)}% · ${displayDate(first[0])} 至今`;
  elements.peakValue.textContent = formatValue.format(peak[1]);
  elements.peakDate.textContent = displayDate(peak[0]);
  elements.historyDays.textContent = `${series.points.length} 天`;
}

function renderTable(points) {
  const rows = [...points].reverse().map(([date, value]) => {
    const row = document.createElement("tr");
    const values = [displayDate(date), state.city, state.disease, formatValue.format(value)];
    values.forEach((valueText, index) => {
      const cell = document.createElement("td");
      cell.textContent = valueText;
      if (index === 3) cell.className = "numeric";
      row.append(cell);
    });
    return row;
  });
  elements.table.replaceChildren(...rows);
}

function chartGeometry(points) {
  const rect = elements.canvas.getBoundingClientRect();
  const width = Math.max(300, rect.width);
  const height = Math.max(260, rect.height);
  const padding = { top: 22, right: 22, bottom: 42, left: 58 };
  const values = points.map((point) => point[1]);
  let min = Math.min(...values);
  let max = Math.max(...values);
  const spread = max - min || Math.max(Math.abs(max) * 0.1, 1);
  min = Math.max(0, min - spread * 0.14);
  max += spread * 0.14;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const mapped = points.map(([date, value], index) => ({
    date,
    value,
    x: padding.left + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth),
    y: padding.top + ((max - value) / (max - min || 1)) * plotHeight,
  }));
  return { width, height, padding, min, max, plotWidth, plotHeight, mapped };
}

function drawChart(points, highlightedIndex = null) {
  const canvas = elements.canvas;
  const context = canvas.getContext("2d");
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const geometry = chartGeometry(points);
  canvas.width = Math.round(geometry.width * ratio);
  canvas.height = Math.round(geometry.height * ratio);
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, geometry.width, geometry.height);
  state.chartPoints = geometry.mapped;

  context.font = '12px "SF Pro Display", "PingFang SC", sans-serif';
  context.fillStyle = "#7a8380";
  context.strokeStyle = "#e4e8e5";
  context.lineWidth = 1;

  for (let tick = 0; tick <= 4; tick += 1) {
    const y = geometry.padding.top + (tick / 4) * geometry.plotHeight;
    const value = geometry.max - (tick / 4) * (geometry.max - geometry.min);
    context.beginPath();
    context.moveTo(geometry.padding.left, y);
    context.lineTo(geometry.width - geometry.padding.right, y);
    context.stroke();
    context.textAlign = "right";
    context.textBaseline = "middle";
    context.fillText(formatValue.format(value), geometry.padding.left - 10, y);
  }

  const labelIndexes = unique([
    0,
    Math.floor((points.length - 1) / 3),
    Math.floor(((points.length - 1) * 2) / 3),
    points.length - 1,
  ]);
  context.textAlign = "center";
  context.textBaseline = "top";
  labelIndexes.forEach((index) => {
    const point = geometry.mapped[index];
    context.fillText(formatShortDate.format(parseDate(point.date)), point.x, geometry.height - 25);
  });

  const gradient = context.createLinearGradient(0, geometry.padding.top, 0, geometry.height);
  gradient.addColorStop(0, "rgba(11, 127, 120, 0.22)");
  gradient.addColorStop(1, "rgba(11, 127, 120, 0)");
  context.beginPath();
  geometry.mapped.forEach((point, index) => {
    if (index === 0) context.moveTo(point.x, point.y);
    else context.lineTo(point.x, point.y);
  });
  context.lineTo(geometry.mapped.at(-1).x, geometry.height - geometry.padding.bottom);
  context.lineTo(geometry.mapped[0].x, geometry.height - geometry.padding.bottom);
  context.closePath();
  context.fillStyle = gradient;
  context.fill();

  context.beginPath();
  geometry.mapped.forEach((point, index) => {
    if (index === 0) context.moveTo(point.x, point.y);
    else context.lineTo(point.x, point.y);
  });
  context.strokeStyle = "#0b7f78";
  context.lineWidth = 3;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.stroke();

  geometry.mapped.forEach((point, index) => {
    const active = index === highlightedIndex;
    context.beginPath();
    context.arc(point.x, point.y, active ? 6 : 3.5, 0, Math.PI * 2);
    context.fillStyle = active ? "#f7b733" : "#ffffff";
    context.fill();
    context.strokeStyle = "#0b7f78";
    context.lineWidth = active ? 3 : 2;
    context.stroke();
  });
}

function nearestPoint(event) {
  const rect = elements.canvas.getBoundingClientRect();
  const clientX = event.touches?.[0]?.clientX ?? event.clientX;
  const clientY = event.touches?.[0]?.clientY ?? event.clientY;
  const x = clientX - rect.left;
  const y = clientY - rect.top;
  let nearest = null;
  state.chartPoints.forEach((point, index) => {
    const distance = Math.hypot(point.x - x, point.y - y);
    if (!nearest || distance < nearest.distance) nearest = { index, distance, point };
  });
  return nearest && nearest.distance < 42 ? nearest : null;
}

function showTooltip(event) {
  const nearest = nearestPoint(event);
  if (!nearest) {
    elements.tooltip.hidden = true;
    drawChart(state.points);
    return;
  }
  drawChart(state.points, nearest.index);
  elements.tooltip.innerHTML = `<span>${displayDate(nearest.point.date)}</span><strong>${formatValue.format(nearest.point.value)}</strong>`;
  elements.tooltip.style.left = `${nearest.point.x}px`;
  elements.tooltip.style.top = `${nearest.point.y}px`;
  elements.tooltip.hidden = false;
}

function render() {
  const series = selectedSeries();
  const points = visiblePoints(series);
  if (!series || points.length === 0) {
    showError("这个组合暂时没有可显示的数据。");
    return;
  }
  state.points = points;
  elements.status.hidden = true;
  elements.dashboard.hidden = false;
  elements.chartKicker.textContent = `${state.city} · ${state.disease}`;
  elements.chartTitle.textContent = `${state.range === "all" ? "全部历史" : `最近 ${state.range} 天`}趋势`;
  elements.canvas.setAttribute(
    "aria-label",
    `${state.city}${state.disease}${elements.chartTitle.textContent}，从 ${displayDate(points[0][0])} 到 ${displayDate(points.at(-1)[0])}`,
  );
  renderMetrics(series, points);
  renderTable(points);
  requestAnimationFrame(() => drawChart(points));
  syncUrl();
}

function downloadCsv() {
  const rows = [
    ["date", "city", "disease", "index_value"],
    ...state.points.map(([date, value]) => [date, state.city, state.disease, value]),
  ];
  const csv = `\ufeff${rows.map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\r\n")}\r\n`;
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${state.city}-${state.disease}-${state.range}天.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function bindEvents() {
  elements.city.addEventListener("change", () => {
    state.city = elements.city.value;
    render();
  });
  elements.disease.addEventListener("change", () => {
    state.disease = elements.disease.value;
    render();
  });
  elements.range.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-range]");
    if (!button) return;
    state.range = button.dataset.range;
    elements.range.querySelectorAll("button").forEach((item) => {
      item.setAttribute("aria-pressed", String(item === button));
    });
    render();
  });
  elements.download.addEventListener("click", downloadCsv);
  elements.canvas.addEventListener("mousemove", showTooltip);
  elements.canvas.addEventListener("touchstart", showTooltip, { passive: true });
  elements.canvas.addEventListener("mouseleave", () => {
    elements.tooltip.hidden = true;
    drawChart(state.points);
  });
  window.addEventListener("resize", () => {
    elements.tooltip.hidden = true;
    if (state.points.length) drawChart(state.points);
  });
}

async function start() {
  bindEvents();
  try {
    const response = await fetch("./data/indexes.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const documentData = await response.json();
    if (documentData.version !== 1 || !Array.isArray(documentData.series)) {
      throw new Error("数据格式无效");
    }
    state.document = documentData;
    const params = new URLSearchParams(window.location.search);
    const cities = unique(documentData.series.map((item) => item.city));
    const diseases = unique(documentData.series.map((item) => item.disease));
    const requestedCity = params.get("city");
    const normalizedCity = cities.find((city) => city === requestedCity || city.replace(/市$/, "") === requestedCity);
    state.city = normalizedCity || cities.find((city) => city === "杭州市") || cities[0];
    state.disease = diseases.includes(params.get("disease"))
      ? params.get("disease")
      : diseases.find((disease) => disease === "新冠") || diseases[0];
    state.range = ["14", "30", "90", "all"].includes(params.get("range")) ? params.get("range") : "14";

    fillSelect(elements.city, cities, state.city);
    fillSelect(elements.disease, diseases, state.disease);
    elements.range.querySelectorAll("button").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.range === state.range));
    });

    const allDates = documentData.series.flatMap((item) => item.points.map((point) => point[0]));
    const minDate = allDates.reduce((a, b) => (a < b ? a : b));
    const maxDate = allDates.reduce((a, b) => (a > b ? a : b));
    elements.updatedAt.textContent = new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(documentData.updated_at));
    elements.coverage.textContent = `${displayDate(minDate)} — ${displayDate(maxDate)}`;
    render();
  } catch (error) {
    showError("数据暂时无法载入，请稍后刷新。上一版数据不会因抓取失败而被覆盖。");
    console.error(error);
  }
}

start();
