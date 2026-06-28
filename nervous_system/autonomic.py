"""
autonomic.py — autonomic effector pathways + baroreflex for digi-soul.

Extends the spiking NervousSystem with the two biologically distinct autonomic
effector arms, a baroreflex negative-feedback loop, emergent HRV diagnostics,
and an HPA axis with explicit cortisol negative feedback.

This module is a clean extension of the existing nervous_system package — it
does NOT replace the Neuron/Synapse spiking network. The spiking circuit
(circuit.py) feeds graded "requests" into the AutonomicController, which
integrates them with realistic latency asymmetry and closes the baroreflex
loop against the vascular system's published blood pressure.

Sources:
  - Draghici & Taylor 2018 (PMID 28844537) — baroreflex sensitivity, HRV bands
  - Shoemaker 2017      (PMID 28871339) — sympathetic rate+recruitment coding, saturation
  - Salzer 2015         (PMID 26054742) — myelinated-fiber conduction-velocity classes
  - Tan 2019            (PMID 29654380) — vagal control of heart rate / HRV
  - Perrelli 2024       (PMID 38927393) — CRH–noradrenaline positive-feedback in stress
"""

import asyncio
import math
import random
from collections import deque

from core.endocrine_bus import HORMONE_MAX


# ----------------------------------------------------------------------
# Conduction-velocity classes (Erlanger–Gasser), Salzer 2015 PMID 26054742
# Representative midpoints of the published ranges, metres/second.
# ----------------------------------------------------------------------
FIBER_VELOCITY_MPS: dict[str, float] = {
    "Aalpha": 100.0,  # 80–120  proprioceptive / somatic motor   (PMID 26054742)
    "Abeta":   55.0,  # 35–75   touch / pressure                  (PMID 26054742)
    "Adelta":  17.0,  # 5–30    sharp pain, baroreceptor afferent (PMID 26054742)
    "B":        9.0,  # 3–15    preganglionic autonomic (myelin)  (PMID 26054742)
    "C":        1.0,  # 0.5–2   unmyelinated postganglionic / pain(PMID 26054742)
}

# Approximate afferent/efferent path length brainstem ↔ thorax (m).
DEFAULT_PATH_M = 0.30


def conduction_delay(fiber: str, distance_m: float = DEFAULT_PATH_M) -> float:
    """Transmission delay (s) for a fiber class over a path length.

    Replaces instantaneous signaling: fast somatic reflexes (Aα) arrive in a
    few ms, slow unmyelinated visceral C-fibers take hundreds of ms.
    Salzer 2015 (PMID 26054742).
    """
    v = FIBER_VELOCITY_MPS.get(fiber, FIBER_VELOCITY_MPS["B"])
    return distance_m / v


# ----------------------------------------------------------------------
# Autonomic effector latencies — Draghici & Taylor 2018 (PMID 28844537)
# The vagal-fast / sympathetic-slow asymmetry is the key modeling parameter.
# ----------------------------------------------------------------------
VAGAL_ONSET_S = 0.3    # parasympathetic onset <1 s (ACh + muscarinic GIRK K+)
VAGAL_TAU_S   = 0.6    # near beat-to-beat decay of vagal effect
SYMP_ONSET_S  = 2.0    # sympathetic latency ~1–5 s (NE second-messenger cascade)
SYMP_TAU_S    = 14.0   # slow rise; 1−e^(−25/14) ≈ 0.83 → peak ~20–30 s

# Resting autonomic balance — net vagal dominance gives resting HR 60–80 bpm
# against an intrinsic ~100–110 bpm (full blockade). Draghici & Taylor 2018.
VAGAL_REST = 0.35
SYMP_REST  = 0.15
# Net autonomic tone at rest (negative = vagal dominance). drive_effectors works
# on deviation from this set point so the controller stays silent at rest instead
# of fighting the SA node's intrinsic rhythm. Draghici & Taylor 2018 (PMID 28844537).
RESTING_NET = SYMP_REST - VAGAL_REST

