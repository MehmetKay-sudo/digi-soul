"""
circuit.py — neural circuit definition for digi-soul

Kept separate from main.py (which imports Tkinter) so the circuit can be
imported in headless contexts: tests, CI, SSH sessions, or any deployment
without a display. main.py and test_run.py both import build_neural_circuit
from here, guaranteeing the test always uses the same tuning as production.
"""

from core.bus import MessageBus
from nervous_system.nervous_system import NervousSystem


def build_neural_circuit(ns: NervousSystem, bus: MessageBus):
    """
    Neural circuit layout:

      SENSORY              INTERNEURONS           MOTOR
      ───────              ────────────           ─────
      sensory_cardiac  ──► inter_brainstem  ──►  motor_cardiac      → heart.regulate
      sensory_chemo    ──► inter_brainstem  ──►  motor_respiratory  → lungs.breathe_faster
      sensory_glucose  ──► inter_hypothal   ──►  motor_cardiac (inhibitory)
      sensory_spaces   ──► inter_hypothal   ──►  motor_respiratory  → compensate breathing

    sensory_spaces (Zhang 2020): fires when physiological space quality drops below
    0.7 — drives hypothalamic interneuron to increase respiratory rate as compensation.

    Inhibitory synapse: inter_hypothalamus → motor_cardiac (weight=-0.5)
    LTP: all excitatory synapses strengthen with repeated use.
    Sleep/wake: neuron thresholds double during sleep phase.

    NOTE ON TUNING: thresholds were lowered (sensory ~0.5, inter_brainstem 1.0)
    so the reflex arc fires during normal resting operation rather than only
    during a crisis. With the original thresholds the leaky-integrator decay
    erased each sensory input before the next arrived, so no neuron ever
    reached threshold, LTP never engaged, and the motor reflexes never fired.
    """
    # Sensory neurons
    ns.add_neuron("sensory_cardiac",    threshold=0.5,  decay_rate=0.05)
    ns.add_neuron("sensory_chemo",      threshold=0.5,  decay_rate=0.04)
    ns.add_neuron("sensory_glucose",    threshold=0.9,  decay_rate=0.05)
    ns.add_neuron("sensory_spaces",     threshold=0.6,  decay_rate=0.04)  # Zhang 2020

    # Interneurons
    ns.add_neuron("inter_brainstem",    threshold=1.0,  decay_rate=0.03)
    ns.add_neuron("inter_hypothalamus", threshold=0.8,  decay_rate=0.04)

    # Motor neurons
    ns.add_neuron("motor_cardiac",      threshold=0.9,  decay_rate=0.06)
    ns.add_neuron("motor_respiratory",  threshold=0.8,  decay_rate=0.06)

    # Synapses (excitatory unless weight < 0)
    ns.connect("sensory_cardiac",    "inter_brainstem",    weight=0.7,  delay=0.02)
    ns.connect("sensory_chemo",      "inter_brainstem",    weight=0.9,  delay=0.015)
    ns.connect("inter_brainstem",    "motor_cardiac",      weight=1.0,  delay=0.02)
    ns.connect("inter_brainstem",    "motor_respiratory",  weight=0.8,  delay=0.02)
    ns.connect("sensory_glucose",    "inter_hypothalamus", weight=1.0,  delay=0.03)
    ns.connect("inter_hypothalamus", "motor_cardiac",      weight=-0.5, delay=0.03)  # inhibitory
    ns.connect("sensory_spaces",     "inter_hypothalamus", weight=0.7,  delay=0.025)
    ns.connect("inter_hypothalamus", "motor_respiratory",  weight=0.5,  delay=0.02)

    # Motor callbacks — fired neuron → organ command via bus
    async def on_motor_cardiac(neuron):
        # The cardiac reflex arc is vagally mediated (cardioinhibitory). Feed a
        # fast phasic vagal burst into the autonomic controller so HR/HRV control
        # flows through the two-arm effector model (Tan 2019, PMID 29654380).
        ns.autonomic.request_vagal(0.2)
        await bus.route("nervous_system", "heart", {
            "signal": "neural_cmd", "cmd": "regulate"
        })

    async def on_motor_respiratory(neuron):
        await bus.route("nervous_system", "lungs", {
            "signal": "neural_cmd", "cmd": "breathe_faster"
        })

    ns.neurons["motor_cardiac"].on_fire     = on_motor_cardiac
    ns.neurons["motor_respiratory"].on_fire = on_motor_respiratory
