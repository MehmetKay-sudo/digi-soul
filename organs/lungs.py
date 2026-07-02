"""
Enhanced Lungs
==============
Based on: Elmas & Kunduracioglu (2025) §2.5 — respiratory system:
  - Trachea, bronchi, alveoli for gas exchange
  - Zhang (2020) §3(1): alveolar spaces are ESSENTIAL for gas exchange.
    When spaces fill with fluid (pneumonia) or narrow, O2 exchange fails.

Space-quality integration:
  - Alveolar space quality directly affects oxygen extraction efficiency
  - Narrowed thoracic spaces → reduced tidal volume → lower O2 saturation

Breath-driven phonation (respiratory power source for speech):
  The lungs are the power supply for voice. During speech the diaphragm and
  the expiratory muscles regulate a raised, roughly constant *subglottal
  pressure* (Ps) beneath the closed/vibrating vocal folds. This pressure is
  the single physical quantity the language module reads to drive loudness and
  (partly) pitch — so it lives HERE, in the lungs, as the one source of truth.
  The language module reads it live via bus._organs["lungs"].subglottal_pressure();
  no state is duplicated.

  Subglottal pressure during speech:
    - Normal conversational/soft-to-comfortable speech: ~5–10 cmH2O
    - Typical conversational level: ~10 cmH2O
    Sources: Sundberg (voice acoustics); Houlton et al. 2011, PMID 22024843.
  At rest (tidal breathing, no phonation) there is no sustained driving
  pressure for voice, so Ps ≈ 0 cmH2O for the acoustic layer.
"""

import asyncio

from core.organ import Organ

BREATH_NORMAL = 2.0  # seconds per phase (15 breaths/min)

# ── Subglottal pressure (breath → phonation) ──────────────────────────────
# Units: cmH2O. Values from Sundberg; Houlton 2011 (PMID 22024843).
SUBGLOTTAL_PRESSURE_REST          = 0.0   # no phonation → no voice-driving pressure
SUBGLOTTAL_PRESSURE_SPEECH_MIN    = 5.0   # lower bound of normal speech range
SUBGLOTTAL_PRESSURE_SPEECH_MAX    = 10.0  # upper bound of normal speech range
SUBGLOTTAL_PRESSURE_CONVERSATIONAL = 10.0 # typical conversational level (~10 cmH2O)