# Baroreflex (Draghici & Taylor 2018 PMID 28844537)
MAP_SETPOINT_MMHG = 93.0   # mean arterial pressure operating point
BRS_MS_PER_MMHG   = 15.0   # baroreflex sensitivity (healthy adult 10–20 ms/mmHg)
VAGAL_BARO_GAIN   = 0.025  # per mmHg error → vagal drive (loads vagus when BP↑)
SYMP_BARO_GAIN    = 0.015  # per mmHg error → sympathetic drive (unloading → BP↓)

# HRV reference (Draghici & Taylor 2018 PMID 28844537; Task Force 1996)
# resting SDNN ≈ 50 ms, RMSSD ≈ 42 ms, LF/HF ≈ 1.5–2.0; HF 0.15–0.40 Hz is vagal.
HRV_WINDOW   = 32     # NN intervals retained for rolling HRV statistics
RSA_DEPTH    = 0.06   # respiratory sinus arrhythmia depth scaled by vagal tone

REQUEST_DECAY = 0.6   # per-tick decay of transient neuron-driven drive requests


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class AutonomicController:
    """
    Two distinct autonomic effector arms driving the heart & vasculature:

      vagal (parasympathetic): fast onset (<1 s), beat-to-beat — slows HR
      sympathetic:             slow onset (1–5 s), peak 20–30 s — speeds HR

    Sympathetic output is graded and saturating (rate + recruitment coding),
    not a binary stress switch (Shoemaker 2017 PMID 28871339).

    The controller closes the baroreflex loop against blood pressure published
    by the vascular system and exposes HRV/HF power as an emergent diagnostic
    of vagal tone (Draghici & Taylor 2018 PMID 28844537).
    """

    def __init__(self, bus, endocrine=None):
        self.bus = bus
        self.endocrine = endocrine

        # Graded drives, 0..1
        self.vagal_drive = VAGAL_REST
        self.sympathetic_drive = SYMP_REST

        # Transient boosts injected by the spiking circuit's motor neurons
        self._vagal_request = 0.0
        self._symp_request = 0.0

        # Baroreflex input
        self.map_mmHg = MAP_SETPOINT_MMHG
        self._last_map = MAP_SETPOINT_MMHG

        # Sympathetic onset buffer (latency asymmetry)
        self._symp_pending = SYMP_REST
        self._symp_active = SYMP_REST
        self._symp_pending_clock = 0.0

        # HRV state
        self._rr = deque(maxlen=HRV_WINDOW)   # NN intervals (ms)
        self._rsa_phase = 0.0
        self._brs_est = BRS_MS_PER_MMHG

    # ------------------------------------------------------------------
    # Inputs from the spiking circuit / organ listener
    # ------------------------------------------------------------------

    def request_vagal(self, intensity: float = 0.3):
        """Cardioinhibitory (vagal) burst from a motor neuron firing."""
        self._vagal_request = _clip(self._vagal_request + intensity)

    def request_sympathetic(self, intensity: float = 0.3):
        """Cardioacceleratory (sympathetic) burst from a motor neuron firing."""
        self._symp_request = _clip(self._symp_request + intensity)

    def note_pressure(self, map_mmHg: float):
        """Baroreceptor input — latest mean arterial pressure (mmHg)."""
        self._last_map = self.map_mmHg
        self.map_mmHg = map_mmHg

    def record_beat(self, bpm: float):
        """Feed one cardiac cycle into the HRV buffer.

        Vagal tone injects respiratory sinus arrhythmia (HF-band oscillation),
        so HRV is emergent rather than prescribed (Tan 2019 PMID 29654380).
        """
        if bpm <= 0:
            return
        rr = 60000.0 / bpm                      # NN interval in ms
        self._rsa_phase += 0.45                 # advances the RSA oscillation
        rsa = 1.0 + self.vagal_drive * RSA_DEPTH * math.sin(self._rsa_phase)
        rr_eff = rr * rsa + random.uniform(-3.0, 3.0)
        self._rr.append(rr_eff)

    # ------------------------------------------------------------------
    # Sympathetic saturation — Shoemaker 2017 (PMID 28871339)
    # ------------------------------------------------------------------

    @staticmethod
    def _saturate(raw: float) -> float:
        """Graded burst output saturates at high drive (rate + recruitment).

        Sigmoid so that sympathetic outflow grades smoothly and plateaus
        instead of behaving as an on/off switch. Shoemaker 2017 (PMID 28871339).
        """
        return 1.0 / (1.0 + math.exp(-4.0 * (raw - 0.5)))

    def _stress_input(self) -> float:
        """Circulating-catecholamine contribution to sympathetic drive."""
        if not self.endocrine:
            return 0.0
        adr = self.endocrine.get_level("adrenaline")
        return _clip(adr / 60.0, 0.0, 0.6)

    # ------------------------------------------------------------------
    # Integration step (called by NervousSystem loop)
    # ------------------------------------------------------------------

    def step(self, dt: float):
        # Baroreflex error: +ve → BP above setpoint → load baroreceptors
        err = self.map_mmHg - MAP_SETPOINT_MMHG

        # --- Vagal arm: fast, responds to BP rise within one tick ---------
        vagal_target = _clip(
            VAGAL_REST + err * VAGAL_BARO_GAIN + self._vagal_request
        )
        alpha_v = min(1.0, dt / VAGAL_TAU_S)
        self.vagal_drive += (vagal_target - self.vagal_drive) * alpha_v

        # --- Sympathetic arm: slow onset + slow rise, saturating ----------
        symp_target = self._saturate(
            SYMP_REST - err * SYMP_BARO_GAIN + self._symp_request
            + self._stress_input()
        )
        # Onset latency: a new target only becomes "active" after SYMP_ONSET_S
        if abs(symp_target - self._symp_pending) > 0.01:
            self._symp_pending = symp_target
            self._symp_pending_clock = 0.0
        else:
            self._symp_pending_clock += dt
        if self._symp_pending_clock >= SYMP_ONSET_S:
            self._symp_active = self._symp_pending
        alpha_s = min(1.0, dt / SYMP_TAU_S)
        self.sympathetic_drive += (self._symp_active - self.sympathetic_drive) * alpha_s

        # Decay transient neuron-driven requests
        self._vagal_request *= REQUEST_DECAY
        self._symp_request *= REQUEST_DECAY

    # ------------------------------------------------------------------
    # Effector output — chronotropic + vasomotor commands via MessageBus
    # ------------------------------------------------------------------

    async def _route_after(self, fiber: str, target: str, message: dict):
        """Route an effector command after that fiber class's conduction delay.

        Replaces instantaneous visceral signaling: sympathetic postganglionic
        axons are unmyelinated C fibers (0.5–2 m/s, slow), while vagal cardiac
        efferents travel in myelinated preganglionic B fibers (3–15 m/s, faster).
        Salzer 2015 (PMID 26054742).
        """
        await asyncio.sleep(conduction_delay(fiber))
        await self.bus.route("nervous_system", target, message)

    async def drive_effectors(self):
        """Translate net autonomic tone into heart + vascular commands.

        Commands are issued on the *deviation* from the resting set point
        (RESTING_NET), so at rest the controller emits only a benign "regulate"
        and never drags the heart toward its bpm floor.

        delta > 0 → sympathetic predominance (speed up / vasoconstrict)
        delta < 0 → vagal predominance       (slow down / vasodilate)
        Effector commands are delayed by fiber conduction velocity, preserving
        the vagal-fast (B) / sympathetic-slow (C) asymmetry at the wire level.
        Uses only the existing organ command vocabulary (no organ rewrite).
        """
        delta = (self.sympathetic_drive - self.vagal_drive) - RESTING_NET
        if delta > 0.12:
            asyncio.create_task(self._route_after(
                "C", "heart", {"signal": "neural_cmd", "cmd": "increase_bpm"}))
            asyncio.create_task(self._route_after(
                "C", "vascular_system", {"signal": "neural_cmd", "cmd": "vasoconstrict"}))
        elif delta < -0.12:
            asyncio.create_task(self._route_after(
                "B", "heart", {"signal": "neural_cmd", "cmd": "decrease_bpm"}))
            asyncio.create_task(self._route_after(
                "B", "vascular_system", {"signal": "neural_cmd", "cmd": "vasodilate"}))
        else:
            await self.bus.route("nervous_system", "heart",
                                 {"signal": "neural_cmd", "cmd": "regulate"})

    # ------------------------------------------------------------------
    # Emergent HRV diagnostics — queryable index of vagal tone
    # ------------------------------------------------------------------

    def hrv(self) -> dict:
        n = len(self._rr)
        if n < 3:
            return {"sdnn": 0.0, "rmssd": 0.0, "lf_hf": 0.0, "hf_power": 0.0}
        rr = list(self._rr)
        mean = sum(rr) / n
        sdnn = math.sqrt(sum((x - mean) ** 2 for x in rr) / n)            # ms
        diffs = [rr[i + 1] - rr[i] for i in range(n - 1)]
        rmssd = math.sqrt(sum(d * d for d in diffs) / len(diffs))          # ms (vagal)
        # HF power is vagally mediated (RSA); LF reflects baroreflex+sympathetic.
        # LF/HF ≈ 1.5–2.0 at rest (Draghici & Taylor 2018 PMID 28844537).
        hf_power = rmssd
        lf_hf = (0.5 + 1.6 * self.sympathetic_drive) / (0.2 + self.vagal_drive)
        return {
            "sdnn": round(sdnn, 1),
            "rmssd": round(rmssd, 1),
            "lf_hf": round(lf_hf, 2),
            "hf_power": round(hf_power, 1),
        }

    def diagnostics(self) -> dict:
        d = {
            "vagal_drive": round(self.vagal_drive, 3),
            "sympathetic_drive": round(self.sympathetic_drive, 3),
            "map_mmHg": round(self.map_mmHg, 1),
            "brs_ms_per_mmHg": BRS_MS_PER_MMHG,
        }
        d.update(self.hrv())
        return d


