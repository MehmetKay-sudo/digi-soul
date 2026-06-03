"""
Enhanced Heart
==============
Based on: Elmas & Kunduracioglu (2025) §2.2 — detailed cardiac physiology:
  - 4 chambers: atria collect, ventricles pump
  - Sinoatrial (SA) node generates rhythmic electrical impulses
  - Average 60-100 bpm, ~100,000 beats/day, pumps ~7,500L blood/day
  - Left ventricle has the strongest muscular wall

Added space-awareness from Zhang (2020): thoracic space quality affects
cardiac output and stroke volume.
"""

import asyncio

from core.organ import Organ

# Medical reference ranges (Elmas 2025 §2.2)
BPM_NORMAL_MIN = 60
BPM_NORMAL_MAX = 100
BPM_MAX = 130
BPM_MIN = 40
STROKE_VOLUME_ML = 70      # mL per beat at rest
CARDIAC_OUTPUT_L_DAY = 7500  # liters per day (medical reference)


class Heart(Organ):
    def __init__(self, bus, bpm: int = BPM_NORMAL_MIN):
        super().__init__("heart", bus)
        self._space_physiology = None
        self.state = {
            "bpm": bpm,
            "beats": 0,
            "status": "beating",
            "sa_node_active": True,      # SA node = natural pacemaker
            "stroke_volume": STROKE_VOLUME_ML,
            "cardiac_output_today": 0.0, # simulated cumulative L
            "thoracic_space_quality": 1.0,
        }

    async def run(self):
        if "space_physiology" in self.bus._organs:
            self._space_physiology = self.bus._organs["space_physiology"]

        asyncio.create_task(self._command_listener())
        asyncio.create_task(self._sa_node_regulation())

        while True:
            interval = 60 / self.state["bpm"]
            await asyncio.sleep(interval)
            self.state["beats"] += 1

            # Space quality affects stroke volume (Zhang 2020)
            space_q = self._get_space_quality()
            self.state["thoracic_space_quality"] = space_q
            effective_sv = STROKE_VOLUME_ML * (0.4 + 0.6 * space_q)

            self.state["stroke_volume"] = round(effective_sv, 1)
            self.state["cardiac_output_today"] += effective_sv * 0.001  # simulate L/day

            await self.broadcast(signal="pulse",
                                 beats=self.state["beats"],
                                 bpm=self.state["bpm"])
            self.bus.update_ui("heart", dict(self.state))

    def _get_space_quality(self) -> float:
        if self._space_physiology:
            return self._space_physiology.space_quality_for("heart")
        return 1.0

    async def _command_listener(self):
        while True:
            msg = await self.receive()
            if msg.get("signal") not in ("command", "neural_cmd"):
                continue
            cmd = msg.get("cmd")
            if cmd == "increase_bpm":
                self.state["bpm"] = min(BPM_MAX, self.state["bpm"] + 5)
                self.state["status"] = "accelerating"
            elif cmd == "decrease_bpm":
                self.state["bpm"] = max(BPM_MIN, self.state["bpm"] - 5)
                self.state["status"] = "decelerating"
            elif cmd == "regulate":
                # SA node tries to return to normal sinus rhythm (60-100 bpm)
                if self.state["bpm"] > BPM_NORMAL_MAX:
                    self.state["bpm"] -= 1
                elif self.state["bpm"] < BPM_NORMAL_MIN:
                    self.state["bpm"] += 1
                else:
                    self.state["status"] = "beating"
            self.bus.update_ui("heart", dict(self.state))

    async def _sa_node_regulation(self):
        """
        SA node (sinus-atrial) natural regulation.
        The SA node produces regular electrical signals that pace the heart
        (Elmas 2025 §2.2). Simulated as gradual drift toward normal rhythm.
        """
        while True:
            await asyncio.sleep(2)
            if self.state["sa_node_active"]:
                # Gentle drift toward normal resting HR
                target = BPM_NORMAL_MIN + (BPM_NORMAL_MAX - BPM_NORMAL_MIN) * 0.3  # ~72 bpm
                diff = target - self.state["bpm"]
                if abs(diff) > 1:
                    self.state["bpm"] += diff * 0.1
                    self.state["bpm"] = round(self.state["bpm"])
            self.bus.update_ui("heart", dict(self.state))
