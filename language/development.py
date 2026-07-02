"""
development.py — region-specific neurodevelopmental plasticity engine.

Language does not mature as one homogeneous whole-brain curve. Different neural
regions open and close their high-plasticity windows at different times, and in
a fixed order:

    EARLY-MATURING  → auditory / phonetic cortex and the dorsal language tract
    LATE-MATURING   → prefrontal cortex, which carries hierarchical SYNTAX

This module turns that ordering into a timeline-based engine: given the body's
age it returns a *per-region* plasticity / gain value in [0, 1] (or a density
ratio, where noted). The prefrontal_syntax output is meant to drive the BA44
combinatorial-engine gain in language/universal_grammar.py, so that syntactic
competence lags behind phonetic competence exactly as it does biologically.

────────────────────────────────────────────────────────────────────────────
Scientific anchors (peer-reviewed; PMIDs on every constant):

  Phonetic critical window .... 6-12 months; native contrasts sharpen while
                                non-native contrasts decline (perceptual
                                narrowing).            Kuhl 2006, PMID 16472309

  Myelination sensitive window  6-24 months for the dorsal tract (arcuate
  (arcuate / SLF) .............. fasciculus / superior longitudinal fasciculus);
                                input-dependent, driven by conversational
                                turn-taking.           Huber 2023, PMID 36746626

  Synaptogenesis .............. peak rate of synapse formation at 2-4 months in
                                early sensory / auditory cortex; maximum cortical
                                synaptic density around ~1 year; then ~40% of
                                synapses are eliminated between 8 months and
                                11 years.
                                Huttenlocher 1987, PMID 3583840
                                Huttenlocher 1984, PMID 6731486 (peak ~1 yr)

  Prefrontal / syntax ......... late-maturing; dendritic spine density reaches
  (late) ...................... 2-3x the adult level during childhood, and
                                pruning continues into the third decade of life
                                (~30 y).               Petanjek 2011, PMID 21788513

  Native-grammar acquirability  monotonically falling with a knee at puberty
  (critical period) ........... (~12-15 y): roughly linear decline before, a
                                low flat plateau after (NOT a hard cut-off).
                                Johnson & Newport 1989, PMID 2920538

────────────────────────────────────────────────────────────────────────────
Honesty note on the learning MECHANISM:
  There is NO established single quantitative Hebbian learning-rate constant for
  the human brain, so none is invented here. Hebbian / statistical learning is
  modelled as a *mechanism* — plasticity within a region is realised only in
  proportion to the INPUT the region receives (e.g. conversational turn-taking
  for myelination). See `myelination_gain(input_level=...)`.

  Where a curve needs a shape between the literature-fixed knots, the ramp/decay
  bounds and any residual-floor are labelled ENGINEERING constants (tunable,
  not literature values). Every literature-derived number carries its PMID.
"""

from __future__ import annotations

# ── Literature-anchored constants (PMID on each) ─────────────────────────────

# Phonetic critical window — native contrasts up, non-native down.
PHONETIC_WINDOW_MONTHS = (6, 12)              # PMID 16472309 (Kuhl 2006)

# Dorsal language-tract (arcuate / SLF) myelination sensitive window;
# input-dependent (conversational turn-taking).
MYELINATION_WINDOW_MONTHS = (6, 24)           # PMID 36746626 (Huber 2023)

# Synaptogenesis: peak *rate* of synapse formation (early sensory/auditory).
SYNAPTOGENESIS_PEAK_MONTHS = (2, 4)           # PMID 3583840 (Huttenlocher 1987)
# Maximum cortical synaptic *density* (~1 year of age).
MAX_CORTICAL_DENSITY_MONTHS = 12              # PMID 6731486 (Huttenlocher 1984)
# ~40% of synapses eliminated between 8 months and 11 years (= 132 months).
SYNAPTIC_ELIMINATION_FRACTION = 0.40          # PMID 3583840 (Huttenlocher 1987)
SYNAPTIC_ELIMINATION_SPAN_MONTHS = (8, 132)   # PMID 3583840 (8 mo → 11 y)

# Prefrontal (late-maturing, syntax): childhood dendritic-spine density is
# 2-3x adult, and pruning runs into the third decade (~30 y).
PREFRONTAL_SPINE_PEAK_RATIO = (2.0, 3.0)      # PMID 21788513 (Petanjek 2011)
PREFRONTAL_PRUNING_END_YEARS = 30             # PMID 21788513 (third decade)

# Native-grammar acquirability: puberty knee, decline-then-plateau shape.
GRAMMAR_KNEE_YEARS = (12, 15)                 # PMID 2920538 (Johnson & Newport 1989)

