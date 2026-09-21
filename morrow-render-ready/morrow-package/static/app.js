const state = {
  events: [],
  selectedDate: new Date(),
  monthDate: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  filter: "all",
  editingId: null,
  aiSuggestions: [],
};

const colors = {
  Coral: ["#c65d6e", "#f7e1e0"],
  Marigold: ["#c88b24", "#faedc9"],
  Teal: ["#4a9284", "#dceee8"],
  Plum: ["#795b85", "#e9e0ec"],
  Ink: ["#4b5872", "#e3e8f0"],
};

const $ = (selector) => document.querySelector(selector);
const pad = (value) => String(value).padStart(2, "0");
const dateKey = (value) => `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
const parseDate = (value) => {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
};
const sameDay = (a, b) => dateKey(a) === dateKey(b);
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
}[char]));

function showStatus(message, error = false) {
  const node = $("#status");
  node.textContent = message || "";
  node.style.color = error ? "#ad3249" : "";
  if (message) window.setTimeout(() => { if (node.textContent === message) node.textContent = ""; }, 3500);
}

async function api(url, options = {}) {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(csrf ? { "X-CSRF-Token": csrf } : {}), ...(options.headers || {}) },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || "The request could not be completed.");
  return body;
}

function visibleEvents() {
  return state.events.filter((event) => state.filter === "all" || event.type === state.filter);
}

function occursOn(event, target) {
  if (event.type === "birthday") return event.date.slice(5) === dateKey(target).slice(5);
  return event.date === dateKey(target);
}

function eventsForDate(target) {
  return visibleEvents().filter((event) => occursOn(event, target));
}

function render() {
  $("#month-label").textContent = state.monthDate.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  $("#selected-label").textContent = sameDay(state.selectedDate, new Date()) ? "TODAY" : "SELECTED DAY";
  $("#selected-date-label").textContent = state.selectedDate.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
  renderCalendar();
  renderSelected();
  renderUpcoming();
}

function renderCalendar() {
  const grid = $("#calendar-grid");
  grid.innerHTML = "";
  const first = new Date(state.monthDate.getFullYear(), state.monthDate.getMonth(), 1);
  const mondayOffset = (first.getDay() + 6) % 7;
  const start = new Date(first);
  start.setDate(first.getDate() - mondayOffset);

  for (let index = 0; index < 42; index += 1) {
    const current = new Date(start);
    current.setDate(start.getDate() + index);
    const cell = document.createElement("div");
    cell.className = `day-cell ${current.getMonth() === state.monthDate.getMonth() ? "" : "outside"} ${sameDay(current, state.selectedDate) ? "selected" : ""}`;

    const dayButton = document.createElement("button");
    dayButton.className = `day-number ${sameDay(current, new Date()) ? "today" : ""}`;
    dayButton.textContent = current.getDate();
    dayButton.addEventListener("click", () => selectDate(current));
    cell.appendChild(dayButton);

    eventsForDate(current).slice(0, 2).forEach((event) => {
      const chip = document.createElement("button");
      chip.className = "event-chip";
      chip.textContent = `● ${event.title}`;
      chip.style.color = colors[event.color][0];
      chip.style.background = colors[event.color][1];
      chip.title = event.title;
      chip.addEventListener("click", (click) => {
        click.stopPropagation();
        openEvent(event);
      });
      cell.appendChild(chip);
    });
    const remaining = eventsForDate(current).length - 2;
    if (remaining > 0) {
      const more = document.createElement("div");
      more.className = "more-events";
      more.textContent = `+${remaining} more`;
      cell.appendChild(more);
    }
    grid.appendChild(cell);
  }
}

function selectDate(value) {
  state.selectedDate = new Date(value);
  if (state.selectedDate.getMonth() !== state.monthDate.getMonth()) {
    state.monthDate = new Date(state.selectedDate.getFullYear(), state.selectedDate.getMonth(), 1);
  }
  render();
}

function renderSelected() {
  const container = $("#selected-events");
  const events = eventsForDate(state.selectedDate);
  if (!events.length) {
    container.innerHTML = '<div class="empty"><strong>Nothing planned yet</strong><span>A blank day can be a lovely thing.</span></div>';
    return;
  }
  container.innerHTML = events.map(eventRow).join("");
  container.querySelectorAll("[data-edit-id]").forEach((button) => {
    button.addEventListener("click", () => openEvent(state.events.find((event) => event.id === button.dataset.editId)));
  });
}

function eventRow(event) {
  const detail = event.all_day ? "All day" : event.time;
  const kind = event.type === "birthday" ? "Birthday · repeats yearly" : "Event";
  return `<div class="event-row">
    <span class="event-dot" style="background:${colors[event.color][0]}"></span>
    <div class="event-row-content">
      <div class="event-row-title">${escapeHtml(event.title)}</div>
      <div class="event-row-detail">${escapeHtml(detail)} · ${kind}</div>
    </div>
    <button class="edit-link" data-edit-id="${event.id}">Edit</button>
  </div>`;
}

function upcomingEvents() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return visibleEvents().map((event) => {
    let occurrence = parseDate(event.date);
    if (event.type === "birthday") {
      occurrence = new Date(today.getFullYear(), occurrence.getMonth(), occurrence.getDate());
      if (occurrence < today) occurrence.setFullYear(today.getFullYear() + 1);
    }
    return { event, occurrence };
  }).filter((item) => {
    const days = (item.occurrence - today) / 86400000;
    return days >= 0 && days <= 60;
  }).sort((a, b) => a.occurrence - b.occurrence).slice(0, 6);
}

function renderUpcoming() {
  const container = $("#upcoming-events");
  const items = upcomingEvents();
  if (!items.length) {
    container.innerHTML = '<div class="empty"><span>Your next sixty days are wide open.</span></div>';
    return;
  }
  container.innerHTML = items.map(({ event, occurrence }) => `
    <div class="upcoming-item" data-date="${dateKey(occurrence)}">
      <div class="date-badge">${occurrence.toLocaleDateString(undefined, { month: "short" }).toUpperCase()}<br>${occurrence.getDate()}</div>
      <div><div class="upcoming-title">${escapeHtml(event.title)}</div><div class="upcoming-detail">${occurrence.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}${event.time ? ` · ${escapeHtml(event.time)}` : ""}</div></div>
      <span class="event-dot" style="background:${colors[event.color][0]}"></span>
    </div>`).join("");
  container.querySelectorAll(".upcoming-item").forEach((item) => {
    item.addEventListener("click", () => selectDate(parseDate(item.dataset.date)));
  });
}

function clearForm() {
  $("#event-form").reset();
  $("#event-id").value = "";
  $("#event-all-day").checked = true;
  $("#event-date").value = dateKey(state.selectedDate);
  $("#event-color").value = "Coral";
  $("#event-reminder").value = "1";
  $("#delete-button").hidden = true;
  updateTimeVisibility();
}

function openEvent(event = null) {
  state.editingId = event?.id || null;
  if (!event || !event.id) {
    clearForm();
    if (event) {
      $("#event-name").value = event.title || "";
      $("#event-date").value = event.date || dateKey(state.selectedDate);
      $("#event-type").value = event.type || "event";
      $("#event-time").value = event.time || "";
      $("#event-color").value = event.color || "Coral";
      $("#event-reminder").value = String(event.reminder ?? 1);
      $("#event-notes").value = event.notes || "";
      $("#event-all-day").checked = event.all_day !== false;
      updateTimeVisibility();
    }
  } else {
    $("#event-id").value = event.id;
    $("#event-name").value = event.title;
    $("#event-date").value = event.date;
    $("#event-type").value = event.type;
    $("#event-time").value = event.time || "";
    $("#event-color").value = event.color;
    $("#event-reminder").value = String(event.reminder);
    $("#event-notes").value = event.notes || "";
    $("#event-all-day").checked = event.all_day;
    $("#delete-button").hidden = false;
    updateTimeVisibility();
  }
  $("#dialog-label").textContent = event?.id ? "EDIT DATE" : "NEW DATE";
  $("#event-dialog").showModal();
}

function updateTimeVisibility() {
  const allDay = $("#event-all-day").checked;
  $("#time-label").style.display = allDay ? "none" : "block";
  $("#type-hint").textContent = $("#event-type").value === "birthday"
    ? "Birthdays repeat every year."
    : "Events happen once on the chosen date.";
}

async function saveEvent(formEvent) {
  formEvent.preventDefault();
  const id = $("#event-id").value;
  const payload = {
    title: $("#event-name").value.trim(),
    date: $("#event-date").value,
    type: $("#event-type").value,
    time: $("#event-time").value,
    color: $("#event-color").value,
    reminder: Number($("#event-reminder").value),
    notes: $("#event-notes").value.trim(),
    all_day: $("#event-all-day").checked,
  };
  try {
    const result = await api(id ? `/api/events/${id}` : "/api/events", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    if (id) state.events = state.events.map((event) => event.id === id ? result.event : event);
    else state.events.push(result.event);
    state.selectedDate = parseDate(result.event.date);
    state.monthDate = new Date(state.selectedDate.getFullYear(), state.selectedDate.getMonth(), 1);
    $("#event-dialog").close();
    render();
    showStatus(id ? "Date updated." : "Date saved.");
  } catch (error) {
    showStatus(error.message, true);
  }
}

async function deleteEvent() {
  const id = $("#event-id").value;
  const event = state.events.find((item) => item.id === id);
  if (!event || !window.confirm(`Remove “${event.title}” from your calendar?`)) return;
  try {
    await api(`/api/events/${id}`, { method: "DELETE" });
    state.events = state.events.filter((item) => item.id !== id);
    $("#event-dialog").close();
    render();
    showStatus("Date deleted.");
  } catch (error) {
    showStatus(error.message, true);
  }
}

function exportEvents() {
  const blob = new Blob([JSON.stringify({ app: "Morrow Web", version: 1, events: state.events }, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "morrow-calendar.json";
  link.click();
  URL.revokeObjectURL(link.href);
}

async function importEvents(file) {
  try {
    const payload = JSON.parse(await file.text());
    const result = await api("/api/import", { method: "POST", body: JSON.stringify(payload) });
    state.events = result.events;
    render();
    showStatus(`${result.count} dates imported.`);
  } catch (error) {
    showStatus(error.message || "Import failed.", true);
  }
}

async function loadEvents() {
  try {
    const result = await api("/api/events");
    state.events = result.events;
    render();
  } catch (error) {
    showStatus(error.message, true);
  }
}

function openAiDialog() {
  $("#ai-month").value = `${state.monthDate.getFullYear()}-${pad(state.monthDate.getMonth() + 1)}`;
  $("#ai-prompt").value = "";
  $("#ai-result").innerHTML = "";
  $("#ai-dialog").showModal();
}

function renderAiSuggestions(result) {
  state.aiSuggestions = result.suggestions || [];
  const resultNode = $("#ai-result");
  if (!state.aiSuggestions.length) {
    resultNode.innerHTML = '<div class="empty">No suggestions came back. Try a more specific request.</div>';
    return;
  }
  const providerLabel = result.provider ? ` · via ${result.provider}` : "";
  const warning = result.warning ? `<div class="ai-warning">${escapeHtml(result.warning)}</div>` : "";
  resultNode.innerHTML = `<div class="ai-result-heading">Suggestions${providerLabel}</div>${warning}` +
    state.aiSuggestions.map((suggestion, index) => `
      <div class="ai-suggestion">
        <div class="event-dot" style="background:${colors[suggestion.color]?.[0] || colors.Coral[0]}"></div>
        <div class="ai-suggestion-copy">
          <strong>${escapeHtml(suggestion.title)}</strong>
          <span>${escapeHtml(suggestion.date)} · ${escapeHtml(suggestion.notes || "A date worth keeping.")}</span>
        </div>
        <button type="button" class="edit-link" data-ai-index="${index}">Use</button>
      </div>`).join("");
  resultNode.querySelectorAll("[data-ai-index]").forEach((button) => {
    button.addEventListener("click", () => {
      const suggestion = state.aiSuggestions[Number(button.dataset.aiIndex)];
      $("#ai-dialog").close();
      openEvent(suggestion);
    });
  });
}

async function requestAiSuggestions() {
  const prompt = $("#ai-prompt").value.trim();
  if (!prompt) {
    $("#ai-result").innerHTML = '<div class="form-error">Tell the assistant what kind of dates you want.</div>';
    return;
  }
  const submit = $("#ai-submit");
  submit.disabled = true;
  submit.textContent = "Thinking…";
  $("#ai-result").innerHTML = '<div class="empty">Researching and shaping a few ideas…</div>';
  try {
    const result = await api("/api/ai/suggestions", {
      method: "POST",
      body: JSON.stringify({
        prompt,
        month: $("#ai-month").value,
        provider: $("#ai-provider").value,
      }),
    });
    renderAiSuggestions(result);
  } catch (error) {
    $("#ai-result").innerHTML = `<div class="form-error">${escapeHtml(error.message)}</div>`;
  } finally {
    submit.disabled = false;
    submit.textContent = "Suggest dates";
  }
}

async function showSettings() {
  $("#settings-dialog").showModal();
  try {
    const status = await api("/api/integrations");
    $("#integration-status").textContent = `Configured: OpenAI ${status.openai ? "yes" : "no"} · Tavily ${status.tavily ? "yes" : "no"} · Groq ${status.groq ? "yes" : "no"}`;
  } catch {
    $("#integration-status").textContent = "Configuration status unavailable.";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => {
    state.filter = button.dataset.filter;
    document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("active", item === button));
    $("#filter-select").value = state.filter;
    render();
  }));
  $("#filter-select").addEventListener("change", (event) => {
    state.filter = event.target.value;
    document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("active", item.dataset.filter === state.filter));
    render();
  });
  $("#today-button").addEventListener("click", () => { state.selectedDate = new Date(); state.monthDate = new Date(new Date().getFullYear(), new Date().getMonth(), 1); render(); });
  $("#previous-month").addEventListener("click", () => { state.monthDate.setMonth(state.monthDate.getMonth() - 1); render(); });
  $("#next-month").addEventListener("click", () => { state.monthDate.setMonth(state.monthDate.getMonth() + 1); render(); });
  $("#add-button").addEventListener("click", () => openEvent());
  $("#ai-button").addEventListener("click", openAiDialog);
  $("#selected-add").addEventListener("click", () => openEvent());
  $("#event-form").addEventListener("submit", saveEvent);
  $("#cancel-button").addEventListener("click", () => $("#event-dialog").close());
  $("#delete-button").addEventListener("click", deleteEvent);
  $("#event-all-day").addEventListener("change", updateTimeVisibility);
  $("#event-type").addEventListener("change", updateTimeVisibility);
  $("#export-button").addEventListener("click", exportEvents);
  $("#import-button").addEventListener("click", () => $("#import-file").click());
  $("#import-file").addEventListener("change", (event) => { if (event.target.files[0]) importEvents(event.target.files[0]); event.target.value = ""; });
  $("#settings-button").addEventListener("click", showSettings);
  $("#settings-close").addEventListener("click", () => $("#settings-dialog").close());
  $("#settings-done").addEventListener("click", () => $("#settings-dialog").close());
  $("#ai-close").addEventListener("click", () => $("#ai-dialog").close());
  $("#ai-cancel").addEventListener("click", () => $("#ai-dialog").close());
  $("#ai-submit").addEventListener("click", requestAiSuggestions);
  loadEvents();
});