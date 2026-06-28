import queue
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

# ── Organ positions (x, y) on 460×700 body canvas ────────────────────────────
ORGAN_CONFIG = {
    "brain":             {"pos": (230,  68), "color": "#9b59b6", "label": "BRAIN"},
    "heart":             {"pos": (192, 278), "color": "#e74c3c", "label": "HEART"},
    "lungs":             {"pos": (268, 258), "color": "#3498db", "label": "LUNGS"},
    "stomach":           {"pos": (208, 355), "color": "#e67e22", "label": "STOMACH"},
    "liver":             {"pos": (278, 340), "color": "#c0392b", "label": "LIVER"},
    "kidney":            {"pos": (278, 398), "color": "#27ae60", "label": "KIDNEY"},
    "pancreas":          {"pos": (195, 372), "color": "#f39c12", "label": "PANCREAS"},
    "adrenal_gland":     {"pos": (275, 375), "color": "#e74c3c", "label": "ADRENAL"},
    "immune_system":     {"pos": (230, 148), "color": "#1abc9c", "label": "IMMUNE"},
    "space_physiology":  {"pos": (230, 500), "color": "#5dade2", "label": "SPACES"},
    "muscular_system":   {"pos": (148, 330), "color": "#d35400", "label": "MUSCLE"},
    "vascular_system":   {"pos": (162, 300), "color": "#8e44ad", "label": "VASCULAR"},
}

CANVAS_W, CANVAS_H = 460, 700
PANEL_W = 360

# General palette
BG       = "#0d0d1a"
FG       = "#00ff88"
NS_FG    = "#00cfff"
ENDO_FG  = "#f1c40f"
HW_FG    = "#e67e22"
ALERT_FG = "#ff4444"
FONT     = ("Courier", 9)
FONT_B   = ("Courier", 9, "bold")
FONT_T   = ("Courier", 11, "bold")

# Cortisol-specific (mirrors cortisol_monitor.py)
CORTISOL_MEDIUM    = 30.0
CORTISOL_HIGH      = 60.0
CORTISOL_NORMAL_C  = "#27ae60"   # green
CORTISOL_MEDIUM_C  = "#f39c12"   # amber
CORTISOL_HIGH_C    = "#e74c3c"   # red
CORTISOL_HISTORY   = 60          # sparkline data points
GAUGE_W, GAUGE_H   = 60, 240


def _make_scrollable(parent, bg=BG):
    frame_outer = tk.Frame(parent, bg=bg)
    canvas = tk.Canvas(frame_outer, bg=bg, highlightthickness=0)
    scrollbar = ttk.Scrollbar(frame_outer, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=bg)
    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    return frame_outer, inner


