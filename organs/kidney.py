import asyncio
import random

from core.organ import Organ


class Kidney(Organ):
    NORMAL_GFR = 120     # mL/min — glomerular filtration rate
    UREA_MAX = 60        # mg/dL
    UREA_NORMAL = 15     # mg/dL
    EXCRETION_EVERY = 10 # beats between excretion events

    def __init__(self, bus):
        super().__init__("kidney", bus)
        self.state = {
            "status": "filtering",
            "filtration_rate": self.NORMAL_GFR,  # mL/min
            "urea_level": 15,                    # mg/dL
            "fluid_balance": 100,                # percent
            "blood_pressure": "normal",
            "last_action": "—",
        }
        self._beats = 0

    async def run(self):
        asyncio.create_task(self._fluid_regulation())
        while True:
            msg = await self.receive()
            signal = msg.get("signal")

            if signal == "pulse":
                self._beats += 1
                self.state["urea_level"] = min(self.UREA_MAX, self.state["urea_level"] + 0.3)

                if self._beats % self.EXCRETION_EVERY == 0:
                    excreted = min(self.state["urea_level"] - self.UREA_NORMAL, 15)
                    self.state["urea_level"] = max(self.UREA_NORMAL,
                                                   self.state["urea_level"] - excreted)
                    self.state["last_action"] = f"excreted {excreted:.1f} mg/dL urea"
                    self.state["status"] = "excreting"
                else:
                    self.state["status"] = "filtering"

            elif signal == "glucose":
                level = msg.get("level", 90)
                if level > 130:
                    # Hyperglycemia — kidneys filter excess glucose
                    self.state["filtration_rate"] = min(160, self.state["filtration_rate"] + 10)
                    self.state["last_action"] = "filtering excess glucose"
                    self.state["status"] = "stressed"
                else:
                    self.state["filtration_rate"] = self.NORMAL_GFR
                    self.state["status"] = "filtering"

            self.bus.update_ui("kidney", dict(self.state))

    async def _fluid_regulation(self):
        """Manages fluid balance and blood pressure."""
        while True:
            await asyncio.sleep(7)
            self.state["fluid_balance"] += random.randint(-6, 6)

            if self.state["fluid_balance"] > 110:
                self.state["fluid_balance"] -= 10
                self.state["last_action"] = "excreting excess fluid"
                self.state["blood_pressure"] = "elevated"
            elif self.state["fluid_balance"] < 90:
                self.state["fluid_balance"] += 8
                self.state["last_action"] = "retaining fluid"
                self.state["blood_pressure"] = "low"
            else:
                self.state["blood_pressure"] = "normal"

            self.bus.update_ui("kidney", dict(self.state))
