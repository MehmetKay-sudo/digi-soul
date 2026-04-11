"""
cortisol_monitor.py  —  standalone cortisol stress monitor

Simulates cortisol dynamics and visualises the level in a Tkinter window.
Completely independent from main.py — no other digi-soul imports required.

Run:
    python cortisol_monitor.py

Simulation behaviour:
  • Cortisol drifts around a baseline (~15 units)
  • 6 % chance per tick of a stress spike (+20-45 units)
  • Exponential decay back toward baseline (half-life ≈ 12 s)
  • UI refreshes every 200 ms

Thresholds:
  LOW    0-30    green   — normal / calm
  MEDIUM 30-60   yellow  — elevated / mild stress
  HIGH   60+     red     — stress / alert state
"""

import asyncio
import math
import queue
import random
import threading
import tkinter as tk

# ── Simulation parameters ─────────────────────────────────────────────────────
BASELINE      = 15.0    # resting cortisol (arbitrary units)
HALF_LIFE     = 12.0    # seconds — exponential decay toward baseline
TICK          = 0.4     # seconds between simulation steps
SPIKE_PROB    = 0.06    # probability of a stress spike per tick
SPIKE_MIN     = 20.0
SPIKE_MAX     = 45.0

# ── Thresholds ─────────────────────────────────────────────────────────────────
MEDIUM_THRESHOLD = 30.0
HIGH_THRESHOLD   = 60.0

# ── Colours ────────────────────────────────────────────────────────────────────
BG           = "#0d0d1a"
NORMAL_COLOR = "#27ae60"   # green
MEDIUM_COLOR = "#f39c12"   # amber
HIGH_COLOR   = "#e74c3c"   # red
TEXT_FG      = "#ecf0f1"
DIM_FG       = "#555577"
FONT_MONO    = ("Courier", 10)
FONT_LARGE   = ("Courier", 18, "bold")
FONT_TITLE   = ("Courier", 13, "bold")

GAUGE_W = 80
GAUGE_H = 300


# ── Simulation coroutine ──────────────────────────────────────────────────────

async def run_simulation(data_queue: queue.Queue):
    level = BASELINE
    decay = math.log(2) / HALF_LIFE   # λ for exponential decay

    while True:
        await asyncio.sleep(TICK)

        # Exponential decay toward baseline
        level = BASELINE + (level - BASELINE) * math.exp(-decay * TICK)

        # Natural noise
        level += random.gauss(0, 0.8)

        # Stress spike
        if random.random() < SPIKE_PROB:
            spike = random.uniform(SPIKE_MIN, SPIKE_MAX)
            level += spike

        level = max(0.0, min(100.0, level))
        data_queue.put_nowait(round(level, 2))


def start_simulation(data_queue: queue.Queue):
    asyncio.run(run_simulation(data_queue))


# ── Tkinter UI ────────────────────────────────────────────────────────────────

