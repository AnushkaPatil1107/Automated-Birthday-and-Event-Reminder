"""
Morrow — a single-file birthday and event calendar.

Run with:
    python birthday_event_calendar.py

The app uses only Python's standard library. Calendar data is stored in
morrow_events.json beside this file.
"""

from __future__ import annotations

import calendar
import json
import uuid
from datetime import date, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "Morrow — Birthday & Event Calendar"
DATA_FILE = Path(__file__).with_name("morrow_events.json")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
COLORS = {
    "Coral": ("#c65d6e", "#f7e1e0"),
    "Marigold": ("#c88b24", "#faedc9"),
    "Teal": ("#4a9284", "#dceee8"),
    "Plum": ("#795b85", "#e9e0ec"),
    "Ink": ("#4b5872", "#e3e8f0"),
}
REMINDERS = {
    "No reminder": 0,
    "On the day": 0,
    "1 day before": 1,
    "1 week before": 7,
}


def today_key() -> str:
    return date.today().isoformat()


def parse_key(value: str) -> date:
    return date.fromisoformat(value)


def key_for(value: date) -> str:
    return value.isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def add_days(value: str, amount: int) -> str:
    return key_for(parse_key(value) + timedelta(days=amount))


def occurrence_key(event: dict, year: int) -> str:
    if event.get("type") == "birthday":
        return f"{year}-{event['date'][5:]}"
    return event["date"]


def next_occurrence(event: dict, from_date: date | None = None) -> str:
    current = from_date or date.today()
    if event.get("type") != "birthday":
        return event["date"]
    this_year = occurrence_key(event, current.year)
    if this_year >= current.isoformat():
        return this_year
    return occurrence_key(event, current.year + 1)


def clean_event(raw: dict) -> dict | None:
    if not isinstance(raw, dict) or not raw.get("title") or not raw.get("date"):
        return None
    try:
        parse_key(str(raw["date"]))
    except (TypeError, ValueError):
        return None
    event_type = "birthday" if raw.get("type") == "birthday" else "event"
    color = raw.get("color") if raw.get("color") in COLORS else "Coral"
    reminder = raw.get("reminder") if raw.get("reminder") in REMINDERS else "No reminder"
    return {
        "id": str(raw.get("id") or new_id()),
        "title": str(raw["title"]).strip(),
        "date": str(raw["date"]),
        "type": event_type,
        "time": str(raw.get("time") or ""),
        "color": color,
        "reminder": reminder,
        "notes": str(raw.get("notes") or "").strip(),
        "all_day": bool(raw.get("all_day", raw.get("allDay", True))),
    }


def seed_events() -> list[dict]:
    current = date.today()
    return [
        {
            "id": new_id(),
            "title": "Mum's birthday",
            "date": key_for(current + timedelta(days=6)),
            "type": "birthday",
            "time": "",
            "color": "Coral",
            "reminder": "1 week before",
            "notes": "Order the lemon cake she likes.",
            "all_day": True,
        },
        {
            "id": new_id(),
            "title": "Dinner at Sorella",
            "date": key_for(current + timedelta(days=13)),
            "type": "event",
            "time": "19:30",
            "color": "Teal",
            "reminder": "1 day before",
            "notes": "Reservation under Avery.",
            "all_day": False,
        },
    ]


