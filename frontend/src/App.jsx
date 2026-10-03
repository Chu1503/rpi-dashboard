import React, { useCallback, useEffect, useRef, useState } from "react";

const DASHBOARD_REFRESH_MS = 60_000;
const STEPS_REFRESH_MS = 2 * 60_000;
const HEART_RATE_REFRESH_MS = 2 * 60_000;
const ASSISTANT_POLL_MS = 250;
const DISPLAY_CONTROL_POLL_MS = 1_000;
const DASHBOARD_TIME_ZONE = document.getElementById("root")?.dataset.timeZone || undefined;
const NOTE_COLORS = [
  "#ffd9d5", "#d9f8cf", "#f3f9bd", "#c9f3f1",
  "#e6dbff", "#ffe1bd", "#d4e9ff"
];
const DUCK_COLORS = [
  "#ffd9d5", "#f3f9bd", "#fff0ad", "#c9f3f1",
  "#e6dbff", "#ffe1bd", "#d4e9ff"
];

function localDate(value, options = {}) {
  if (!value) return "";
  return new Intl.DateTimeFormat(undefined, {
    ...options,
    ...(DASHBOARD_TIME_ZONE ? { timeZone: DASHBOARD_TIME_ZONE } : {})
  }).format(new Date(value));
}

function localDateKey(value = new Date()) {
  if (!DASHBOARD_TIME_ZONE) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: DASHBOARD_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(value);
  const part = (type) => parts.find((item) => item.type === type)?.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

function civilDateLabel(value) {
  if (!value) return "";
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short", day: "numeric", timeZone: "UTC"
  })
    .format(new Date(Date.UTC(year, month - 1, day)))
    .toUpperCase();
}

function titleColor(title) {
  const normalized = String(title || "Untitled event")
    .trim()
    .replace(/\s+/g, " ")
    .toLocaleLowerCase();
  let hash = 2166136261;
  for (let index = 0; index < normalized.length; index += 1) {
    hash ^= normalized.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return DUCK_COLORS[(hash >>> 0) % DUCK_COLORS.length];
}

function displayTitle(title) {
  return String(title || "Untitled event")
    .trim()
    .replace(/\s+/g, " ")
    .toLocaleLowerCase()
    .replace(/(^|[\s/–—-])(\p{L})/gu, (_, prefix, letter) =>
      `${prefix}${letter.toLocaleUpperCase()}`
    );
}

function sleepValue(minutes) {
  if (minutes == null) return "--";
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function eventTime(event) {
  if (event.all_day) return "ALL DAY";
  const format = (value) =>
    new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      ...(DASHBOARD_TIME_ZONE ? { timeZone: DASHBOARD_TIME_ZONE } : {})
    }).format(new Date(value));
  return event.end ? `${format(event.start)} – ${format(event.end)}` : format(event.start);
}

function eventDateObject(event) {
  if (!event?.all_day) return new Date(event.start);
  const [year, month, day] = String(event.start).split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function eventDay(event) {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    ...(event.all_day
      ? { timeZone: "UTC" }
      : DASHBOARD_TIME_ZONE ? { timeZone: DASHBOARD_TIME_ZONE } : {})
  })
    .format(eventDateObject(event));
}

function eventDate(event) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    ...(event.all_day
      ? { timeZone: "UTC" }
      : DASHBOARD_TIME_ZONE ? { timeZone: DASHBOARD_TIME_ZONE } : {})
  })
    .format(eventDateObject(event));
}

function eventDateKey(event) {
  return event?.all_day ? event.start : localDateKey(eventDateObject(event));
}

function calendarDayGroups(events) {
  const days = [];
  events.forEach((event) => {
    const key = eventDateKey(event);
    const current = days[days.length - 1];
    if (current?.key === key) current.events.push(event);
    else days.push({ key, events: [event] });
  });
  return days;
}

