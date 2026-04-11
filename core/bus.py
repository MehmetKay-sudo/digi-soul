import queue


class MessageBus:
    def __init__(self):
        self._organs = {}
        self.ui_queue: queue.Queue = queue.Queue()   # → tkinter canvas
        self.bridge = None                           # optional HardwareBridge

    def register(self, organ):
        self._organs[organ.name] = organ

    async def route(self, sender: str, target: str, message: dict):
        if target in self._organs:
            await self._organs[target].inbox.put({"from": sender, **message})

    async def broadcast(self, sender: str, message: dict):
        for name, organ in self._organs.items():
            if name != sender:
                await organ.inbox.put({"from": sender, **message})

    def update_ui(self, organ_name: str, state: dict):
        self.ui_queue.put_nowait((organ_name, state))
        if self.bridge:
            self.bridge.process(organ_name, state)
