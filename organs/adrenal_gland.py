import asyncio

from core.organ import Organ

ADRENALINE_THRESHOLD = 5   # below this → calm
CORTISOL_THRESHOLD   = 10


class AdrenalGland(Organ):
    """
    Releases adrenaline (epinephrine) on acute stress and cortisol on sustained stress.

    Triggers:
      - brain alert signal
      - oxygen below 90 %
      - high toxin load alert from liver

    Effects:
      - heart: increase BPM
      - lungs: breathe faster
      - endocrine: adrenaline + cortisol surge
    """

    def __init__(self, bus, endocrine):
        super().__init__("adrenal_gland", bus)
        self.endocrine = endocrine
        self.state = {
            "mode": "rest",
            "adrenaline": 0.0,
            "cortisol":   round(endocrine.get_level("cortisol"), 1),
            "last_trigger": "—",
        }

    async def run(self):
        asyncio.create_task(self._level_monitor())
        while True:
            msg = await self.receive()
            signal = msg.get("signal")

            if signal == "alert":
                await self._activate(msg, intensity=1.0)

            elif signal == "oxygen":
                if msg.get("level", 100) < 90:
                    await self._activate(msg, intensity=0.6)

            elif signal == "pulse":
                # Monitor for tachycardia (BPM already handled by brain, but adrenal reacts too)
                pass

    async def _activate(self, trigger_msg, intensity: float = 1.0):
        adr_amount = round(30 * intensity, 1)
        crt_amount = round(12 * intensity, 1)
        self.endocrine.secrete("adrenaline", amount=adr_amount, source="adrenal_gland")
        self.endocrine.secrete("cortisol",   amount=crt_amount, source="adrenal_gland")

        self.state["mode"] = "fight-or-flight"
        self.state["last_trigger"] = trigger_msg.get("signal", "?")
        self._sync_levels()

        # Cascade to organs
        await self.send("heart", signal="command",  cmd="increase_bpm")
        await self.send("lungs", signal="command",  cmd="breathe_faster")
        await self.send("brain", signal="alert",
                        source="adrenal_gland", msg=f"adrenaline surge ({adr_amount}u)")
        self.bus.update_ui("adrenal_gland", dict(self.state))

    async def _level_monitor(self):
        while True:
            await asyncio.sleep(3)
            self._sync_levels()
            adr = self.endocrine.get_level("adrenaline")
            if adr < ADRENALINE_THRESHOLD and self.endocrine.get_level("cortisol") < CORTISOL_THRESHOLD:
                self.state["mode"] = "rest"
            self.bus.update_ui("adrenal_gland", dict(self.state))

    def _sync_levels(self):
        self.state["adrenaline"] = round(self.endocrine.get_level("adrenaline"), 1)
        self.state["cortisol"]   = round(self.endocrine.get_level("cortisol"),   1)
