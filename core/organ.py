import asyncio


class Organ:
    def __init__(self, name: str, bus):
        self.name = name
        self.bus = bus
        self.inbox = asyncio.Queue()
        self.state = {}

    async def run(self):
        raise NotImplementedError

    async def send(self, target: str, **kwargs):
        await self.bus.route(self.name, target, kwargs)

    async def broadcast(self, **kwargs):
        await self.bus.broadcast(self.name, kwargs)

    async def receive(self):
        return await self.inbox.get()
