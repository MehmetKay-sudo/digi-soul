"""
Hardware Bridge — translates organ states into robot subsystem commands.

Mapping logic:
  heart.bpm              →  motor speed  (40 BPM = 0%, 120 BPM = 100%)
  lungs.oxygen           →  sensor rate  (high O2 = frequent polling)
  brain.alert            →  alert LED + display text
  brain.glucose          →  power mode   (low glucose = conserve, high = boost)
  adrenal.adrenaline     →  motor boost + shoulder servo activation
  nervous_system         →  servo reflexes on motor neuron fires + sleep mode
  liver.toxin_load       →  display warning
  muscular_system        →  locomotion servos (legs via motor speed) +
                             arm servos (shoulder_l/r, hand_l/r)
  vascular_system        →  motor speed modulation (hypotension slows motor)
  circadian (sleep)      →  power conserve + motor off
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
        elif organ_name == "muscular_system":
            self._map_muscles(state)
        elif organ_name == "vascular_system":
            self._map_vascular(state)

        self.state_queue.put_nowait(self.robot.get_state())

    # ------------------------------------------------------------------
    # Per-organ mapping functions
    # ------------------------------------------------------------------

    def _map_heart(self, state: dict):
        bpm   = state.get("bpm", 60)
        speed = max(0.0, (bpm - 40) * 100 / 80)
        self.robot.set_motor_speed(speed)

    def _map_lungs(self, state: dict):
        o2   = state.get("oxygen_level", 100)
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
            boost = min(100.0, self.robot.state["motor_speed"] + adr * 0.4)
            self.robot.set_motor_speed(boost)
            self.robot.set_servo("shoulder_l", adr * 0.5)
            self.robot.set_servo("shoulder_r", adr * 0.5)

    def _map_ns(self, state: dict):
        meta = state.get("_meta", {})
        if meta.get("sleep_state") == "sleeping":
            self.robot.set_power_mode("conserve")
            self.robot.set_motor_speed(0)
            self.robot.set_display("SLEEP MODE")

    def _map_liver(self, state: dict):
        toxin = state.get("toxin_load", 0)
        if toxin > 60:
            self.robot.set_display(f"WARNING: liver toxin {toxin:.0f}%")

    def _map_muscles(self, state: dict):
        """
        Muscle fatigue and activity → servo torques and motor speed modifier.

        Locomotion group drives leg/motor output.
        Arms group drives shoulder and hand servos.
        Fatigue reduces torque proportionally (tired muscles are weaker).
        """
        fatigue    = state.get("fatigue", {})
        activity   = state.get("activity_level", 0)
        strength   = max(0.0, 1.0 - fatigue.get("locomotion", 0) / 100)

        # Active locomotion boosts motor speed (capped by current heart-driven base)
        if activity > 0 and "locomotion" in state.get("fatigue", {}):
            current_speed = self.robot.state["motor_speed"]
            loco_boost    = strength * 15.0
            self.robot.set_motor_speed(min(100.0, current_speed + loco_boost))

        # Arms: shoulder/hand servos reflect muscle torque
        arm_strength = max(0.0, 1.0 - fatigue.get("arms", 0) / 100)
        if activity > 0:
            torque = arm_strength * 60.0
            self.robot.set_servo("shoulder_l", torque)
            self.robot.set_servo("shoulder_r", torque)
            self.robot.set_servo("hand_l",     arm_strength * 40.0)
            self.robot.set_servo("hand_r",     arm_strength * 40.0)

        # Posture: neck servo
        posture_strength = max(0.0, 1.0 - fatigue.get("posture", 0) / 100)
        self.robot.set_servo("neck", posture_strength * 30.0)

    def _map_vascular(self, state: dict):
        """
        Vascular status modulates motor: hypotension reduces locomotion capacity
        (insufficient perfusion pressure to sustain full motor output).
        """
        status   = state.get("status", "normal")
        systolic = state.get("systolic", 120)

        if status == "hypotension":
            # Reduce motor to 60% max under hypotension
            reduced = min(self.robot.state["motor_speed"], systolic * 0.5)
            self.robot.set_motor_speed(max(0.0, reduced))
            self.robot.set_display(f"LOW BP: {systolic:.0f} mmHg — motor reduced")
        elif status == "hypertension" and systolic > 160:
            # Severe hypertension: warn but don't cut motor
            self.robot.set_display(f"HIGH BP: {systolic:.0f} mmHg")
