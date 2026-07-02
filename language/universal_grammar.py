"""
Universal Grammar module — innate linguistic structure.

Based on: Chomsky, N. "Language and Mind" (3rd ed., Cambridge University Press)
  Chapter 7: "Biolinguistics and the Human Language Faculty"

  "Language is as much a part of our biological nature as the visual system
   or the immune system." — Chomsky (2006)

  Universal Grammar (UG): the innate linguistic knowledge that every human
  speaker is born with. It defines the possible structures of human language
  independent of any particular language learned. This is I-language
  (internal, individual, intensional) — the computational system inside the mind.

Practical implementation for Digi-Soul:
  Digi-Soul's language module is modelled on the biolinguistic view: it starts
  with a fixed set of primitive categories (UG) and builds its corpus on top.
  This mirrors the distinction between the innate Language Acquisition Device
  and the learned lexicon/grammar.

  Six UG primitives implemented here correspond to Chomsky's functional/lexical
  distinction and the basic thematic roles of linguistics:

    AGENT    — entities that act (subjects, experiencers)
    ACTION   — verbs, processes, events
    STATE    — copular/stative predicates, properties
    NEGATION — logical negation operators
    MODIFIER — degree words, adverbs, intensifiers
    QUESTION — wh-words, interrogative markers (recursive inquiry)

  Corpus texts are annotated against these primitives. The speak() prompt
  receives a structural summary so that Claude generates language that is
  consistent with the body's current linguistic register.

Neurolinguistic grounding (added 2026-07-02):
  The syntactic processing here is organised along the DUAL-STREAM model of
  Hickok & Poeppel 2007 (PMID 17431404):
    - a VENTRAL stream (bilateral) for comprehension / lexical-semantics, and
    - a DORSAL stream (left-lateralised) for perception → articulation and,
      via the arcuate fasciculus / SLF, syntactic production.
  Broca's area BA44 is modelled as a "combinatorial engine" running the
  operation MERGE (recursive hierarchy building), with an individually
  settable gain that scales syntactic competence — Friederici 2020
  (PMID 31735144) and Liu 2023 (PMID 37287773). The per-body, age-dependent
  value for this gain is produced by language/development.py.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ── Innate UG lexical categories ─────────────────────────────────────────────
UG_CATEGORIES: dict[str, list[str]] = {
    "AGENT": [
        "i", "we", "you", "he", "she", "they", "it", "who",
        "robot", "body", "brain", "system", "organ", "cell",
        "self", "digi", "soul",
    ],
    "ACTION": [
        "run", "move", "send", "think", "feel", "know", "make", "go",
        "activate", "fire", "breathe", "beat", "regulate", "respond",
        "detect", "process", "control", "emit", "receive", "produce",
        "release", "secrete", "filter", "pump", "contract", "expand",
    ],
    "STATE": [
        "is", "are", "was", "were", "be", "been", "being",
        "seem", "appear", "remain", "stay", "maintain", "hold",
        "exist", "contain", "carry",
    ],
    "NEGATION": [
        "not", "no", "never", "without", "lack", "absent", "fail",
        "stop", "prevent", "block", "inhibit", "suppress", "reduce",
    ],
    "MODIFIER": [
        "very", "quite", "more", "less", "most", "least", "always",
        "low", "high", "fast", "slow", "normal", "critical", "acute",
        "chronic", "stable", "elevated", "reduced", "increased",
    ],
    "QUESTION": [
        "what", "where", "when", "why", "how", "which", "whether",
        "who", "whose",
    ],
}

# Chomsky's subordinating conjunctions signal recursive phrase structure.
# Each such marker is treated as evidence of a MERGE operation that embeds one
# phrase inside another (see BA44 combinatorial engine below).
RECURSION_MARKERS = {
    "that", "which", "who", "whose", "when", "where",
    "if", "because", "although", "while", "since", "after", "before",
}

# ── Dual-stream cortical organisation (Hickok & Poeppel 2007, PMID 17431404) ──
# Language processing is split across two cortical pathways:
#
#   VENTRAL STREAM  — bilaterally organised (weakly lateralised); maps the
#                     signal onto MEANING — the lexical-semantic / comprehension
#                     interface.
#   DORSAL STREAM   — strongly LEFT-lateralised; maps perception onto
#                     ARTICULATION (the sensorimotor interface for production)
#                     and, through the arcuate fasciculus / SLF, feeds the
#                     combinatorial syntactic engine in Broca's area (BA44).
#
# Digi-Soul routing below is a MODELLING METAPHOR (not a literal anatomical
# claim): the meaning-bearing UG categories are treated as ventral-stream
# content, while structural/production-driving categories plus recursive
# hierarchy building are treated as dorsal-stream work.
VENTRAL_STREAM_CATEGORIES = ("AGENT", "STATE", "MODIFIER", "NEGATION")  # meaning
DORSAL_STREAM_CATEGORIES  = ("ACTION", "QUESTION")                      # production

# ── Broca's area BA44 as a combinatorial engine ──────────────────────────────
# BA44 (pars opercularis) implements the core syntactic operation MERGE — the
# recursive combination of elements into hierarchical structure ("hierarchy
# building"), the computational heart of the language faculty:
#   Friederici 2020, PMID 31735144 — BA44 as the hub for hierarchical syntax.
#   Liu 2023,       PMID 37287773 — BA44's combinatorial / hierarchy-building role.
#
# BA44_SYNTAX_GAIN scales how strongly the combinatorial engine can build and
# hold hierarchical structure. It is an INDIVIDUALLY SETTABLE parameter
# (per-body syntactic competence); 1.0 == typical mature-adult reference. During
# development it is lowered (immature prefrontal circuitry) — the age-dependent
# value is supplied by language/development.py (prefrontal_syntax region).
BA44_SYNTAX_GAIN_DEFAULT = 1.0


class UniversalGrammar:
    """
    Innate linguistic structure — Digi-Soul's biolinguistic foundation.

    Lives inside the LanguageModule. The corpus is always interpreted through
    this structural lens before being passed to Claude for generation.

    Usage:
        ug = UniversalGrammar()
        ann = ug.annotate("The brain activates the heart to increase speed.")
        # → {'AGENT': 0.25, 'ACTION': 0.5, ...}

        summary = ug.structural_summary()
        # → "Biolinguistic structure (Chomsky UG): ACTION=0.42, AGENT=0.28, ..."
    """

    CATEGORIES = list(UG_CATEGORIES.keys())

    def __init__(self, syntax_gain: float = BA44_SYNTAX_GAIN_DEFAULT):
        # Session-level accumulator: tracks UG usage across all indexed documents
        # (simulates growth of I-language competence over time)
        self._session_counts: Counter = Counter({c: 0 for c in self.CATEGORIES})
        self._texts_annotated: int = 0

        # BA44 combinatorial-engine gain (Merge strength). Individually settable;
        # development.py can drive this down for an immature prefrontal cortex.
        self.syntax_gain: float = float(syntax_gain)

    def set_syntax_gain(self, gain: float) -> None:
        """
        Set the BA44 combinatorial-engine gain (Friederici 2020, PMID 31735144).
        Typically fed from language/development.py so that syntactic competence
        tracks prefrontal maturation. 1.0 == mature-adult reference.
        """
        self.syntax_gain = max(0.0, float(gain))

    # ── Core methods ──────────────────────────────────────────────────────

    def annotate(self, text: str) -> dict[str, float]:
        """
        Annotate text with UG category weights.
        Returns normalized distribution over the 6 innate categories.
        Updates session-level I-language accumulator.
        """
        tokens = re.findall(r"[a-zA-Z]+", text.lower())
        counts: Counter = Counter()
        for token in tokens:
            for cat, keywords in UG_CATEGORIES.items():
                if token in keywords:
                    counts[cat] += 1
                    break   # each token matches at most one category

        self._session_counts.update(counts)
        self._texts_annotated += 1

        total = max(1, sum(counts.values()))
        return {cat: round(counts.get(cat, 0) / total, 3) for cat in self.CATEGORIES}

    def dominant_categories(self, annotation: dict[str, float], n: int = 3) -> list[str]:
        """Return the n most prominent UG categories in an annotation."""
        return sorted(annotation, key=annotation.get, reverse=True)[:n]

    def combinatorial_engine(self, text: str) -> dict:
        """
        Model Broca's BA44 as a MERGE-based combinatorial engine and route the
        text across the dual-stream architecture (Hickok & Poeppel 2007,
        PMID 17431404; Friederici 2020, PMID 31735144; Liu 2023, PMID 37287773).

        Each recursion marker (subordinating conjunction / relativiser) is taken
        as evidence of a MERGE operation embedding one phrase inside another
        ("hierarchy building"). Raw operations are scaled by the individually-set
        BA44 gain to give the *effective* syntactic yield.

        Returns:
          merge_operations  — raw count of hierarchy-building (Merge) operations
          hierarchy_depth   — proxy for maximum embedding depth (Merge stacking)
          syntax_gain       — current BA44 gain
          syntactic_yield   — merge_operations * BA44 gain (effective competence)
          ventral_load      — share of categorised tokens carrying meaning
          dorsal_load       — share of categorised tokens driving production
          dominant_stream   — 'ventral' | 'dorsal' | 'balanced'
        """
        tokens    = re.findall(r"[a-zA-Z]+", text.lower())
        sentences = [s for s in re.split(r"[.!?]", text) if s.strip()]

        merge_operations = sum(1 for t in tokens if t in RECURSION_MARKERS)

        # Max embedding depth ≈ 1 base clause + the most Merge markers stacked
        # inside any single clause.
        deepest_clause = 0
        for s in sentences:
            clause_tokens = re.findall(r"[a-zA-Z]+", s.lower())
            deepest_clause = max(
                deepest_clause,
                sum(1 for t in clause_tokens if t in RECURSION_MARKERS),
            )
        hierarchy_depth = (1 + deepest_clause) if tokens else 0

        # Dual-stream routing: split categorised tokens by ventral vs dorsal.
        ventral_kw = {kw for c in VENTRAL_STREAM_CATEGORIES for kw in UG_CATEGORIES[c]}
        dorsal_kw  = {kw for c in DORSAL_STREAM_CATEGORIES  for kw in UG_CATEGORIES[c]}
        ventral_hits = sum(1 for t in tokens if t in ventral_kw)
        dorsal_hits  = sum(1 for t in tokens if t in dorsal_kw)
        categorised  = ventral_hits + dorsal_hits

        if categorised:
            ventral_load = round(ventral_hits / categorised, 3)
            dorsal_load  = round(dorsal_hits / categorised, 3)
        else:
            ventral_load = dorsal_load = 0.0

        if ventral_load > dorsal_load:
            dominant_stream = "ventral"
        elif dorsal_load > ventral_load:
            dominant_stream = "dorsal"
        else:
            dominant_stream = "balanced"

        return {
            "merge_operations": merge_operations,
            "hierarchy_depth":  hierarchy_depth,
            "syntax_gain":      round(self.syntax_gain, 3),
            "syntactic_yield":  round(merge_operations * self.syntax_gain, 3),
            "ventral_load":     ventral_load,
            "dorsal_load":      dorsal_load,
            "dominant_stream":  dominant_stream,
        }

    def parse(self, text: str) -> dict:
        """
        Parse text into a UG structural summary (Chomsky-style analysis).
        Returns:
          - categories:      normalized UG distribution
          - dominant:        top-3 categories
          - sentence_count:  number of clauses detected
          - recursion_depth: count of subordinating conjunctions (proxy for embedding)
          - i_language_notes: characterization of the text's I-language register
          - syntax:          BA44 combinatorial-engine + dual-stream analysis
        """
        annotation    = self.annotate(text)
        sentences     = [s.strip() for s in re.split(r"[.!?]", text) if s.strip()]
        tokens        = re.findall(r"[a-zA-Z]+", text.lower())
        recursion_depth = sum(1 for t in tokens if t in RECURSION_MARKERS)

        return {
            "categories":       annotation,
            "dominant":         self.dominant_categories(annotation),
            "sentence_count":   len(sentences),
            "recursion_depth":  recursion_depth,
            "i_language_notes": self._i_language_summary(annotation),
            "syntax":           self.combinatorial_engine(text),
        }

    def structural_summary(self) -> str:
        """
        Produce a natural-language summary of the corpus's UG character.
        Injected into the speak() system prompt so Claude generates language
        consistent with the body's current linguistic register.
        """
        syntax_note = self._syntax_gain_note()

        if self._texts_annotated == 0:
            return (
                "Biolinguistic baseline active (Chomsky UG). "
                "No corpus loaded yet — speaking from innate structure only. "
                f"{syntax_note}"
            )

        total = max(1, sum(self._session_counts.values()))
        top_3 = sorted(
            self._session_counts, key=self._session_counts.get, reverse=True
        )[:3]
        proportions = {c: round(self._session_counts[c] / total, 2) for c in top_3}
        pct_str = ", ".join(f"{c}={v:.0%}" for c, v in proportions.items())
        return (
            f"Biolinguistic structure (Chomsky UG) across {self._texts_annotated} "
            f"indexed texts: dominant categories {pct_str}. "
            f"I-language register: {self._i_language_summary_global()}. "
            f"{syntax_note}"
        )

    def _syntax_gain_note(self) -> str:
        """
        Describe the BA44 combinatorial-engine gain for the speak() prompt so
        that generated syntactic complexity tracks the body's syntactic
        competence (Friederici 2020, PMID 31735144).
        """
        g = self.syntax_gain
        if g >= 0.9:
            level = "mature — full hierarchical (recursive) syntax available"
        elif g >= 0.6:
            level = "developing — moderate embedding, simpler clauses preferred"
        elif g >= 0.3:
            level = "early — mostly flat, short clauses; little embedding"
        else:
            level = "minimal — telegraphic, largely unstructured output"
        return f"Syntactic engine (BA44 Merge) gain {g:.2f}: {level}."

    # ── Internal helpers ──────────────────────────────────────────────────

    def _i_language_summary(self, annotation: dict[str, float]) -> str:
        dominant = self.dominant_categories(annotation)
        first = dominant[0] if dominant else "STATE"
        if first == "ACTION":
            return "Action-dominant: imperative or procedural I-language"
        elif first == "STATE":
            return "State-dominant: declarative or descriptive I-language"
        elif first == "QUESTION":
            return "Interrogative I-language: recursive inquiry mode"
        elif first == "NEGATION":
            return "Negation-heavy: constraint or inhibitory I-language"
        elif first == "AGENT":
            return "Agent-foregrounded: subject-prominent I-language"
        else:
            return "Modifier-rich: evaluative I-language"

    def _i_language_summary_global(self) -> str:
        dominant = sorted(
            self._session_counts, key=self._session_counts.get, reverse=True
        )
        return self._i_language_summary(
            {c: self._session_counts[c] for c in self.CATEGORIES}
        )
