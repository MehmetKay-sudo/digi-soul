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

# Chomsky's subordinating conjunctions signal recursive phrase structure
RECURSION_MARKERS = {
    "that", "which", "who", "whose", "when", "where",
    "if", "because", "although", "while", "since", "after", "before",
}


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

    def __init__(self):
        # Session-level accumulator: tracks UG usage across all indexed documents
        # (simulates growth of I-language competence over time)
        self._session_counts: Counter = Counter({c: 0 for c in self.CATEGORIES})
        self._texts_annotated: int = 0

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

    def parse(self, text: str) -> dict:
        """
        Parse text into a UG structural summary (Chomsky-style analysis).
        Returns:
          - categories:      normalized UG distribution
          - dominant:        top-3 categories
          - sentence_count:  number of clauses detected
          - recursion_depth: count of subordinating conjunctions (proxy for embedding)
          - i_language_notes: characterization of the text's I-language register
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
        }

    def structural_summary(self) -> str:
        """
        Produce a natural-language summary of the corpus's UG character.
        Injected into the speak() system prompt so Claude generates language
        consistent with the body's current linguistic register.
        """
        if self._texts_annotated == 0:
            return (
                "Biolinguistic baseline active (Chomsky UG). "
                "No corpus loaded yet — speaking from innate structure only."
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
            f"I-language register: {self._i_language_summary_global()}."
        )

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
