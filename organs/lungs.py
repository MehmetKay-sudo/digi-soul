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
"""

import asyncio

from core.organ import Organ

BREATH_NORMAL = 2.0  # seconds per phase (15 breaths/min)


class Lungs(Organ):
    def __init__(self, bus, breath_interval: float = BREATH_NORMAL):
        super().__init__("lungs", bus)
        self._space_physiology = None
        self.breath_interval = breath_interval
        self.state = {
            "phase": "inhale",
            "cycles": 0,
            "oxygen_level": 100,
            "alveolar_space_quality": 1.0,
            "tidal_volume_ml": 500,     # mL — typical adult
            "status": "breathing",
            "rate": "normal",
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
            self.bus.update_ui("lungs", dict(self.state))
            await asyncio.sleep(self.breath_interval)

            # Exhale
            self.state["phase"] = "exhale"
            self.state["cycles"] += 1
            self.state["oxygen_level"] = 90 + int(o2_efficiency * 15)
            await self.broadcast(signal="oxygen", level=self.state["oxygen_level"],
                                 space_quality=space_q)
            self.bus.update_ui("lungs", dict(self.state))
            await asyncio.sleep(self.breath_interval)

    def _get_space_quality(self) -> float:
        if self._space_physiology:
            return self._space_physiology.space_quality_for("lungs")
        return 1.0

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
            self.bus.update_ui("lungs", dict(self.state))
