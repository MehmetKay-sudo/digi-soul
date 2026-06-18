"""
Muscular System
===============
Based on: Elmas & Kunduracioglu (2025) §2.2 — locomotor system:
  - Skeletal muscles enable movement, posture, and locomotion
  - Muscle contraction consumes ATP (requires glucose + oxygen)
  - Fatigue accumulates with sustained exertion; rest allows recovery
  - Adrenaline boosts strength and delays fatigue onset

Muscle groups modeled:
  - locomotion : leg muscles → maps to motor speed
  - arms       : shoulder/hand servos for manipulation
  - posture    : core/neck stability for balance

Signals received:
  - command / neural_cmd : "contract_locomotion" | "contract_arms" |
                            "activate_posture" | "relax"
  - oxygen               : O2 level affects endurance capacity
  - glucose              : energy substrate — low glucose = reduced power
  - circadian            : sleep → all groups relax

Signals emitted:
  - muscle_status (broadcast): fatigue map, activity level
  - alert (to brain)          : when any group exceeds FATIGUE_ALERT

Space integration (Zhang 2020):
  Dermal spaces surround skeletal muscle. Narrowed dermal spaces reduce
  interstitial fluid exchange, accelerating metabolic waste accumulation
  and fatigue.
"""

import asyncio

from core.organ import Organ

FATIGUE_ALERT   = 80.0   # percent — triggers brain alert
FATIGUE_RATE    = 8.0    # percent per second while active
RECOVERY_RATE   = 2.0    # percent per second while resting
MUSCLE_GROUPS   = ("locomotion", "arms", "posture")


class MuscularSystem(Organ):
    def __init__(self, bus, endocrine):
        super().__init__("muscular_system", bus)
        self.endocrine = endocrine
        self._space_physiology = None
        self.state = {
            "status":         "idle",
            "activity_level": 0,
            "fatigue": {g: 0.0 for g in MUSCLE_GROUPS},
            "strength_boost": 0.0,    # adrenaline-driven
            "glucose_level":  90,
            "oxygen_level":   100,
            "last_action":    "—",
            "alert":          None,
        }
        self._active: set[str] = set()

    async def run(self):
        if "space_physiology" in self.bus._organs:
            self._space_physiology = self.bus._organs["space_physiology"]
        asyncio.create_task(self._fatigue_loop())
        while True:
            msg = await self.receive()
            signal = msg.get("signal")

            if signal in ("command", "neural_cmd"):
                await self._handle_command(msg.get("cmd", ""))
            elif signal == "oxygen":
                self.state["oxygen_level"] = msg.get("level", 100)
            elif signal == "glucose":
                self.state["glucose_level"] = msg.get("level", 90)
            elif signal == "circadian":
                if msg.get("mode") == "sleep":
                    self._active.clear()
                    self.state["status"]         = "idle"
                    self.state["activity_level"] = 0
                    self.state["last_action"]    = "sleep — all groups relaxed"

            self.bus.update_ui("muscular_system", dict(self.state))

    async def _handle_command(self, cmd: str):
        if cmd == "contract_locomotion":
            self._active.add("locomotion")
            self.state["status"]      = "active"
            self.state["last_action"] = "locomotion active"
        elif cmd == "contract_arms":
            self._active.add("arms")
            self.state["status"]      = "active"
            self.state["last_action"] = "arms contracting"
        elif cmd == "activate_posture":
            self._active.add("posture")
            self.state["last_action"] = "posture engaged"
        elif cmd == "relax":
            self._active.clear()
            self.state["status"]         = "idle"
            self.state["activity_level"] = 0
            self.state["last_action"]    = "relaxed"
        self.bus.update_ui("muscular_system", dict(self.state))

    async def _fatigue_loop(self):
        while True:
            await asyncio.sleep(1.0)

            adr = self.endocrine.get_level("adrenaline")
            self.state["strength_boost"] = round(min(50.0, adr * 0.8), 1)

            # Availability factors (low O2 / glucose → faster fatigue, slower recovery)
            o2_factor  = max(0.1, self.state["oxygen_level"] / 100)
            glc_factor = max(0.1, min(1.0, self.state["glucose_level"] / 90))

            # Space quality: dermal zone affects metabolic waste clearance
            space_q = 1.0
            if self._space_physiology:
                space_q = self._space_physiology.space_quality_for("muscular_system")
            space_q = max(0.1, space_q)

            activity = 0
            for group in MUSCLE_GROUPS:
                if group in self._active:
                    # Adrenaline slightly delays fatigue (boosts effective capacity)
                    adr_bonus = 1.0 + self.state["strength_boost"] / 200
                    eff_rate  = FATIGUE_RATE / (o2_factor * glc_factor * space_q * adr_bonus)
                    self.state["fatigue"][group] = min(100.0,
                        self.state["fatigue"][group] + eff_rate)
                    activity += 33
                else:
                    # Adrenaline slightly slows recovery (residual muscle tension)
                    rec = RECOVERY_RATE * (1.0 - 0.2 * (adr / 100))
                    self.state["fatigue"][group] = max(0.0,
                        self.state["fatigue"][group] - rec)

            self.state["activity_level"] = activity

            # Alert if any group is critically fatigued
            max_fatigue = max(self.state["fatigue"].values())
            if max_fatigue > FATIGUE_ALERT:
                self.state["alert"] = f"FATIGUE {max_fatigue:.0f}%"
                await self.send("brain", signal="alert",
                                source="muscular_system",
                                msg=f"muscle fatigue {max_fatigue:.0f}%")
            else:
                self.state["alert"] = None

            if not self._active and max_fatigue < 10:
                self.state["status"] = "idle"

            self.bus.update_ui("muscular_system", dict(self.state))
