"""
language_module.py — Language Module for Digi-Soul Brain

Handles ingestion, storage, and retrieval of text (*.txt) files.
Uses the Anthropic API (Claude) to generate speech from loaded memory.
Integrates with the Brain via the MessageBus.

Signals received (from brain or other organs):
    { "signal": "language", "cmd": "load",   "path": "<filepath>" }
    { "signal": "language", "cmd": "save",   "text": "<text>", "filename": "<name.txt>" }
    { "signal": "language", "cmd": "query",  "keyword": "<word>" }
    { "signal": "language", "cmd": "recall", "doc_id": "<id>" }
    { "signal": "language", "cmd": "speak",  "prompt": "<text>", "style": "<style>" }

Signals emitted → brain:
    { "signal": "language_result", "cmd": "...", "result": ... }

Environment:
    ANTHROPIC_API_KEY  — required for the "speak" command
"""

import asyncio
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import anthropic

from core.organ import Organ

STORAGE_DIR = Path(__file__).parent / "memory"
CLAUDE_MODEL = "claude-opus-4-6"


class LanguageModule(Organ):
    """
    Language processing module — reads and stores .txt files,
    builds a simple vocabulary index, and answers keyword queries.
    Acts as an Organ so it plugs straight into the MessageBus.
    """

    def __init__(self, bus, storage_dir: Path = STORAGE_DIR):
        super().__init__("language_module", bus)
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # In-memory corpus: { doc_id: {"text": str, "path": Path, "vocab": Counter} }
        self.corpus: dict[str, dict] = {}

        # Anthropic client — reads ANTHROPIC_API_KEY from environment
        self._claude = anthropic.Anthropic()

        self.state = {
            "status":        "ready",
            "docs_loaded":   0,
            "last_action":   "—",
            "last_doc_id":   None,
            "vocab_size":    0,
            "last_spoken":   None,
            "alert":         None,
        }

    # ── Public helpers (usable directly without the bus) ───────────────

    def load_file(self, path: str | Path) -> str:
        """Read a .txt file, index it, and return its doc_id."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if path.suffix.lower() != ".txt":
            raise ValueError(f"Only .txt files are supported, got: {path.suffix}")

        text = path.read_text(encoding="utf-8")
        doc_id = self._index(text, source_path=path)
        return doc_id

    def save_text(self, text: str, filename: str) -> Path:
        """Persist raw text to storage_dir and index it. Returns saved path."""
        if not filename.endswith(".txt"):
            filename += ".txt"
        dest = self.storage_dir / filename
        dest.write_text(text, encoding="utf-8")
        self._index(text, source_path=dest)
        return dest

    def query(self, keyword: str) -> list[dict]:
        """Return docs that contain keyword, sorted by frequency."""
        kw = keyword.lower().strip()
        results = []
        for doc_id, doc in self.corpus.items():
            count = doc["vocab"].get(kw, 0)
            if count:
                results.append({
                    "doc_id":    doc_id,
                    "path":      str(doc["path"]),
                    "frequency": count,
                    "excerpt":   self._excerpt(doc["text"], kw),
                })
        results.sort(key=lambda r: r["frequency"], reverse=True)
        return results

    def speak(self, prompt: str, style: str = "thoughtful") -> str:
        """
        Generate a spoken response via Claude, grounded in the loaded language memory.
        The corpus is injected as the system context so Digi-Soul speaks from what it knows.
        """
        corpus_context = self._build_corpus_context()
        system = (
            "You are the language centre of Digi-Soul, a digital humanoid brain. "
            "You speak with the knowledge, vocabulary, and style drawn from your language memory. "
            f"Your language memory currently contains:\n\n{corpus_context}\n\n"
            f"Speak in a {style} style. Be concise — two to four sentences maximum."
        )
        message = self._claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    def recall(self, doc_id: str) -> dict | None:
        """Return full stored document or None."""
        doc = self.corpus.get(doc_id)
        if not doc:
            return None
        return {
            "doc_id": doc_id,
            "path":   str(doc["path"]),
            "text":   doc["text"],
            "words":  sum(doc["vocab"].values()),
        }

    # ── Organ loop (MessageBus integration) ────────────────────────────

    async def run(self):
        while True:
            msg = await self.receive()
            if msg.get("signal") != "language":
                continue

            cmd = msg.get("cmd", "")
            result = await self._handle(cmd, msg)
            self.bus.update_ui("language_module", dict(self.state))

            await self.send("brain", signal="language_result", cmd=cmd, result=result)

    # ── Internal ───────────────────────────────────────────────────────

    async def _handle(self, cmd: str, msg: dict):
        try:
            if cmd == "load":
                doc_id = self.load_file(msg["path"])
                self.state["last_action"] = f"loaded {msg['path']}"
                return {"ok": True, "doc_id": doc_id}

            elif cmd == "save":
                filename = msg.get("filename") or self._auto_filename()
                dest = self.save_text(msg["text"], filename)
                self.state["last_action"] = f"saved {dest.name}"
                return {"ok": True, "path": str(dest)}

            elif cmd == "query":
                hits = self.query(msg["keyword"])
                self.state["last_action"] = f"query '{msg['keyword']}' → {len(hits)} hits"
                return {"ok": True, "hits": hits}

            elif cmd == "recall":
                doc = self.recall(msg["doc_id"])
                self.state["last_action"] = f"recall {msg['doc_id']}"
                return {"ok": bool(doc), "doc": doc}

            elif cmd == "speak":
                prompt = msg.get("prompt", "Say something.")
                style  = msg.get("style", "thoughtful")
                loop = asyncio.get_running_loop()
                text = await loop.run_in_executor(None, lambda: self.speak(prompt, style))
                self.state["last_action"] = f"spoke ({style})"
                self.state["last_spoken"] = text[:80] + ("…" if len(text) > 80 else "")
                return {"ok": True, "text": text}

            else:
                return {"ok": False, "error": f"Unknown cmd: {cmd}"}

        except Exception as exc:
            self.state["alert"] = str(exc)
            return {"ok": False, "error": str(exc)}

    def _index(self, text: str, source_path: Path) -> str:
        """Tokenise text, build vocab Counter, store in corpus."""
        tokens = re.findall(r"[a-zA-ZÀ-ÿ]+", text.lower())
        vocab  = Counter(tokens)
        doc_id = source_path.stem + "_" + datetime.now().strftime("%H%M%S%f")

        self.corpus[doc_id] = {
            "text":  text,
            "path":  source_path,
            "vocab": vocab,
        }

        # Update shared state
        self.state["docs_loaded"] += 1
        self.state["last_doc_id"]  = doc_id
        self.state["last_action"]  = f"indexed {source_path.name}"
        self.state["vocab_size"]   = len(
            set().union(*(d["vocab"].keys() for d in self.corpus.values()))
        )
        return doc_id

    @staticmethod
    def _excerpt(text: str, keyword: str, window: int = 60) -> str:
        """Return a short excerpt around the first occurrence of keyword."""
        idx = text.lower().find(keyword)
        if idx == -1:
            return ""
        start = max(0, idx - window)
        end   = min(len(text), idx + len(keyword) + window)
        return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")

    def _build_corpus_context(self, max_docs: int = 6, preview_chars: int = 300) -> str:
        """Summarise the loaded corpus for Claude's system prompt."""
        if not self.corpus:
            return "(no language memory loaded yet)"
        parts = []
        for doc in list(self.corpus.values())[:max_docs]:
            preview = doc["text"][:preview_chars].replace("\n", " ").strip()
            parts.append(f"• [{doc['path'].name}] {preview}{'…' if len(doc['text']) > preview_chars else ''}")
        return "\n".join(parts)

    @staticmethod
    def _auto_filename() -> str:
        return "doc_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt"
