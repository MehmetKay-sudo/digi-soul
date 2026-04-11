import asyncio

from core.organ import Organ

BREATH_NORMAL = 2.0  # seconds per phase


class Lungs(Organ):
    def __init__(self, bus, breath_interval: float = BREATH_NORMAL):
        super().__init__("lungs", bus)
        self.breath_interval = breath_interval
        self.state = {
            "phase": "inhale",
            "cycles": 0,
            "oxygen_level": 100,
            "status": "breathing",
            "rate": "normal",
        }

    async def run(self):
        asyncio.create_task(self._command_listener())
        while True:
            # Inhale
            self.state["phase"] = "inhale"
            self.bus.update_ui("lungs", dict(self.state))
            await asyncio.sleep(self.breath_interval)

            # Exhale
            self.state["phase"] = "exhale"
            self.state["cycles"] += 1
            self.state["oxygen_level"] = 95 + (self.state["cycles"] % 6)
            await self.broadcast(signal="oxygen", level=self.state["oxygen_level"])
            self.bus.update_ui("lungs", dict(self.state))
            await asyncio.sleep(self.breath_interval)

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
