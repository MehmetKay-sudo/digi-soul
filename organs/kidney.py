"""
Enhanced Kidney
===============
Based on: Elmas & Kunduracioglu (2025) §2.4 — Kidney functions include:
  - Glomerular filtration rate (GFR ~120 mL/min)
  - RAAS (renin-angiotensin-aldosterone system) for blood pressure
  - Erythropoietin (EPO) production for red blood cell stimulation
  - Fluid & electrolyte balance, acid-base homeostasis

Also: Zhang (2020) — space quality affects filtration efficiency.
"""

import asyncio
import random

from core.organ import Organ


class Kidney(Organ):
    NORMAL_GFR = 120     # mL/min (Elmas 2025 §2.4)
    UREA_MAX = 60        # mg/dL
    UREA_NORMAL = 18     # mg/dL (typical adult reference)
    EXCRETION_EVERY = 10 # beats between excretion events

    # RAAS thresholds (Elmas 2025 §2.4)
    BP_LOW_THRESHOLD  = 85   # mmHg systolic — triggers RAAS
    BP_HIGH_THRESHOLD = 130  # mmHg — suppresses renin

    # Erythropoietin
    EPO_BASE = 10              # mU/mL baseline
    EPO_HYPOXIA_THRESHOLD = 95 # blood O2% below this → EPO boost

    # Blood flow (from vascular_system blood_flow broadcast)
    BASELINE_KIDNEY_FLOW = 20  # % of cardiac output at rest

    def __init__(self, bus, endocrine=None):
        super().__init__("kidney", bus)
        self.endocrine = endocrine
        self._space_physiology = None   # resolved at runtime
        self.state = {
            "status": "filtering",
            "filtration_rate": self.NORMAL_GFR,  # mL/min
            "urea_level": 18,                    # mg/dL
            "fluid_balance": 100,                # percent
            "blood_pressure": "normal",
            "bp_systolic": 120,                  # mmHg — simulated
            "renin_level": 0,                    # RAAS: renin activity (0-100)
            "erythropoietin": self.EPO_BASE,     # mU/mL
            "ph":          7.40,                 # arterial pH — normal 7.35-7.45 (Elmas 2025 §2.4)
            "bicarbonate": 24,                   # mEq/L — renal buffer (normal 22-26)
            "last_action": "—",
        }
        self._beats = 0
        self._last_co2 = 40.0

    async def run(self):
        # Find space physiology organ
        if "space_physiology" in self.bus._organs:
            self._space_physiology = self.bus._organs["space_physiology"]

        asyncio.create_task(self._fluid_regulation())
        asyncio.create_task(self._raas_loop())
        asyncio.create_task(self._acid_base_regulation())

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
                    self.state["filtration_rate"] = min(160, self.state["filtration_rate"] + 10)
                    self.state["last_action"] = "filtering excess glucose"
                    self.state["status"] = "stressed"
                else:
                    self.state["filtration_rate"] = self.NORMAL_GFR
                    self.state["status"] = "filtering"

            elif signal == "oxygen":
                o2  = msg.get("level", 100)
                self._last_co2 = msg.get("co2", self._last_co2)
                if o2 < self.EPO_HYPOXIA_THRESHOLD:
                    # Hypoxia → boost EPO production (Elmas 2025 §2.4)
                    boost = (self.EPO_HYPOXIA_THRESHOLD - o2) * 2
                    self.state["erythropoietin"] = min(50, self.EPO_BASE + boost)
                    self.state["last_action"] = f"hypoxia: EPO ↑ to {self.state['erythropoietin']:.0f}"
                else:
                    self.state["erythropoietin"] = max(self.EPO_BASE,
                                                       self.state["erythropoietin"] - 0.5)

            elif signal == "blood_flow":
                # Renal perfusion scales GFR: fight-or-flight cuts kidney flow → lower GFR
                kidney_flow = msg.get("flows", {}).get("kidneys", self.BASELINE_KIDNEY_FLOW)
                ratio = max(0.3, min(1.2, kidney_flow / self.BASELINE_KIDNEY_FLOW))
                self.state["filtration_rate"] = int(self.NORMAL_GFR * ratio)
                self.state["last_action"] = f"renal flow {kidney_flow}%: GFR={self.state['filtration_rate']}"

            elif signal == "space_status":
                # Zhang 2020: space narrowing reduces filtration efficiency
                quality = msg.get("overall", 1.0)
                if quality < 0.6:
                    penalty = 1.0 - (0.6 - quality) * 1.5
                    self.state["filtration_rate"] = int(self.NORMAL_GFR * max(0.3, penalty))
                    self.state["last_action"] = f"space narrow: GFR ↓ to {self.state['filtration_rate']}"
                    self.state["status"] = "compressed"
                else:
                    self.state["filtration_rate"] = self.NORMAL_GFR

            self.bus.update_ui("kidney", dict(self.state))

    async def _fluid_regulation(self):
        """Manages fluid balance and blood pressure (Elmas 2025 §2.4)."""
        while True:
            await asyncio.sleep(7)
            self.state["fluid_balance"] += random.randint(-6, 6)

            if self.state["fluid_balance"] > 110:
                self.state["fluid_balance"] -= 10
                self.state["last_action"] = "excreting excess fluid"
                self.state["blood_pressure"] = "elevated"
                self.state["bp_systolic"] = min(150, self.state["bp_systolic"] + 3)
            elif self.state["fluid_balance"] < 90:
                self.state["fluid_balance"] += 8
                self.state["last_action"] = "retaining fluid"
                self.state["blood_pressure"] = "low"
                self.state["bp_systolic"] = max(80, self.state["bp_systolic"] - 3)
            else:
                self.state["blood_pressure"] = "normal"
                # Drift toward 120
                self.state["bp_systolic"] += (120 - self.state["bp_systolic"]) * 0.1

            self.bus.update_ui("kidney", dict(self.state))

    async def _raas_loop(self):
        """
        Renin-Angiotensin-Aldosterone System simulation (Elmas 2025 §2.4).
        When BP drops → renin released → angiotensin → aldosterone → fluid retention.
        """
        while True:
            await asyncio.sleep(5)
            bp = self.state["bp_systolic"]

            if bp < self.BP_LOW_THRESHOLD:
                # Activate RAAS: kidney → renin → angiotensin → adrenal → aldosterone
                self.state["renin_level"] = min(100, self.state["renin_level"] + 8)
                self.state["last_action"] = f"RAAS active (renin={self.state['renin_level']:.0f})"
                await self.send("adrenal_gland", signal="raas",
                                renin=self.state["renin_level"])
            elif bp > self.BP_HIGH_THRESHOLD:
                # Suppress renin
                self.state["renin_level"] = max(0, self.state["renin_level"] - 6)
            else:
                # Normal range — slow decay
                self.state["renin_level"] = max(0, self.state["renin_level"] - 2)

            # Aldosterone (secreted by adrenal in response to renin) → Na+ retention → fluid up
            if self.endocrine:
                aldo = self.endocrine.get_level("aldosterone")
                if aldo > 10:
                    self.state["fluid_balance"] = min(115,
                        self.state["fluid_balance"] + aldo * 0.05)
                    self.state["last_action"] = f"aldosterone: Na+ retention ({aldo:.0f}u)"

            self.bus.update_ui("kidney", dict(self.state))

    async def _acid_base_regulation(self):
        """
        Acid-base homeostasis (Elmas 2025 §2.4).
        Simplified Henderson-Hasselbalch: pH shifts with PCO2 from lungs.
        Kidney compensates by retaining or excreting bicarbonate (HCO3).
        Also handles ADH-driven water retention when dehydrated.
        """
        while True:
            await asyncio.sleep(4)

            # Respiratory component: rising CO2 lowers pH (respiratory acidosis)
            co2_deviation = self._last_co2 - 40.0
            # 0.008 per mmHg: every 10 mmHg rise in PCO2 → pH falls ~0.08 (Elmas 2025 §2.4)
            self.state["ph"] = round(
                max(7.10, min(7.60, 7.40 - co2_deviation * 0.008)), 2
            )

            # Renal compensation: adjust bicarbonate to buffer pH
            ph = self.state["ph"]
            if ph < 7.35:
                self.state["bicarbonate"] = min(30, self.state["bicarbonate"] + 0.5)
                self.state["last_action"] = f"retaining HCO₃ (pH {ph})"
            elif ph > 7.45:
                self.state["bicarbonate"] = max(18, self.state["bicarbonate"] - 0.5)
                self.state["last_action"] = f"excreting HCO₃ (pH {ph})"

            if ph < 7.20 or ph > 7.60:
                await self.send("brain", signal="alert",
                                source="kidney", msg=f"acid-base crisis pH={ph}")

            # ADH integration: secrete when dehydrated, respond to circulating ADH
            if self.endocrine:
                if self.state["fluid_balance"] < 92:
                    self.endocrine.secrete("adh", amount=15, source="kidney")
                adh_level = self.endocrine.get_level("adh")
                if adh_level > 20:
                    self.state["fluid_balance"] = min(
                        110, self.state["fluid_balance"] + adh_level * 0.1
                    )
                    self.state["last_action"] = f"ADH water retention ({adh_level:.0f}u)"

            self.bus.update_ui("kidney", dict(self.state))
