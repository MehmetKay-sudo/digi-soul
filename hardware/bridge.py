"""
Hardware Bridge — translates organ states into robot subsystem commands.

Mapping logic:
  heart.bpm         →  motor speed  (60 BPM = 50%, 120 BPM = 100%)
  lungs.oxygen      →  sensor rate  (high O2 = frequent polling, low O2 = slower)
  brain.alert       →  alert LED + display text
  brain.glucose     →  power mode   (low glucose = conserve, high = boost)
  adrenal.adrenaline→  motor boost + servo activation
  nervous_system    →  servo reflexes on motor neuron fires
  circadian (sleep) →  power conserve + slow motor
"""

import queue

from hardware.mock_robot import MockRobot


class HardwareBridge:
    def __init__(self, robot: MockRobot | None = None):
        self.robot = robot or MockRobot()
        self.state_queue: queue.Queue = queue.Queue()   # → canvas hardware panel

    # ------------------------------------------------------------------
    # Called by MessageBus on every organ/NS state update
    # ------------------------------------------------------------------

    def process(self, organ_name: str, state: dict):
        if organ_name == "heart":
            self._map_heart(state)
        elif organ_name == "lungs":
            self._map_lungs(state)
        elif organ_name == "brain":
            self._map_brain(state)
        elif organ_name == "adrenal_gland":
            self._map_adrenal(state)
        elif organ_name == "nervous_system":
            self._map_ns(state)
        elif organ_name == "liver":
            self._map_liver(state)

        self.state_queue.put_nowait(self.robot.get_state())

    # ------------------------------------------------------------------
    # Per-organ mapping functions
    # ------------------------------------------------------------------

    def _map_heart(self, state: dict):
        bpm = state.get("bpm", 60)
        # 40 BPM → 0%, 60 BPM → 50%, 120 BPM → 100%
        speed = max(0.0, (bpm - 40) * 100 / 80)
        self.robot.set_motor_speed(speed)

    def _map_lungs(self, state: dict):
        o2 = state.get("oxygen_level", 100)
        # High O2 → sensors poll frequently; low O2 → reduce load
        rate = max(1.0, o2 / 10.0)
        self.robot.set_sensor_rate(rate)

    def _map_brain(self, state: dict):
        alert = state.get("alert")
        if alert:
            self.robot.set_alert(True, str(alert))
            self.robot.set_display(f"ALERT: {str(alert)[:50]}")
        else:
            self.robot.set_alert(False)
            self.robot.set_display("DIGI-SOUL NOMINAL")

        glucose = state.get("glucose_level", 90)
        if glucose < 65:
            self.robot.set_power_mode("conserve")
        elif glucose > 130:
            self.robot.set_power_mode("boost")
        else:
            self.robot.set_power_mode("normal")

    def _map_adrenal(self, state: dict):
        adr = state.get("adrenaline", 0)
        if adr > 20:
            # Adrenaline surge → motor speed boost + reflex servo activation
            boost = min(100.0, self.robot.state["motor_speed"] + adr * 0.4)
            self.robot.set_motor_speed(boost)
            self.robot.set_servo("shoulder_l", adr * 0.5)
            self.robot.set_servo("shoulder_r", adr * 0.5)

    def _map_ns(self, state: dict):
        meta = state.get("_meta", {})
        # Sleep/wake → power mode + motor idle
        if meta.get("sleep_state") == "sleeping":
            self.robot.set_power_mode("conserve")
            self.robot.set_motor_speed(0)
            self.robot.set_display("SLEEP MODE")

        # LTP weights available for future adaptive servo tuning
        # ltp = meta.get("ltp_weights", {})

    def _map_liver(self, state: dict):
        toxin = state.get("toxin_load", 0)
        if toxin > 60:
            self.robot.set_display(f"WARNING: liver toxin {toxin:.0f}%")