class MorrowCalendar(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x820")
        self.minsize(960, 680)
        self.configure(bg="#f8f4ed")

        self.events = self.load_events()
        self.selected_date = date.today()
        self.month_date = date.today().replace(day=1)
        self.filter_value = "All dates"
        self.notifications_enabled = False
        self.notified: set[str] = set()
        self.calendar_grid: ttk.Frame | None = None
        self.selected_panel: ttk.Frame | None = None
        self.upcoming_panel: ttk.Frame | None = None

        self.setup_styles()
        self.build_ui()
        self.refresh()
        self.after(60_000, self.check_reminders)

    def setup_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Arial", 10), background="#f8f4ed", foreground="#292a3a")
        style.configure("TFrame", background="#f8f4ed")
        style.configure("Card.TFrame", background="#fffdf9", relief="solid", borderwidth=1)
        style.configure("Title.TLabel", font=("Arial", 25, "bold"), background="#f8f4ed", foreground="#292a3a")
        style.configure("Subtitle.TLabel", font=("Arial", 10), background="#f8f4ed", foreground="#747381")
        style.configure("Section.TLabel", font=("Arial", 9, "bold"), background="#f8f4ed", foreground="#a43d53")
        style.configure("CardTitle.TLabel", font=("Arial", 18, "bold"), background="#fffdf9", foreground="#292a3a")
        style.configure("CardBody.TLabel", background="#fffdf9", foreground="#292a3a")
        style.configure("MutedCard.TLabel", background="#fffdf9", foreground="#747381")
        style.configure("Primary.TButton", font=("Arial", 10, "bold"), foreground="white", background="#b8325c", padding=(13, 9))
        style.map("Primary.TButton", background=[("active", "#982847")])
        style.configure("Quiet.TButton", font=("Arial", 10), foreground="#515163", background="#fffdf9", padding=(9, 7))
        style.map("Quiet.TButton", background=[("active", "#eee9e1")])
        style.configure("Nav.TButton", anchor="w", font=("Arial", 10), foreground="#515163", background="#f8f4ed", padding=(12, 10))
        style.map("Nav.TButton", background=[("active", "#e1efeb")])
        style.configure("Day.TButton", font=("Arial", 9, "bold"), foreground="#292a3a", background="#fffdf9", padding=4)
        style.map("Day.TButton", background=[("active", "#e1efeb")])
        style.configure("Today.TButton", font=("Arial", 9, "bold"), foreground="white", background="#b8325c", padding=4)
        style.configure("TEntry", padding=7)
        style.configure("TCombobox", padding=6)

    def load_events(self) -> list[dict]:
        if DATA_FILE.exists():
            try:
                payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                raw_events = payload.get("events", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
                return [event for item in raw_events if (event := clean_event(item))]
            except (OSError, json.JSONDecodeError):
                pass
        events = seed_events()
        self.save_events(events)
        return events

    def save_events(self, events: list[dict] | None = None) -> None:
        try:
            DATA_FILE.write_text(
                json.dumps({"app": "Morrow Python", "version": 1, "events": events or self.events}, indent=2),
                encoding="utf-8",
            )
        except OSError:
            messagebox.showwarning("Could not save", f"Morrow could not write to:\n{DATA_FILE}")

    def build_ui(self) -> None:
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(outer, width=220)
        sidebar.grid(row=0, column=0, sticky="nsw", padx=(16, 12), pady=18)
        sidebar.grid_propagate(False)
        self.make_brand(sidebar)
        ttk.Label(sidebar, text="YOUR SPACE", style="Section.TLabel").pack(anchor="w", pady=(42, 8), padx=10)
        ttk.Button(sidebar, text="▦  Calendar", style="Nav.TButton", command=lambda: self.set_filter("All dates")).pack(fill="x")
        ttk.Button(sidebar, text="♧  Birthdays", style="Nav.TButton", command=lambda: self.set_filter("Birthdays")).pack(fill="x")
        ttk.Button(sidebar, text="☷  Events", style="Nav.TButton", command=lambda: self.set_filter("Events")).pack(fill="x")
        ttk.Label(sidebar, text="TOOLS", style="Section.TLabel").pack(anchor="w", pady=(32, 8), padx=10)
        ttk.Button(sidebar, text="⚙  Settings", style="Nav.TButton", command=self.open_settings).pack(fill="x")

        quote = ttk.Frame(sidebar, style="Card.TFrame", padding=14)
        quote.pack(side="bottom", fill="x", pady=8)
        ttk.Label(quote, text="The little dates matter.", font=("Arial", 11, "bold"), background="#fffdf9", foreground="#292a3a", wraplength=170).pack(anchor="w")
        ttk.Label(quote, text="A quiet place for the people and plans worth remembering.", style="MutedCard.TLabel", wraplength=170).pack(anchor="w", pady=(8, 0))

        main = ttk.Frame(outer)
        main.grid(row=0, column=1, sticky="nsew", padx=(4, 22), pady=18)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(1, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        header.columnconfigure(0, weight=1)
        heading = ttk.Frame(header)
        heading.grid(row=0, column=0, sticky="w")
        ttk.Label(heading, text="PERSONAL CALENDAR", style="Section.TLabel").pack(anchor="w")
        ttk.Label(heading, text="Your dates, in one place.", style="Title.TLabel").pack(anchor="w", pady=(3, 0))
        controls = ttk.Frame(header)
        controls.grid(row=0, column=1, sticky="e")
        ttk.Button(controls, text="Today", style="Quiet.TButton", command=self.go_today).pack(side="left", padx=3)
        ttk.Button(controls, text="←", style="Quiet.TButton", command=lambda: self.change_month(-1)).pack(side="left", padx=3)
        ttk.Button(controls, text="→", style="Quiet.TButton", command=lambda: self.change_month(1)).pack(side="left", padx=3)
        ttk.Button(controls, text="+  Add a date", style="Primary.TButton", command=self.open_add).pack(side="left", padx=(14, 0))

        calendar_card = ttk.Frame(main, style="Card.TFrame", padding=16)
        calendar_card.grid(row=1, column=0, sticky="nsew", padx=(0, 14))
        calendar_card.columnconfigure(0, weight=1)
        calendar_card.rowconfigure(1, weight=1)
        month_bar = ttk.Frame(calendar_card, style="Card.TFrame")
        month_bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        month_bar.columnconfigure(0, weight=1)
        self.month_label = ttk.Label(month_bar, text="", style="CardTitle.TLabel")
        self.month_label.grid(row=0, column=0, sticky="w")
        self.month_hint = ttk.Label(month_bar, text="A gentle overview of what's ahead.", style="MutedCard.TLabel")
        self.month_hint.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.filter_box = ttk.Combobox(month_bar, values=("All dates", "Birthdays", "Events"), state="readonly", width=14)
        self.filter_box.set(self.filter_value)
        self.filter_box.grid(row=0, column=1, rowspan=2, sticky="e")
        self.filter_box.bind("<<ComboboxSelected>>", lambda _event: self.set_filter(self.filter_box.get()))

        self.calendar_grid = ttk.Frame(calendar_card, style="Card.TFrame")
        self.calendar_grid.grid(row=1, column=0, sticky="nsew")
        for index in range(7):
            self.calendar_grid.columnconfigure(index, weight=1)
        for index in range(7):
            self.calendar_grid.rowconfigure(index, weight=1)

        side = ttk.Frame(main)
        side.grid(row=1, column=1, sticky="nsew")
        side.rowconfigure(1, weight=1)
        side.columnconfigure(0, weight=1)
        self.selected_panel = ttk.Frame(side, style="Card.TFrame", padding=18)
        self.selected_panel.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self.upcoming_panel = ttk.Frame(side, style="Card.TFrame", padding=18)
        self.upcoming_panel.grid(row=1, column=0, sticky="nsew")
        self.upcoming_panel.columnconfigure(0, weight=1)

        footer = ttk.Frame(main, style="Card.TFrame", padding=12)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, text="🔒  Your dates stay on this computer. Export a backup whenever you like.", style="MutedCard.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="Import", style="Quiet.TButton", command=self.import_events).grid(row=0, column=1, padx=3)
        ttk.Button(footer, text="Export", style="Quiet.TButton", command=self.export_events).grid(row=0, column=2, padx=3)

    def make_brand(self, parent: ttk.Frame) -> None:
        brand = ttk.Frame(parent)
        brand.pack(anchor="w", padx=10)
        mark = tk.Label(brand, text="▦", font=("Arial", 18, "bold"), fg="white", bg="#b8325c", width=2, height=1)
        mark.pack(side="left", padx=(0, 9))
        words = ttk.Frame(brand)
        words.pack(side="left")
        ttk.Label(words, text="morrow", font=("Arial", 18, "bold"), background="#f8f4ed", foreground="#292a3a").pack(anchor="w")
        ttk.Label(words, text="dates worth keeping", font=("Arial", 8), background="#f8f4ed", foreground="#747381").pack(anchor="w")

    def set_filter(self, value: str) -> None:
        self.filter_value = value
        self.filter_box.set(value)
        self.refresh()

    def filtered_events(self) -> list[dict]:
        if self.filter_value == "Birthdays":
            return [event for event in self.events if event["type"] == "birthday"]
        if self.filter_value == "Events":
            return [event for event in self.events if event["type"] == "event"]
        return list(self.events)

    def events_for_date(self, target: date) -> list[dict]:
        return [
            event for event in self.filtered_events()
            if occurrence_key(event, target.year) == target.isoformat()
        ]

    def refresh(self) -> None:
        self.month_label.configure(text=self.month_date.strftime("%B %Y"))
        self.render_calendar()
        self.render_selected_day()
        self.render_upcoming()

    def render_calendar(self) -> None:
        if not self.calendar_grid:
            return
        for child in self.calendar_grid.winfo_children():
            child.destroy()
        for index, name in enumerate(WEEKDAYS):
            ttk.Label(self.calendar_grid, text=name.upper(), anchor="center", font=("Arial", 8, "bold"), background="#fffdf9", foreground="#747381").grid(row=0, column=index, sticky="ew", pady=(0, 7))

        month_calendar = calendar.Calendar(firstweekday=0).monthdatescalendar(self.month_date.year, self.month_date.month)
        while len(month_calendar) < 6:
            last = month_calendar[-1][-1]
            month_calendar.append([last + timedelta(days=index + 1) for index in range(7)])

        for row, week in enumerate(month_calendar, start=1):
            self.calendar_grid.rowconfigure(row, weight=1)
            for column, cell_date in enumerate(week):
                outside = cell_date.month != self.month_date.month
                selected = cell_date == self.selected_date
                today = cell_date == date.today()
                cell = tk.Frame(self.calendar_grid, bg="#e1efeb" if selected else "#fffdf9", highlightthickness=1, highlightbackground="#e9e4dc")
                cell.grid(row=row, column=column, sticky="nsew")
                day_style = "Today.TButton" if today else "Day.TButton"
                ttk.Button(cell, text=str(cell_date.day), style=day_style, command=lambda value=cell_date: self.select_date(value)).pack(anchor="w", padx=5, pady=(4, 3))
                if outside:
                    cell.configure(bg="#fbf8f3")
                for event in self.events_for_date(cell_date)[:2]:
                    color, tint = COLORS[event["color"]]
                    chip = tk.Label(cell, text=f"● {event['title']}", anchor="w", bg=tint, fg=color, font=("Arial", 8, "bold"))
                    chip.pack(fill="x", padx=4, pady=1)
                remaining = len(self.events_for_date(cell_date)) - 2
                if remaining > 0:
                    tk.Label(cell, text=f"+{remaining} more", anchor="w", bg=cell.cget("bg"), fg="#747381", font=("Arial", 8)).pack(fill="x", padx=5, pady=(1, 0))

    def select_date(self, value: date) -> None:
        self.selected_date = value
        if value.month != self.month_date.month:
            self.month_date = value.replace(day=1)
        self.refresh()

    def go_today(self) -> None:
        self.selected_date = date.today()
        self.month_date = date.today().replace(day=1)
        self.refresh()

    def change_month(self, amount: int) -> None:
        month_index = self.month_date.month - 1 + amount
        year = self.month_date.year + month_index // 12
        month = month_index % 12 + 1
        self.month_date = date(year, month, 1)
        self.refresh()

    def render_selected_day(self) -> None:
        if not self.selected_panel:
            return
        for child in self.selected_panel.winfo_children():
            child.destroy()
        self.selected_panel.columnconfigure(0, weight=1)
        header = ttk.Frame(self.selected_panel, style="Card.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="TODAY" if self.selected_date == date.today() else "SELECTED DAY", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=f"{self.selected_date.strftime('%A, %B')} {self.selected_date.day}", style="CardTitle.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Button(header, text="+", style="Quiet.TButton", command=lambda: self.open_add(self.selected_date)).grid(row=0, column=1, rowspan=2, sticky="e")
        selected = self.events_for_date(self.selected_date)
        if not selected:
            ttk.Label(self.selected_panel, text="Nothing planned yet", style="CardBody.TLabel").grid(row=1, column=0, pady=(22, 4))
            ttk.Label(self.selected_panel, text="A blank day can be a lovely thing.", style="MutedCard.TLabel").grid(row=2, column=0)
            ttk.Button(self.selected_panel, text="Add something", style="Quiet.TButton", command=lambda: self.open_add(self.selected_date)).grid(row=3, column=0, pady=(14, 0))
        else:
            for row, event in enumerate(selected, start=1):
                self.event_row(self.selected_panel, event, row)

    def event_row(self, parent: ttk.Frame, event: dict, row: int) -> None:
        color, tint = COLORS[event["color"]]
        wrapper = tk.Frame(parent, bg="#fbf8f3", highlightthickness=1, highlightbackground="#e9e4dc")
        wrapper.grid(row=row, column=0, sticky="ew", pady=(8, 0))
        wrapper.columnconfigure(0, weight=1)
        text = f"{event['title']}\n{'All day' if event['all_day'] else event['time']} · {'Birthday · repeats yearly' if event['type'] == 'birthday' else 'Event'}"
        tk.Label(wrapper, text=text, justify="left", anchor="w", bg="#fbf8f3", fg="#292a3a", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="ew", padx=10, pady=9)
        tk.Label(wrapper, text="Edit", bg="#fbf8f3", fg=color, cursor="hand2", font=("Arial", 9, "bold")).grid(row=0, column=1, padx=6)
        wrapper.winfo_children()[-1].bind("<Button-1>", lambda _event: self.open_edit(event))

    def render_upcoming(self) -> None:
        if not self.upcoming_panel:
            return
        for child in self.upcoming_panel.winfo_children():
            child.destroy()
        self.upcoming_panel.columnconfigure(0, weight=1)
        ttk.Label(self.upcoming_panel, text="NEXT UP", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self.upcoming_panel, text="Keep in mind", style="CardTitle.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 10))
        upcoming: list[tuple[str, dict]] = []
        for event in self.events:
            date_key = next_occurrence(event)
            distance = (parse_key(date_key) - date.today()).days
            if 0 <= distance <= 60:
                upcoming.append((date_key, event))
        upcoming.sort(key=lambda item: item[0])
        if not upcoming:
            ttk.Label(self.upcoming_panel, text="Your next sixty days are wide open.", style="MutedCard.TLabel").grid(row=2, column=0, pady=20)
            return
        for row, (date_key, event) in enumerate(upcoming[:6], start=2):
            color, _ = COLORS[event["color"]]
            line = ttk.Frame(self.upcoming_panel, style="Card.TFrame")
            line.grid(row=row, column=0, sticky="ew", pady=4)
            line.columnconfigure(1, weight=1)
            badge = tk.Label(line, text=f"{parse_key(date_key).strftime('%b').upper()}\n{parse_key(date_key).day}", bg="#eee9e1", fg="#515163", font=("Arial", 9, "bold"), width=5, pady=4)
            badge.grid(row=0, column=0, rowspan=2, padx=(0, 9))
            ttk.Label(line, text=event["title"], style="CardBody.TLabel", font=("Arial", 10, "bold")).grid(row=0, column=1, sticky="w")
            detail_date = parse_key(date_key)
            detail = f"{detail_date.strftime('%a, %b')} {detail_date.day}"
            if event["time"]:
                detail += f" · {event['time']}"
            ttk.Label(line, text=detail, style="MutedCard.TLabel").grid(row=1, column=1, sticky="w")
            tk.Label(line, text="●", fg=color, bg="#fffdf9", font=("Arial", 13)).grid(row=0, column=2, rowspan=2, padx=4)
            line.bind("<Button-1>", lambda _event, value=parse_key(date_key): self.select_date(value))
            for child in line.winfo_children():
                child.bind("<Button-1>", lambda _event, value=parse_key(date_key): self.select_date(value))

    def open_add(self, value: date | None = None) -> None:
        target = value or self.selected_date
        self.open_event_dialog(
            {
                "id": "",
                "title": "",
                "date": key_for(target),
                "type": "event",
                "time": "",
                "color": "Coral",
                "reminder": "1 day before",
                "notes": "",
                "all_day": True,
            }
        )

    def open_edit(self, event: dict) -> None:
        self.open_event_dialog(dict(event))

    def open_event_dialog(self, event: dict) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Edit date" if event["id"] else "New date")
        dialog.geometry("470x650")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg="#fffdf9")
        dialog.columnconfigure(0, weight=1)

        ttk.Label(dialog, text="EDIT DATE" if event["id"] else "NEW DATE", style="Section.TLabel").grid(row=0, column=0, sticky="w", padx=24, pady=(22, 2))
        ttk.Label(dialog, text="What should we remember?", style="CardTitle.TLabel").grid(row=1, column=0, sticky="w", padx=24, pady=(0, 16))
        form = ttk.Frame(dialog, padding=(24, 0, 24, 0))
        form.grid(row=2, column=0, sticky="nsew")
        form.columnconfigure(0, weight=1)

        title_var = tk.StringVar(value=event["title"])
        date_var = tk.StringVar(value=event["date"])
        type_var = tk.StringVar(value="Birthday" if event["type"] == "birthday" else "Event")
        time_var = tk.StringVar(value=event["time"])
        color_var = tk.StringVar(value=event["color"])
        reminder_var = tk.StringVar(value=event["reminder"])
        all_day_var = tk.BooleanVar(value=event["all_day"])

        self.form_label(form, "Name", 0)
        ttk.Entry(form, textvariable=title_var).grid(row=1, column=0, sticky="ew", pady=(0, 11))
        row = 2
        ttk.Label(form, text="Date (YYYY-MM-DD)").grid(row=row, column=0, sticky="w")
        ttk.Entry(form, textvariable=date_var).grid(row=row + 1, column=0, sticky="ew", pady=(3, 11))
        ttk.Label(form, text="Kind").grid(row=row + 2, column=0, sticky="w")
        kind = ttk.Combobox(form, textvariable=type_var, values=("Event", "Birthday"), state="readonly")
        kind.grid(row=row + 3, column=0, sticky="ew", pady=(3, 0))
        hint = ttk.Label(form, text="Birthdays repeat every year.", style="MutedCard.TLabel")
        hint.grid(row=row + 4, column=0, sticky="w", pady=(3, 10))
        ttk.Checkbutton(form, text="All day", variable=all_day_var).grid(row=row + 5, column=0, sticky="w", pady=(0, 8))
        ttk.Label(form, text="Time (optional)").grid(row=row + 6, column=0, sticky="w")
        ttk.Entry(form, textvariable=time_var).grid(row=row + 7, column=0, sticky="ew", pady=(3, 10))
        ttk.Label(form, text="Color").grid(row=row + 8, column=0, sticky="w")
        ttk.Combobox(form, textvariable=color_var, values=tuple(COLORS), state="readonly").grid(row=row + 9, column=0, sticky="ew", pady=(3, 10))
        ttk.Label(form, text="Reminder").grid(row=row + 10, column=0, sticky="w")
        ttk.Combobox(form, textvariable=reminder_var, values=tuple(REMINDERS), state="readonly").grid(row=row + 11, column=0, sticky="ew", pady=(3, 10))
        ttk.Label(form, text="Notes (optional)").grid(row=row + 12, column=0, sticky="w")
        notes = tk.Text(form, height=3, font=("Arial", 10), relief="solid", borderwidth=1)
        notes.grid(row=row + 13, column=0, sticky="ew", pady=(3, 0))
        notes.insert("1.0", event["notes"])
        kind.bind("<<ComboboxSelected>>", lambda _event: hint.configure(text="Birthdays repeat every year." if type_var.get() == "Birthday" else "Events happen once on the chosen date."))

        actions = ttk.Frame(dialog)
        actions.grid(row=3, column=0, sticky="ew", padx=24, pady=20)
        actions.columnconfigure(0, weight=1)
        if event["id"]:
            ttk.Button(actions, text="Delete", style="Quiet.TButton", command=lambda: self.delete_event(event["id"], dialog)).grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text="Cancel", style="Quiet.TButton", command=dialog.destroy).grid(row=0, column=1, padx=4)

        def save() -> None:
            title = title_var.get().strip()
            if not title:
                messagebox.showerror("Name required", "Give this date a name.", parent=dialog)
                return
            try:
                parse_key(date_var.get().strip())
            except ValueError:
                messagebox.showerror("Date required", "Use a date in YYYY-MM-DD format.", parent=dialog)
                return
            updated = {
                **event,
                "title": title,
                "date": date_var.get().strip(),
                "type": "birthday" if type_var.get() == "Birthday" else "event",
                "time": "" if all_day_var.get() else time_var.get().strip(),
                "color": color_var.get(),
                "reminder": reminder_var.get(),
                "notes": notes.get("1.0", "end").strip(),
                "all_day": all_day_var.get(),
            }
            if event["id"]:
                self.events = [updated if item["id"] == event["id"] else item for item in self.events]
            else:
                updated["id"] = new_id()
                self.events.append(updated)
            self.save_events()
            self.selected_date = parse_key(updated["date"])
            self.month_date = self.selected_date.replace(day=1)
            dialog.destroy()
            self.refresh()

        ttk.Button(actions, text="Save date", style="Primary.TButton", command=save).grid(row=0, column=2, padx=(4, 0))

    @staticmethod
    def form_label(parent: ttk.Frame, text: str, row: int) -> None:
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w")

    def delete_event(self, event_id: str, dialog: tk.Toplevel | None = None) -> None:
        event = next((item for item in self.events if item["id"] == event_id), None)
        if not event or not messagebox.askyesno("Delete date", f"Remove “{event['title']}” from your calendar?"):
            return
        self.events = [item for item in self.events if item["id"] != event_id]
        self.save_events()
        if dialog:
            dialog.destroy()
        self.refresh()

    def open_settings(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Morrow settings")
        dialog.geometry("430x300")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg="#fffdf9")
        ttk.Label(dialog, text="PREFERENCES", style="Section.TLabel").pack(anchor="w", padx=24, pady=(24, 2))
        ttk.Label(dialog, text="Make Morrow yours.", style="CardTitle.TLabel").pack(anchor="w", padx=24, pady=(0, 18))
        enabled = tk.BooleanVar(value=self.notifications_enabled)
        box = ttk.Frame(dialog, style="Card.TFrame", padding=15)
        box.pack(fill="x", padx=24)
        ttk.Checkbutton(box, text="Browser-style reminders while this app is open", variable=enabled).pack(anchor="w")
        ttk.Label(box, text="Reminders are shown as desktop popups while this Python app is running.", style="MutedCard.TLabel", wraplength=340).pack(anchor="w", pady=(8, 0))
        ttk.Button(dialog, text="Done", style="Primary.TButton", command=lambda: self.save_settings(enabled.get(), dialog)).pack(fill="x", padx=24, pady=22)

    def save_settings(self, enabled: bool, dialog: tk.Toplevel) -> None:
        self.notifications_enabled = enabled
        dialog.destroy()
        self.check_reminders()

    def check_reminders(self) -> None:
        if self.notifications_enabled:
            now = date.today()
            for event in self.events:
                if event["reminder"] == "No reminder":
                    continue
                occurrence = next_occurrence(event, now)
                reminder_day = add_days(occurrence, -REMINDERS[event["reminder"]])
                key = f"{event['id']}:{occurrence}:{event['reminder']}"
                if reminder_day == now.isoformat() and key not in self.notified:
                    self.notified.add(key)
                    messagebox.showinfo("Morrow reminder", f"{event['title']}\n{event['reminder']}", parent=self)
        self.after(60_000, self.check_reminders)

    def export_events(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export calendar",
            defaultextension=".json",
            filetypes=(("JSON calendar", "*.json"), ("All files", "*.*")),
            initialfile="morrow-calendar.json",
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps({"app": "Morrow Python", "version": 1, "events": self.events}, indent=2), encoding="utf-8")
            messagebox.showinfo("Export complete", "Your calendar backup is ready.")
        except OSError as error:
            messagebox.showerror("Export failed", str(error))

    def import_events(self) -> None:
        path = filedialog.askopenfilename(title="Import calendar", filetypes=(("JSON calendar", "*.json"), ("All files", "*.*")))
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            raw_events = payload.get("events", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
            imported = [event for item in raw_events if (event := clean_event(item))]
            if not imported:
                raise ValueError("No valid dates were found.")
            self.events = imported
            self.save_events()
            self.refresh()
            messagebox.showinfo("Import complete", f"{len(imported)} dates imported.")
        except (OSError, json.JSONDecodeError, ValueError) as error:
            messagebox.showerror("Import failed", str(error))


if __name__ == "__main__":
    MorrowCalendar().mainloop()