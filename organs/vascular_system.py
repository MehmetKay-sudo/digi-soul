"""
Vascular System
===============
Based on: Kong et al. (2026) "Advances and applications of organ-on-a-chip technology"
  — OOC microfluidic channels replicate blood vessel architecture and flow dynamics.
  Key insight: vessels are physiological spaces (Zhang 2020). When thoracic spaces
  narrow, vessel lumens compress → increased peripheral resistance → hypertension.

Also: Elmas & Kunduracioglu (2025) §2.1 — cardiovascular circulation:
  - Blood pressure: systolic (contraction) / diastolic (relaxation)
  - MAP ≈ CO × Total Peripheral Resistance
  - Vasoconstriction (adrenaline) raises BP and redirects flow to muscles
  - Vasodilation lowers resistance → distributes flow to gut/skin

Blood flow distribution (percent of cardiac output, resting):
  brain 20%, heart 5%, lungs 100% (all blood passes through), muscles 15%,
  gut 25%, kidneys 20%, other 15%.
  In fight-or-flight (high adrenaline): muscles ↑, gut ↓ (redistribution).

Signals received:
  - pulse      : BPM from heart (cardiac rate)
  - oxygen     : SpO2 from lungs
  - command    : "vasodilate" | "vasoconstrict"

Signals emitted (broadcast):
  - blood_flow : per-organ flow rates + cardiac output
  - alert (to brain): hypertension / hypotension
"""

import asyncio
import random

from core.organ import Organ

BP_HIGH_SYSTOLIC  = 140   # mmHg — hypertension threshold
BP_LOW_SYSTOLIC   = 90    # mmHg — hypotension threshold
BASE_RESISTANCE   = 1.0   # normalized total peripheral resistance
MONITOR_INTERVAL  = 1.0   # seconds


class VascularSystem(Organ):
    def __init__(self, bus, endocrine):
        super().__init__("vascular_system", bus)
        self.endocrine = endocrine
        self._space_physiology = None
        self._heart            = None
        self.state = {
            "status":            "normal",
            "systolic":          120.0,
            "diastolic":         80.0,
            "pulse_pressure":    40.0,
            "vessel_resistance": BASE_RESISTANCE,
            "cardiac_output":    5.0,    # L/min at rest
            "blood_flow": {
                "brain":   20,
                "heart":   5,
                "lungs":   100,
                "muscles": 15,
                "gut":     25,
                "kidneys": 20,
                "other":   15,
            },
            "o2_saturation": 98,
            "alert":         None,
        }
        self._bpm = 60

    async def run(self):
        if "space_physiology" in self.bus._organs:
            self._space_physiology = self.bus._organs["space_physiology"]
        if "heart" in self.bus._organs:
            self._heart = self.bus._organs["heart"]

        asyncio.create_task(self._vascular_monitor())
        while True:
            msg = await self.receive()
            signal = msg.get("signal")

            if signal == "pulse":
                self._bpm = msg.get("bpm", self._bpm)
            elif signal == "oxygen":
                self.state["o2_saturation"] = msg.get("level", 98)
            elif signal in ("command", "neural_cmd"):
                cmd = msg.get("cmd", "")
                if cmd == "vasodilate":
                    self.state["vessel_resistance"] = max(
                        0.5, self.state["vessel_resistance"] - 0.1
                    )
                elif cmd == "vasoconstrict":
                    self.state["vessel_resistance"] = min(
                        2.5, self.state["vessel_resistance"] + 0.15
                    )

    async def _vascular_monitor(self):
        while True:
            await asyncio.sleep(MONITOR_INTERVAL)

            # Stroke volume from heart if available, else standard 70 mL
            sv = 70.0
            if self._heart:
                sv = self._heart.state.get("stroke_volume", 70.0)

            # Cardiac output (L/min)
            co = (self._bpm * sv) / 1000.0
            self.state["cardiac_output"] = round(co, 2)

            # Adrenaline → vasoconstriction (raises peripheral resistance)
            adr = self.endocrine.get_level("adrenaline")
            adr_factor = 1.0 + adr * 0.008

            # Zhang 2020: thoracic space narrowing compresses great vessels → more resistance
            space_factor = 1.0
            if self._space_physiology:
                thoracic_q = self._space_physiology.state["zones"].get("thoracic", 0.85)
                space_factor = 1.0 + (1.0 - thoracic_q) * 0.4

            resistance = (
                BASE_RESISTANCE * adr_factor * space_factor
                + random.uniform(-0.02, 0.02)
            )
            self.state["vessel_resistance"] = round(resistance, 3)

            # Blood pressure: simplified Ohm's law analog (MAP = CO × TPR)
            # Systolic ≈ 120 × resistance × (CO / 5L baseline)
            systolic  = 120.0 * resistance * (co / 5.0)
            self.state["systolic"]       = round(min(220.0, max(60.0, systolic)), 1)
            self.state["diastolic"]      = round(self.state["systolic"] * 0.67, 1)
            self.state["pulse_pressure"] = round(
                self.state["systolic"] - self.state["diastolic"], 1
            )

            # Fight-or-flight redistribution: muscles ↑, gut ↓
            if adr > 20:
                self.state["blood_flow"]["muscles"] = min(35, 15 + int(adr * 0.4))
                self.state["blood_flow"]["gut"]     = max(10, 25 - int(adr * 0.3))
            else:
                self.state["blood_flow"]["muscles"] = 15
                self.state["blood_flow"]["gut"]     = 25

            # Alerts
            if self.state["systolic"] > BP_HIGH_SYSTOLIC:
                self.state["status"] = "hypertension"
                msg_txt = (
                    f"BP {self.state['systolic']:.0f}/"
                    f"{self.state['diastolic']:.0f} mmHg"
                )
                self.state["alert"] = f"HYPERTENSION: {msg_txt}"
                await self.send("brain", signal="alert",
                                source="vascular_system", msg=msg_txt)
            elif self.state["systolic"] < BP_LOW_SYSTOLIC:
                self.state["status"] = "hypotension"
                self.state["alert"]  = f"HYPOTENSION: {self.state['systolic']:.0f} mmHg"
                await self.send("brain", signal="alert",
                                source="vascular_system",
                                msg=f"low BP {self.state['systolic']:.0f}")
            else:
                self.state["status"] = "normal"
                self.state["alert"]  = None

            # Broadcast blood-flow data so organs can scale delivery efficiency
            await self.broadcast(
                signal="blood_flow",
                flows=dict(self.state["blood_flow"]),
                o2_saturation=self.state["o2_saturation"],
                cardiac_output=self.state["cardiac_output"],
            )

            self.bus.update_ui("vascular_system", dict(self.state))
