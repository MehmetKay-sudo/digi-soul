import asyncio
from typing import Callable, Optional


class Neuron:
    """
    Biological neuron model with:
      - Membrane potential accumulation from synaptic inputs
      - Threshold-based action potential firing
      - Post-fire refractory reset
      - Passive potential decay (leaky integrator)
      - Modifiable threshold (for sleep/wake cycles)
    """

    def __init__(self, name: str, threshold: float = 1.0, decay_rate: float = 0.05):
        self.name = name
        self._base_threshold = threshold   # stored for sleep/wake reset
        self.threshold = threshold
        self.decay_rate = decay_rate
        self.potential = 0.0
        self.fire_count = 0
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.synapses_out: list = []
        self.on_fire: Optional[Callable] = None   # async callback(neuron)

    async def run(self):
        asyncio.create_task(self._decay_loop())
        while True:
            msg = await self.inbox.get()
            strength = msg.get("strength", 1.0)
            self.potential = max(0.0, self.potential + strength)   # inhibitory → can't go negative
            if self.potential >= self.threshold:
                await self._fire()

    async def _fire(self):
        self.fire_count += 1
        self.potential = 0.0   # refractory reset
        if self.on_fire:
            await self.on_fire(self)
        for synapse in self.synapses_out:
            asyncio.create_task(synapse.transmit())

    async def _decay_loop(self):
        """Leaky integrator — potential slowly fades without input."""
        while True:
            await asyncio.sleep(0.5)
            if self.potential > 0:
                self.potential = max(0.0, self.potential - self.decay_rate)
