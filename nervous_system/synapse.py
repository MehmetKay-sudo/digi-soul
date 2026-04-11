import asyncio

# Long-term potentiation parameters
LTP_INCREMENT  = 0.04    # weight gain per transmission (excitatory only)
LTP_MAX_FACTOR = 2.5     # max weight = base_weight * this
LTP_DECAY_RATE = 0.001   # weight drifts back toward base per decay tick


class Synapse:
    """
    Synaptic connection with long-term potentiation (LTP).

    weight > 0  →  excitatory  (increases post-synaptic potential)
    weight < 0  →  inhibitory  (decreases post-synaptic potential)
    delay       →  axonal conduction delay (seconds)

    LTP: each transmission on an excitatory synapse slightly increases weight,
    modelling Hebbian learning ("neurons that fire together, wire together").
    Weight slowly decays back toward the baseline when not in use.
    """

    def __init__(self, pre, post, weight: float = 1.0, delay: float = 0.02):
        self.pre = pre
        self.post = post
        self.base_weight = weight
        self.weight = weight
        self.delay = delay
        self.transmissions = 0

    async def transmit(self):
        await asyncio.sleep(self.delay)
        self.transmissions += 1

        # LTP: potentiate excitatory synapses with use
        if self.weight > 0:
            max_w = self.base_weight * LTP_MAX_FACTOR
            self.weight = min(max_w, self.weight + LTP_INCREMENT)

        await self.post.inbox.put({
            "from": self.pre.name,
            "strength": self.weight,
        })

    def decay_ltp(self):
        """
        Called periodically by NervousSystem monitor.
        Drifts weight back toward base_weight (forgetting unused pathways).
        """
        if abs(self.weight - self.base_weight) > 0.001:
            if self.weight > self.base_weight:
                self.weight = max(self.base_weight, self.weight - LTP_DECAY_RATE)
            else:
                self.weight = min(self.base_weight, self.weight + LTP_DECAY_RATE)
