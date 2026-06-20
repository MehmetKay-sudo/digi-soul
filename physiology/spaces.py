"""
Physiological Space Model
=========================
Based on: Zhang K. (2020) "The Significance of Physiological Spaces in the Body
and Its Medical Implications". Research Article, Beijing Taijitang TCM Hospital.

Key insight: the human body is NOT just solid organs — it is physical structures
PLUS the spaces between them. These spaces are critical for:
  - gas exchange (lungs need alveolar space)
  - blood flow (vessel lumens are spaces)
  - neural transmission (synaptic clefts are spaces)
  - heat regulation (dermal spaces dissipate heat)
  - nutrient/waste transport (interstitial spaces)

When spaces NARROW (cold, stress, fluid imbalance), organ function degrades.
When spaces are healthy, organs perform at peak.

This module tracks space quality across the body and feeds it into the
simulation bus so every organ can respond to its local space conditions.

Reference thresholds from Zhang 2020 §3, §4.4:
  - Cold temperature → tissue contraction → space narrowing → organ compression
  - Adequate hydration → space maintenance
  - Normal metabolism requires space quality > 0.6
"""

import asyncio
import math
import random

from core.organ import Organ

# ── Space zones (anatomical regions, mapped to organ groups) ──────────
SPACE_ZONES = {
    "cranial":    {"organs": ["brain"],               "base_quality": 0.90},
    "thoracic":   {"organs": ["heart", "lungs"],       "base_quality": 0.85},
    "abdominal":  {"organs": ["liver", "kidney",
                               "pancreas", "stomach"], "base_quality": 0.80},
    "pelvic":     {"organs": ["immune_system"],        "base_quality": 0.85},
    "dermal":     {"organs": [],                       "base_quality": 0.75},
}

# Effects
SPACE_NARROW_WARNING = 0.55   # below this → alert
SPACE_CRITICAL       = 0.35   # below this → severe dysfunction


class SpacePhysiology(Organ):
    """
    Monitors and regulates physiological spaces throughout the body.

    Publishes to the bus:
      signal="space_status" with per-zone quality and overall health.

    Organs can query their local space quality and adjust performance.
    """

    def __init__(self, bus, endocrine):
        super().__init__("space_physiology", bus)
        self.endocrine = endocrine
        self.state = {
            "status": "nominal",
            "overall_space_quality": 0.85,
            "zones": {name: cfg["base_quality"]
                      for name, cfg in SPACE_ZONES.items()},
            "temperature_factor": 1.0,      # 1.0 = optimal, <1 = cold
            "hydration_factor": 1.0,        # 1.0 = optimal
            "alert": None,
        }
        self._cycle = 0

    # ── Public API for other organs ───────────────────────────────────

    def space_quality_for(self, organ_name: str) -> float:
        """
        Returns the current space quality (0.0-1.0) for the zone
        containing the given organ. Used by organs to scale their output.
        """
        for zone_name, cfg in SPACE_ZONES.items():
            if organ_name in cfg["organs"]:
                return self.state["zones"].get(zone_name, cfg["base_quality"])
        return 0.80  # default for unknown organs

    # ── Main loop ─────────────────────────────────────────────────────

    async def run(self):
        """Quarter-second cycle updating space dynamics."""
        asyncio.create_task(self._drain_inbox())
        while True:
            await asyncio.sleep(0.25)
            self._cycle += 1

            # 1. Environmental: temperature (simulated seasonal drift)
            temp_raw = 0.5 + 0.5 * math.sin(self._cycle * 0.003)
            self.state["temperature_factor"] = max(0.4, temp_raw)

            # 2. Hydration from kidney fluid_balance (normal=100, range ~80-115)
            kidney = self.bus._organs.get("kidney")
            if kidney:
                fluid = kidney.state.get("fluid_balance", 100)
                self.state["hydration_factor"] = max(0.5, min(1.0, fluid / 100))
            else:
                self.state["hydration_factor"] = 0.85

            # 3. Cortisol (stress) narrows spaces (Zhang 2020 §4.4)
            cortisol = self.endocrine.get_level("cortisol")
            stress_penalty = min(0.35, cortisol / 200)

            # 4. Compute per-zone quality
            for zone_name, cfg in SPACE_ZONES.items():
                base = cfg["base_quality"]
                # Temperature effect — cold narrows spaces (clinical observation)
                thermal = self.state["temperature_factor"]
                # Hydration effect
                hydra   = self.state["hydration_factor"]
                # Stress penalty
                stress  = 1.0 - stress_penalty
                # Random physiological fluctuation (Zhang: spaces are dynamic)
                jitter  = random.uniform(0.97, 1.03)

                quality = base * thermal * hydra * stress * jitter
                self.state["zones"][zone_name] = max(0.1, min(1.0, quality))

            # 5. Overall metric
            self.state["overall_space_quality"] = sum(
                self.state["zones"].values()
            ) / len(self.state["zones"])

            # 6. Alerts
            min_zone = min(self.state["zones"].values())
            if min_zone < SPACE_CRITICAL:
                self.state["status"] = "critical"
                self.state["alert"] = (
                    f"CRITICAL: space narrowing in multiple zones "
                    f"({min_zone:.0%})"
                )
            elif min_zone < SPACE_NARROW_WARNING:
                self.state["status"] = "warning"
                self.state["alert"] = (
                    f"space narrowing detected — "
                    f"worst zone at {min_zone:.0%} quality"
                )
            else:
                self.state["status"] = "nominal"
                self.state["alert"] = None

            # 7. Broadcast every 4 cycles (~1 second)
            if self._cycle % 4 == 0:
                await self.broadcast(
                    signal="space_status",
                    zones=dict(self.state["zones"]),
                    overall=self.state["overall_space_quality"],
                    temperature_factor=self.state["temperature_factor"],
                    hydration_factor=self.state["hydration_factor"],
                )

            self.bus.update_ui("space_physiology", dict(self.state))

    async def _drain_inbox(self):
        """Discard organ broadcasts — SpacePhysiology drives itself from its own cycle."""
        while True:
            await self.inbox.get()
