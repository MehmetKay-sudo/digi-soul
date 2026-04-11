import asyncio

from core.organ import Organ

THREAT_DANGER = 50     # percent — severe inflammation threshold
PATROL_INTERVAL = 8.0  # seconds between patrol cycles


class ImmuneSystem(Organ):
    """
    Continuous surveillance for biological threats.

    Threat sources:
      - liver alert (high toxin load)
      - explicit 'pathogen' signal (injectable via bus for testing)
      - sustained high cortisol → immunosuppression

    Responses:
      - mild threat  → antibody production, mild inflammation
      - high threat  → cytokine storm, severe inflammation, brain alert
      - immunosuppression (high cortisol) → reduced response
    """

    def __init__(self, bus, endocrine):
        super().__init__("immune_system", bus)
        self.endocrine = endocrine
        self.state = {
            "status":       "surveillance",
            "threat_level": 0,        # 0-100 %
            "white_cells":  100,      # capacity %
            "inflammation": "none",
            "antibodies":   0,
            "last_response": "—",
        }

    async def run(self):
        asyncio.create_task(self._patrol())
        while True:
            msg = await self.receive()
            signal = msg.get("signal")

            if signal == "alert" and msg.get("source") == "liver":
                await self._respond(severity=0.6, cause="liver toxin alert")
            elif signal == "pathogen":
                severity = msg.get("severity", 0.5)
                await self._respond(severity=severity, cause=f"pathogen (sev={severity})")
            elif signal == "glucose":
                # Sustained hyperglycemia impairs immune function
                if msg.get("level", 90) > 140:
                    self.state["white_cells"] = max(50, self.state["white_cells"] - 5)
                    self.state["last_response"] = "hyperglycemia suppressing immunity"
                    self.bus.update_ui("immune_system", dict(self.state))

    async def _respond(self, severity: float, cause: str):
        # Cortisol suppresses immune response
        cortisol = self.endocrine.get_level("cortisol")
        effective_severity = severity * max(0.3, 1 - cortisol / 120)

        self.state["threat_level"] = min(100, self.state["threat_level"] + 20 * effective_severity)
        self.state["white_cells"]  = max(0, self.state["white_cells"] - 8 * effective_severity)
        self.state["antibodies"]   = min(100, self.state["antibodies"] + 5)
        self.state["last_response"] = cause

        if self.state["threat_level"] > THREAT_DANGER:
            self.state["inflammation"] = "severe"
            self.state["status"] = "fighting"
            self.endocrine.secrete("cytokines", amount=20 * effective_severity, source="immune")
            await self.send("brain", signal="alert",
                            source="immune_system",
                            msg=f"threat {self.state['threat_level']:.0f}% — cytokine release")
        elif self.state["threat_level"] > 20:
            self.state["inflammation"] = "mild"
            self.state["status"] = "responding"
        else:
            self.state["inflammation"] = "none"
            self.state["status"] = "surveillance"

        self.bus.update_ui("immune_system", dict(self.state))

    async def _patrol(self):
        """Natural recovery and routine immune surveillance."""
        while True:
            await asyncio.sleep(PATROL_INTERVAL)
            if self.state["threat_level"] > 0:
                self.state["threat_level"] = max(0, self.state["threat_level"] - 12)
                self.state["white_cells"]  = min(100, self.state["white_cells"] + 4)
            if self.state["threat_level"] < 15:
                self.state["inflammation"] = "none"
                self.state["status"] = "surveillance"
            self.bus.update_ui("immune_system", dict(self.state))
