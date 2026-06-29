"""
language_module.py — Language Module for Digi-Soul Brain

Handles ingestion, storage, and retrieval of text (*.txt) files.
Uses the Anthropic API (Claude) to generate speech from loaded memory.
Integrates with the Brain via the MessageBus.

Universal Grammar layer (Chomsky, "Language and Mind"):
  Every text loaded is annotated against six innate UG primitives (AGENT,
  ACTION, STATE, NEGATION, MODIFIER, QUESTION). The structural summary of
  the corpus is prepended to each speak() system prompt so Claude generates
  language consistent with Digi-Soul's current linguistic register.
  A new "parse" command exposes the UG structure of any input text.

Signals received (from brain or other organs):
    { "signal": "language", "cmd": "load",   "path": "<filepath>" }
    { "signal": "language", "cmd": "save",   "text": "<text>", "filename": "<name.txt>" }
    { "signal": "language", "cmd": "query",  "keyword": "<word>" }
    { "signal": "language", "cmd": "recall", "doc_id": "<id>" }
    { "signal": "language", "cmd": "speak",   "prompt": "<text>", "style": "<style>" }
    { "signal": "language", "cmd": "parse",   "text": "<text>" }
    { "signal": "language", "cmd": "perceive", "path": "<doc.pdf|doc.txt>" }   ← NEW

Document perception (Layer 2 — sensory channel):
    The "perceive" command lets the digital body "read" an external document
    (PDF or .txt) as a perception event. The text is extracted via
    document_reader, persisted into language memory, and indexed (vocabulary +
    Universal Grammar) exactly like any other loaded text — so a perceived
    document is fully recallable and feeds future speak() calls.

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
from language.document_reader import read_document
from language.universal_grammar import UniversalGrammar

STORAGE_DIR  = Path(__file__).parent / "memory"
CLAUDE_MODEL = "claude-opus-4-6"


class LanguageModule(Organ):
    """
    Language processing module — reads and stores .txt files, builds a
    vocabulary index, answers keyword queries, generates speech via Claude,
    and parses text using the Universal Grammar layer.
    """

    def __init__(self, bus, storage_dir: Path = STORAGE_DIR):
        super().__init__("language_module", bus)
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # In-memory corpus: { doc_id: {"text", "path", "vocab", "ug_annotation"} }
        self.corpus: dict[str, dict] = {}

        # Universal Grammar — innate linguistic structure (Chomsky)
        self._ug = UniversalGrammar()

        # Anthropic client
        self._claude = anthropic.Anthropic()

        self.state = {
            "status":        "ready",
            "docs_loaded":   0,
            "last_action":   "—",
            "last_doc_id":   None,
            "vocab_size":    0,
            "last_spoken":   None,
            "grammar_stats": {},   # UG category distribution over full corpus
            "alert":         None,
        }

    # ── Public helpers ────────────────────────────────────────────────────

    def load_file(self, path: str | Path) -> str:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if path.suffix.lower() != ".txt":
            raise ValueError(f"Only .txt files are supported, got: {path.suffix}")
        text   = path.read_text(encoding="utf-8")
        doc_id = self._index(text, source_path=path)
        return doc_id

    def perceive_document(self, path: str | Path) -> dict:
        """
        Perceive an external document (PDF or .txt) as a sensory input.

        Reads the document into plain text via the document_reader channel,
        persists the extracted text into language memory, and indexes it
        (vocabulary + Universal Grammar) so it is recallable and shapes future
        speech. Returns perception metadata including the new doc_id.

        Raises (surfaced cleanly to the brain by _handle's error wrapper):
            FileNotFoundError, UnsupportedDocumentError, EmptyDocumentError,
            DocumentReadError.
        """
        src          = Path(path)
        text         = read_document(src)                 # typed errors on failure
        dest, doc_id = self.save_text(text, f"perceived_{src.stem}.txt")
        return {
            "doc_id": doc_id,
            "source": str(src),
            "stored": str(dest),
            "chars":  len(text),
        }

    def save_text(self, text: str, filename: str) -> tuple[Path, str]:
        """Persist `text` to memory and index it.

        Returns a (dest_path, doc_id) tuple so callers get the storage location
        and the new corpus doc_id explicitly — no need to read state afterwards.
        """
        if not filename.endswith(".txt"):
            filename += ".txt"
        dest = self.storage_dir / filename
        dest.write_text(text, encoding="utf-8")
        doc_id = self._index(text, source_path=dest)
        return dest, doc_id

    def query(self, keyword: str) -> list[dict]:
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
        Generate a spoken response via Claude, grounded in:
          1. The loaded language memory (corpus)
          2. The Universal Grammar structural summary (Chomsky UG)

        The UG layer ensures the generated language is consistent with
        the dominant structural register of the corpus — an action-dominant
        corpus produces more imperative speech; a state-dominant corpus
        produces more declarative speech.
        """
        corpus_context = self._build_corpus_context()
        ug_summary     = self._ug.structural_summary()

        system = (
            "You are the language centre of Digi-Soul, a digital humanoid brain. "
            "You speak with the knowledge, vocabulary, and style drawn from your language memory. "
            f"Your language memory contains:\n\n{corpus_context}\n\n"
            f"Linguistic structure (Universal Grammar analysis):\n{ug_summary}\n\n"
            f"Speak in a {style} style. Be concise — two to four sentences maximum. "
            "Let the UG register guide your sentence structure."
        )
        message = self._claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    def recall(self, doc_id: str) -> dict | None:
        doc = self.corpus.get(doc_id)
        if not doc:
            return None
        return {
            "doc_id":        doc_id,
            "path":          str(doc["path"]),
            "text":          doc["text"],
            "words":         sum(doc["vocab"].values()),
            "ug_annotation": doc.get("ug_annotation", {}),
        }

    # ── Organ loop ────────────────────────────────────────────────────────

    async def run(self):
        while True:
            msg = await self.receive()
            if msg.get("signal") != "language":
                continue

            cmd    = msg.get("cmd", "")
            result = await self._handle(cmd, msg)
            self.bus.update_ui("language_module", dict(self.state))
            await self.send("brain", signal="language_result", cmd=cmd, result=result)

    # ── Internal dispatch ─────────────────────────────────────────────────

    async def _handle(self, cmd: str, msg: dict):
        try:
            if cmd == "load":
                doc_id = self.load_file(msg["path"])
                self.state["last_action"] = f"loaded {msg['path']}"
                return {"ok": True, "doc_id": doc_id}

            elif cmd == "perceive":
                info = self.perceive_document(msg["path"])
                self.state["last_action"] = (
                    f"perceived {Path(msg['path']).name} ({info['chars']} chars)"
                )
                return {"ok": True, **info}

            elif cmd == "save":
                filename    = msg.get("filename") or self._auto_filename()
                dest, doc_id = self.save_text(msg["text"], filename)
                self.state["last_action"] = f"saved {dest.name}"
                return {"ok": True, "path": str(dest), "doc_id": doc_id}

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
                loop   = asyncio.get_running_loop()
                text   = await loop.run_in_executor(
                    None, lambda: self.speak(prompt, style)
                )
                self.state["last_action"] = f"spoke ({style})"
                self.state["last_spoken"] = (
                    text[:80] + ("…" if len(text) > 80 else "")
                )
                return {"ok": True, "text": text}

            elif cmd == "parse":
                text   = msg.get("text", "")
                result = self._ug.parse(text)
                self.state["last_action"] = f"parsed text ({result['sentence_count']} sentences)"
                return {"ok": True, "parse_result": result}

            else:
                return {"ok": False, "error": f"Unknown cmd: {cmd}"}

        except Exception as exc:
            self.state["alert"] = str(exc)
            return {"ok": False, "error": str(exc)}

    def _index(self, text: str, source_path: Path) -> str:
        tokens     = re.findall(r"[a-zA-ZÀ-ÿ]+", text.lower())
        vocab      = Counter(tokens)
        ug_ann     = self._ug.annotate(text)
        doc_id     = source_path.stem + "_" + datetime.now().strftime("%H%M%S%f")

        self.corpus[doc_id] = {
            "text":          text,
            "path":          source_path,
            "vocab":         vocab,
            "ug_annotation": ug_ann,
        }

        self.state["docs_loaded"] += 1
        self.state["last_doc_id"]  = doc_id
        self.state["last_action"]  = f"indexed {source_path.name}"
        self.state["vocab_size"]   = len(
            set().union(*(d["vocab"].keys() for d in self.corpus.values()))
        )
        # Update grammar stats: average UG distribution across corpus
        cats = list(ug_ann.keys())
        self.state["grammar_stats"] = {
            cat: round(
                sum(d["ug_annotation"].get(cat, 0) for d in self.corpus.values())
                / len(self.corpus),
                3,
            )
            for cat in cats
        }
        return doc_id

    @staticmethod
    def _excerpt(text: str, keyword: str, window: int = 60) -> str:
        idx = text.lower().find(keyword)
        if idx == -1:
            return ""
        start = max(0, idx - window)
        end   = min(len(text), idx + len(keyword) + window)
        return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")

    def _build_corpus_context(self, max_docs: int = 6, preview_chars: int = 300) -> str:
        if not self.corpus:
            return "(no language memory loaded yet)"
        parts = []
        for doc in list(self.corpus.values())[:max_docs]:
            preview = doc["text"][:preview_chars].replace("\n", " ").strip()
            parts.append(
                f"• [{doc['path'].name}] {preview}"
                f"{'…' if len(doc['text']) > preview_chars else ''}"
            )
        return "\n".join(parts)

    @staticmethod
    def _auto_filename() -> str:
        return "doc_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt"
