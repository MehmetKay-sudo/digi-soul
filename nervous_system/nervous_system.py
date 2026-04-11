import asyncio

from nervous_system.neuron import Neuron
from nervous_system.synapse import Synapse

# Compressed sleep/wake cycle (seconds) — real circadian rhythm is 24h
WAKE_DURATION  = 90    # seconds awake
SLEEP_DURATION = 45    # seconds asleep

# During sleep, neuron thresholds are multiplied by this factor
SLEEP_THRESHOLD_FACTOR = 2.2


class NervousSystem:
    """
    Neural network of Neurons connected by Synapses.

    Features:
      - Sensory transduction: listens to organ broadcasts, stimulates sensory neurons
      - Motor output: motor neuron on_fire callbacks send commands to organs via bus
      - Long-term potentiation: synapses strengthen with repeated use
      - Sleep/wake cycle: compressed circadian oscillator modulates neuron thresholds
      - Inhibitory circuits: negative-weight synapses suppress downstream neurons

    Registers with MessageBus as "nervous_system" to receive all organ broadcasts.
    """

    def __init__(self, bus, endocrine=None):
        self.bus = bus
        self.endocrine = endocrine          # optional, used for melatonin secretion
        self.name = "nervous_system"
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.neurons: dict[str, Neuron] = {}
        self.synapses: list[Synapse] = []
        self.sleep_state: str = "awake"

    # ------------------------------------------------------------------
    # Network construction
    # ------------------------------------------------------------------

    def add_neuron(self, name: str, threshold: float = 1.0,
                   decay_rate: float = 0.05) -> Neuron:
        neuron = Neuron(name, threshold, decay_rate)
        self.neurons[name] = neuron
        return neuron

    def connect(self, pre_name: str, post_name: str,
                weight: float = 1.0, delay: float = 0.02) -> Synapse:
        pre = self.neurons[pre_name]
        post = self.neurons[post_name]
        synapse = Synapse(pre, post, weight, delay)
        pre.synapses_out.append(synapse)
        self.synapses.append(synapse)
        return synapse

    async def stimulate(self, neuron_name: str, strength: float = 1.0):
        if neuron_name in self.neurons:
            await self.neurons[neuron_name].inbox.put({
                "from": "stimulus",
                "strength": strength,
            })

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    async def run(self):
        tasks = [asyncio.create_task(n.run()) for n in self.neurons.values()]
        tasks += [
            asyncio.create_task(self._organ_listener()),
            asyncio.create_task(self._monitor()),
            asyncio.create_task(self._sleep_wake_cycle()),
        ]
        await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    # Sensory transduction — organ signals → sensory neuron stimulations
    # ------------------------------------------------------------------

    async def _organ_listener(self):
        while True:
            msg = await self.inbox.get()
            signal = msg.get("signal")
            sender = msg.get("from", "")

            if signal == "pulse" and sender == "heart":
                beats = msg.get("beats", 0)
                if beats % 5 == 0:
                    await self.stimulate("sensory_cardiac", strength=0.6)

            elif signal == "oxygen":
                level = msg.get("level", 100)
                strength = 1.0 if level < 96 else 0.2
                await self.stimulate("sensory_chemo", strength=strength)

            elif signal == "glucose":
                level = msg.get("level", 90)
                if level < 65:
                    await self.stimulate("sensory_glucose", strength=1.0)
                elif level > 130:
                    # Excess glucose — mild inhibitory signal to slow cardiac
                    await self.stimulate("sensory_glucose", strength=-0.3)

            elif signal == "alert":
                # General threat → activate stress pathway
                await self.stimulate("sensory_chemo", strength=0.8)

    # ------------------------------------------------------------------
    # Sleep / Wake cycle
    # ------------------------------------------------------------------

    async def _sleep_wake_cycle(self):
        while True:
            # ── WAKE ──────────────────────────────────────────────────
            self.sleep_state = "awake"
            for n in self.neurons.values():
                n.threshold = n._base_threshold
            if self.endocrine:
                self.endocrine.secrete("cortisol", amount=8, source="circadian")
            await self._broadcast_circadian("wake")
            await asyncio.sleep(WAKE_DURATION)

            # ── SLEEP ─────────────────────────────────────────────────
            self.sleep_state = "sleeping"
            for n in self.neurons.values():
                n.threshold = n._base_threshold * SLEEP_THRESHOLD_FACTOR
            if self.endocrine:
                self.endocrine.secrete("melatonin", amount=40, source="pineal")
            await self._broadcast_circadian("sleep")
            await asyncio.sleep(SLEEP_DURATION)

    async def _broadcast_circadian(self, mode: str):
        await self.bus.broadcast("nervous_system", {
            "signal": "circadian", "mode": mode
        })

    # ------------------------------------------------------------------
    # Monitoring — LTP decay + UI updates
    # ------------------------------------------------------------------

    async def _monitor(self):
        while True:
            await asyncio.sleep(0.4)
            for synapse in self.synapses:
                synapse.decay_ltp()

            state = {
                name: {
                    "potential": round(n.potential, 3),
                    "threshold": round(n.threshold, 2),
                    "fires":     n.fire_count,
                    "synapses":  len(n.synapses_out),
                }
                for name, n in self.neurons.items()
            }
            state["_meta"] = {
                "sleep_state":        self.sleep_state,
                "total_transmissions": sum(s.transmissions for s in self.synapses),
                "ltp_weights":        {
                    f"{s.pre.name}→{s.post.name}": round(s.weight, 3)
                    for s in self.synapses
                },
            }
            self.bus.update_ui("nervous_system", state)
