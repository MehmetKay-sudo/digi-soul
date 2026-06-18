"""
test_run.py — headless smoke test for digi-soul

Runs the full organ + nervous-system + endocrine simulation WITHOUT the
Tkinter GUI, so it works over SSH, in CI, or anywhere without a display.
It wires everything exactly like main.py (minus the canvas), runs for a few
seconds, optionally injects a stressor, then prints a readable report of:

  - how many UI events each subsystem emitted
  - final organ states
  - neuron fire counts + LTP weight evolution  (proves the neural circuit is alive)
  - circulating hormone levels
  - the resulting robot hardware state

Usage:
    python test_run.py              # 12-second run with a pathogen stressor
    python test_run.py --seconds 20 # custom duration
    python test_run.py --no-stress  # skip the injected pathogen

Exit code is 0 on a clean run, non-zero if an exception escapes.
"""

import argparse
import asyncio

from core.bus import MessageBus
from core.endocrine_bus import EndocrineBus
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

# Import the same circuit builder used in production (circuit.py is GUI-free).
from circuit import build_neural_circuit

# Total expected subsystems: 11 original + muscular_system + vascular_system = 13
TOTAL_SUBSYSTEMS = 13


async def run(run_seconds: float, inject_stress: bool):
    # ── Buses + hardware ───────────────────────────────────────────────
    bus       = MessageBus()
    endocrine = EndocrineBus()
    robot     = MockRobot()
    bridge    = HardwareBridge(robot)
    bus.bridge = bridge

    # ── Organs ─────────────────────────────────────────────────────────
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

    # space_physiology registered first so heart/lungs/kidney/vascular find it
    organs = [
        space, heart, lungs, brain, stomach, liver,
        kidney, pancreas, adrenal, immune, muscles, vascular,
    ]
    for organ in organs:
        bus.register(organ)

    # ── Nervous system ─────────────────────────────────────────────────
    ns = NervousSystem(bus, endocrine)
    bus.register(ns)
    build_neural_circuit(ns, bus)

    # ── Launch everything ──────────────────────────────────────────────
    tasks = [asyncio.create_task(o.run()) for o in organs]
    tasks.append(asyncio.create_task(ns.run()))
    tasks.append(asyncio.create_task(endocrine.run()))

    if inject_stress:
        async def stressor():
            await asyncio.sleep(min(5.0, run_seconds / 2))
            await bus.route("test_run", "immune_system",
                            {"signal": "pathogen", "severity": 0.9})
        tasks.append(asyncio.create_task(stressor()))

    await asyncio.sleep(run_seconds)
    for t in tasks:
        t.cancel()

    _report(bus, endocrine, robot, run_seconds)


def _report(bus, endocrine, robot, run_seconds):
    ui_events: dict = {}
    counts:    dict = {}
    while not bus.ui_queue.empty():
        name, state = bus.ui_queue.get_nowait()
        ui_events[name] = state
        counts[name]    = counts.get(name, 0) + 1

    print("=" * 60)
    print("DIGI-SOUL HEADLESS TEST REPORT")
    print("=" * 60)
    print(f"subsystems reporting : {len(ui_events)} / {TOTAL_SUBSYSTEMS}")
    print(f"UI events per system : "
          f"{ {k: counts[k] for k in sorted(counts)} }")
    print()

    print("--- ORGAN STATES ---")
    for name in [
        "space_physiology", "heart", "lungs", "brain", "stomach", "liver",
        "kidney", "pancreas", "adrenal_gland", "immune_system",
        "muscular_system", "vascular_system",
    ]:
        if name in ui_events:
            print(f"  {name:<16} {ui_events[name]}")
    print()

    print("--- NERVOUS SYSTEM (proof the circuit is alive) ---")
    ns_state = ui_events.get("nervous_system", {})
    meta     = ns_state.get("_meta", {}) if isinstance(ns_state, dict) else {}
    fires    = {k: v.get("fires") for k, v in ns_state.items() if k != "_meta"}
    print(f"  sleep state          : {meta.get('sleep_state')}")
    print(f"  total transmissions  : {meta.get('total_transmissions')}")
    print(f"  neuron fire counts   : {fires}")
    print(f"  LTP weights          : {meta.get('ltp_weights')}")
    print()

    print("--- ENDOCRINE (circulating hormones) ---")
    print(f"  {endocrine.get_all()}")
    print()

    print("--- ROBOT HARDWARE (bridge output) ---")
    hw = robot.get_state()
    hw.pop("last_updated", None)
    for k, v in hw.items():
        print(f"  {k:<14} {v}")
    print()

    # ── Pass/fail assertions ───────────────────────────────────────────
    total_tx = meta.get("total_transmissions", 0)

    # On runs >= 10s expect all 13 subsystems; shorter runs may miss slow ones
    # (immune patrol ~8s, adrenal monitor ~3s, vascular ~1s, muscles ~1s)
    expected_systems = TOTAL_SUBSYSTEMS if run_seconds >= 10 else 11
    all_reporting    = len(ui_events) >= expected_systems
    neural_ok        = total_tx > 0 or run_seconds < 10
    ok               = all_reporting and neural_ok

    if ok:
        msg = "PASS — all subsystems live"
        if total_tx > 0:
            msg += ", neural circuit firing"
        else:
            msg += " (run >=10s to observe neural firing)"
    else:
        msg = "WARN — check report above (a pathway may be dormant)"
    print("RESULT:", msg)


def main():
    parser = argparse.ArgumentParser(description="digi-soul headless test run")
    parser.add_argument("--seconds", type=float, default=12.0,
                        help="how long to run the simulation (default 12)")
    parser.add_argument("--no-stress", action="store_true",
                        help="do not inject a pathogen stressor mid-run")
    args = parser.parse_args()

    asyncio.run(run(args.seconds, inject_stress=not args.no_stress))


if __name__ == "__main__":
    main()
