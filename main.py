import asyncio
import threading
import tkinter as tk
from pathlib import Path

from core.bus import MessageBus
from core.endocrine_bus import EndocrineBus
from canvas.display import BodyCanvas
from hardware.bridge import HardwareBridge
from hardware.mock_robot import MockRobot

from organs.brain import Brain
from organs.heart import Heart
from organs.kidney import Kidney
from organs.liver import Liver
from organs.lungs import Lungs
from organs.stomach import Stomach
from organs.pancreas import Pancreas
from organs.adrenal_gland import AdrenalGland
from organs.immune_system import ImmuneSystem

from nervous_system.nervous_system import NervousSystem

IMAGE_PATH = Path(__file__).parent / "humanbody.jpg"


def build_neural_circuit(ns: NervousSystem, bus: MessageBus):
    """
    Neural circuit layout:

      SENSORY              INTERNEURONS           MOTOR
      ───────              ────────────           ─────
      sensory_cardiac  ──► inter_brainstem  ──►  motor_cardiac      → heart.regulate
      sensory_chemo    ──► inter_brainstem  ──►  motor_respiratory  → lungs.breathe_faster
      sensory_glucose  ──► inter_hypothal   ──►  motor_cardiac (inhibitory)

    Inhibitory synapse: inter_hypothalamus → motor_cardiac (weight=-0.5)
    LTP: all excitatory synapses strengthen with repeated use.
    Sleep/wake: neuron thresholds double during sleep phase.
    """
    # Sensory neurons
    ns.add_neuron("sensory_cardiac",    threshold=1.0,  decay_rate=0.08)
    ns.add_neuron("sensory_chemo",      threshold=0.8,  decay_rate=0.06)
    ns.add_neuron("sensory_glucose",    threshold=0.9,  decay_rate=0.05)

    # Interneurons
    ns.add_neuron("inter_brainstem",    threshold=1.2,  decay_rate=0.04)
    ns.add_neuron("inter_hypothalamus", threshold=0.8,  decay_rate=0.04)

    # Motor neurons
    ns.add_neuron("motor_cardiac",      threshold=1.0,  decay_rate=0.06)
    ns.add_neuron("motor_respiratory",  threshold=0.9,  decay_rate=0.06)

    # Synapses (excitatory unless weight < 0)
    ns.connect("sensory_cardiac",    "inter_brainstem",    weight=0.7,  delay=0.02)
    ns.connect("sensory_chemo",      "inter_brainstem",    weight=0.9,  delay=0.015)
    ns.connect("inter_brainstem",    "motor_cardiac",      weight=1.0,  delay=0.02)
    ns.connect("inter_brainstem",    "motor_respiratory",  weight=0.8,  delay=0.02)
    ns.connect("sensory_glucose",    "inter_hypothalamus", weight=1.0,  delay=0.03)
    ns.connect("inter_hypothalamus", "motor_cardiac",      weight=-0.5, delay=0.03)  # inhibitory

    # Motor callbacks — fired neuron → organ command via bus
    async def on_motor_cardiac(neuron):
        await bus.route("nervous_system", "heart", {
            "signal": "neural_cmd", "cmd": "regulate"
        })

    async def on_motor_respiratory(neuron):
        await bus.route("nervous_system", "lungs", {
            "signal": "neural_cmd", "cmd": "breathe_faster"
        })

    ns.neurons["motor_cardiac"].on_fire    = on_motor_cardiac
    ns.neurons["motor_respiratory"].on_fire = on_motor_respiratory


async def run_all(organs, ns, endocrine):
    tasks = [asyncio.create_task(o.run()) for o in organs]
    tasks.append(asyncio.create_task(ns.run()))
    tasks.append(asyncio.create_task(endocrine.run()))
    await asyncio.gather(*tasks)


def start_asyncio(organs, ns, endocrine):
    asyncio.run(run_all(organs, ns, endocrine))


def main():
    # ── Core buses ────────────────────────────────────────────────────
    bus      = MessageBus()
    endocrine = EndocrineBus()

    # ── Hardware bridge ────────────────────────────────────────────────
    robot  = MockRobot()
    bridge = HardwareBridge(robot)
    bus.bridge = bridge   # bus calls bridge.process() on every state update

    # ── Organs ────────────────────────────────────────────────────────
    heart        = Heart(bus, bpm=60)
    lungs        = Lungs(bus, breath_interval=2.0)
    brain        = Brain(bus)
    stomach      = Stomach(bus)
    liver        = Liver(bus)
    kidney       = Kidney(bus)
    pancreas     = Pancreas(bus, endocrine)
    adrenal      = AdrenalGland(bus, endocrine)
    immune       = ImmuneSystem(bus, endocrine)

    organs = [heart, lungs, brain, stomach, liver, kidney, pancreas, adrenal, immune]
    for organ in organs:
        bus.register(organ)

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
        ui_queue       = bus.ui_queue,
        endocrine_queue = endocrine.ui_queue,
        hw_queue       = bridge.state_queue,
        image_path     = str(IMAGE_PATH),
    )
    root.mainloop()


if __name__ == "__main__":
    main()
