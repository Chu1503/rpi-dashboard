"use strict";

const HEART_RATE_REFRESH_MS = 5 * 60 * 1000;
const state = { loaded: false, heartRateLoadedSeparately: false };
const $ = (id) => document.getElementById(id);

function updateGreeting() {
  $("greeting").textContent = `Hey ${document.body.dataset.displayName}`;
}

function formatUpdated(meta) {
  if (!meta) return "";
  if (!meta.updated_at) return meta.message || "Unable to update";
  const time = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" })
    .format(new Date(meta.updated_at));
  return meta.stale ? `Last successful update ${time}` : `Updated ${time}`;
}

function setStatus(id, meta) {
  const element = $(id);
  if (!element) return;
  element.textContent = formatUpdated(meta);
  element.classList.toggle("stale", Boolean(meta?.stale || !meta?.available));
}

function staleSuffix(meta) {
  return meta?.stale ? " · Last known" : "";
}

function renderHealth(section) {
  const data = section.data || {};
  const meta = section.meta || {};
  if (data.sleep_minutes != null) {
    const hours = Math.floor(data.sleep_minutes / 60);
    const minutes = data.sleep_minutes % 60;
    $("sleep-value").textContent = `${hours}h ${minutes}m`;
  } else $("sleep-value").textContent = "--";
  let sleepDetail = "Last sleep";
  if (data.sleep_ended_at) {
    sleepDetail += ` · ${new Intl.DateTimeFormat(undefined, {
      month: "short", day: "numeric"
    }).format(new Date(data.sleep_ended_at))}`;
  }
  $("sleep-detail").textContent = `${sleepDetail}${staleSuffix(meta)}`;

  $("steps-value").textContent = data.steps == null ? "--" : Number(data.steps).toLocaleString();
  $("steps-detail").textContent = meta.stale ? "Last known" : "";

  if (!state.heartRateLoadedSeparately) renderHeartRate(section);
}

function renderHeartRate(section) {
  const data = section.data || {};
  const meta = section.meta || {};
  $("heart-value").textContent = data.heart_rate == null ? "--" : `${data.heart_rate} bpm`;
  let heartDetail = "Latest measurement";
  if (data.heart_rate_measured_at) {
    heartDetail += ` · ${new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(data.heart_rate_measured_at))}`;
  }
  $("heart-detail").textContent = heartDetail + staleSuffix(meta);
}

async function refreshHeartRate({ manual = false } = {}) {
  try {
    const response = await fetch(manual ? "/api/heart-rate/refresh" : "/api/heart-rate", {
      method: manual ? "POST" : "GET",
      cache: "no-store"
    });
    if (!response.ok) throw new Error(`Heart rate returned ${response.status}`);
    renderHeartRate(await response.json());
    state.heartRateLoadedSeparately = true;
  } catch (error) {
    console.warn("Heart-rate refresh failed", error);
  }
}

function renderWeather(section) {
  const data = section.data || {};
  const meta = section.meta || {};
  $("weather-value").textContent = data.temperature_c == null ? "--" : `${Math.round(data.temperature_c)}°C`;
  $("weather-detail").textContent = `${data.condition || meta.message || "Unable to update"}${staleSuffix(meta)}`;
}

function dueLabel(value) {
  if (!value) return "";
  // Google Tasks due values are dates represented at midnight UTC; interpret the
  // YYYY-MM-DD portion locally so western timezones do not display the prior day.
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(date);
}

function renderTasks(section) {
  const container = $("tasks-list");
  const tasks = section.data?.tasks || [];
  container.replaceChildren();
  if (!tasks.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = section.meta?.available ? "Nothing waiting on you" : "Tasks are not configured yet";
    container.append(empty);
  } else {
    for (const task of tasks) {
      const row = document.createElement("div");
      row.className = "task";
      const marker = document.createElement("span");
      marker.className = "task-marker";
      marker.setAttribute("aria-hidden", "true");
      const copy = document.createElement("div");
      copy.className = "task-copy";
      const title = document.createElement("div");
      title.className = "task-title";
      title.textContent = task.title;
      copy.append(title);
      if (task.due) {
        const meta = document.createElement("div");
        meta.className = "task-meta";
        meta.textContent = dueLabel(task.due);
        copy.append(meta);
      }
      row.append(marker, copy);
      container.append(row);
    }
    const moreCount = section.data?.more_count || 0;
    if (moreCount) {
      const more = document.createElement("div");
      more.className = "task more-row";
      more.textContent = `+ ${moreCount} more`;
      container.append(more);
    }
  }
  setStatus("tasks-status", section.meta);
}

function eventTime(value) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric", minute: "2-digit", hour12: true
  }).format(new Date(value)).toUpperCase();
}

function eventTimeRange(event) {
  if (event.all_day) return "ALL DAY";
  return event.end ? `${eventTime(event.start)} – ${eventTime(event.end)}` : eventTime(event.start);
}

