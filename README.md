# digi-soul

> A biologically-inspired operating system for humanoid robots — where every subsystem is an organ, every organ is a program, and together they form a living digital body.

---

## Concept

Humanoid robots are coming. The hardware is advancing fast. What lags behind is the *software soul* — the internal architecture that makes a robot not just move, but **regulate itself** the way a living organism does.

**digi-soul** models the human body as an operating system:

- Each organ is an independent async process with its own state
- Organs communicate through two channels: a **neural bus** (fast, signal-based) and an **endocrine bus** (slow, hormone-based, with decay)
- A **nervous system** of neurons and synapses routes signals, fires reflexes, and strengthens pathways through long-term potentiation
- A **hardware bridge** maps organ outputs directly to robot subsystems — motor speed, sensor rate, servo torque, power mode

The result is a self-regulating system. When oxygen drops, the brain tells the heart to beat faster and the lungs to breathe harder. When glucose is low, the pancreas releases glucagon and the liver responds. When a threat is detected, the adrenal gland floods the system with adrenaline. The robot doesn't need to be told — it *reacts*.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        asyncio event loop                    │
│                                                             │
│   ORGANS                    NERVOUS SYSTEM                  │
│   ──────                    ───────────────                  │
│   Heart      ──pulse──►    sensory_cardiac                  │
│   Lungs      ──O2─────►    sensory_chemo   ──► interneuron  │
│   Liver      ──glucose►    sensory_glucose       │           │
│   Stomach                                        ▼           │
│   Kidney                                   motor_cardiac    │
│   Pancreas                                 motor_respiratory│
│   AdrenalGland                                  │           │
│   ImmuneSystem                                  ▼           │
│   Brain  ◄──────────────────────────────── organ commands   │
│                                                             │
│   ENDOCRINE BUS (slow, hormone half-life decay)             │
│   insulin · glucagon · adrenaline · cortisol                │
│   melatonin · cytokines                                     │
│                                                             │
│   HARDWARE BRIDGE                                           │
│   heart.bpm      → motor speed                              │
│   lungs.O2       → sensor poll rate                         │
│   brain.alert    → alert LED + display                      │
│   adrenal        → servo activation                         │
│   sleep/wake     → power mode                               │
└─────────────────────────────────────────────────────────────┘
         │
    ┌────▼─────────────────┐
    │  Tkinter Canvas      │
    │  body silhouette     │
    │  + 5 live tabs:      │
    │  Organs / Neural /   │
    │  Endocrine /         │
    │  Cortisol / Hardware │
    └──────────────────────┘
```

### Two communication channels

| Channel | Speed | Mechanism | Example |
|---|---|---|---|
| **Neural bus** | Fast (ms) | `asyncio.Queue` direct routing | Heart pulse → Brain counts it |
| **Endocrine bus** | Slow (seconds) | Hormone levels with exponential decay | Pancreas secretes insulin → Liver responds over 25s |

### Nervous system

Neurons accumulate membrane potential from incoming synaptic signals. When potential exceeds a threshold, the neuron fires — propagating signals downstream and triggering motor callbacks that command organs. Three features:

- **Long-term potentiation (LTP)** — excitatory synapses strengthen with repeated use, up to 2.5× their base weight
- **Inhibitory synapses** — negative-weight connections suppress downstream neurons (e.g. high glucose inhibits cardiac drive)
- **Sleep/wake cycle** — a compressed circadian oscillator doubles all neuron thresholds during sleep, secretes melatonin, and sets the robot to power-conserve mode

---

## Organs

| Organ | Role |
|---|---|
| **Heart** | Beats at configurable BPM, broadcasts pulse to all organs. Responds to speed-up/slow-down commands from Brain and motor neurons. |
| **Lungs** | Inhale/exhale cycle, broadcasts oxygen level. Responds to breathe-faster commands. |
| **Brain** | Monitors oxygen and glucose, raises alerts, commands Heart and Lungs to compensate. Responds to circadian signals. |
| **Stomach** | Simulates digestion cycles, sends nutrient signals to Liver. |
| **Liver** | Regulates blood glucose via glycogenolysis, detoxifies blood on each pulse, responds to insulin/glucagon from Pancreas. |
| **Kidney** | Filters urea on each heartbeat, manages fluid balance and blood pressure, increases filtration under hyperglycemia. |
| **Pancreas** | Monitors glucose, secretes insulin (high) or glucagon (low) into the endocrine bus. |
| **Adrenal Gland** | Fight-or-flight: releases adrenaline and cortisol on alerts or low O2, boosts heart and lungs. |
| **Immune System** | Continuous threat surveillance, responds to toxin alerts with cytokine release, cortisol suppresses its response. |

---

## Project structure

```
digi-soul/
├── main.py                  # entry point — wires everything together
├── cortisol_monitor.py      # standalone cortisol stress monitor (test module)
├── requirements.txt
│
├── core/
│   ├── organ.py             # base Organ class (inbox, send, broadcast, receive)
│   ├── bus.py               # fast neural message bus + hardware bridge hook
│   └── endocrine_bus.py     # slow hormone channel with exponential decay
│
├── organs/
│   ├── heart.py
│   ├── lungs.py
│   ├── brain.py
│   ├── stomach.py
│   ├── liver.py
│   ├── kidney.py
│   ├── pancreas.py
│   ├── adrenal_gland.py
│   └── immune_system.py
│
├── nervous_system/
│   ├── neuron.py            # membrane potential, threshold firing, decay, LTP
│   ├── synapse.py           # weight, delay, LTP strengthening
│   └── nervous_system.py   # network, sleep/wake cycle, sensory transduction
│
├── hardware/
│   ├── bridge.py            # organ state → robot subsystem mapping
│   └── mock_robot.py        # simulated hardware (swap for real drivers)
│
└── canvas/
    └── display.py           # tkinter UI: body silhouette + 5 tabs
