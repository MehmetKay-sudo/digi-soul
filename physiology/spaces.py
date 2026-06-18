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

Meridian pathways (Zhang 2020 §4.3):
  "Meridians are relatively stable and relatively orderly spaces in the body."
  In Western terms: anatomically adjacent zones share fascial pathways. Narrowing
  in one zone propagates partial narrowing to anatomically connected zones.

  Implemented as weighted adjacency: when zone A is significantly worse than its
  neighbour B, B is pulled down by coupling × deficit × propagation_factor.

  Adjacency map (anatomical connections):
    cranial   ↔  thoracic   (cervicothoracic fascial junction)
    thoracic  ↔  abdominal  (diaphragm / thoracoabdominal fascia)
    abdominal ↔  pelvic     (iliopsoas / pelvic floor)
    pelvic    ↔  dermal     (superficial fascia of thighs)

ADH integration (Elmas 2025 §2.4):
  Antidiuretic hormone released by kidney/hypothalamus promotes water retention,
  improving interstitial hydration → better space maintenance.
"""

import asyncio
import math
import random

from core.organ import Organ

# ── Space zones ──────────────────────────────────────────────────────────────
SPACE_ZONES: dict[str, dict] = {
    "cranial":   {"organs": ["brain"],                         "base_quality": 0.90},
    "thoracic":  {"organs": ["heart", "lungs", "vascular_system"], "base_quality": 0.85},
    "abdominal": {"organs": ["liver", "kidney", "pancreas",
                              "stomach"],                       "base_quality": 0.80},
    "pelvic":    {"organs": ["immune_system"],                  "base_quality": 0.85},
    "dermal":    {"organs": ["muscular_system"],                "base_quality": 0.75},
}

# Meridian adjacency: zone → [(neighbour, coupling_strength)]
# Coupling 0-1: how strongly narrowing in a neighbour pulls this zone down.
MERIDIAN_ADJACENCY: dict[str, list[tuple[str, float]]] = {
    "cranial":   [("thoracic",  0.25)],
    "thoracic":  [("cranial",   0.25), ("abdominal", 0.35)],
    "abdominal": [("thoracic",  0.35), ("pelvic",    0.25)],
    "pelvic":    [("abdominal", 0.25), ("dermal",    0.18)],
    "dermal":    [("pelvic",    0.18)],
}

MERIDIAN_PROPAGATION = 0.18   # fraction of deficit transmitted per update cycle

SPACE_NARROW_WARNING = 0.55
SPACE_CRITICAL       = 0.35


class SpacePhysiology(Organ):
    """
    Monitors and regulates physiological spaces throughout the body.

    New in this version:
      - Meridian propagation: narrowing in one zone diffuses to adjacent zones
      - ADH integration: antidiuretic hormone from endocrine bus improves hydration
      - Zone pressure tracking (proxy for fluid accumulation)
      - Kidney fluid-balance signal updates hydration factor directly
    """

    def __init__(self, bus, endocrine):
        super().__init__("space_physiology", bus)
        self.endocrine = endocrine
        self.state = {
            "status":               "nominal",
            "overall_space_quality": 0.85,
            "zones":    {name: cfg["base_quality"] for name, cfg in SPACE_ZONES.items()},
            "zone_pressure": {name: 0.0 for name in SPACE_ZONES},  # 0=normal, >0=compressed
            "temperature_factor": 1.0,
            "hydration_factor":   1.0,
            "alert":              None,
            "meridian_active":    False,   # True when propagation is dampening any zone
        }
        self._cycle           = 0
        self._kidney_fluid    = 100.0   # updated via bus signal

    # ── Public API ────────────────────────────────────────────────────────

    def space_quality_for(self, organ_name: str) -> float:
        for zone_name, cfg in SPACE_ZONES.items():
            if organ_name in cfg["organs"]:
                return self.state["zones"].get(zone_name, cfg["base_quality"])
        return 0.80

    # ── Main loop ─────────────────────────────────────────────────────────

    async def run(self):
        asyncio.create_task(self._drain_inbox())
        while True:
            await asyncio.sleep(0.25)
            self._cycle += 1

            # 1. Environmental: temperature (simulated seasonal/circadian drift)
            temp_raw = 0.5 + 0.5 * math.sin(self._cycle * 0.003)
            self.state["temperature_factor"] = max(0.4, temp_raw)

            # 2. Hydration: blend kidney fluid balance + ADH from endocrine bus
            adh = self.endocrine.get_level("adh")
            adh_bonus = min(0.15, adh / 200)   # ADH retains water → improves hydration
            base_hydration = 0.7 + 0.3 * (
                0.5 + 0.5 * math.sin(self._cycle * 0.005)
            )
            # Kidney fluid balance (100 = optimal): scale it to [0,1]
            kidney_factor = max(0.4, min(1.0, self._kidney_fluid / 100))
            self.state["hydration_factor"] = min(1.0, base_hydration * kidney_factor + adh_bonus)

            # 3. Cortisol (chronic stress) narrows spaces (Zhang 2020 §4.4)
            cortisol       = self.endocrine.get_level("cortisol")
            stress_penalty = min(0.35, cortisol / 200)

            # 4. Compute raw per-zone quality (independent physiology)
            raw: dict[str, float] = {}
            for zone_name, cfg in SPACE_ZONES.items():
                base    = cfg["base_quality"]
                thermal = self.state["temperature_factor"]
                hydra   = self.state["hydration_factor"]
                stress  = 1.0 - stress_penalty
                jitter  = random.uniform(0.97, 1.03)
                q = base * thermal * hydra * stress * jitter
                raw[zone_name] = max(0.1, min(1.0, q))

            # 5. Meridian propagation: adjacent narrowing diffuses across zones
            propagated = dict(raw)
            meridian_active = False
            for zone, neighbours in MERIDIAN_ADJACENCY.items():
                for neighbour, coupling in neighbours:
                    deficit = propagated[zone] - propagated[neighbour]
                    if deficit > 0.08:   # only propagate meaningful differences
                        pull = deficit * coupling * MERIDIAN_PROPAGATION
                        propagated[zone] = max(0.1, propagated[zone] - pull)
                        meridian_active = True

            self.state["zones"]           = propagated
            self.state["meridian_active"] = meridian_active

            # 6. Zone pressure (proxy: worse quality → higher compression pressure)
            for zone in SPACE_ZONES:
                q = propagated[zone]
                # Pressure rises as quality falls below normal (0.8)
                self.state["zone_pressure"][zone] = round(max(0.0, (0.8 - q) * 25), 2)

            # 7. Overall metric
            self.state["overall_space_quality"] = round(
                sum(propagated.values()) / len(propagated), 4
            )

            # 8. Alerts
            min_zone = min(propagated.values())
            worst_name = min(propagated, key=propagated.get)
            if min_zone < SPACE_CRITICAL:
                self.state["status"] = "critical"
                self.state["alert"] = (
                    f"CRITICAL: {worst_name} space narrowing ({min_zone:.0%})"
                )
            elif min_zone < SPACE_NARROW_WARNING:
                self.state["status"] = "warning"
                self.state["alert"] = (
                    f"space narrowing detected — {worst_name} at {min_zone:.0%} quality"
                )
            else:
                self.state["status"] = "nominal"
                self.state["alert"]  = None

            # 9. Broadcast every 4 cycles (~1 second)
            if self._cycle % 4 == 0:
                await self.broadcast(
                    signal="space_status",
                    zones=dict(propagated),
                    overall=self.state["overall_space_quality"],
                    temperature_factor=self.state["temperature_factor"],
                    hydration_factor=self.state["hydration_factor"],
                    meridian_active=meridian_active,
                )

            self.bus.update_ui("space_physiology", dict(self.state))

    async def _drain_inbox(self):
        """Listen for kidney fluid balance updates; discard everything else."""
        while True:
            msg = await self.inbox.get()
            # Pick up kidney fluid balance so hydration tracks real organ state
            if msg.get("signal") == "kidney_status":
                self._kidney_fluid = msg.get("fluid_balance", self._kidney_fluid)
