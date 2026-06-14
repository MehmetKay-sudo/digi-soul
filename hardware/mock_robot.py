"""
Mock robot hardware.

Simulates the physical subsystems of a humanoid robot.
Replace this class with real hardware drivers when deploying on actual hardware.

Subsystems:
  motor        — locomotion speed (0-100 %)
  power_mode   — energy management (normal / conserve / boost)
  sensor_rate  — how frequently sensors are polled (Hz)
  alert_led    — visual/audio alert indicator
  servos       — reflex actuator states (dict of joint → torque %)
  display      — status text sent to on-board display
"""

import copy
import time


class MockRobot:
    def __init__(self):
        self.state: dict = {
            "motor_speed":   50,       # percent
            "power_mode":    "normal",
            "sensor_rate":   10,       # Hz
            "alert_led":     False,
            "alert_msg":     None,
            "servos": {
                "neck":      0,
                "shoulder_l": 0,
                "shoulder_r": 0,
                "hand_l":    0,
                "hand_r":    0,
            },
            "display": "DIGI-SOUL ONLINE",
            "last_updated": time.time(),
        }
        self._log: list[str] = []

    # ------------------------------------------------------------------
    # Subsystem setters  (swap for real GPIO / ROS calls)
    # ------------------------------------------------------------------

    def set_motor_speed(self, speed: float):
        speed = round(max(0.0, min(100.0, speed)), 1)
        if speed != self.state["motor_speed"]:
            self._log_cmd(f"MOTOR  speed={speed}%")
        self.state["motor_speed"] = speed
        self._touch()

    def set_power_mode(self, mode: str):
        if mode != self.state["power_mode"]:
            self._log_cmd(f"POWER  mode={mode}")
        self.state["power_mode"] = mode
        self._touch()

    def set_sensor_rate(self, hz: float):
        hz = round(max(1.0, min(50.0, hz)), 1)
        if hz != self.state["sensor_rate"]:
            self._log_cmd(f"SENSOR rate={hz}Hz")
        self.state["sensor_rate"] = hz
        self._touch()

    def set_alert(self, active: bool, msg: str | None = None):
        if active != self.state["alert_led"]:
            self._log_cmd(f"ALERT  active={active}  msg={msg}")
        self.state["alert_led"] = active
        self.state["alert_msg"] = msg
        self._touch()

    def set_servo(self, joint: str, torque: float):
        torque = round(max(-100.0, min(100.0, torque)), 1)
        self.state["servos"][joint] = torque
        self._log_cmd(f"SERVO  {joint}={torque}%")
        self._touch()

    def set_display(self, text: str):
        self.state["display"] = text[:64]
        self._touch()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _touch(self):
        self.state["last_updated"] = time.time()

    def _log_cmd(self, cmd: str):
        entry = f"[{time.strftime('%H:%M:%S')}] {cmd}"
        self._log.append(entry)
        if len(self._log) > 100:
            self._log.pop(0)

    def recent_log(self, n: int = 6) -> list[str]:
        return self._log[-n:]

    def get_state(self) -> dict:
        # Deep copy so the Tkinter UI thread reads a fully independent snapshot —
        # the nested "servos" dict would otherwise be shared with the asyncio
        # thread that mutates it, causing a cross-thread race condition.
        return copy.deepcopy(self.state)
