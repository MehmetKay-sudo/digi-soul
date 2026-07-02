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
import math
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import anthropic

from core.organ import Organ
from language.development import DevelopmentEngine
from language.document_reader import read_document
from language.universal_grammar import UniversalGrammar

STORAGE_DIR  = Path(__file__).parent / "memory"
CLAUDE_MODEL = "claude-opus-4-6"

# Default developmental age for a Digi-Soul body: 30 years (= 360 months).
# In development.py, prefrontal spine-pruning (Petanjek 2011, PMID 21788513)
# completes at ~30 y, so DevelopmentEngine.suggested_syntax_gain() == 1.0 there.
# Anchoring the default here keeps a fresh (adult) agent's BA44 syntax gain at
# the mature 1.0 reference — existing behaviour is unchanged.
DEFAULT_DEVELOPMENTAL_AGE_MONTHS = 360.0


# ══════════════════════════════════════════════════════════════════════════
# ACOUSTIC OUTPUT LAYER — parametrisation of the spoken voice signal
# ══════════════════════════════════════════════════════════════════════════
# This layer turns Digi-Soul's physiological state into the physical acoustic
# parameters of speech: fundamental frequency (F0, perceived pitch), formant
# frequencies (vowel timbre) and intensity (loudness). Values are drawn from
# peer-reviewed phonetics literature; each constant carries its source. Where
# the literature is uncertain, a CLEARLY-COMMENTED placeholder/default is used
# rather than invented precision.
#
# The breath → phonation coupling lives across two organs: the LUNGS own the
# subglottal pressure (single source of truth), and this module maps that
# pressure to loudness and pitch. dsg-engineer2 can wire acoustic_state() into
# language_bridge.py as the public read-out.
# --------------------------------------------------------------------------

# ── Fundamental frequency F0 (Hz) — mean speaking/crying pitch by demographic
# Adult means: Peterson & Barney (1952), DOI 10.1121/1.1906875.
# Newborn cry fundamental ~500 Hz: Out et al. (2010), PMID 20889206.
F0_MALE_ADULT   = 130.0   # adult male speaking F0 (~120–130 Hz)
F0_FEMALE_ADULT = 220.0   # adult female speaking F0 (~210–220 Hz)
F0_CHILD_10_12  = 265.0   # child ~10–12 yr speaking F0
F0_NEWBORN_CRY  = 500.0   # newborn cry fundamental (Out et al. 2010)

# ── Formants F1/F2/F3 (Hz) — MALE reference vowels
# Adult-male measured means: Hillenbrand et al. (1995), PMID 7759650.
# Formants scale with vocal-tract length, so female/child tracts (shorter)
# shift these systematically upward — see VOCAL_TRACT_FORMANT_SCALE below.
FORMANTS_MALE_HZ = {
    # vowel : (F1, F2, F3)
    "i": (290.0, 2200.0, 2950.0),   # close front /i/  (Hillenbrand 1995)
    "ɑ": (700.0, 1750.0, 2450.0),   # open back  /ɑ/  (Hillenbrand 1995)
    # /u/ (close back rounded): researcher flagged the exact F1/F2/F3 as
    # UNCERTAIN pending full-text extraction. Placeholder derived from the
    # canonical close-back region (F1≈300, F2≈870, F3≈2240, Hillenbrand-range)
    # — treat as provisional, NOT a verified measurement.
    "u": (300.0, 870.0, 2240.0),    # PLACEHOLDER — verify against full text
}

# Multiplicative formant-shift factors relative to the adult-male tract.
# Shorter tract → higher formants. These are documented approximations of the
# male→female/child scaling in Hillenbrand (1995); the age/sex factor is meant
# to feed the model, not to assert exact per-speaker values.
VOCAL_TRACT_FORMANT_SCALE = {
    "male_adult":   1.00,   # reference
    "female_adult": 1.17,   # ~15–20% higher formants (shorter tract)
    "child_10_12":  1.25,   # children higher still
    # Newborn formants are poorly characterised in this dataset → provisional.
    "newborn":      1.35,   # PLACEHOLDER — provisional, verify before use
}

# F0 per demographic profile (keys match VOCAL_TRACT_FORMANT_SCALE).
F0_BY_PROFILE = {
    "male_adult":   F0_MALE_ADULT,
    "female_adult": F0_FEMALE_ADULT,
    "child_10_12":  F0_CHILD_10_12,
    "newborn":      F0_NEWBORN_CRY,
}