class Lungs(Organ):
    def __init__(self, bus, breath_interval: float = BREATH_NORMAL):
        super().__init__("lungs", bus)
        self._space_physiology = None
        self.breath_interval = breath_interval

        # Phonation drive (diaphragm / expiratory effort). Off by default.
        self._phonating = False
        self._phonation_effort = 0.0   # 0.0–1.0 → maps into the speech Ps range

        self.state = {
            "phase": "inhale",
            "cycles": 0,
            "oxygen_level": 100,
            "co2_level": 40.0,          # mmHg — normal arterial PCO2 35-45
            "alveolar_space_quality": 1.0,
            "tidal_volume_ml": 500,     # mL — typical adult
            "status": "breathing",
            "rate": "normal",
            # Subglottal pressure driving voice (cmH2O). Single source of truth,
            # read live by the language module. Rest = no phonation.
            "subglottal_pressure_cmh2o": SUBGLOTTAL_PRESSURE_REST,
            "phonating": False,
        }

    async def run(self):
        if "space_physiology" in self.bus._organs:
            self._space_physiology = self.bus._organs["space_physiology"]

        asyncio.create_task(self._command_listener())
        while True:
            # Inhale — space quality affects how much O2 we can extract
            space_q = self._get_space_quality()
            self.state["alveolar_space_quality"] = space_q

            # Zhang 2020 §3(1): alveolar spaces necessary for gas exchange
            o2_efficiency = 0.3 + 0.7 * space_q
            self.state["tidal_volume_ml"] = int(500 * (0.5 + 0.5 * space_q))

            self.state["phase"] = "inhale"
            self._update_subglottal_pressure()
            self.bus.update_ui("lungs", dict(self.state))
            await asyncio.sleep(self.breath_interval)

            # Exhale — speech is powered by the expiratory airflow
            self.state["phase"] = "exhale"
            self.state["cycles"] += 1
            self._update_subglottal_pressure()
            self.state["oxygen_level"] = min(100, 90 + int(o2_efficiency * 10))

            # CO2 rises with metabolism, falls with breathing rate and alveolar efficiency
            metabolic_co2 = 1.5
            expelled_co2  = (BREATH_NORMAL / self.breath_interval) * 1.5 * o2_efficiency
            self.state["co2_level"] = round(
                max(35.0, min(50.0, self.state["co2_level"] + metabolic_co2 - expelled_co2)), 1
            )

            await self.broadcast(signal="oxygen", level=self.state["oxygen_level"],
                                 co2=self.state["co2_level"], space_quality=space_q)
            self.bus.update_ui("lungs", dict(self.state))
            await asyncio.sleep(self.breath_interval)

    def _get_space_quality(self) -> float:
        if self._space_physiology:
            return self._space_physiology.space_quality_for("lungs")
        return 1.0

    # ── Breath → phonation (subglottal pressure) ──────────────────────────

    def set_phonation(self, active: bool, effort: float = 1.0) -> None:
        """Engage or release the voice-driving expiratory effort.

        `effort` (0.0–1.0) is the diaphragm/expiratory-muscle drive: 0.0 maps
        to the low end of the normal speech range (~5 cmH2O), 1.0 to the
        conversational/high end (~10 cmH2O). Setting `active=False` returns the
        lungs to quiet tidal breathing (Ps ≈ 0 for the acoustic layer).
        """
        self._phonating = bool(active)
        self._phonation_effort = max(0.0, min(1.0, float(effort)))
        self._update_subglottal_pressure()
        self.bus.update_ui("lungs", dict(self.state))

    def subglottal_pressure(self) -> float:
        """Current subglottal pressure (cmH2O) — the single source of truth.

        The language module reads this live to derive loudness and pitch, so no
        acoustic state is duplicated across organs.
        """
        return self.state["subglottal_pressure_cmh2o"]

    def _update_subglottal_pressure(self) -> None:
        """Diaphragm/expiratory drive → subglottal pressure.

        When phonating, effort maps linearly across the normal speech range
        (5–10 cmH2O). Alveolar space quality scales the achievable pressure —
        collapsed/fluid-filled spaces (Zhang 2020) weaken the expiratory power
        source and thus the voice.
        """
        if self._phonating:
            span = SUBGLOTTAL_PRESSURE_SPEECH_MAX - SUBGLOTTAL_PRESSURE_SPEECH_MIN
            pressure = SUBGLOTTAL_PRESSURE_SPEECH_MIN + self._phonation_effort * span
            pressure *= self.state["alveolar_space_quality"]  # weakened by poor spaces
        else:
            pressure = SUBGLOTTAL_PRESSURE_REST
        self.state["subglottal_pressure_cmh2o"] = round(pressure, 1)
        self.state["phonating"] = self._phonating

    async def _command_listener(self):
        while True:
            msg = await self.receive()
            if msg.get("signal") not in ("command", "neural_cmd"):
                continue
            cmd = msg.get("cmd")
            if cmd in ("breathe_faster", "breathe_deep"):
                self.breath_interval = max(0.8, self.breath_interval - 0.3)
                self.state["rate"] = "elevated"
            elif cmd == "breathe_normal":
                self.breath_interval = BREATH_NORMAL
                self.state["rate"] = "normal"
            elif cmd == "phonate":
                # Engage voice-driving expiratory effort (0.0–1.0, default 1.0).
                self.set_phonation(True, msg.get("effort", 1.0))
            elif cmd == "stop_phonation":
                self.set_phonation(False)
            self.bus.update_ui("lungs", dict(self.state))
