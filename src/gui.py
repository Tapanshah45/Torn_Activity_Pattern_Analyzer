"""
Torn City Sleep Pattern Analyser — GUI
Built with CustomTkinter for a clean, modern Windows desktop experience.

Layout
──────
┌──────────────────────────────────────────────────────────────┐
│  Header bar  (title + theme toggle)                          │
├────────────────────┬─────────────────────────────────────────┤
│  LEFT PANEL        │  RIGHT PANEL                            │
│  • File picker     │  • Player detail view                   │
│  • Min-sleep spin  │    – sleep cycles table                 │
│  • Analyse button  │    – AFK blocks table                   │
│  • Progress bar    │    – summary cards                      │
│  • Results table   │                                         │
├────────────────────┴─────────────────────────────────────────┤
│  Status bar                                                  │
└──────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import List, Optional

import customtkinter as ctk

from src.engine import CampaignAnalyzerEngine
from src.models import PlayerProfile
from src.streamer import get_campaign_metadata

# ── Appearance ────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_ACCENT   = "#3B8ED0"
_BG_CARD  = "#1e1e2e"
_BG_ROW_A = "#2a2a3e"
_BG_ROW_B = "#252535"
_FG_MAIN  = "#cdd6f4"
_FG_DIM   = "#6c7086"
_GREEN    = "#a6e3a1"
_YELLOW   = "#f9e2af"
_RED      = "#f38ba8"
_MAUVE    = "#cba6f7"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tz_color(tz: str) -> str:
    """Color-code the inferred timezone string."""
    if tz == "Unknown":
        return _FG_DIM
    try:
        offset = int(tz.replace("UTC", "").replace("+", ""))
        if -3 <= offset <= 3:
            return _GREEN
        if -7 <= offset <= 7:
            return _YELLOW
        return _RED
    except ValueError:
        return _FG_MAIN


# ── Scrollable table widget ───────────────────────────────────────────────────

class ScrollableTable(ctk.CTkScrollableFrame):
    """
    Generic scrollable table with configurable columns.
    Each row is a list of strings; clicking a row fires on_select(row_index).
    """

    COL_PAD = 8

    def __init__(self, master, columns: list[tuple[str, int]], on_select=None, **kwargs):
        super().__init__(master, **kwargs)
        self.columns = columns        # [(header_text, width), ...]
        self.on_select = on_select
        self._rows: list[list[ctk.CTkLabel]] = []
        self._selected: Optional[int] = None
        self._build_header()

    def _build_header(self):
        for col, (text, width) in enumerate(self.columns):
            lbl = ctk.CTkLabel(
                self, text=text, width=width, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=_ACCENT,
            )
            lbl.grid(row=0, column=col, padx=(self.COL_PAD, 0), pady=(4, 6), sticky="w")
        # divider
        div = ctk.CTkFrame(self, height=1, fg_color=_ACCENT)
        div.grid(row=1, column=0, columnspan=len(self.columns), sticky="ew", padx=4)

    def clear(self):
        for row_labels in self._rows:
            for lbl in row_labels:
                lbl.destroy()
        self._rows.clear()
        self._selected = None

    def add_row(self, values: list[str], colors: list[Optional[str]] = None):
        row_idx = len(self._rows)
        grid_row = row_idx + 2          # offset past header + divider
        bg = _BG_ROW_A if row_idx % 2 == 0 else _BG_ROW_B
        labels = []
        for col, (val, (_, width)) in enumerate(zip(values, self.columns)):
            fg = (colors[col] if colors and col < len(colors) else None) or _FG_MAIN
            lbl = ctk.CTkLabel(
                self, text=val, width=width, anchor="w",
                font=ctk.CTkFont(size=12),
                text_color=fg,
                fg_color=bg,
                corner_radius=0,
            )
            lbl.grid(row=grid_row, column=col, padx=(self.COL_PAD, 0), pady=1, sticky="ew")
            lbl.bind("<Button-1>", lambda e, r=row_idx: self._click(r))
            labels.append(lbl)
        self._rows.append(labels)

    def _click(self, row_idx: int):
        # De-highlight previous
        if self._selected is not None and self._selected < len(self._rows):
            bg = _BG_ROW_A if self._selected % 2 == 0 else _BG_ROW_B
            for lbl in self._rows[self._selected]:
                lbl.configure(fg_color=bg)
        # Highlight new
        for lbl in self._rows[row_idx]:
            lbl.configure(fg_color="#313244")
        self._selected = row_idx
        if self.on_select:
            self.on_select(row_idx)

    def select_row(self, row_idx: int):
        self._click(row_idx)


# ── Main application window ───────────────────────────────────────────────────

class TornAnalyzerApp(ctk.CTk):

    # Column definitions for main results table
    _MAIN_COLS = [
        ("ID",          70),
        ("Name",       140),
        ("Sleep Window", 120),
        ("Avg Dur",      70),
        ("TZ",           70),
        ("Cycles",       55),
        ("AFK",          45),
    ]

    # Column definitions for detail tables
    _SLEEP_COLS = [
        ("Date",        100),
        ("Start UTC",    80),
        ("End UTC",      80),
        ("Duration",     70),
        ("Context",     160),
    ]

    def __init__(self):
        super().__init__()
        self.title("Torn City — Sleep Pattern Analyser")
        self.geometry("1280x780")
        self.minsize(900, 600)
        self.configure(fg_color="#11111b")

        self._profiles: List[PlayerProfile] = []
        self._file_path: Optional[str] = None
        self._analysing = False

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_left_panel()
        self._build_right_panel()
        self._build_status_bar()

    def _build_header(self):
        hdr = ctk.CTkFrame(self, height=52, fg_color=_BG_CARD, corner_radius=0)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr, text="⚔  Torn City Sleep Pattern Analyser",
            font=ctk.CTkFont(size=17, weight="bold"), text_color=_ACCENT,
        ).grid(row=0, column=0, padx=18, pady=14, sticky="w")

        self._theme_btn = ctk.CTkButton(
            hdr, text="☀  Light", width=90, height=30,
            fg_color="transparent", border_width=1, border_color=_ACCENT,
            text_color=_ACCENT, command=self._toggle_theme,
        )
        self._theme_btn.grid(row=0, column=2, padx=14, pady=10, sticky="e")

    def _build_left_panel(self):
        panel = ctk.CTkFrame(self, width=340, fg_color=_BG_CARD, corner_radius=0)
        panel.grid(row=1, column=0, sticky="nsew", padx=(0, 1))
        panel.grid_rowconfigure(7, weight=1)
        panel.grid_propagate(False)

        # ── File selection ──────────────────────────────────────────
        ctk.CTkLabel(panel, text="Campaign File", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=_FG_DIM).grid(row=0, column=0, padx=16, pady=(18, 4), sticky="w")

        file_row = ctk.CTkFrame(panel, fg_color="transparent")
        file_row.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        file_row.grid_columnconfigure(0, weight=1)

        self._file_label = ctk.CTkLabel(
            file_row, text="No file selected", anchor="w",
            font=ctk.CTkFont(size=11), text_color=_FG_DIM,
            wraplength=220,
        )
        self._file_label.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            file_row, text="Browse", width=74, height=28,
            command=self._browse_file,
        ).grid(row=0, column=1, padx=(8, 0))

        # ── Settings ────────────────────────────────────────────────
        ctk.CTkLabel(panel, text="Min Inactivity Gap (hours)",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=_FG_DIM).grid(row=2, column=0, padx=16, pady=(8, 4), sticky="w")

        spin_frame = ctk.CTkFrame(panel, fg_color="transparent")
        spin_frame.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="w")

        self._min_sleep_var = tk.DoubleVar(value=4.0)
        self._min_sleep_entry = ctk.CTkEntry(
            spin_frame, width=70, textvariable=self._min_sleep_var,
            font=ctk.CTkFont(size=13),
        )
        self._min_sleep_entry.grid(row=0, column=0)

        ctk.CTkButton(spin_frame, text="▲", width=26, height=20,
                      command=lambda: self._nudge_sleep(0.5)).grid(row=0, column=1, padx=(4, 0))
        ctk.CTkButton(spin_frame, text="▼", width=26, height=20,
                      command=lambda: self._nudge_sleep(-0.5)).grid(row=0, column=2, padx=(2, 0))

        # ── Analyse button ──────────────────────────────────────────
        self._analyse_btn = ctk.CTkButton(
            panel, text="▶  Analyse", height=38,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_analysis,
        )
        self._analyse_btn.grid(row=4, column=0, padx=12, pady=(4, 6), sticky="ew")

        # ── Export button ───────────────────────────────────────────
        self._export_btn = ctk.CTkButton(
            panel, text="⬇  Export JSON", height=32,
            fg_color="transparent", border_width=1, border_color=_ACCENT,
            text_color=_ACCENT,
            command=self._export_json,
            state="disabled",
        )
        self._export_btn.grid(row=5, column=0, padx=12, pady=(0, 10), sticky="ew")

        # ── Progress bar ────────────────────────────────────────────
        self._progress = ctk.CTkProgressBar(panel, height=6)
        self._progress.set(0)
        self._progress.grid(row=6, column=0, padx=12, pady=(0, 10), sticky="ew")

        # ── Results table ───────────────────────────────────────────
        ctk.CTkLabel(panel, text="Results", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=_FG_DIM).grid(row=7, column=0, padx=16, pady=(0, 4), sticky="nw")

        self._results_table = ScrollableTable(
            panel,
            columns=self._MAIN_COLS,
            on_select=self._on_player_select,
            fg_color="transparent",
            scrollbar_button_color=_ACCENT,
        )
        self._results_table.grid(row=8, column=0, padx=4, pady=(0, 4), sticky="nsew")
        panel.grid_rowconfigure(8, weight=1)

    def _build_right_panel(self):
        self._right = ctk.CTkFrame(self, fg_color="#13131f", corner_radius=0)
        self._right.grid(row=1, column=1, sticky="nsew")
        self._right.grid_columnconfigure(0, weight=1)
        self._right.grid_rowconfigure(1, weight=1)
        self._right.grid_rowconfigure(3, weight=1)

        # placeholder
        self._placeholder = ctk.CTkLabel(
            self._right,
            text="Select a player from the results list\nto view their detailed sleep analysis.",
            font=ctk.CTkFont(size=14), text_color=_FG_DIM,
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        # summary cards row (hidden until a player is selected)
        self._cards_frame = ctk.CTkFrame(self._right, fg_color="transparent")
        self._cards: dict[str, ctk.CTkLabel] = {}
        for i, (key, icon) in enumerate([
            ("sleep_window", "🌙  Sleep Window"),
            ("avg_dur",      "⏱  Avg Duration"),
            ("timezone",     "🌍  Timezone"),
            ("snapshots",    "📷  Snapshots"),
        ]):
            card = ctk.CTkFrame(self._cards_frame, fg_color=_BG_CARD, corner_radius=10)
            card.grid(row=0, column=i, padx=8, pady=8, sticky="ew")
            self._cards_frame.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=11),
                         text_color=_FG_DIM).pack(padx=14, pady=(10, 2))
            val_lbl = ctk.CTkLabel(card, text="—",
                                   font=ctk.CTkFont(size=14, weight="bold"),
                                   text_color=_FG_MAIN)
            val_lbl.pack(padx=14, pady=(0, 10))
            self._cards[key] = val_lbl

        # detail player header
        self._detail_name = ctk.CTkLabel(
            self._right, text="", font=ctk.CTkFont(size=16, weight="bold"),
            text_color=_ACCENT,
        )

        # sleep cycles table
        self._sleep_section_lbl = ctk.CTkLabel(
            self._right, text="Primary Sleep Cycles",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=_FG_DIM,
        )
        self._sleep_table = ScrollableTable(
            self._right,
            columns=self._SLEEP_COLS,
            fg_color="transparent",
        )

        # AFK table
        self._afk_section_lbl = ctk.CTkLabel(
            self._right, text="Work / AFK Blocks",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=_FG_DIM,
        )
        self._afk_table = ScrollableTable(
            self._right,
            columns=self._SLEEP_COLS,
            fg_color="transparent",
        )

        # peak hours bar
        self._peak_lbl = ctk.CTkLabel(
            self._right, text="Peak Active Hours (UTC)",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=_FG_DIM,
        )
        self._peak_canvas = tk.Canvas(
            self._right, height=44, bg="#13131f", highlightthickness=0,
        )

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self, height=26, fg_color=_BG_CARD, corner_radius=0)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        self._status_var = tk.StringVar(value="Ready. Open a campaign JSON file to begin.")
        ctk.CTkLabel(bar, textvariable=self._status_var,
                     font=ctk.CTkFont(size=11), text_color=_FG_DIM,
                     anchor="w").grid(row=0, column=0, padx=12, sticky="w")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        mode = ctk.get_appearance_mode()
        if mode == "Dark":
            ctk.set_appearance_mode("light")
            self._theme_btn.configure(text="🌙  Dark")
        else:
            ctk.set_appearance_mode("dark")
            self._theme_btn.configure(text="☀  Light")

    def _nudge_sleep(self, delta: float):
        try:
            val = float(self._min_sleep_var.get())
            val = max(1.0, round(val + delta, 1))
            self._min_sleep_var.set(val)
        except (ValueError, tk.TclError):
            self._min_sleep_var.set(4.0)

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select Campaign JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self._file_path = path
            short = path if len(path) <= 48 else "…" + path[-45:]
            self._file_label.configure(text=short, text_color=_FG_MAIN)
            self._set_status(f"Loaded: {path}")

    def _start_analysis(self):
        if self._analysing:
            return
        if not self._file_path:
            messagebox.showwarning("No File", "Please select a campaign JSON file first.")
            return
        try:
            min_sleep = float(self._min_sleep_var.get())
        except (ValueError, tk.TclError):
            messagebox.showerror("Invalid Input", "Min inactivity gap must be a number.")
            return

        self._analysing = True
        self._analyse_btn.configure(state="disabled", text="Analysing…")
        self._export_btn.configure(state="disabled")
        self._progress.set(0)
        self._progress.start()          # indeterminate spin
        self._results_table.clear()
        self._profiles.clear()
        self._hide_detail()
        self._set_status("Analysing campaign data…")

        threading.Thread(
            target=self._run_analysis,
            args=(self._file_path, min_sleep),
            daemon=True,
        ).start()

    def _run_analysis(self, file_path: str, min_sleep: float):
        try:
            meta = get_campaign_metadata(file_path)
            faction = meta.get("faction_name", "Unknown")
            member_count = int(meta.get("member_count", 0))

            engine = CampaignAnalyzerEngine(file_path, min_sleep_gap=min_sleep)
            profiles: List[PlayerProfile] = []

            for i, profile in enumerate(engine.run()):
                profiles.append(profile)
                # Stream rows into table on main thread
                self.after(0, self._append_result_row, profile)
                progress = (i + 1) / max(member_count, 1)
                self.after(0, self._progress.set, min(progress, 1.0))

            self.after(0, self._analysis_done, profiles, faction)
        except Exception as exc:
            self.after(0, self._analysis_error, str(exc))

    def _analysis_done(self, profiles: List[PlayerProfile], faction: str):
        self._profiles = profiles
        self._analysing = False
        self._progress.stop()
        self._progress.set(1.0)
        self._analyse_btn.configure(state="normal", text="▶  Analyse")
        if profiles:
            self._export_btn.configure(state="normal")
        self._set_status(
            f"Done — {len(profiles)} member(s) analysed from faction '{faction}'."
        )

    def _analysis_error(self, msg: str):
        self._analysing = False
        self._progress.stop()
        self._progress.set(0)
        self._analyse_btn.configure(state="normal", text="▶  Analyse")
        self._set_status(f"Error: {msg}")
        messagebox.showerror("Analysis Failed", msg)

    def _append_result_row(self, p: PlayerProfile):
        self._results_table.add_row(
            [
                str(p.player_id),
                p.name,
                p.estimated_sleep_window_utc,
                f"{p.avg_sleep_duration_hours:.1f}h",
                p.inferred_timezone,
                str(len(p.primary_sleep_cycles)),
                str(len(p.secondary_afk_blocks)),
            ],
            colors=[
                None, _FG_MAIN, _YELLOW, None,
                _tz_color(p.inferred_timezone), _GREEN, None,
            ],
        )

    def _export_json(self):
        if not self._profiles:
            return
        path = filedialog.asksaveasfilename(
            title="Export JSON Report",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile="torn_analysis_report.json",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([p.model_dump() for p in self._profiles], f, indent=2, default=str)
            self._set_status(f"Exported {len(self._profiles)} profiles → {path}")
            messagebox.showinfo("Export Complete", f"Saved to:\n{path}")
        except OSError as e:
            messagebox.showerror("Export Failed", str(e))

    # ── Detail panel ──────────────────────────────────────────────────────────

    def _on_player_select(self, row_idx: int):
        if row_idx >= len(self._profiles):
            return
        self._show_detail(self._profiles[row_idx])

    def _hide_detail(self):
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self._cards_frame.grid_remove()
        self._detail_name.grid_remove()
        self._sleep_section_lbl.grid_remove()
        self._sleep_table.grid_remove()
        self._afk_section_lbl.grid_remove()
        self._afk_table.grid_remove()
        self._peak_lbl.grid_remove()
        self._peak_canvas.grid_remove()

    def _show_detail(self, p: PlayerProfile):
        self._placeholder.place_forget()

        # reconfigure grid
        self._right.grid_rowconfigure(0, weight=0)
        self._right.grid_rowconfigure(1, weight=0)
        self._right.grid_rowconfigure(2, weight=1)
        self._right.grid_rowconfigure(3, weight=0)
        self._right.grid_rowconfigure(4, weight=1)
        self._right.grid_rowconfigure(5, weight=0)
        self._right.grid_rowconfigure(6, weight=0)

        # player name
        self._detail_name.configure(
            text=f"{p.name}  ·  ID {p.player_id}"
        )
        self._detail_name.grid(row=0, column=0, padx=20, pady=(14, 6), sticky="w")

        # summary cards
        self._cards["sleep_window"].configure(
            text=p.estimated_sleep_window_utc or "—"
        )
        self._cards["avg_dur"].configure(
            text=f"{p.avg_sleep_duration_hours:.1f} h"
        )
        self._cards["timezone"].configure(
            text=p.inferred_timezone,
            text_color=_tz_color(p.inferred_timezone),
        )
        self._cards["snapshots"].configure(text=str(p.total_snapshots))
        self._cards_frame.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")

        # sleep cycles table
        self._sleep_section_lbl.configure(
            text=f"Primary Sleep Cycles  ({len(p.primary_sleep_cycles)})"
        )
        self._sleep_section_lbl.grid(row=2, column=0, padx=20, pady=(4, 2), sticky="nw")

        self._sleep_table.clear()
        for b in p.primary_sleep_cycles:
            date, start_t = b.start_utc.split(" ")
            _, end_t      = b.end_utc.split(" ")
            self._sleep_table.add_row(
                [date, start_t, end_t, f"{b.duration_hours:.1f}h", b.context],
                colors=[_FG_DIM, _YELLOW, _GREEN, None, _FG_DIM],
            )
        if not p.primary_sleep_cycles:
            self._sleep_table.add_row(["No sleep cycles detected", "", "", "", ""],
                                       colors=[_FG_DIM] * 5)
        self._sleep_table.grid(row=2, column=0, padx=8, pady=(28, 4), sticky="nsew")

        # AFK table
        self._afk_section_lbl.configure(
            text=f"Work / AFK Blocks  ({len(p.secondary_afk_blocks)})"
        )
        self._afk_section_lbl.grid(row=3, column=0, padx=20, pady=(8, 2), sticky="nw")

        self._afk_table.clear()
        for b in p.secondary_afk_blocks:
            date, start_t = b.start_utc.split(" ")
            _, end_t      = b.end_utc.split(" ")
            self._afk_table.add_row(
                [date, start_t, end_t, f"{b.duration_hours:.1f}h", b.context],
                colors=[_FG_DIM, _MAUVE, _MAUVE, None, _FG_DIM],
            )
        if not p.secondary_afk_blocks:
            self._afk_table.add_row(["No AFK blocks detected", "", "", "", ""],
                                     colors=[_FG_DIM] * 5)
        self._afk_table.grid(row=4, column=0, padx=8, pady=(28, 4), sticky="nsew")

        # peak hours bar chart
        self._peak_lbl.grid(row=5, column=0, padx=20, pady=(8, 2), sticky="w")
        self._peak_canvas.grid(row=6, column=0, padx=8, pady=(0, 14), sticky="ew")
        self._draw_peak_hours(p.peak_active_hours_utc)

        self._set_status(
            f"Showing: {p.name} · {p.inferred_timezone} · "
            f"{len(p.primary_sleep_cycles)} sleep cycle(s)"
        )

    def _draw_peak_hours(self, peak_hours: list[int]):
        self._peak_canvas.update_idletasks()
        w = self._peak_canvas.winfo_width() or 600
        h = 44
        self._peak_canvas.configure(width=w, height=h)
        self._peak_canvas.delete("all")

        cell_w = w / 24
        for hour in range(24):
            x0 = hour * cell_w + 2
            x1 = x0 + cell_w - 4
            is_peak = hour in peak_hours
            fill = _ACCENT if is_peak else "#2a2a3e"
            self._peak_canvas.create_rectangle(x0, 4, x1, 34, fill=fill, outline="")
            if is_peak:
                self._peak_canvas.create_text(
                    (x0 + x1) / 2, 39, text=str(hour),
                    fill=_FG_MAIN, font=("Consolas", 8),
                )

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self._status_var.set(msg)


def run_gui():
    app = TornAnalyzerApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
