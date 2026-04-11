import asyncio

from core.organ import Organ

BPM_NORMAL = 60
BPM_MAX = 130
BPM_MIN = 40


class Heart(Organ):
    def __init__(self, bus, bpm: int = BPM_NORMAL):
        super().__init__("heart", bus)
        self.state = {"bpm": bpm, "beats": 0, "status": "beating"}

    async def run(self):
        # Command listener runs concurrently with the beat loop
        asyncio.create_task(self._command_listener())
        while True:
            interval = 60 / self.state["bpm"]
            await asyncio.sleep(interval)
            self.state["beats"] += 1
            await self.broadcast(signal="pulse", beats=self.state["beats"])
            self.bus.update_ui("heart", dict(self.state))

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
                if self.state["bpm"] > BPM_NORMAL + 2:
                    self.state["bpm"] -= 1
                elif self.state["bpm"] < BPM_NORMAL - 2:
                    self.state["bpm"] += 1
                else:
                    self.state["status"] = "beating"
            self.bus.update_ui("heart", dict(self.state))