async function requestJson(url, options) {
  const response = await fetch(url, { cache: "no-store", ...options });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

function RefreshButton({ busy, onClick }) {
  return (
    <button
      className="refresh-control"
      type="button"
      aria-label="Refresh all dashboard data"
      title="Refresh all data"
      disabled={busy}
      onClick={onClick}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M20 11a8.1 8.1 0 0 0-15.5-2M4 4v5h5M4 13a8.1 8.1 0 0 0 15.5 2M20 20v-5h-5" />
      </svg>
    </button>
  );
}

function AssistantReply({ message }) {
  if (!message) return null;
  return (
    <aside className="assistant-reply" role="status" aria-live="polite">
      <span>Alfred</span>
      <p>{message}</p>
    </aside>
  );
}

function MetricTile({ className, label, value, detail }) {
  return (
    <article className={`metric-tile ${className}`}>
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
      <span className="metric-detail">{detail || "\u00a0"}</span>
    </article>
  );
}

function Metrics({ health, steps, heart, weather }) {
  const healthData = health?.data || {};
  const stepsData = steps?.data || healthData;
  const heartData = heart?.data || healthData;
  const weatherData = weather?.data || {};
  const sleepDate = healthData.sleep_ended_at
    ? `LAST SLEEP · ${localDate(healthData.sleep_ended_at, { month: "short", day: "numeric" }).toUpperCase()}`
    : "LAST SLEEP";
  const heartDetail = heartData.heart_rate_measured_at
    ? `MEASURED · ${localDate(heartData.heart_rate_measured_at, { hour: "numeric", minute: "2-digit" }).toUpperCase()}`
    : "LATEST MEASUREMENT";
  const stepsDetail = !stepsData.steps_date
    ? "UNAVAILABLE"
    : stepsData.steps_date === localDateKey()
      ? "TODAY"
      : `LAST KNOWN · ${civilDateLabel(stepsData.steps_date)}`;

  return (
    <section className="metric-collage" aria-label="Health and weather">
      <MetricTile className="sleep-tile" label="Sleep" value={sleepValue(healthData.sleep_minutes)} detail={sleepDate} />
      <MetricTile className="steps-tile" label="Steps" value={stepsData.steps == null ? "--" : Number(stepsData.steps).toLocaleString()} detail={stepsDetail} />
      <MetricTile className="heart-tile" label="Heart rate" value={heartData.heart_rate == null ? "--" : `${heartData.heart_rate} bpm`} detail={heartDetail} />
      <MetricTile className="weather-tile" label="Weather" value={weatherData.temperature_c == null ? "--" : `${Math.round(weatherData.temperature_c)}°C`} detail={(weatherData.condition || "UNAVAILABLE").toUpperCase()} />
    </section>
  );
}

function Tasks({ section }) {
  const allTasks = section?.data?.tasks || [];
  const tasks = allTasks.slice(0, 14);

  return (
    <section className="task-zone" aria-label="Tasks">
      <div className="sticky-row">
        {tasks.length ? tasks.map((task, index) => (
          <article
            className="sticky-note"
            key={task.id || `${task.title}-${index}`}
            style={{ "--note-color": NOTE_COLORS[index % NOTE_COLORS.length] }}
          >
            <h3>{task.title}</h3>
          </article>
        )) : (
          <div className="tasks-empty">
            {section?.meta?.available === false
              ? "Google Tasks needs authorization."
              : "Nothing waiting on you."}
          </div>
        )}
      </div>
    </section>
  );
}

function Duck({ event }) {
  const color = titleColor(event.title);
  const title = displayTitle(event.title);
  return (
    <article
      className="pond-event"
      style={{ "--duck-color": color }}
      aria-label={`${title}, ${eventTime(event)}`}
    >
      <div className="duck">
        <div className="duck-art" aria-hidden="true">
          <span className="duck-piece duck-head" />
          <span className="duck-piece duck-body" />
          <span className="duck-piece duck-tail" />
        </div>
        <div className="duck-copy">
          <h3 title={title}>{title}</h3>
          <time dateTime={event.start}>{eventTime(event)}</time>
        </div>
      </div>
    </article>
  );
}

function CalendarDay({ group }) {
  const representative = group.events[0];
  const dayColor = titleColor(`calendar-day-${group.key}`);
  const columns = Math.min(group.events.length, 4);
  const rows = Math.ceil(group.events.length / 4);
  return (
    <section
      className="duck-day-group"
      style={{
        "--day-span": columns,
        "--day-rows": rows,
        "--day-event-columns": columns,
        "--day-color": dayColor
      }}
      aria-label={`${eventDay(representative)} ${eventDate(representative)}`}
    >
      <div
        className="day-group-events"
      >
        {group.events.map((event, index) => (
          <Duck key={`${event.id || event.start}-${index}`} event={event} />
        ))}
      </div>
      <div className="event-date">
        <strong>{eventDay(representative)}</strong>
        <span>{eventDate(representative)}</span>
      </div>
    </section>
  );
}

function Pond({ section }) {
  const events = (section?.data?.events || []).slice(0, 8);
  const dayGroups = calendarDayGroups(events);
  return (
    <section className="pond-zone" aria-label="Upcoming calendar events">
      <div className={`pond${events.length ? " has-events" : " is-empty"}`}>
        {!events.length && <div className="water-shape" aria-hidden="true" />}
        <div className="duck-row">
          {events.length ? dayGroups.map((group) => (
            <CalendarDay key={group.key} group={group} />
          )) : (
            <div className="pond-empty">The pond is clear.</div>
          )}
        </div>
      </div>
    </section>
  );
}

export default function App() {
  const displayName = document.getElementById("root")?.dataset.displayName || "Chu";
  const [dashboard, setDashboard] = useState(null);
  const [steps, setSteps] = useState(null);
  const [heart, setHeart] = useState(null);
  const [busy, setBusy] = useState(false);
  const [assistantMessage, setAssistantMessage] = useState("");
  const assistantSequence = useRef(null);
  const assistantAudio = useRef(null);
  const assistantAudioUrl = useRef(null);
  const assistantAudioContext = useRef(null);
  const hdmiKeepAlive = useRef(null);

  const loadDashboard = useCallback(async (manual = false) => {
    const data = await requestJson(manual ? "/api/refresh" : "/api/dashboard", {
      method: manual ? "POST" : "GET"
    });
    setDashboard(data);
  }, []);

  const loadHeart = useCallback(async (manual = false) => {
    const data = await requestJson(manual ? "/api/heart-rate/refresh" : "/api/heart-rate", {
      method: manual ? "POST" : "GET"
    });
    setHeart(data);
  }, []);

  const loadSteps = useCallback(async (manual = false) => {
    const data = await requestJson(manual ? "/api/steps/refresh" : "/api/steps", {
      method: manual ? "POST" : "GET"
    });
    setSteps(data);
  }, []);

  useEffect(() => {
    loadDashboard().catch((error) => console.warn("Dashboard refresh failed", error));
    loadSteps().catch((error) => console.warn("Steps refresh failed", error));
    loadHeart().catch((error) => console.warn("Heart-rate refresh failed", error));
    const dashboardTimer = window.setInterval(
      () => loadDashboard().catch((error) => console.warn("Dashboard refresh failed", error)),
      DASHBOARD_REFRESH_MS
    );
    const heartTimer = window.setInterval(
      () => loadHeart().catch((error) => console.warn("Heart-rate refresh failed", error)),
      HEART_RATE_REFRESH_MS
    );
    const stepsTimer = window.setInterval(
      () => loadSteps().catch((error) => console.warn("Steps refresh failed", error)),
      STEPS_REFRESH_MS
    );
    return () => {
      window.clearInterval(dashboardTimer);
      window.clearInterval(stepsTimer);
      window.clearInterval(heartTimer);
    };
  }, [loadDashboard, loadHeart, loadSteps]);

  useEffect(() => {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return undefined;
    const context = new AudioContextClass({ latencyHint: "interactive" });
    const oscillator = context.createOscillator();
    const keepAliveGain = context.createGain();
    oscillator.frequency.value = 18;
    keepAliveGain.gain.value = 0.00001;
    oscillator.connect(keepAliveGain).connect(context.destination);
    oscillator.start();
    context.resume().catch(() => {});
    assistantAudioContext.current = context;
    hdmiKeepAlive.current = oscillator;
    return () => {
      oscillator.stop();
      context.close();
      assistantAudioContext.current = null;
      hdmiKeepAlive.current = null;
    };
  }, []);

  useEffect(() => {
    let stopped = false;
    let refreshing = false;
    const pollDisplayControl = async () => {
      if (refreshing) return;
      try {
        const command = await requestJson("/api/display/control");
        if (stopped || !command.action) return;
        if (command.action === "scroll") {
          const maxScroll = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
          const position = Math.max(0, Math.min(1, Number(command.position) || 0));
          window.scrollTo({ top: maxScroll * position, behavior: "smooth" });
          return;
        }
        if (command.action !== "refresh") return;
        refreshing = true;
        await Promise.allSettled([
          requestJson("/api/refresh", { method: "POST" }),
          requestJson("/api/steps/refresh", { method: "POST" }),
          requestJson("/api/heart-rate/refresh", { method: "POST" })
        ]);
        if (!stopped) window.location.reload();
      } catch (error) {
        console.warn("Display control poll failed", error);
      }
    };
    pollDisplayControl();
    const timer = window.setInterval(pollDisplayControl, DISPLAY_CONTROL_POLL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let stopped = false;
    let polling = false;
    const pollAssistant = async () => {
      if (polling) return;
      polling = true;
      const suffix = assistantSequence.current == null
        ? ""
        : `?after=${encodeURIComponent(assistantSequence.current)}`;
      try {
        const data = await requestJson(`/api/assistant/latest${suffix}`);
        if (stopped) return;
        if (assistantSequence.current == null) {
          assistantSequence.current = data.sequence;
          return;
        }
        if (!data.message) return;
        setAssistantMessage(data.message);
        assistantAudio.current?.pause();
        if (assistantAudioUrl.current) URL.revokeObjectURL(assistantAudioUrl.current);
        assistantAudioUrl.current = null;

        // Start from Microsoft's first audio chunks instead of waiting for the
        // complete file. If streaming is unavailable, retain the proven WAV
        // blob path as a transparent fallback.
        let audio = new Audio(`/api/assistant/speech-stream/${data.sequence}`);
        audio.preload = "auto";
        audio.volume = 1;
        assistantAudio.current = audio;
        try {
          await audio.play();
        } catch (streamError) {
          audio.pause();
          console.warn("Streaming speech failed; using WAV fallback", streamError);
          const response = await fetch(`/api/assistant/speech/${data.sequence}`, {
            cache: "no-store"
          });
          if (!response.ok) {
            throw new Error(`Speech endpoint returned ${response.status}`);
          }
          const audioUrl = URL.createObjectURL(await response.blob());
          assistantAudioUrl.current = audioUrl;
          audio = new Audio(audioUrl);
          audio.preload = "auto";
          audio.volume = 1;
          assistantAudio.current = audio;
          await audio.play();
        }
        assistantSequence.current = data.sequence;
      } catch (error) {
        console.warn("Assistant listener failed", error);
      } finally {
        polling = false;
      }
    };
    pollAssistant();
    const timer = window.setInterval(pollAssistant, ASSISTANT_POLL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      assistantAudio.current?.pause();
      if (assistantAudioUrl.current) URL.revokeObjectURL(assistantAudioUrl.current);
    };
  }, []);

  useEffect(() => {
    if (!assistantMessage) return undefined;
    const timer = window.setTimeout(() => setAssistantMessage(""), 18_000);
    return () => window.clearTimeout(timer);
  }, [assistantMessage]);

  const refreshAll = useCallback(async () => {
    setBusy(true);
    try {
      await Promise.all([loadDashboard(true), loadSteps(true), loadHeart(true)]);
    } catch (error) {
      console.warn("Manual refresh failed", error);
    } finally {
      setBusy(false);
    }
  }, [loadDashboard, loadHeart, loadSteps]);

  const visibleTaskCount = Math.min(dashboard?.tasks?.data?.tasks?.length || 0, 14);
  const taskRows = visibleTaskCount > 7 ? 2 : 1;
  const visibleEventCount = Math.min(dashboard?.calendar?.data?.events?.length || 0, 8);
  const pondRows = visibleEventCount > 4 ? 2 : 1;

  return (
    <main className="dashboard-frame">
      <div
        className="paper-canvas"
        data-pond-rows={pondRows}
        style={{ "--task-rows": taskRows, "--pond-rows": pondRows }}
      >
        <RefreshButton busy={busy} onClick={refreshAll} />
        <AssistantReply message={assistantMessage} />
        <header className="hero-zone">
          <div className="greeting-lockup">
            <p>Hey</p>
            <h1>{displayName}</h1>
          </div>
          <Metrics health={dashboard?.health} steps={steps} heart={heart} weather={dashboard?.weather} />
        </header>
        <Tasks section={dashboard?.tasks} />
        <Pond section={dashboard?.calendar} />
      </div>
    </main>
  );
}
