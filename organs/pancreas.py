import asyncio

from core.organ import Organ

GLUCOSE_HIGH = 110   # mg/dL — triggers insulin
GLUCOSE_LOW = 70     # mg/dL — triggers glucagon


class Pancreas(Organ):
    def __init__(self, bus, endocrine):
        super().__init__("pancreas", bus)
        self.endocrine = endocrine
        self.state = {
            "status": "monitoring",
            "insulin":  round(endocrine.get_level("insulin"), 1),
            "glucagon": round(endocrine.get_level("glucagon"), 1),
            "last_action": "—",
        }

    async def run(self):
        asyncio.create_task(self._hormone_monitor())
        while True:
            msg = await self.receive()
            if msg.get("signal") != "glucose":
                continue

            level = msg.get("level", 90)

            if level > GLUCOSE_HIGH:
                amount = min(25, (level - GLUCOSE_HIGH) * 0.8)
                self.endocrine.secrete("insulin", amount=amount, source="pancreas")
                # Tell liver to store glucose, not release it
                await self.send("liver", signal="hormone",
                                hormone="insulin", level=self.endocrine.get_level("insulin"))
                self.state["last_action"] = f"secreted insulin ({amount:.1f}u) — glucose={level}"
                self.state["status"] = "secreting insulin"

            elif level < GLUCOSE_LOW:
                amount = min(20, (GLUCOSE_LOW - level) * 0.9)
                self.endocrine.secrete("glucagon", amount=amount, source="pancreas")
                await self.send("liver", signal="hormone",
                                hormone="glucagon", level=self.endocrine.get_level("glucagon"))
                self.state["last_action"] = f"secreted glucagon ({amount:.1f}u) — glucose={level}"
                self.state["status"] = "secreting glucagon"

            else:
                self.state["status"] = "monitoring"

            self._sync_hormone_state()
            self.bus.update_ui("pancreas", dict(self.state))

    async def _hormone_monitor(self):
        """Refresh displayed hormone levels every 2 s (endocrine bus decays continuously)."""
        while True:
            await asyncio.sleep(2)
            self._sync_hormone_state()
            self.bus.update_ui("pancreas", dict(self.state))

    def _sync_hormone_state(self):
        self.state["insulin"]  = round(self.endocrine.get_level("insulin"), 1)
        self.state["glucagon"] = round(self.endocrine.get_level("glucagon"), 1)