# ── Pressure → loudness (subglottal pressure Ps → intensity in dB SPL)
# Ladefoged & McKinney (1963): sound level rises ~8–9 dB SPL per DOUBLING of
# the *excess* lung (subglottal) pressure above the phonation threshold.
DB_SPL_PER_PRESSURE_DOUBLING = 8.0    # dB SPL per doubling of excess Ps
PHONATION_THRESHOLD_PRESSURE = 3.0    # cmH2O — Ps below this yields no voice
                                      # (typical phonation threshold pressure)
# Reference operating point for the loudness curve: conversational speech
# (~10 cmH2O Ps) is taken as ~60 dB SPL at 1 m. SPL_REF anchors the log law;
# it is a nominal reference level, not a claim about a specific talker.
SPL_REFERENCE_DB          = 60.0      # dB SPL at the reference pressure
SPL_REFERENCE_PRESSURE    = 10.0      # cmH2O (conversational level)

# ── Pressure → F0 (subglottal pressure Ps → pitch)
# Raising Ps raises F0. Reported coefficients span roughly 2–5 Hz per cmH2O.
# We default to the mid-range; the EXACT value requires full-text verification
# (marked uncertain by the researcher) and is intentionally a single tunable
# constant so it can be corrected in one place.
F0_HZ_PER_CMH2O           = 3.0       # Hz per cmH2O — DEFAULT, verify full text
F0_PRESSURE_REFERENCE     = SPL_REFERENCE_PRESSURE  # Ps at which F0 = base F0