# ── Engineering constants (modelling shape only — NOT literature values) ─────
# Small residual plasticity floor so no window closes to a hard zero (the
# critical-period literature describes decline, not a hard cut-off).
_PLASTICITY_FLOOR = 0.05
# Residual grammar acquirability on the post-puberty plateau. Johnson & Newport
# report a low, variable, individual-dependent plateau rather than one number,
# so this is exposed as a tunable engineering parameter, not a literature value.
GRAMMAR_PLATEAU_FLOOR = 0.5
# Engineering decay bounds: how far past a window's close plasticity fades to
# the floor. Chosen for smoothness; not literature values.
_PHONETIC_DECAY_END_MONTHS = 24               # ~1 window-width past close
_MYELINATION_DECAY_END_MONTHS = 48            # taper past the sensitive window
# Prefrontal spine density is treated as plateaued through early childhood
# before pruning begins; this ramp bound is an engineering choice.
_PREFRONTAL_PLATEAU_END_YEARS = 5


# ── Small numeric helpers ────────────────────────────────────────────────────

def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _soft_window(
    t: float,
    rise0: float,
    full0: float,
    full1: float,
    close1: float,
    floor: float = _PLASTICITY_FLOOR,
) -> float:
    """
    Piecewise-linear plasticity window in [floor, 1].

        floor ── rise ──▶ 1.0 ── plateau ── 1.0 ── decay ──▶ floor

    The literature fixes the plateau [full0, full1] (the sensitive window);
    `rise0` and `close1` are engineering ramp/decay bounds (shape only).
    """
    if t <= rise0:
        return floor
    if t < full0:
        return floor + (1.0 - floor) * (t - rise0) / (full0 - rise0)
    if t <= full1:
        return 1.0
    if t < close1:
        return floor + (1.0 - floor) * (close1 - t) / (close1 - full1)
    return floor


# ── The engine ───────────────────────────────────────────────────────────────

