"use strict";

const state = {
  manifest: null,
  document: null,
  city: "",
  disease: "",
  range: "14",
  startDate: "",
  endDate: "",
  points: [],
  chartPoints: [],
};

const cityCache = new Map();
let activeCityRequest = 0;

const elements = {
  city: document.querySelector("#city-select"),
  disease: document.querySelector("#disease-select"),
  range: document.querySelector("#range-options"),
  startDate: document.querySelector("#start-date"),
  endDate: document.querySelector("#end-date"),
  status: document.querySelector("#status"),
  dashboard: document.querySelector("#dashboard"),
  canvas: document.querySelector("#trend-chart"),
  tooltip: document.querySelector("#chart-tooltip"),
  coverage: document.querySelector("#coverage-summary"),
  chartNote: document.querySelector("#chart-note"),
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
const formatAxisDate = new Intl.DateTimeFormat("zh-CN", {
  year: "2-digit",
  month: "numeric",
  day: "numeric",
});
const dayMilliseconds = 24 * 60 * 60 * 1000;

function parseDate(date) {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function displayDate(date) {
  return formatDate.format(parseDate(date));
}

function pointSource(point) {
  return point[2] === "manual_hangzhou_xlsx" ? "手工历史" : "自动归档";
}

function dateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function unique(values) {
  return [...new Set(values)];
}

function showError(message) {
  elements.status.textContent = message;
  elements.status.hidden = false;
  elements.dashboard.hidden = true;
}

function showLoading() {
  elements.status.textContent = "数据载入中…";
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

async function fetchCityDocument(city) {
  const record = state.manifest.cities.find((item) => item.city === city);
  if (!record || !/^cities\/\d{6}\.json$/.test(record.file)) {
    throw new Error("城市数据路径无效");
  }
  if (cityCache.has(record.city_id)) return cityCache.get(record.city_id);
  const response = await fetch(`./data/${record.file}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const documentData = await response.json();
  if (
    documentData.version !== 1
    || documentData.city !== record.city
    || String(documentData.city_id) !== String(record.city_id)
    || !Array.isArray(documentData.series)
  ) {
    throw new Error("城市数据格式无效");
  }
  cityCache.set(record.city_id, documentData);
  return documentData;
}

async function activateCity(preferredDisease, shouldRender = true) {
  const requestId = ++activeCityRequest;
  showLoading();
  const documentData = await fetchCityDocument(state.city);
  if (requestId !== activeCityRequest) return false;
  state.document = documentData;
  const diseases = unique(documentData.series.map((item) => item.disease));
  state.disease = diseases.includes(preferredDisease)
    ? preferredDisease
    : diseases.find((disease) => disease === "新冠") || diseases[0];
  fillSelect(elements.disease, diseases, state.disease);
  if (shouldRender) render();
  return true;
}

function visiblePoints(series) {
  if (!series) return [];
  if (state.range === "custom") {
    return series.points.filter(
      ([date]) => date >= state.startDate && date <= state.endDate,
    );
  }
  if (state.range === "all") return series.points;
  const latest = parseDate(series.points.at(-1)[0]);
  latest.setDate(latest.getDate() - Number(state.range) + 1);
  const cutoff = dateKey(latest);
  return series.points.filter(([date]) => date >= cutoff);
}

function visibleBounds(series, points) {
  if (state.range === "custom") return [state.startDate, state.endDate];
  if (state.range === "all") return [points[0][0], points.at(-1)[0]];
  const end = parseDate(series.points.at(-1)[0]);
  const start = new Date(end);
  start.setDate(start.getDate() - Number(state.range) + 1);
  return [dateKey(start), dateKey(end)];
}

function updateDateBounds(series) {
  if (!series?.points.length) return;
  elements.startDate.min = series.points[0][0];
  elements.startDate.max = series.points.at(-1)[0];
  elements.endDate.min = series.points[0][0];
  elements.endDate.max = series.points.at(-1)[0];
}

function updateRangeButtons() {
  elements.range.querySelectorAll("button").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.range === state.range));
  });
}

function syncUrl() {
  const url = new URL(window.location.href);
  url.searchParams.set("city", state.city.replace(/市$/, ""));
  url.searchParams.set("disease", state.disease);
  url.searchParams.set("range", state.range);
  if (state.range === "custom" && state.startDate && state.endDate) {
    url.searchParams.set("start", state.startDate);
    url.searchParams.set("end", state.endDate);
  } else {
    url.searchParams.delete("start");
    url.searchParams.delete("end");
  }
  history.replaceState(null, "", url);
}

function renderTable(points) {
  const rows = [...points].reverse().map((point) => {
    const [date, value] = point;
    const row = document.createElement("tr");
    const values = [
      displayDate(date),
      state.city,
      state.disease,
      formatValue.format(value),
      pointSource(point),
    ];
    values.forEach((valueText, index) => {
      const cell = document.createElement("td");
      cell.textContent = valueText;
      if (index === 3) cell.className = "numeric";
      if (index === 4 && point[2] === "manual_hangzhou_xlsx") cell.className = "manual-source";
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
  const padding = { top: 22, right: 22, bottom: 42, left: 94 };
  const values = points.map((point) => point[1]);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const useLogScale = rawMin > 0 && rawMax / rawMin >= 20;
  const scaleValue = (value) => (useLogScale ? Math.log10(value) : value);
  const displayValue = (value) => (useLogScale ? 10 ** value : value);
  let min = scaleValue(rawMin);
  let max = scaleValue(rawMax);
  const spread = max - min || Math.max(Math.abs(max) * 0.1, 1);
  min = useLogScale ? min - spread * 0.08 : Math.max(0, min - spread * 0.14);
  max += spread * 0.14;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const times = points.map(([date]) => parseDate(date).getTime());
  const [startDate, endDate] = visibleBounds(selectedSeries(), points);
  const minTime = parseDate(startDate).getTime();
  const maxTime = parseDate(endDate).getTime();
  const timeSpread = maxTime - minTime;
  const mapped = points.map((point, index) => {
    const [date, value] = point;
    return {
      date,
      value,
      source: pointSource(point),
      time: times[index],
      x: padding.left + (timeSpread ? ((times[index] - minTime) / timeSpread) * plotWidth : plotWidth / 2),
      y: padding.top + ((max - scaleValue(value)) / (max - min || 1)) * plotHeight,
    };
  });
  return {
    width, height, padding, min, max, minTime, maxTime, plotWidth, plotHeight,
    mapped, displayValue, useLogScale,
  };
}

function splitSegments(points) {
  return points.reduce((segments, point) => {
    const current = segments.at(-1);
    if (!current || point.time - current.at(-1).time > dayMilliseconds) segments.push([point]);
    else current.push(point);
    return segments;
  }, []);
}

function drawSegment(context, segment, geometry, gradient) {
  if (segment.length > 1) {
    context.beginPath();
    segment.forEach((point, index) => {
      if (index === 0) context.moveTo(point.x, point.y);
      else context.lineTo(point.x, point.y);
    });
    context.lineTo(segment.at(-1).x, geometry.height - geometry.padding.bottom);
    context.lineTo(segment[0].x, geometry.height - geometry.padding.bottom);
    context.closePath();
    context.fillStyle = gradient;
    context.fill();

    context.beginPath();
    segment.forEach((point, index) => {
      if (index === 0) context.moveTo(point.x, point.y);
      else context.lineTo(point.x, point.y);
    });
    context.strokeStyle = "#0b7f78";
    context.lineWidth = 3;
    context.lineJoin = "round";
    context.lineCap = "round";
    context.stroke();
  }
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
    const value = geometry.displayValue(
      geometry.max - (tick / 4) * (geometry.max - geometry.min),
    );
    context.beginPath();
    context.moveTo(geometry.padding.left, y);
    context.lineTo(geometry.width - geometry.padding.right, y);
    context.stroke();
    context.textAlign = "right";
    context.textBaseline = "middle";
    context.fillText(formatValue.format(value), geometry.padding.left - 10, y);
  }

  context.textAlign = "center";
  context.textBaseline = "top";
  for (let tick = 0; tick <= 3; tick += 1) {
    const ratio = tick / 3;
    const time = geometry.minTime + ratio * (geometry.maxTime - geometry.minTime);
    const x = geometry.padding.left + ratio * geometry.plotWidth;
    const label = geometry.maxTime === geometry.minTime
      ? formatShortDate.format(new Date(time))
      : formatAxisDate.format(new Date(time));
    context.fillText(label, x, geometry.height - 25);
  }

  const gradient = context.createLinearGradient(0, geometry.padding.top, 0, geometry.height);
  gradient.addColorStop(0, "rgba(11, 127, 120, 0.22)");
  gradient.addColorStop(1, "rgba(11, 127, 120, 0)");
  splitSegments(geometry.mapped).forEach((segment) => drawSegment(context, segment, geometry, gradient));

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
  elements.tooltip.innerHTML = `<span>${displayDate(nearest.point.date)} · ${nearest.point.source}</span><strong>${formatValue.format(nearest.point.value)}</strong>`;
  elements.tooltip.style.left = `${nearest.point.x}px`;
  elements.tooltip.style.top = `${nearest.point.y}px`;
  elements.tooltip.hidden = false;
}

function render() {
  const series = selectedSeries();
  updateDateBounds(series);
  const points = visiblePoints(series);
  if (!series || points.length === 0) {
    showError("所选日期范围内暂无数据。");
    syncUrl();
    return;
  }
  state.points = points;
  elements.status.hidden = true;
  elements.dashboard.hidden = false;
  elements.canvas.setAttribute(
    "aria-label",
    `${state.city}${state.disease}趋势图，从 ${displayDate(points[0][0])} 到 ${displayDate(points.at(-1)[0])}，折线在缺失日期处断开`,
  );
  const [visibleStart, visibleEnd] = visibleBounds(series, points);
  const start = parseDate(visibleStart);
  const end = parseDate(visibleEnd);
  const calendarDays = Math.round((end - start) / dayMilliseconds) + 1;
  const segments = points.reduce((count, point, index) => {
    if (index === 0) return 1;
    return count + (parseDate(point[0]) - parseDate(points[index - 1][0]) > dayMilliseconds ? 1 : 0);
  }, 0);
  const manualDays = points.filter((point) => point[2] === "manual_hangzhou_xlsx").length;
  const details = [
    `记录 ${points.length} / ${calendarDays} 天`,
    `缺失 ${calendarDays - points.length} 天`,
    `${segments} 个连续数据段`,
  ];
  if (manualDays) details.push(`其中手工历史 ${manualDays} 天`);
  elements.coverage.textContent = details.join(" · ");
  const values = points.map((point) => point[1]);
  const useLogScale = Math.min(...values) > 0 && Math.max(...values) / Math.min(...values) >= 20;
  elements.chartNote.textContent = useLogScale
    ? "缺失日期保留为空，折线不会跨过数据缺口。当前数值跨度较大，纵轴自动使用对数比例。"
    : "缺失日期保留为空，折线不会跨过数据缺口。";
  renderTable(points);
  requestAnimationFrame(() => drawChart(points));
  syncUrl();
}

function downloadCsv() {
  const rows = [
    ["date", "city", "disease", "index_value", "source"],
    ...state.points.map((point) => [point[0], state.city, state.disease, point[1], pointSource(point)]),
  ];
  const csv = `\ufeff${rows.map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\r\n")}\r\n`;
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  const rangeLabel = state.range === "custom"
    ? `${state.startDate}_至_${state.endDate}`
    : state.range;
  anchor.download = `${state.city}-${state.disease}-${rangeLabel}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function bindEvents() {
  elements.city.addEventListener("change", async () => {
    state.city = elements.city.value;
    try {
      await activateCity(state.disease);
    } catch (error) {
      showError("数据暂时无法载入，请稍后刷新。");
      console.error(error);
    }
  });
  elements.disease.addEventListener("change", () => {
    state.disease = elements.disease.value;
    render();
  });
  elements.range.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-range]");
    if (!button) return;
    state.range = button.dataset.range;
    state.startDate = "";
    state.endDate = "";
    elements.startDate.value = "";
    elements.endDate.value = "";
    updateRangeButtons();
    render();
  });
  elements.startDate.addEventListener("change", () => {
    state.startDate = elements.startDate.value;
    const series = selectedSeries();
    if (state.startDate) {
      state.endDate = state.endDate || series.points.at(-1)[0];
      if (state.startDate > state.endDate) state.endDate = state.startDate;
      state.range = "custom";
    } else if (state.endDate) {
      state.startDate = series.points[0][0];
      state.range = "custom";
    } else {
      state.range = "all";
    }
    elements.startDate.value = state.startDate;
    elements.endDate.value = state.endDate;
    updateRangeButtons();
    render();
  });
  elements.endDate.addEventListener("change", () => {
    state.endDate = elements.endDate.value;
    const series = selectedSeries();
    if (state.endDate) {
      state.startDate = state.startDate || series.points[0][0];
      if (state.endDate < state.startDate) state.startDate = state.endDate;
      state.range = "custom";
    } else if (state.startDate) {
      state.endDate = series.points.at(-1)[0];
      state.range = "custom";
    } else {
      state.range = "all";
    }
    elements.startDate.value = state.startDate;
    elements.endDate.value = state.endDate;
    updateRangeButtons();
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
    const response = await fetch("./data/manifest.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const manifest = await response.json();
    if (manifest.version !== 2 || !Array.isArray(manifest.cities) || !manifest.cities.length) {
      throw new Error("数据格式无效");
    }
    state.manifest = manifest;
    const params = new URLSearchParams(window.location.search);
    const cities = manifest.cities.map((item) => item.city);
    const requestedCity = params.get("city");
    const normalizedCity = cities.find(
      (city) => city === requestedCity || city.replace(/市$/, "") === requestedCity,
    );
    state.city = normalizedCity || cities.find((city) => city === "杭州市") || cities[0];
    fillSelect(elements.city, cities, state.city);
    await activateCity(params.get("disease"), false);

    const requestedRange = params.get("range");
    const requestedStart = params.get("start") || "";
    const requestedEnd = params.get("end") || "";
    const validDate = (value) => /^\d{4}-\d{2}-\d{2}$/.test(value);
    const initialSeries = selectedSeries();
    if (requestedRange === "custom" && (validDate(requestedStart) || validDate(requestedEnd))) {
      state.range = "custom";
      state.startDate = validDate(requestedStart) ? requestedStart : initialSeries.points[0][0];
      state.endDate = validDate(requestedEnd) ? requestedEnd : initialSeries.points.at(-1)[0];
      if (state.startDate > state.endDate) {
        [state.startDate, state.endDate] = [state.endDate, state.startDate];
      }
    } else {
      state.range = ["14", "30", "90", "365", "all"].includes(requestedRange)
        ? requestedRange
        : "14";
      state.startDate = "";
      state.endDate = "";
    }

    elements.startDate.value = state.startDate;
    elements.endDate.value = state.endDate;
    updateRangeButtons();
    render();
  } catch (error) {
    showError("数据暂时无法载入，请稍后刷新。");
    console.error(error);
  }
}

start();
