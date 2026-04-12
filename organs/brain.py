from core.organ import Organ

OXYGEN_LOW   = 96
GLUCOSE_LOW  = 65
GLUCOSE_HIGH = 130


class Brain(Organ):
    def __init__(self, bus):
        super().__init__("brain", bus)
        self.state = {
            "status":         "active",
            "pulses_received": 0,
            "oxygen_level":   100,
            "glucose_level":  90,
            "sleep_mode":     False,
            "last_signal":    "—",
            "alert":          None,
        }

    async def run(self):
        while True:
            msg = await self.receive()
            signal = msg.get("signal")

            if signal == "pulse":
                self.state["pulses_received"] += 1
                self.state["last_signal"] = f"pulse #{self.state['pulses_received']}"

            elif signal == "oxygen":
                level = msg.get("level", 100)
                self.state["oxygen_level"] = level
                self.state["last_signal"] = f"O2={level}%"
                if level < OXYGEN_LOW:
                    self.state["alert"] = f"LOW O2: {level}%"
                    await self.send("heart", signal="command", cmd="increase_bpm")
                    await self.send("lungs", signal="command", cmd="breathe_faster")
                else:
                    if self.state["alert"] and "O2" in str(self.state["alert"]):
                        self.state["alert"] = None
                        await self.send("heart", signal="command", cmd="regulate")
                        await self.send("lungs", signal="command", cmd="breathe_normal")

            elif signal == "glucose":
                level = msg.get("level", 90)
                self.state["glucose_level"] = level
                self.state["last_signal"] = f"glucose={level} mg/dL"
                if level < GLUCOSE_LOW:
                    self.state["alert"] = f"LOW GLUCOSE: {level} mg/dL"
                elif level > GLUCOSE_HIGH:
                    self.state["alert"] = f"HIGH GLUCOSE: {level} mg/dL"
                else:
                    if self.state["alert"] and "GLUCOSE" in str(self.state["alert"]):
                        self.state["alert"] = None

            elif signal == "alert":
                source = msg.get("source", "?")
                self.state["alert"] = f"[{source.upper()}] {msg.get('msg', '')}"
                self.state["last_signal"] = f"alert from {source}"

            elif signal == "circadian":
                mode = msg.get("mode", "wake")
                self.state["sleep_mode"] = (mode == "sleep")
                self.state["status"] = "sleeping" if mode == "sleep" else "active"
                self.state["last_signal"] = f"circadian → {mode}"

            elif signal == "language_result":
                cmd    = msg.get("cmd", "?")
                result = msg.get("result", {})
                if result.get("ok"):
                    self.state["last_signal"] = f"lang/{cmd} ok"
                    if cmd == "speak" and result.get("text"):
                        spoken = result["text"]
                        self.state["last_signal"] = f"spoke: {spoken[:60]}{'…' if len(spoken) > 60 else ''}"
                else:
                    self.state["alert"] = f"[LANG] {result.get('error', 'unknown error')}"
                    self.state["last_signal"] = f"lang/{cmd} error"

            self.bus.update_ui("brain", dict(self.state))
