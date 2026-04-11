import asyncio
import math
import queue


# Compressed half-lives (seconds) — real biology is hours/minutes,
# shortened here so changes are visible in a live demo.
HORMONE_HALF_LIVES: dict[str, float] = {
    "adrenaline": 12,   # epinephrine — short burst
    "cortisol":   60,   # sustained stress
    "insulin":    25,   # glucose uptake signal
    "glucagon":   25,   # glucose release signal
    "melatonin": 120,   # sleep induction
    "cytokines":  40,   # immune inflammatory signal
}

# Maximum circulating level (arbitrary units, 0-100)
HORMONE_MAX = 100.0


class EndocrineBus:
    """
    Slow hormonal communication channel.

    Unlike the fast neural MessageBus, hormones:
      - persist in the bloodstream with a half-life
      - are sensed by any organ that queries the bus
      - decay exponentially over time

    Usage:
        endocrine.secrete("insulin", amount=20, source="pancreas")
        level = endocrine.get_level("insulin")
    """

    def __init__(self):
        self._levels: dict[str, float] = {h: 0.0 for h in HORMONE_HALF_LIVES}
        self.ui_queue: queue.Queue = queue.Queue()   # → canvas endocrine panel

    # ------------------------------------------------------------------
    # API for organs
    # ------------------------------------------------------------------

    def secrete(self, hormone: str, amount: float, source: str = "?"):
        if hormone not in self._levels:
            self._levels[hormone] = 0.0
        self._levels[hormone] = min(HORMONE_MAX, self._levels[hormone] + amount)

    def get_level(self, hormone: str) -> float:
        return round(self._levels.get(hormone, 0.0), 2)

    def get_all(self) -> dict[str, float]:
        return {h: round(v, 2) for h, v in self._levels.items()}

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    async def run(self):
        """Decay loop — runs every second, halves levels according to half-life."""
        while True:
            await asyncio.sleep(1.0)
            for hormone, half_life in HORMONE_HALF_LIVES.items():
                # Exponential decay: N(t) = N0 * e^(-λt), λ = ln2 / t½
                decay_factor = math.exp(-math.log(2) / half_life)
                self._levels[hormone] = max(0.0, self._levels[hormone] * decay_factor)
            self.ui_queue.put_nowait(self.get_all())