function dateKey(value) {
  const date = value instanceof Date ? value : new Date(value);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(dayKey, amount) {
  const [year, month, day] = dayKey.split("-").map(Number);
  const result = new Date(year, month - 1, day + amount, 12);
  return dateKey(result);
}

function dayDistance(from, to) {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}

function dayHeading(dayKey, todayKey) {
  const distance = dayDistance(todayKey, dayKey);
  if (distance === 0) return "TODAY";
  if (distance === 1) return "TOMORROW";
  return new Intl.DateTimeFormat("en-US", { timeZone: "UTC", weekday: "long" })
    .format(new Date(`${dayKey}T12:00:00Z`)).toUpperCase();
}

function shortDate(dayKey) {
  return new Intl.DateTimeFormat("en-US", { timeZone: "UTC", month: "short", day: "numeric" })
    .format(new Date(`${dayKey}T12:00:00Z`)).toUpperCase();
}

function readableTextColor(hexColor) {
  const match = /^#([0-9a-f]{6})$/i.exec(hexColor || "");
  if (!match) return "#f4f8f7";
  const value = Number.parseInt(match[1], 16);
  const red = (value >> 16) & 255;
  const green = (value >> 8) & 255;
  const blue = value & 255;
  return (red * 299 + green * 587 + blue * 114) / 1000 > 152 ? "#0b1518" : "#f4f8f7";
}

function groupCalendarEvents(events) {
  const groups = new Map();
  for (const event of events) {
    const key = event.all_day ? event.start.slice(0, 10) : dateKey(event.start);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(event);
  }
  return [...groups.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, dayEvents]) => [key, dayEvents.sort((left, right) => {
      if (left.all_day !== right.all_day) return left.all_day ? -1 : 1;
      return left.start.localeCompare(right.start);
    })]);
}

function duckPiece(className, water = false) {
  const piece = document.createElement("span");
  piece.className = `${water ? "duck-water-piece" : "duck-piece"} ${className}`;
  return piece;
}

function makeDuck(event, isNext, rowIndex) {
  const row = document.createElement("article");
  row.className = `duck-event${isNext ? " is-next" : ""}`;
  const color = event.color || "#78938b";
  row.style.setProperty("--duck-color", color);
  row.style.setProperty("--duck-ink", readableTextColor(color));
  row.style.setProperty("--duck-indent", `${(rowIndex % 2) * 5}px`);
  row.setAttribute("aria-label", `${eventTimeRange(event)}, ${event.title}`);

  const art = document.createElement("div");
  art.className = "duck-art";
  art.setAttribute("aria-hidden", "true");
  art.append(duckPiece("duck-head"), duckPiece("duck-body"), duckPiece("duck-tail"));

  const water = document.createElement("span");
  water.className = "duck-water";
  water.setAttribute("aria-hidden", "true");
  water.append(duckPiece("duck-head", true), duckPiece("duck-body", true), duckPiece("duck-tail", true));

  if (isNext) {
    const indicator = document.createElement("span");
    indicator.className = "next-indicator";
    indicator.setAttribute("aria-hidden", "true");
    row.append(indicator);
  }

  const content = document.createElement("div");
  content.className = "duck-content";
  const title = document.createElement("h3");
  title.title = event.title;
  title.textContent = event.title;
  const time = document.createElement("time");
  time.dateTime = event.start;
  time.textContent = eventTimeRange(event);
  content.append(title, time);
  row.prepend(art, water);
  row.append(content);
  return row;
}

function makeDaySection(dayKey, events, todayKey, nextEventId) {
  const section = document.createElement("section");
  section.className = "day-section";
  const heading = document.createElement("header");
  heading.className = "day-heading";
  const headingText = document.createElement("h3");
  const name = document.createElement("span");
  name.className = "day-name";
  name.textContent = dayHeading(dayKey, todayKey);
  const date = document.createElement("span");
  date.className = "day-date";
  date.textContent = shortDate(dayKey);
  headingText.append(name, date);
  heading.append(headingText);

  const list = document.createElement("div");
  list.className = "event-list";
  events.forEach((event, index) => list.append(makeDuck(event, event.id === nextEventId, index)));
  section.append(heading, list);
  return section;
}

function renderCalendar(section) {
  const container = $("calendar-list");
  const events = section.data?.events || [];
  container.replaceChildren();
  if (!events.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state calendar-empty";
    empty.textContent = section.meta?.available ? "Nothing scheduled for the next 14 days" : "Calendar is not configured yet";
    container.append(empty);
  } else {
    const agenda = document.createElement("div");
    agenda.className = "calendar-agenda";
    const todayKey = dateKey(new Date());
    const now = Date.now();
    const nextEvent = events
      .filter((event) => !event.all_day && new Date(event.start).getTime() >= now)
      .sort((left, right) => new Date(left.start) - new Date(right.start))[0];
    for (const [key, dayEvents] of groupCalendarEvents(events)) {
      agenda.append(makeDaySection(key, dayEvents, todayKey, nextEvent?.id));
    }
    container.append(agenda);
  }
  setStatus("calendar-status", section.meta);
}

function renderDashboard(payload) {
  renderTasks(payload.tasks);
  renderCalendar(payload.calendar);
  renderHealth(payload.health);
  renderWeather(payload.weather);
  state.loaded = true;
}

async function refreshDashboard({ manual = false } = {}) {
  const button = $("refresh-button");
  if (manual) {
    button.disabled = true;
    button.classList.add("is-refreshing");
  }
  try {
    const response = await fetch(manual ? "/api/refresh" : "/api/dashboard", {
      method: manual ? "POST" : "GET",
      cache: "no-store"
    });
    if (!response.ok) throw new Error(`Dashboard returned ${response.status}`);
    const payload = await response.json();
    renderDashboard(payload);
    if (manual) await refreshHeartRate({ manual: true });
  } catch (error) {
    console.warn("Alfred refresh failed", error);
  } finally {
    if (manual) {
      button.disabled = false;
      button.classList.remove("is-refreshing");
    }
  }
}

updateGreeting();
refreshDashboard();
refreshHeartRate();
$("refresh-button").addEventListener("click", () => refreshDashboard({ manual: true }));
setInterval(updateGreeting, 60_000);
setInterval(refreshDashboard, 60_000);
setInterval(refreshHeartRate, HEART_RATE_REFRESH_MS);
