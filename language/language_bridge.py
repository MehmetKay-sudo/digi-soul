"""
language_bridge.py — Rapbot ↔ Digi-Soul Language Bridge

Syncs .txt files from rapbot's memory folder into the digi-soul language module,
and allows rap verses generated during a battle to be written back into the
shared memory so the brain's vocabulary grows over time.

Usage (standalone):
    from language.language_module import LanguageModule
    from language.language_bridge import RapbotBridge

    lm     = LanguageModule(bus=None)          # bus=None for offline use
    bridge = RapbotBridge(lm)
    bridge.sync()                              # pull all rapbot txt files
    bridge.push_verse("I'm the king of rhyme, one bar at a time", label="battle_01")

Usage (via MessageBus signal to language_module):
    { "signal": "language", "cmd": "load", "path": "<rapbot_memory_path>/<file>.txt" }
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from language.language_module import LanguageModule

# Canonical paths — relative to this file's location inside digi-soul/language/
_GITHUB_DIR    = Path(__file__).parent.parent.parent          # .../GitHub/
RAPBOT_ROOT    = _GITHUB_DIR / "rapbot" / "rapbot"            # .../GitHub/rapbot/rapbot/
RAPBOT_MEMORY  = RAPBOT_ROOT / "memory"                       # rapbot's own memory folder


class RapbotBridge:
    """
    One-way and two-way sync between rapbot's text repository and
    the digi-soul language module's memory store.
    """

    def __init__(self, language_module: "LanguageModule"):
        self.lm = language_module

    # ── Ingest rapbot → digi-soul ──────────────────────────────────────

    def sync(self, rapbot_root: Path = RAPBOT_ROOT) -> list[str]:
        """
        Load every .txt file found under rapbot_root into the language module.
        Returns list of doc_ids that were indexed.

        Files loaded (if present):
          - adjectives.txt        (word bank)
          - memory/*.txt          (training texts / lyrics)
        """
        rapbot_root = Path(rapbot_root)
        doc_ids: list[str] = []

        if not rapbot_root.exists():
            print(f"[bridge] rapbot not found at {rapbot_root} — skipping sync")
            return doc_ids

        # 1. Top-level txt files (adjectives.txt, any other word banks)
        for txt in rapbot_root.glob("*.txt"):
            try:
                doc_ids.append(self.lm.load_file(txt))
                print(f"[bridge] indexed {txt.name}")
            except Exception as exc:
                print(f"[bridge] skipped {txt.name}: {exc}")

        # 2. memory/ subfolder
        memory_dir = rapbot_root / "memory"
        if memory_dir.exists():
            for txt in memory_dir.glob("*.txt"):
                try:
                    doc_ids.append(self.lm.load_file(txt))
                    print(f"[bridge] indexed memory/{txt.name}")
                except Exception as exc:
                    print(f"[bridge] skipped memory/{txt.name}: {exc}")
        else:
            print(f"[bridge] no memory/ folder found at {memory_dir} — only top-level files loaded")

        print(f"[bridge] sync complete — {len(doc_ids)} file(s) indexed")
        return doc_ids

    # ── Write back digi-soul ← rapbot verse ───────────────────────────

    def push_verse(self, verse: str, label: str = "verse") -> Path:
        """
        Persist a rap verse (generated during a battle) into the language module's
        persistent memory so future Claude prompts draw on it.

        Args:
            verse:  The rap text to store.
            label:  Short tag used in the filename (e.g. "battle_round_1").

        Returns:
            Path of the saved .txt file inside language/memory/.
        """
        filename = f"rapbot_{label}.txt"
        dest = self.lm.save_text(verse, filename)
        print(f"[bridge] verse saved → {dest}")
        return dest

    # ── Convenience: sync + report ─────────────────────────────────────

    def status(self) -> dict:
        return {
            "corpus_size":  self.lm.state["docs_loaded"],
            "vocab_size":   self.lm.state["vocab_size"],
            "last_action":  self.lm.state["last_action"],
            "rapbot_root":  str(RAPBOT_ROOT),
            "storage_dir":  str(self.lm.storage_dir),
        }