class CortisolMonitor:
    HISTORY_LEN = 60   # data points kept for the sparkline

    def __init__(self, root: tk.Tk, data_queue: queue.Queue):
        self.root = root
        self.data_queue = data_queue
        self.history: list[float] = [BASELINE] * self.HISTORY_LEN
        self.current = BASELINE
        self._alert_visible = False

        root.title("Cortisol Monitor")
        root.configure(bg=BG)
        root.resizable(False, False)

        self._build_ui()
        self._poll()

    # ── Layout ────────────────────────────────────────────────────────

    def _build_ui(self):
        # Title
        tk.Label(self.root, text="CORTISOL MONITOR", bg=BG, fg=TEXT_FG,
                 font=FONT_TITLE).pack(pady=(16, 4))
        tk.Label(self.root, text="stress hormone level (AU)", bg=BG,
                 fg=DIM_FG, font=FONT_MONO).pack(pady=(0, 12))

        # Main row: gauge  +  readout / history
        row = tk.Frame(self.root, bg=BG)
        row.pack(padx=20, pady=4)

        # ── Vertical bar gauge ──────────────────────────────────────
        gauge_frame = tk.Frame(row, bg=BG)
        gauge_frame.pack(side=tk.LEFT, padx=(0, 20))

        # Labels on the right of the gauge
        labels_frame = tk.Frame(gauge_frame, bg=BG)
        labels_frame.pack(side=tk.LEFT)
        for lvl, label in [(HIGH_THRESHOLD, "HIGH"), (MEDIUM_THRESHOLD, "MED"), (0, "LOW")]:
            pct = 1 - lvl / 100
            y_px = int(pct * GAUGE_H)
            tk.Label(labels_frame, text=f"{lvl:>3.0f} {label}",
                     bg=BG, fg=DIM_FG, font=("Courier", 8)).place(
                x=0, y=y_px - 6)
        labels_frame.configure(width=60, height=GAUGE_H)

        self._gauge_canvas = tk.Canvas(gauge_frame, width=GAUGE_W,
                                       height=GAUGE_H, bg="#111122",
                                       highlightthickness=1,
                                       highlightbackground="#333355")
        self._gauge_canvas.pack(side=tk.LEFT)

        # Threshold lines on gauge
        for thresh, color in [(HIGH_THRESHOLD, HIGH_COLOR),
                              (MEDIUM_THRESHOLD, MEDIUM_COLOR)]:
            y = self._level_to_y(thresh)
            self._gauge_canvas.create_line(0, y, GAUGE_W, y,
                                           fill=color, dash=(4, 3), width=1)

        # Fill bar
        self._bar = self._gauge_canvas.create_rectangle(
            4, GAUGE_H - 4, GAUGE_W - 4, GAUGE_H - 4,
            fill=NORMAL_COLOR, outline="")

        # ── Right column: value + history sparkline ──────────────
        right = tk.Frame(row, bg=BG)
        right.pack(side=tk.LEFT, anchor=tk.N)

        tk.Label(right, text="LEVEL", bg=BG, fg=DIM_FG,
                 font=FONT_MONO).pack()
        self._level_label = tk.Label(right, text="0.00", bg=BG,
                                     fg=NORMAL_COLOR, font=FONT_LARGE, width=8)
        self._level_label.pack(pady=(2, 10))

        tk.Label(right, text="STATUS", bg=BG, fg=DIM_FG,
                 font=FONT_MONO).pack()
        self._status_label = tk.Label(right, text="CALM", bg=BG,
                                      fg=NORMAL_COLOR, font=("Courier", 12, "bold"),
                                      width=10)
        self._status_label.pack(pady=(2, 12))

        # Sparkline
        tk.Label(right, text="HISTORY (60 ticks)", bg=BG,
                 fg=DIM_FG, font=("Courier", 8)).pack()
        self._spark = tk.Canvas(right, width=220, height=70,
                                bg="#111122", highlightthickness=1,
                                highlightbackground="#333355")
        self._spark.pack(pady=(2, 0))

        # ── Alert banner ──────────────────────────────────────────────
        self._alert_frame = tk.Frame(self.root, bg=HIGH_COLOR)
        self._alert_text = tk.Label(self._alert_frame,
                                    text="!  STRESS ALERT  —  HIGH CORTISOL  !",
                                    bg=HIGH_COLOR, fg="white",
                                    font=("Courier", 12, "bold"), pady=6)
        self._alert_text.pack(fill=tk.X)
        # Don't pack yet — shown/hidden dynamically

        # ── Stats row ─────────────────────────────────────────────────
        self._stats_label = tk.Label(self.root, text="", bg=BG,
                                     fg=DIM_FG, font=("Courier", 9))
        self._stats_label.pack(pady=(8, 12))

    # ── Poll + update ─────────────────────────────────────────────────

    def _poll(self):
        updated = False
        try:
            while True:
                self.current = self.data_queue.get_nowait()
                self.history.append(self.current)
                if len(self.history) > self.HISTORY_LEN:
                    self.history.pop(0)
                updated = True
        except queue.Empty:
            pass

        if updated:
            self._redraw()

        self.root.after(200, self._poll)

    def _redraw(self):
        level = self.current
        color = self._level_color(level)

        # Gauge bar
        y_top = self._level_to_y(level)
        self._gauge_canvas.coords(self._bar, 4, y_top, GAUGE_W - 4, GAUGE_H - 4)
        self._gauge_canvas.itemconfig(self._bar, fill=color)

        # Level label
        self._level_label.config(text=f"{level:>5.1f}", fg=color)

        # Status text
        status, status_color = self._status(level)
        self._status_label.config(text=status, fg=status_color)

        # Alert banner
        if level >= HIGH_THRESHOLD and not self._alert_visible:
            self._alert_frame.pack(fill=tk.X, padx=0, pady=0, before=self._stats_label)
            self._alert_visible = True
        elif level < HIGH_THRESHOLD and self._alert_visible:
            self._alert_frame.pack_forget()
            self._alert_visible = False

        # Sparkline
        self._draw_sparkline(color)

        # Stats
        mn = min(self.history)
        mx = max(self.history)
        avg = sum(self.history) / len(self.history)
        self._stats_label.config(
            text=f"min={mn:.1f}  avg={avg:.1f}  max={mx:.1f}  baseline={BASELINE}"
        )

    def _draw_sparkline(self, line_color: str):
        self._spark.delete("all")
        w = int(self._spark["width"])
        h = int(self._spark["height"])
        data = self.history
        n = len(data)
        if n < 2:
            return

        x_step = w / (n - 1)
        points = []
        for i, val in enumerate(data):
            x = i * x_step
            y = h - (val / 100) * h
            points.append((x, y))

        # Threshold lines
        for thresh, color in [(HIGH_THRESHOLD, HIGH_COLOR),
                              (MEDIUM_THRESHOLD, MEDIUM_COLOR)]:
            y = h - (thresh / 100) * h
            self._spark.create_line(0, y, w, y, fill=color,
                                    dash=(3, 3), width=1)

        # Sparkline
        flat = [coord for p in points for coord in p]
        self._spark.create_line(*flat, fill=line_color, width=2, smooth=True)

    # ── Helpers ───────────────────────────────────────────────────────

    def _level_to_y(self, level: float) -> float:
        return GAUGE_H - (level / 100) * GAUGE_H

    @staticmethod
    def _level_color(level: float) -> str:
        if level >= HIGH_THRESHOLD:
            return HIGH_COLOR
        if level >= MEDIUM_THRESHOLD:
            return MEDIUM_COLOR
        return NORMAL_COLOR

    @staticmethod
    def _status(level: float) -> tuple[str, str]:
        if level >= HIGH_THRESHOLD:
            return "STRESS", HIGH_COLOR
        if level >= MEDIUM_THRESHOLD:
            return "ELEVATED", MEDIUM_COLOR
        return "CALM", NORMAL_COLOR


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    data_queue: queue.Queue = queue.Queue()

    sim_thread = threading.Thread(
        target=start_simulation,
        args=(data_queue,),
        daemon=True,
    )
    sim_thread.start()

    root = tk.Tk()
    CortisolMonitor(root, data_queue)
    root.mainloop()


if __name__ == "__main__":
    main()