class BodyCanvas:
    def __init__(self, root: tk.Tk, ui_queue: queue.Queue,
                 endocrine_queue: queue.Queue, hw_queue: queue.Queue,
                 image_path: str):
        self.root = root
        self.ui_queue        = ui_queue
        self.endocrine_queue = endocrine_queue
        self.hw_queue        = hw_queue
        self.root.title("Digi-Soul")
        self.root.configure(bg=BG)

        # Cortisol state
        self._cortisol_history: list[float] = [10.0] * CORTISOL_HISTORY
        self._cortisol_alert_visible = False

        # ── Left: body silhouette ──────────────────────────────────────
        self.body_canvas = tk.Canvas(self.root, width=CANVAS_W, height=CANVAS_H,
                                     bg=BG, highlightthickness=0)
        self.body_canvas.pack(side=tk.LEFT, fill=tk.Y)

        img = Image.open(image_path).resize((CANVAS_W, CANVAS_H))
        self.photo = ImageTk.PhotoImage(img)
        self.body_canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

        self._ovals: dict = {}
        for name, cfg in ORGAN_CONFIG.items():
            x, y = cfg["pos"]
            r = 12
            oval = self.body_canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=cfg["color"], outline="white", width=2)
            self.body_canvas.create_text(
                x, y + r + 8, text=cfg["label"],
                fill="white", font=("Courier", 6, "bold"))
            self._ovals[name] = oval

        # Sleep indicator
        self._sleep_indicator = self.body_canvas.create_text(
            230, 620, text="", fill="#00cfff", font=("Courier", 9, "bold"))

        # Cortisol stress indicator — shown near adrenal gland when level is HIGH
        ax, ay = ORGAN_CONFIG["adrenal_gland"]["pos"]
        self._cortisol_indicator = self.body_canvas.create_text(
            ax - 38, ay - 22, text="", fill=CORTISOL_HIGH_C,
            font=("Courier", 7, "bold"), anchor=tk.E)

        # ── Right: tabbed info panel ───────────────────────────────────
        panel = tk.Frame(self.root, bg=BG, width=PANEL_W)
        panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        tk.Label(panel, text="[ DIGI-SOUL ]", bg=BG, fg=FG,
                 font=FONT_T).pack(pady=(12, 2))

        self._alert_label = tk.Label(panel, text="", bg=BG, fg=ALERT_FG,
                                     font=FONT_B, wraplength=PANEL_W - 20)
        self._alert_label.pack()

        nb = ttk.Notebook(panel)
        nb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # ── Tab 1: Organs ─────────────────────────────────────────────
        organs_outer, organs_inner = _make_scrollable(nb)
        nb.add(organs_outer, text="Organs")
        self._organ_texts: dict[str, tk.Text] = {}
        for name, cfg in ORGAN_CONFIG.items():
            frame = tk.LabelFrame(organs_inner, text=f" {cfg['label']} ",
                                  bg=BG, fg=cfg["color"], font=FONT_B,
                                  bd=1, relief=tk.RIDGE, labelanchor="nw")
            frame.pack(fill=tk.X, padx=8, pady=3)
            txt = tk.Text(frame, height=4, bg=BG, fg=FG, font=FONT,
                          bd=0, state=tk.DISABLED, wrap=tk.WORD)
            txt.pack(fill=tk.X, padx=4, pady=3)
            self._organ_texts[name] = txt

        # ── Tab 2: Neural ─────────────────────────────────────────────
        ns_frame = tk.Frame(nb, bg=BG)
        nb.add(ns_frame, text="Neural")
        tk.Label(ns_frame, text="Neuron potentials & LTP", bg=BG,
                 fg=NS_FG, font=FONT_B).pack(pady=(8, 4))
        self._ns_text = tk.Text(ns_frame, bg=BG, fg=NS_FG, font=FONT,
                                bd=0, state=tk.DISABLED, wrap=tk.WORD)
        self._ns_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # ── Tab 3: Endocrine ──────────────────────────────────────────
        endo_frame = tk.Frame(nb, bg=BG)
        nb.add(endo_frame, text="Endocrine")
        tk.Label(endo_frame, text="Circulating hormone levels", bg=BG,
                 fg=ENDO_FG, font=FONT_B).pack(pady=(8, 4))
        self._endo_text = tk.Text(endo_frame, height=12, bg=BG, fg=ENDO_FG,
                                  font=FONT, bd=0, state=tk.DISABLED, wrap=tk.WORD)
        self._endo_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # ── Tab 4: Cortisol ───────────────────────────────────────────
        cort_frame = tk.Frame(nb, bg=BG)
        nb.add(cort_frame, text="Cortisol")
        self._build_cortisol_tab(cort_frame)

        # ── Tab 5: Hardware ───────────────────────────────────────────
        hw_frame = tk.Frame(nb, bg=BG)
        nb.add(hw_frame, text="Hardware")
        tk.Label(hw_frame, text="Robot subsystem states", bg=BG,
                 fg=HW_FG, font=FONT_B).pack(pady=(8, 4))
        self._hw_text = tk.Text(hw_frame, bg=BG, fg=HW_FG, font=FONT,
                                bd=0, state=tk.DISABLED, wrap=tk.WORD)
        self._hw_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._poll()

    # ── Cortisol tab builder ──────────────────────────────────────────

    def _build_cortisol_tab(self, parent: tk.Frame):
        tk.Label(parent, text="CORTISOL / STRESS MONITOR", bg=BG,
                 fg=CORTISOL_NORMAL_C, font=FONT_B).pack(pady=(10, 2))
        tk.Label(parent, text="adrenal hormone level (AU)", bg=BG,
                 fg="#555577", font=FONT).pack(pady=(0, 8))

        row = tk.Frame(parent, bg=BG)
        row.pack(padx=12, pady=4)

        # Vertical gauge
        gauge_col = tk.Frame(row, bg=BG)
        gauge_col.pack(side=tk.LEFT, padx=(0, 16))

        self._cort_gauge = tk.Canvas(gauge_col, width=GAUGE_W, height=GAUGE_H,
                                     bg="#111122", highlightthickness=1,
                                     highlightbackground="#333355")
        self._cort_gauge.pack()

        # Threshold lines
        for thresh, color in [(CORTISOL_HIGH, CORTISOL_HIGH_C),
                              (CORTISOL_MEDIUM, CORTISOL_MEDIUM_C)]:
            y = self._cort_level_to_y(thresh)
            self._cort_gauge.create_line(0, y, GAUGE_W, y,
                                         fill=color, dash=(4, 3), width=1)

        self._cort_bar = self._cort_gauge.create_rectangle(
            4, GAUGE_H - 4, GAUGE_W - 4, GAUGE_H - 4,
            fill=CORTISOL_NORMAL_C, outline="")

        # Right column: level + status + sparkline
        right = tk.Frame(row, bg=BG)
        right.pack(side=tk.LEFT, anchor=tk.N)

        tk.Label(right, text="LEVEL", bg=BG, fg="#555577", font=FONT).pack()
        self._cort_level_lbl = tk.Label(right, text=" 0.0", bg=BG,
                                        fg=CORTISOL_NORMAL_C,
                                        font=("Courier", 20, "bold"), width=7)
        self._cort_level_lbl.pack(pady=(2, 8))

        tk.Label(right, text="STATUS", bg=BG, fg="#555577", font=FONT).pack()
        self._cort_status_lbl = tk.Label(right, text="CALM", bg=BG,
                                         fg=CORTISOL_NORMAL_C,
                                         font=("Courier", 12, "bold"), width=10)
        self._cort_status_lbl.pack(pady=(2, 10))

        tk.Label(right, text="HISTORY (60 ticks)", bg=BG,
                 fg="#555577", font=("Courier", 8)).pack()
        self._cort_spark = tk.Canvas(right, width=210, height=65,
                                     bg="#111122", highlightthickness=1,
                                     highlightbackground="#333355")
        self._cort_spark.pack(pady=(2, 0))

        # Alert banner — packed/unpacked dynamically
        self._cort_alert_frame = tk.Frame(parent, bg=CORTISOL_HIGH_C)
        tk.Label(self._cort_alert_frame,
                 text="!  STRESS ALERT  —  HIGH CORTISOL  !",
                 bg=CORTISOL_HIGH_C, fg="white",
                 font=("Courier", 10, "bold"), pady=5).pack(fill=tk.X)

        # Stats
        self._cort_stats_lbl = tk.Label(parent, text="", bg=BG,
                                        fg="#555577", font=("Courier", 8))
        self._cort_stats_lbl.pack(pady=(8, 4))

    # ── Polling ───────────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                name, state = self.ui_queue.get_nowait()
                if name == "nervous_system":
                    self._update_ns(state)
                else:
                    self._update_organ(name, state)
                    self._flash(name)
        except queue.Empty:
            pass

        try:
            while True:
                hormones = self.endocrine_queue.get_nowait()
                self._update_endocrine(hormones)
                self._update_cortisol(hormones.get("cortisol", 0.0))
        except queue.Empty:
            pass

        try:
            while True:
                hw_state = self.hw_queue.get_nowait()
                self._update_hardware(hw_state)
        except queue.Empty:
            pass

        self.root.after(100, self._poll)

    # ── Organ / NS updaters ───────────────────────────────────────────

    def _update_organ(self, name: str, state: dict):
        txt = self._organ_texts.get(name)
        if not txt:
            return
        txt.config(state=tk.NORMAL)
        txt.delete("1.0", tk.END)
        for k, v in state.items():
            if k == "alert":
                continue
            txt.insert(tk.END, f"  {k}: {v}\n")
        txt.config(state=tk.DISABLED)
        alert = state.get("alert")
        if alert:
            self._alert_label.config(text=f"! {alert}")

    def _update_ns(self, state: dict):
        meta        = state.pop("_meta", {})
        sleep_state = meta.get("sleep_state", "awake")
        total_tx    = meta.get("total_transmissions", 0)
        ltp         = meta.get("ltp_weights", {})
        auto        = meta.get("autonomic", {})
        hpa         = meta.get("hpa", {})

        self.body_canvas.itemconfig(
            self._sleep_indicator,
            text="z z z  SLEEP" if sleep_state == "sleeping" else "")

        self._ns_text.config(state=tk.NORMAL)
        self._ns_text.delete("1.0", tk.END)
        self._ns_text.insert(tk.END, f"  state:  {sleep_state.upper()}\n")
        self._ns_text.insert(tk.END, f"  total transmissions: {total_tx}\n\n")
        self._ns_text.insert(tk.END, "  NEURONS\n")
        for neuron, data in state.items():
            bar = self._bar(data["potential"], data["threshold"])
            self._ns_text.insert(
                tk.END,
                f"  {neuron:<22} {bar}  fires={data['fires']}\n")
        self._ns_text.insert(tk.END, "\n  LTP WEIGHTS\n")
        for conn, w in ltp.items():
            self._ns_text.insert(tk.END, f"  {conn:<36} w={w}\n")

        # ── Autonomic effectors + baroreflex ─────────────────────────
        if auto:
            self._ns_text.insert(tk.END, "\n  AUTONOMIC EFFECTORS\n")
            vagal = auto.get("vagal_drive", 0.0)
            symp  = auto.get("sympathetic_drive", 0.0)
            self._ns_text.insert(
                tk.END,
                f"  vagal (parasymp)   {self._bar(vagal, 1.0, 12)} {vagal:>5.3f}\n")
            self._ns_text.insert(
                tk.END,
                f"  sympathetic        {self._bar(symp, 1.0, 12)} {symp:>5.3f}\n")
            self._ns_text.insert(
                tk.END,
                f"  baroreflex  MAP={auto.get('map_mmHg', 0.0):>5.1f} mmHg"
                f"  BRS={auto.get('brs_ms_per_mmHg', 0.0):>4.1f} ms/mmHg\n")

            # ── Emergent HRV metrics (index of vagal tone) ───────────
            self._ns_text.insert(tk.END, "\n  HRV METRICS\n")
            self._ns_text.insert(
                tk.END,
                f"  SDNN={auto.get('sdnn', 0.0):>5.1f} ms"
                f"   RMSSD={auto.get('rmssd', 0.0):>5.1f} ms\n")
            self._ns_text.insert(
                tk.END,
                f"  LF/HF={auto.get('lf_hf', 0.0):>5.2f}"
                f"   HF power={auto.get('hf_power', 0.0):>5.1f} ms\n")

        # ── HPA axis (cortisol negative-feedback loop) ───────────────
        if hpa:
            self._ns_text.insert(tk.END, "\n  HPA AXIS\n")
            self._ns_text.insert(
                tk.END,
                f"  CRH={hpa.get('crh', 0.0):>5.3f}"
                f"   ACTH={hpa.get('acth', 0.0):>5.3f}\n")
            self._ns_text.insert(
                tk.END,
                f"  cortisol={hpa.get('cortisol', 0.0):>5.1f}"
                f"   feedback_gain={hpa.get('feedback_gain', 0.0):>4.2f}\n")

        self._ns_text.config(state=tk.DISABLED)

    def _update_endocrine(self, hormones: dict):
        self._endo_text.config(state=tk.NORMAL)
        self._endo_text.delete("1.0", tk.END)
        self._endo_text.insert(tk.END, "  HORMONE           LEVEL   BAR\n")
        self._endo_text.insert(tk.END, "  " + "─" * 38 + "\n")
        for hormone, level in hormones.items():
            bar = self._bar(level, 100, width=12)
            self._endo_text.insert(
                tk.END, f"  {hormone:<18} {level:>5.1f}   {bar}\n")
        self._endo_text.config(state=tk.DISABLED)

    def _update_hardware(self, hw: dict):
        self._hw_text.config(state=tk.NORMAL)
        self._hw_text.delete("1.0", tk.END)
        servos = hw.pop("servos", {})
        hw.pop("last_updated", None)
        for k, v in hw.items():
            self._hw_text.insert(tk.END, f"  {k:<18} {v}\n")
        self._hw_text.insert(tk.END, "\n  SERVOS\n")
        for joint, torque in servos.items():
            bar = self._bar(abs(torque), 100, width=8)
            self._hw_text.insert(tk.END, f"  {joint:<16} {torque:>6.1f}%  {bar}\n")
        self._hw_text.config(state=tk.DISABLED)

    # ── Cortisol tab updater ──────────────────────────────────────────

    def _update_cortisol(self, level: float):
        self._cortisol_history.append(level)
        if len(self._cortisol_history) > CORTISOL_HISTORY:
            self._cortisol_history.pop(0)

        color = self._cort_color(level)

        # Gauge bar
        y_top = self._cort_level_to_y(level)
        self._cort_gauge.coords(self._cort_bar, 4, y_top, GAUGE_W - 4, GAUGE_H - 4)
        self._cort_gauge.itemconfig(self._cort_bar, fill=color)

        # Labels
        self._cort_level_lbl.config(text=f"{level:>5.1f}", fg=color)
        status, sc = self._cort_status(level)
        self._cort_status_lbl.config(text=status, fg=sc)

        # Alert banner inside tab
        if level >= CORTISOL_HIGH and not self._cortisol_alert_visible:
            self._cort_alert_frame.pack(fill=tk.X, padx=0,
                                        before=self._cort_stats_lbl)
            self._cortisol_alert_visible = True
        elif level < CORTISOL_HIGH and self._cortisol_alert_visible:
            self._cort_alert_frame.pack_forget()
            self._cortisol_alert_visible = False

        # Body canvas indicator near adrenal gland
        if level >= CORTISOL_HIGH:
            self.body_canvas.itemconfig(
                self._cortisol_indicator, text="⚠ CORTISOL")
        elif level >= CORTISOL_MEDIUM:
            self.body_canvas.itemconfig(
                self._cortisol_indicator, text="↑ cortisol")
        else:
            self.body_canvas.itemconfig(self._cortisol_indicator, text="")

        # Sparkline
        self._draw_cortisol_sparkline(color)

        # Stats
        h = self._cortisol_history
        self._cort_stats_lbl.config(
            text=f"min={min(h):.1f}  avg={sum(h)/len(h):.1f}  max={max(h):.1f}")

    def _draw_cortisol_sparkline(self, line_color: str):
        self._cort_spark.delete("all")
        w = int(self._cort_spark["width"])
        h = int(self._cort_spark["height"])
        data = self._cortisol_history
        n = len(data)
        if n < 2:
            return
        x_step = w / (n - 1)
        # Threshold lines
        for thresh, color in [(CORTISOL_HIGH, CORTISOL_HIGH_C),
                              (CORTISOL_MEDIUM, CORTISOL_MEDIUM_C)]:
            y = h - (thresh / 100) * h
            self._cort_spark.create_line(0, y, w, y, fill=color,
                                         dash=(3, 3), width=1)
        # Line
        points = []
        for i, val in enumerate(data):
            points.append(i * x_step)
            points.append(h - (val / 100) * h)
        self._cort_spark.create_line(*points, fill=line_color, width=2, smooth=True)

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _cort_level_to_y(level: float) -> float:
        return GAUGE_H - (max(0.0, min(100.0, level)) / 100) * GAUGE_H

    @staticmethod
    def _cort_color(level: float) -> str:
        if level >= CORTISOL_HIGH:
            return CORTISOL_HIGH_C
        if level >= CORTISOL_MEDIUM:
            return CORTISOL_MEDIUM_C
        return CORTISOL_NORMAL_C

    @staticmethod
    def _cort_status(level: float) -> tuple[str, str]:
        if level >= CORTISOL_HIGH:
            return "STRESS", CORTISOL_HIGH_C
        if level >= CORTISOL_MEDIUM:
            return "ELEVATED", CORTISOL_MEDIUM_C
        return "CALM", CORTISOL_NORMAL_C

    def _bar(self, value: float, maximum: float, width: int = 8) -> str:
        ratio = min(1.0, max(0.0, value / maximum)) if maximum else 0
        filled = int(ratio * width)
        return "[" + "█" * filled + "·" * (width - filled) + "]"

    def _flash(self, name: str):
        oval = self._ovals.get(name)
        if not oval:
            return
        original = ORGAN_CONFIG[name]["color"]
        self.body_canvas.itemconfig(oval, fill="white")
        self.root.after(110, lambda: self.body_canvas.itemconfig(oval, fill=original))