# Default demographic voice profile for Digi-Soul's body.
DEFAULT_VOICE_PROFILE     = "male_adult"


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

        # Neurodevelopmental plasticity engine. Drives the BA44 syntax gain of
        # the Universal Grammar layer from the body's age: syntactic competence
        # lags prefrontal maturation (Petanjek 2011, PMID 21788513). Defaults to
        # an adult age so mature behaviour (gain 1.0) is unchanged; call
        # set_developmental_age(...) to model a younger, syntactically simpler body.
        self._dev = DevelopmentEngine(age_months=DEFAULT_DEVELOPMENTAL_AGE_MONTHS)
        self._sync_syntax_gain()   # push the age-appropriate gain into UG now

        # Anthropic client
        self._claude = anthropic.Anthropic()

        # Demographic voice profile → sets base F0 and formant scaling.
        self._voice_profile = DEFAULT_VOICE_PROFILE

        self.state = {
            "status":        "ready",
            "docs_loaded":   0,
            "last_action":   "—",
            "last_doc_id":   None,
            "vocab_size":    0,
            "last_spoken":   None,
            "grammar_stats": {},   # UG category distribution over full corpus
            "voice_profile": self._voice_profile,
            "acoustics":     {},   # last computed F0 / intensity / formants
            "developmental_age_months": self._dev.age_months,
            "syntax_gain":   round(self._ug.syntax_gain, 3),  # BA44 Merge gain
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

    # ── Developmental plasticity → syntactic competence ───────────────────

    def _sync_syntax_gain(self) -> None:
        """Pull the age-appropriate BA44 gain from the DevelopmentEngine into UG.

        Wires development.py → universal_grammar.py: the prefrontal-maturation
        proxy (Petanjek 2011, PMID 21788513) scales the Merge/combinatorial
        engine so syntactic output tracks the body's neural maturity.

        Caveat (documented by dsg-engineer2 in development.py): the Petanjek
        spine-pruning timeline runs to ~30 y and therefore UNDER-weights the
        syntax children already command. We wire it exactly as delivered — no
        faster curve is invented here.
        """
        self._ug.set_syntax_gain(self._dev.suggested_syntax_gain())

    def set_developmental_age(self, age_months: float) -> None:
        """Set the body's developmental age (months) and re-derive syntax gain.

        Updates the DevelopmentEngine clock, then refreshes the Universal
        Grammar BA44 gain so syntactic competence follows prefrontal maturation.
        A young age lowers the gain (simpler, flatter syntax); an adult age
        (>= ~30 y) leaves it at the mature 1.0 reference.
        """
        self._dev.set_age(months=age_months)
        self._sync_syntax_gain()
        self.state["developmental_age_months"] = self._dev.age_months
        self.state["syntax_gain"] = round(self._ug.syntax_gain, 3)

    # ── Acoustic output layer ─────────────────────────────────────────────

    def set_voice_profile(self, profile: str) -> None:
        """Select the demographic voice profile (sets base F0 + formant scale).

        Valid keys: 'male_adult', 'female_adult', 'child_10_12', 'newborn'.
        """
        if profile not in F0_BY_PROFILE:
            raise ValueError(
                f"Unknown voice profile {profile!r}; "
                f"choose one of {sorted(F0_BY_PROFILE)}"
            )
        self._voice_profile = profile
        self.state["voice_profile"] = profile

    def formants_for(self, vowel: str = "ɑ") -> tuple[float, float, float]:
        """Formant triple (F1, F2, F3) for `vowel` under the active profile.

        Male reference values (Hillenbrand 1995) are scaled up for the shorter
        female/child vocal tract via VOCAL_TRACT_FORMANT_SCALE.
        """
        base = FORMANTS_MALE_HZ.get(vowel)
        if base is None:
            raise ValueError(
                f"No reference formants for vowel {vowel!r}; "
                f"available: {sorted(FORMANTS_MALE_HZ)}"
            )
        scale = VOCAL_TRACT_FORMANT_SCALE.get(self._voice_profile, 1.0)
        return tuple(round(f * scale, 1) for f in base)

    def _subglottal_pressure(self) -> float:
        """Read the current subglottal pressure (cmH2O) from the lungs.

        The lungs are the single source of truth for this value — we never
        duplicate it here. If the lungs are not registered on the bus (e.g. the
        language module is exercised standalone), fall back to the resting 0.
        """
        lungs = self.bus._organs.get("lungs")
        if lungs is not None and hasattr(lungs, "subglottal_pressure"):
            return float(lungs.subglottal_pressure())
        return 0.0

    def current_f0(self, pressure_cmh2o: float | None = None) -> float:
        """Fundamental frequency (Hz): demographic base + pressure contribution.

        F0 = base_F0 + F0_HZ_PER_CMH2O * (Ps − reference Ps). Higher subglottal
        pressure raises pitch (positive coefficient, ~2–5 Hz/cmH2O; default 3).
        Below the phonation threshold there is no voice → F0 = 0.
        """
        ps = self._subglottal_pressure() if pressure_cmh2o is None else pressure_cmh2o
        if ps < PHONATION_THRESHOLD_PRESSURE:
            return 0.0
        base = F0_BY_PROFILE[self._voice_profile]
        return round(base + F0_HZ_PER_CMH2O * (ps - F0_PRESSURE_REFERENCE), 1)

    def intensity_db(self, pressure_cmh2o: float | None = None) -> float:
        """Loudness (dB SPL) from subglottal pressure (Ladefoged & McKinney 1963).

        ~8 dB SPL per doubling of the EXCESS pressure (Ps above the phonation
        threshold), anchored so that conversational Ps (~10 cmH2O) ≈ 60 dB SPL.
        Below threshold there is no phonation → 0 dB SPL.
        """
        ps = self._subglottal_pressure() if pressure_cmh2o is None else pressure_cmh2o
        excess     = ps - PHONATION_THRESHOLD_PRESSURE
        excess_ref = SPL_REFERENCE_PRESSURE - PHONATION_THRESHOLD_PRESSURE
        if excess <= 0 or excess_ref <= 0:
            return 0.0
        doublings = math.log2(excess / excess_ref)
        return round(SPL_REFERENCE_DB + DB_SPL_PER_PRESSURE_DOUBLING * doublings, 1)

    def acoustic_state(self, vowel: str = "ɑ") -> dict:
        """Public read-out of the current acoustic output state.

        Returns F0 (Hz), intensity (dB SPL), the formant triple for `vowel`,
        the driving subglottal pressure, the active voice profile, and whether
        the voice is currently phonating. This is the clean hook dsg-engineer2
        can bind into language_bridge.py — it reads live physiological state
        (lung pressure) without duplicating it.
        """
        ps      = self._subglottal_pressure()
        f1, f2, f3 = self.formants_for(vowel)
        acoustics = {
            "voice_profile":            self._voice_profile,
            "subglottal_pressure_cmh2o": round(ps, 1),
            "phonating":                ps >= PHONATION_THRESHOLD_PRESSURE,
            "f0_hz":                    self.current_f0(ps),
            "intensity_db_spl":         self.intensity_db(ps),
            "vowel":                    vowel,
            "formants_hz":              {"F1": f1, "F2": f2, "F3": f3},
        }
        self.state["acoustics"] = acoustics   # surface to the UI
        return acoustics

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