```

---

## Getting started

**Requirements:** Python 3.11+ and Pillow

```bash
git clone https://github.com/mehmetkay-sudo/digi-soul.git
cd digi-soul
pip install -r requirements.txt
python main.py
```

The UI opens with a human body silhouette on the left. Each organ flashes when it emits a signal. The right panel has five tabs:

- **Organs** — live state of all 9 organs
- **Neural** — neuron potentials, fire counts, LTP weight evolution
- **Endocrine** — circulating hormone levels with decay bars
- **Cortisol** — dedicated stress monitor: gauge, sparkline, alert banner
- **Hardware** — robot subsystem states (motor, servos, sensor rate, power mode)

### Standalone cortisol monitor

The cortisol stress monitor can also run independently — useful for testing or embedding in other projects:

```bash
python cortisol_monitor.py
```

---

## Deploying on real hardware

The `MockRobot` class in `hardware/mock_robot.py` is the only hardware-specific component. Replace it with your actual drivers:

```python
# hardware/mock_robot.py  →  hardware/my_robot.py
class MyRobot:
    def set_motor_speed(self, speed: float):
        # GPIO / ROS / serial command here
        ...

    def set_servo(self, joint: str, torque: float):
        ...
```

Then swap it in `main.py`:

```python
from hardware.my_robot import MyRobot
robot = MyRobot()
bridge = HardwareBridge(robot)
```

Everything else — organs, nervous system, endocrine bus — is hardware-agnostic Python.

---

## Roadmap

- [ ] More organs — pancreatic beta/alpha cell distinction, adrenal cortex vs medulla
- [ ] Sensory input — map robot camera/microphone/touch sensors to organ stimuli
- [ ] Adaptive nervous system — neurons that rewire based on experience (Hebbian learning)
- [ ] Energy metabolism — ATP model linking glucose, oxygen, and motor output budget
- [ ] Multi-body networking — multiple digi-soul instances communicating (colony/swarm)
- [ ] ROS2 integration — publish organ states as ROS topics
- [ ] Raspberry Pi / Jetson target — validated portable deployment

---

## Philosophy

Biology solved self-regulation over millions of years of iteration. Rather than designing robot control systems from scratch with rigid state machines, digi-soul asks: *what if the control architecture looked like the body itself?*

Organs don't wait for a central controller. They publish signals, listen for responses, and adapt. The nervous system learns which pathways fire most often and strengthens them. Hormones carry slow context that neural signals can't — a robot under sustained stress should behave differently from one at rest, not just react to individual events.

This is the foundation for a robot that doesn't just execute commands, but **regulates itself**.

---

## Contact

Interested in contributing or collaborating?  
→ mehmetkay-sudo@proton.me
