import asyncio
import random

from core.organ import Organ


class Stomach(Organ):
    DIGEST_INTERVAL = 8.0  # seconds per digestion cycle

    def __init__(self, bus):
        super().__init__("stomach", bus)
        self.state = {
            "status": "idle",
            "fullness": 70,           # percent
            "acid_level": "normal",
            "digestion_phase": "resting",
            "nutrients_produced": 0,
        }

    async def run(self):
        while True:
            if self.state["fullness"] > 10:
                await self._digest()
            else:
                # Simulate eating
                self.state["status"] = "hungry"
                self.state["digestion_phase"] = "empty"
                self.bus.update_ui("stomach", dict(self.state))
                await asyncio.sleep(2)
                self.state["fullness"] = random.randint(50, 100)
                self.state["status"] = "eating"
                self.bus.update_ui("stomach", dict(self.state))
                await asyncio.sleep(1)

    async def _digest(self):
        self.state["status"] = "digesting"
        self.state["digestion_phase"] = "active"
        self.state["acid_level"] = "high"
        self.bus.update_ui("stomach", dict(self.state))

        await asyncio.sleep(self.DIGEST_INTERVAL)

        nutrient_amount = int(self.state["fullness"] * 0.3)
        self.state["fullness"] = max(0, self.state["fullness"] - 30)
        self.state["nutrients_produced"] += nutrient_amount
        self.state["digestion_phase"] = "absorbing"
        self.state["acid_level"] = "normal"
        self.state["status"] = "absorbing"

        await self.send("liver", signal="nutrient", amount=nutrient_amount)
        self.bus.update_ui("stomach", dict(self.state))
