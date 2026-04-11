import asyncio

from core.organ import Organ

GLUCOSE_MIN  = 70    # mg/dL
GLUCOSE_MAX  = 140   # mg/dL
TOXIN_DANGER = 60    # percent


class Liver(Organ):
    def __init__(self, bus):
        super().__init__("liver", bus)
        self.state = {
            "status":         "active",
            "glucose_level":  90,
            "toxin_load":     5,
            "bile_production": "normal",
            "last_action":    "monitoring",
        }
        self._insulin_suppression = False   # pancreas can suppress glucose release

    async def run(self):
        asyncio.create_task(self._glucose_regulation())
        asyncio.create_task(self._detox_cycle())
        while True:
            msg = await self.receive()
            signal = msg.get("signal")

            if signal == "pulse":
                self.state["toxin_load"] = min(100, self.state["toxin_load"] + 0.3)

            elif signal == "nutrient":
                amount = msg.get("amount", 0)
                self.state["glucose_level"] = min(GLUCOSE_MAX,
                                                  self.state["glucose_level"] + amount * 0.4)
                self.state["last_action"]    = f"stored {amount} nutrient units"
                self.state["bile_production"] = "increased"

            elif signal == "hormone":
                hormone = msg.get("hormone")
                level   = msg.get("level", 0)
                if hormone == "insulin" and level > 10:
                    # Insulin → store glucose, suppress release
                    self._insulin_suppression = True
                    self.state["glucose_level"] = max(GLUCOSE_MIN,
                                                      self.state["glucose_level"] - level * 0.3)
                    self.state["last_action"] = f"insulin response — storing glucose"
                elif hormone == "glucagon" and level > 10:
                    # Glucagon → release stored glucose
                    self._insulin_suppression = False
                    self.state["glucose_level"] = min(GLUCOSE_MAX,
                                                      self.state["glucose_level"] + level * 0.4)
                    self.state["last_action"] = "glucagon response — releasing glucose"

            self.bus.update_ui("liver", dict(self.state))

    async def _glucose_regulation(self):
        while True:
            await asyncio.sleep(4)
            self.state["glucose_level"] = max(50, self.state["glucose_level"] - 3)

            if self.state["glucose_level"] < GLUCOSE_MIN and not self._insulin_suppression:
                self.state["glucose_level"] += 15
                self.state["last_action"] = "glycogenolysis — releasing glucose"

            await self.broadcast(signal="glucose", level=self.state["glucose_level"])
            self.bus.update_ui("liver", dict(self.state))

    async def _detox_cycle(self):
        while True:
            await asyncio.sleep(6)
            if self.state["toxin_load"] > 0:
                self.state["toxin_load"] = max(0, self.state["toxin_load"] - 8)
                self.state["last_action"] = "detoxifying blood"
                if self.state["toxin_load"] > TOXIN_DANGER:
                    self.state["status"] = "overloaded"
                    await self.send("brain", signal="alert",
                                   source="liver",
                                   msg=f"toxin load {self.state['toxin_load']:.0f}%")
                else:
                    self.state["status"] = "active"
                    self.state["bile_production"] = "normal"
            self.bus.update_ui("liver", dict(self.state))