# ----------------------------------------------------------------------
# HPA axis with explicit cortisol negative feedback
# ----------------------------------------------------------------------

PITUITARY_GAIN = 0.8    # CRH → ACTH
ADRENAL_GAIN   = 0.9    # ACTH → cortisol secretion rate
POS_FB_GAIN    = 0.5    # CRH–noradrenaline positive arm (Perrelli 2024 PMID 38927393)


class HPAAxis:
    """
    Hypothalamic–Pituitary–Adrenal axis with the cortisol negative-feedback
    loop made explicit and tunable.

      CRH (hypothalamus) → ACTH (pituitary) → cortisol (adrenal cortex)
      circulating cortisol ⊣ CRH/ACTH   (negative feedback)

    `feedback_gain` ≈ 1.0 is healthy. Detuning it toward 0 releases the
    CRH–noradrenaline positive-feedback arm, letting stress signaling run
    away — the substrate for chronic-stress pathology (Perrelli 2024,
    PMID 38927393). The previous codebase had NO cortisol→CRH/ACTH feedback;
    this class adds it so the loop can be both verified and detuned.
    """

    def __init__(self, endocrine, feedback_gain: float = 1.0):
        self.endocrine = endocrine
        self.feedback_gain = feedback_gain
        self.crh = 0.0
        self.acth = 0.0

    def step(self, stress_drive: float, dt: float) -> dict:
        cortisol = self.endocrine.get_level("cortisol") if self.endocrine else 0.0

        # Negative feedback: circulating cortisol suppresses hypothalamic CRH.
        suppression = self.feedback_gain * (cortisol / HORMONE_MAX)

        # Positive arm only emerges when the negative loop is detuned (gain<1).
        positive = POS_FB_GAIN * (1.0 - self.feedback_gain) * self.crh

        self.crh = max(0.0, stress_drive + positive - suppression)
        self.acth = self.crh * PITUITARY_GAIN

        if self.endocrine:
            self.endocrine.secrete("cortisol",
                                   amount=self.acth * ADRENAL_GAIN * dt,
                                   source="hpa_axis")
        return {
            "crh": round(self.crh, 3),
            "acth": round(self.acth, 3),
            "feedback_gain": self.feedback_gain,
            "cortisol": round(cortisol, 1),
        }
