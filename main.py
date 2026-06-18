import asyncio
import os
import threading
import tkinter as tk
from pathlib import Path

from core.bus import MessageBus
from core.endocrine_bus import EndocrineBus
from canvas.display import BodyCanvas
from hardware.bridge import HardwareBridge
from hardware.mock_robot import MockRobot
from physiology.spaces import SpacePhysiology

from organs.brain import Brain
from organs.heart import Heart
from organs.kidney import Kidney
from organs.liver import Liver
from organs.lungs import Lungs
from organs.stomach import Stomach
from organs.pancreas import Pancreas
from organs.adrenal_gland import AdrenalGland
from organs.immune_system import ImmuneSystem
from organs.muscular_system import MuscularSystem
from organs.vascular_system import VascularSystem

from nervous_system.nervous_system import NervousSystem
from circuit import build_neural_circuit

try:
    from language.language_module import LanguageModule
    _LANGUAGE_AVAILABLE = bool(os.environ.get("ANTHROPIC_API_KEY"))
except ImportError:
    _LANGUAGE_AVAILABLE = False

IMAGE_PATH = Path(__file__).parent / "humanbody.jpg"


async def run_all(organs, ns, endocrine):
    tasks = [asyncio.create_task(o.run()) for o in organs]
    tasks.append(asyncio.create_task(ns.run()))
    tasks.append(asyncio.create_task(endocrine.run()))
    await asyncio.gather(*tasks)


def start_asyncio(organs, ns, endocrine):
    asyncio.run(run_all(organs, ns, endocrine))


def main():
    # ── Core buses ────────────────────────────────────────────────────
    bus       = MessageBus()
    endocrine = EndocrineBus()

    # ── Hardware bridge ────────────────────────────────────────────────
    robot  = MockRobot()
    bridge = HardwareBridge(robot)
    bus.bridge = bridge

    # ── Organs ────────────────────────────────────────────────────────
    # space_physiology must be registered first so organs find it in run()
    space    = SpacePhysiology(bus, endocrine)
    heart    = Heart(bus, bpm=60)
    lungs    = Lungs(bus, breath_interval=2.0)
    brain    = Brain(bus)
    stomach  = Stomach(bus)
    liver    = Liver(bus)
    kidney   = Kidney(bus, endocrine)
    pancreas = Pancreas(bus, endocrine)
    adrenal  = AdrenalGland(bus, endocrine)
    immune   = ImmuneSystem(bus, endocrine)
    muscles  = MuscularSystem(bus, endocrine)
    vascular = VascularSystem(bus, endocrine)

    organs = [
        space, heart, lungs, brain, stomach, liver,
        kidney, pancreas, adrenal, immune, muscles, vascular,
    ]
    for organ in organs:
        bus.register(organ)

    # ── Language module (optional — requires ANTHROPIC_API_KEY) ───────
    if _LANGUAGE_AVAILABLE:
        lang = LanguageModule(bus)
        bus.register(lang)
        organs.append(lang)

    # ── Nervous system ─────────────────────────────────────────────────
    ns = NervousSystem(bus, endocrine)
    bus.register(ns)
    build_neural_circuit(ns, bus)

    # ── Asyncio loop in background thread ─────────────────────────────
    thread = threading.Thread(
        target=start_asyncio,
        args=(organs, ns, endocrine),
        daemon=True,
    )
    thread.start()

    # ── Tkinter canvas in main thread ─────────────────────────────────
    root = tk.Tk()
    BodyCanvas(
        root,
        ui_queue        = bus.ui_queue,
        endocrine_queue = endocrine.ui_queue,
        hw_queue        = bridge.state_queue,
        image_path      = str(IMAGE_PATH),
    )
    root.mainloop()


if __name__ == "__main__":
    main()
