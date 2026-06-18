"""
Brain — cognitive coordinator for Digi-Soul.

Two operating modes:
  1. Hardcoded reflexes (always active, instant response for basic thresholds)
  2. Claude agent (when ANTHROPIC_API_KEY is set): reasons over the full
     vital-sign picture and issues nuanced organ commands via tool calls.
     Cooldown-gated so it fires at most once every REASONING_COOLDOWN_S seconds.
     Falls back silently to reflex mode on API errors.

Fix applied: OXYGEN_LOW corrected from 96 → 94.
  Clinical SpO2 < 94% is the standard concern threshold (not 96%).
  The previous value triggered false alerts every time thoracic space quality
  dipped to ~40%, which is a normal physiological fluctuation.

Based on: organ_agent_idea.txt — "Brain first (highest leverage)"
"""

import asyncio
import os
import time

from core.organ import Organ

OXYGEN_LOW           = 94    # SpO2 % — clinical concern threshold
GLUCOSE_LOW          = 65    # mg/dL
GLUCOSE_HIGH         = 130   # mg/dL
REASONING_COOLDOWN_S = 8.0   # seconds between Claude calls
CLAUDE_MODEL         = "claude-haiku-4-5-20251001"

BRAIN_TOOLS = [
    {
        "name": "command_heart",
        "description": "Send a regulation command to the heart organ.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cmd": {
                    "type": "string",
                    "enum": ["increase_bpm", "decrease_bpm", "regulate"],
                    "description": (
                        "increase_bpm: speed up cardiac rate; "
                        "decrease_bpm: slow it down; "
                        "regulate: return to normal sinus rhythm"
                    ),
                }
            },
            "required": ["cmd"],
        },
    },
    {
        "name": "command_lungs",
        "description": "Send a breathing command to the lungs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cmd": {
                    "type": "string",
                    "enum": ["breathe_faster", "breathe_normal", "breathe_deep"],
                    "description": (
                        "breathe_faster: increase rate for more O2; "
                        "breathe_normal: return to resting rate; "
                        "breathe_deep: slow deep breaths for CO2 clearance"
                    ),
                }
            },
            "required": ["cmd"],
        },
    },
    {
        "name": "broadcast_alert",
        "description": "Broadcast a high-priority alert to all subsystems.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Brief alert text (under 60 characters).",
                }
            },
            "required": ["message"],
        },
    },
    {
        "name": "no_action",
        "description": "All vitals are within acceptable ranges — no intervention needed.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

_BRAIN_SYSTEM = """\
You are the Brain of Digi-Soul — a biologically-inspired operating system inside a humanoid robot.
Maintain homeostasis by issuing organ commands when vitals deviate from normal.

Current vitals:
  Oxygen:    {o2}%  (concern <94%, critical <90%)
  Glucose:   {glucose} mg/dL  (low <70, high >130)
  Heart BPM: {bpm}
  Active alert: {alert}
  Sleep mode:   {sleep_mode}
  Last signal:  {last_signal}

Call exactly ONE tool. If vitals are within normal ranges, call no_action.
No explanations. You are a reflex arc, not a narrator.
"""


class Brain(Organ):
    def __init__(self, bus):
        super().__init__("brain", bus)
        self.state = {
            "status":          "active",
            "pulses_received": 0,
            "oxygen_level":    100,
            "glucose_level":   90,
            "bpm":             60,
            "sleep_mode":      False,
            "last_signal":     "—",
            "alert":           None,
            "reasoning_mode":  "reflex",
        }
        self._needs_reasoning = False
        self._last_reasoning  = 0.0
        self._loop            = None
        self._claude          = None

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            try:
                import anthropic
                self._claude = anthropic.Anthropic(api_key=api_key)
                self.state["reasoning_mode"] = "claude-agent"
            except ImportError:
                pass

    async def run(self):
        self._loop = asyncio.get_running_loop()
        if self._claude:
            asyncio.create_task(self._reasoning_loop())
        while True:
            msg = await self.receive()
            await self._handle(msg)

    # ── Signal handler ─────────────────────────────────────────────────

    async def _handle(self, msg: dict):
        signal = msg.get("signal")

        if signal == "pulse":
            self.state["pulses_received"] += 1
            self.state["bpm"] = msg.get("bpm", self.state["bpm"])
            self.state["last_signal"] = f"pulse #{self.state['pulses_received']}"

        elif signal == "oxygen":
            level = msg.get("level", 100)
            self.state["oxygen_level"] = level
            self.state["last_signal"] = f"O2={level}%"
            if level < OXYGEN_LOW:
                self.state["alert"] = f"LOW O2: {level}%"
                self._needs_reasoning = True
                if not self._claude:
                    await self.send("heart", signal="command", cmd="increase_bpm")
                    await self.send("lungs", signal="command", cmd="breathe_faster")
            else:
                if self.state["alert"] and "O2" in str(self.state["alert"]):
                    self.state["alert"] = None
                    self._needs_reasoning = True
                    if not self._claude:
                        await self.send("heart", signal="command", cmd="regulate")
                        await self.send("lungs", signal="command", cmd="breathe_normal")

        elif signal == "glucose":
            level = msg.get("level", 90)
            self.state["glucose_level"] = level
            self.state["last_signal"] = f"glucose={level} mg/dL"
            if level < GLUCOSE_LOW:
                self.state["alert"] = f"LOW GLUCOSE: {level} mg/dL"
                self._needs_reasoning = True
            elif level > GLUCOSE_HIGH:
                self.state["alert"] = f"HIGH GLUCOSE: {level} mg/dL"
                self._needs_reasoning = True
            else:
                if self.state["alert"] and "GLUCOSE" in str(self.state["alert"]):
                    self.state["alert"] = None

        elif signal == "alert":
            source = msg.get("source", "?")
            self.state["alert"] = f"[{source.upper()}] {msg.get('msg', '')}"
            self.state["last_signal"] = f"alert from {source}"
            self._needs_reasoning = True

        elif signal == "circadian":
            mode = msg.get("mode", "wake")
            self.state["sleep_mode"] = (mode == "sleep")
            self.state["status"] = "sleeping" if mode == "sleep" else "active"
            self.state["last_signal"] = f"circadian → {mode}"

        elif signal == "language_result":
            cmd    = msg.get("cmd", "?")
            result = msg.get("result", {})
            if result.get("ok"):
                self.state["last_signal"] = f"lang/{cmd} ok"
                if cmd == "speak" and result.get("text"):
                    spoken = result["text"]
                    self.state["last_signal"] = (
                        f"spoke: {spoken[:60]}{'…' if len(spoken) > 60 else ''}"
                    )
            else:
                self.state["alert"] = f"[LANG] {result.get('error', 'unknown error')}"
                self.state["last_signal"] = f"lang/{cmd} error"

        self.bus.update_ui("brain", dict(self.state))

    # ── Claude reasoning loop ──────────────────────────────────────────

    async def _reasoning_loop(self):
        while True:
            await asyncio.sleep(2.0)
            if not self._needs_reasoning:
                continue
            now = time.time()
            if now - self._last_reasoning < REASONING_COOLDOWN_S:
                continue
            self._needs_reasoning = False
            self._last_reasoning = now
            try:
                await self._loop.run_in_executor(None, self._call_claude_sync)
            except Exception as exc:
                self.state["alert"] = f"[BRAIN-AGENT] {str(exc)[:60]}"
                self.bus.update_ui("brain", dict(self.state))

    def _call_claude_sync(self):
        """Synchronous Claude call — runs in a thread-pool executor."""
        import asyncio as _asyncio
        system = _BRAIN_SYSTEM.format(
            o2=self.state["oxygen_level"],
            glucose=self.state["glucose_level"],
            bpm=self.state["bpm"],
            alert=self.state["alert"] or "none",
            sleep_mode=self.state["sleep_mode"],
            last_signal=self.state["last_signal"],
        )
        response = self._claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            tools=BRAIN_TOOLS,
            system=system,
            messages=[{"role": "user", "content": "What action should I take?"}],
        )
        for block in response.content:
            if block.type == "tool_use":
                _asyncio.run_coroutine_threadsafe(
                    self._execute_tool(block.name, block.input),
                    self._loop,
                )

    async def _execute_tool(self, name: str, inputs: dict):
        if name == "command_heart":
            await self.send("heart", signal="command", cmd=inputs["cmd"])
        elif name == "command_lungs":
            await self.send("lungs", signal="command", cmd=inputs["cmd"])
        elif name == "broadcast_alert":
            self.state["alert"] = inputs["message"]
            await self.broadcast(signal="alert", source="brain", msg=inputs["message"])
        # no_action: intentional no-op
        self.bus.update_ui("brain", dict(self.state))