class DevelopmentEngine:
    """
    Timeline-based, region-specific plasticity engine.

    Hold a developmental clock (age) and read off each region's current
    plasticity / gain. Regions mature in the biological order
    (auditory/phonetic → dorsal tract → prefrontal/syntax).

    Usage:
        dev = DevelopmentEngine(age_months=9)
        dev.phonetic_plasticity()          # ~1.0 inside the 6-12 mo window
        dev.myelination_gain(input_level=0.8)
        dev.region_plasticity()            # dict of every region at once
        dev.advance(months=6)              # step the clock forward

        # Wire syntactic competence into Universal Grammar:
        ug.set_syntax_gain(dev.suggested_syntax_gain())
    """

    # Region maturation order (early → late). Purely informational.
    REGION_ORDER = (
        "auditory_phonetic",         # earliest
        "dorsal_tract_myelination",
        "prefrontal_syntax",         # latest
    )

    def __init__(self, age_months: float = 0.0):
        self.age_months: float = float(age_months)

    # ── Clock ────────────────────────────────────────────────────────────
    @property
    def age_years(self) -> float:
        return self.age_months / 12.0

    def advance(self, months: float) -> None:
        """Step the developmental clock forward by `months` (may be fractional)."""
        self.age_months = max(0.0, self.age_months + float(months))

    def set_age(self, *, months: float | None = None, years: float | None = None) -> None:
        if months is not None:
            self.age_months = max(0.0, float(months))
        elif years is not None:
            self.age_months = max(0.0, float(years) * 12.0)

    # ── EARLY region: auditory / phonetic (Kuhl 2006, PMID 16472309) ──────
    def phonetic_plasticity(self) -> float:
        """
        Openness of the phonetic learning window. Peaks across the 6-12 month
        native-contrast window, then narrows (perceptual narrowing) toward the
        residual floor. PMID 16472309.
        """
        return _soft_window(
            self.age_months,
            rise0=0.0,
            full0=PHONETIC_WINDOW_MONTHS[0],
            full1=PHONETIC_WINDOW_MONTHS[1],
            close1=_PHONETIC_DECAY_END_MONTHS,
        )

    def native_contrast_gain(self) -> float:
        """
        Native-phoneme discrimination: rises across the window and is retained
        (does not decay away) — native categories, once formed, persist.
        PMID 16472309.
        """
        m = self.age_months
        if m <= 0:
            return _PLASTICITY_FLOOR
        if m >= PHONETIC_WINDOW_MONTHS[1]:
            return 1.0
        # linear rise from birth to window close
        return _clamp(
            _PLASTICITY_FLOOR
            + (1.0 - _PLASTICITY_FLOOR) * m / PHONETIC_WINDOW_MONTHS[1]
        )

    def nonnative_contrast_gain(self) -> float:
        """
        Non-native-phoneme discrimination: present early, then declines across
        the 6-12 month window (perceptual narrowing). PMID 16472309.
        """
        lo, hi = PHONETIC_WINDOW_MONTHS
        m = self.age_months
        if m <= lo:
            return 1.0
        if m >= hi:
            return _PLASTICITY_FLOOR
        return _clamp(1.0 - (1.0 - _PLASTICITY_FLOOR) * (m - lo) / (hi - lo))

    # ── EARLY-MID region: dorsal-tract myelination (Huber 2023, PMID 36746626)
    def myelination_sensitivity(self) -> float:
        """
        How plastic the dorsal language tract (arcuate / SLF) is to input right
        now. Sensitive window 6-24 months. PMID 36746626.
        """
        return _soft_window(
            self.age_months,
            rise0=0.0,
            full0=MYELINATION_WINDOW_MONTHS[0],
            full1=MYELINATION_WINDOW_MONTHS[1],
            close1=_MYELINATION_DECAY_END_MONTHS,
        )

    def myelination_gain(self, input_level: float = 1.0) -> float:
        """
        Realised myelination progress = window sensitivity × INPUT.

        Input-dependent (conversational turn-taking): the sensitive window only
        yields myelination in proportion to input the region actually receives.
        This is the Hebbian / statistical-learning MECHANISM — reinforcement by
        input — deliberately WITHOUT any invented learning-rate constant.
        PMID 36746626.

        `input_level` in [0, 1]: 0 = deprivation, 1 = rich turn-taking.
        """
        return round(self.myelination_sensitivity() * _clamp(input_level), 3)

    # ── Synaptogenesis / density (Huttenlocher 1987/1984) ─────────────────
    def synaptogenesis_rate(self) -> float:
        """
        Normalised *rate* of synapse formation; peaks at 2-4 months in early
        sensory/auditory cortex, then falls. PMID 3583840.
        """
        return _soft_window(
            self.age_months,
            rise0=0.0,
            full0=SYNAPTOGENESIS_PEAK_MONTHS[0],
            full1=SYNAPTOGENESIS_PEAK_MONTHS[1],
            close1=MAX_CORTICAL_DENSITY_MONTHS,
            floor=0.0,
        )

    def synaptic_density(self) -> float:
        """
        Cortical synaptic density normalised to its own peak (= 1.0 at ~1 year,
        PMID 6731486). Rises from birth to the peak, then ~40% of synapses are
        eliminated between 8 months and 11 years, settling to the adult plateau
        of (1 - 0.40) = 0.60 of peak. PMID 3583840.
        """
        m = self.age_months
        peak_m = MAX_CORTICAL_DENSITY_MONTHS
        elim_lo, elim_hi = SYNAPTIC_ELIMINATION_SPAN_MONTHS
        adult = 1.0 - SYNAPTIC_ELIMINATION_FRACTION   # 0.60 of peak

        if m <= 0:
            return _PLASTICITY_FLOOR
        if m < peak_m:
            # rise from birth to peak density at ~1 year
            return _clamp(
                _PLASTICITY_FLOOR + (1.0 - _PLASTICITY_FLOOR) * m / peak_m
            )
        if m <= elim_lo:
            return 1.0                                 # at/near peak plateau
        if m < elim_hi:
            # linear elimination of ~40% of synapses across 8 mo → 11 y
            frac = (m - elim_lo) / (elim_hi - elim_lo)
            return round(1.0 - SYNAPTIC_ELIMINATION_FRACTION * frac, 3)
        return round(adult, 3)                         # adult plateau

    # ── LATE region: prefrontal / syntax (Petanjek 2011, PMID 21788513) ───
    def prefrontal_spine_density(self) -> float:
        """
        Prefrontal dendritic-spine density as a ratio to the ADULT level.
        Childhood peak is 2-3x adult (midpoint used); pruning brings it down to
        1.0 by the end of the third decade (~30 y). PMID 21788513.
        """
        peak_ratio = sum(PREFRONTAL_SPINE_PEAK_RATIO) / 2.0    # 2.5x adult
        y = self.age_years
        if y <= _PREFRONTAL_PLATEAU_END_YEARS:
            return round(peak_ratio, 3)                        # childhood plateau
        if y >= PREFRONTAL_PRUNING_END_YEARS:
            return 1.0                                         # adult
        # linear pruning from childhood peak to adult across the decline span
        span = PREFRONTAL_PRUNING_END_YEARS - _PREFRONTAL_PLATEAU_END_YEARS
        frac = (y - _PREFRONTAL_PLATEAU_END_YEARS) / span
        return round(peak_ratio - (peak_ratio - 1.0) * frac, 3)

    def prefrontal_maturity(self) -> float:
        """
        Prefrontal (syntactic-circuit) maturity in [0, 1]: 0 while spine density
        is still at the childhood peak, 1.0 once pruning has reached the adult
        level (~30 y). This is the proxy for hierarchical-syntax competence.
        PMID 21788513.
        """
        peak_ratio = sum(PREFRONTAL_SPINE_PEAK_RATIO) / 2.0
        density = self.prefrontal_spine_density()
        # map density [peak_ratio → 1.0] onto maturity [0 → 1]
        return round(_clamp((peak_ratio - density) / (peak_ratio - 1.0)), 3)

    # ── Native-grammar acquirability (Johnson & Newport 1989, PMID 2920538)
    def grammar_acquirability(self) -> float:
        """
        Capacity to acquire native-like grammar in [floor, 1]. Highest in
        infancy; roughly linear decline to the puberty knee (~12-15 y, midpoint
        used); a low flat plateau afterwards (NOT a hard cut-off). PMID 2920538.
        The post-puberty plateau value (GRAMMAR_PLATEAU_FLOOR) is a tunable
        engineering parameter, since the literature reports a variable,
        individual-dependent residual rather than one number.
        """
        knee = sum(GRAMMAR_KNEE_YEARS) / 2.0           # 13.5 y
        y = self.age_years
        if y <= 0:
            return 1.0
        if y >= knee:
            return GRAMMAR_PLATEAU_FLOOR
        # linear decline from 1.0 at birth to the plateau floor at the knee
        return round(
            1.0 - (1.0 - GRAMMAR_PLATEAU_FLOOR) * (y / knee), 3
        )

    # ── Bridge to Universal Grammar's BA44 gain ───────────────────────────
    def suggested_syntax_gain(self) -> float:
        """
        Suggested BA44 combinatorial-engine gain for universal_grammar.py.

        This tracks the maturation of the prefrontal substrate that carries
        hierarchical syntax (Petanjek 2011, PMID 21788513) — the "late-maturing"
        region — so it is simply `prefrontal_maturity()`: ~0 in childhood, rising
        to 1.0 once pruning has completed (~30 y).

        It is deliberately kept SEPARATE from `grammar_acquirability()`, which is
        the critical-period capacity to *acquire a new* native grammar
        (Johnson & Newport 1989, PMID 2920538) and DECLINES with age — a
        learnability signal, not a runtime-competence multiplier. Conflating the
        two would wrongly cap a mature adult's syntactic engine.

        Caveat: using Petanjek's protracted spine-pruning timeline as the proxy
        is conservative — it under-weights the substantial syntax children
        command before pruning completes. No faster curve is invented here
        because none was supplied in the literature brief.

        Feed straight into UniversalGrammar.set_syntax_gain(...).
        """
        return self.prefrontal_maturity()

    # ── Aggregate views ───────────────────────────────────────────────────
    def region_plasticity(self, input_level: float = 1.0) -> dict:
        """
        Current plasticity / gain for every modelled region, in maturation
        order. `input_level` feeds the input-dependent myelination gain.
        """
        return {
            "auditory_phonetic": {
                "plasticity":            round(self.phonetic_plasticity(), 3),
                "native_contrast":       round(self.native_contrast_gain(), 3),
                "nonnative_contrast":    round(self.nonnative_contrast_gain(), 3),
                "synaptogenesis_rate":   round(self.synaptogenesis_rate(), 3),
                "synaptic_density":      self.synaptic_density(),
            },
            "dorsal_tract_myelination": {
                "sensitivity":           round(self.myelination_sensitivity(), 3),
                "gain_at_input":         self.myelination_gain(input_level),
            },
            "prefrontal_syntax": {
                "spine_density_ratio":   self.prefrontal_spine_density(),
                "maturity":              self.prefrontal_maturity(),
            },
            "grammar_acquirability":     self.grammar_acquirability(),
            "suggested_syntax_gain":     self.suggested_syntax_gain(),
        }

    def summary(self) -> str:
        """One-line human-readable developmental snapshot."""
        y = self.age_years
        return (
            f"Age {self.age_months:.0f} mo (~{y:.1f} y): "
            f"phonetic={self.phonetic_plasticity():.2f}, "
            f"myelination_sens={self.myelination_sensitivity():.2f}, "
            f"synaptic_density={self.synaptic_density():.2f}, "
            f"prefrontal_maturity={self.prefrontal_maturity():.2f}, "
            f"grammar_acquirability={self.grammar_acquirability():.2f}, "
            f"suggested BA44 gain={self.suggested_syntax_gain():.2f}"
        )
