#!/usr/bin/env python3
"""Nervous System research report generator (dsg2).

Reporting-only utility. NOT a digi-soul runtime dependency.
Builds a professional PDF documenting the research basis for the
NervousSystem module upgrade (PR #1, merge SHA 04521d5).
Run:  python /Users/mehmetkucuk/Documents/GitHub/digi-soul/reports/_generate_nervous_system_report.py
"""

from fpdf import FPDF

REPO_PATH = "/Users/mehmetkucuk/Documents/GitHub/digi-soul"
REPORT_DATE = "2026-06-28"
TITLE = ("Nervous System & Brain-Organ Coupling - Research Basis for the "
         "digi-soul NervousSystem Module")
PREPARED_BY = "dsg-bio-researcher (research) / dsg2 (report)"
OUTPUT = f"{REPO_PATH}/reports/nervous_system_research_{REPORT_DATE}.pdf"

# ---------------------------------------------------------------------------
# latin-1 sanitisation so fpdf core fonts never crash on encoding
# ---------------------------------------------------------------------------
_REPL = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", "→": "->",
    "×": "x", "≤": "<=", "≥": ">=", "µ": "u",
    "°": " deg", " ": " ", " ": " ",
    "²": "2", "³": "3", "–": "-", "é": "e",
    "≈": "~",
}


def s(text):
    if text is None:
        return ""
    for k, v in _REPL.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------
KEY_FINDINGS = [
    ("1. CNS/PNS architecture & brain interface",
     ["The PNS divides into somatic (voluntary) and autonomic (involuntary) "
      "branches; the autonomic branch is the primary brain-to-organ control "
      "channel.",
      "The brainstem (medulla, pons), hypothalamus, and insular/prefrontal "
      "cortex form the central autonomic network.",
      "Rapid signaling depends on myelination / saltatory conduction "
      "(Draghici & Taylor 2018, PMID 28844537; Salzer 2015, PMID 26054742)."]),
    ("2. Autonomic organ regulation",
     ["The arterial baroreflex is the canonical fast negative-feedback loop; "
      "vagal cardiac control often persists when sympathetic pathways are "
      "disrupted.",
      "Sympathetic outflow is graded (rate + recruitment + temporal coding), "
      "not on/off (Shoemaker 2017, PMID 28871339)."]),
    ("3. Neural signaling",
     ["Action-potential propagation speed is set by axon diameter and "
      "myelination (Salzer 2015, PMID 26054742)."]),
    ("4. Brain-organ feedback",
     ["Three parallel bidirectional channels - neural (vagus/enteric), "
      "endocrine (HPA axis), immune (cytokines) (Asadi 2022, PMID 35421277).",
      "HPA feedback can break down: CRH/ACTH 'inappropriately normal' despite "
      "high cortisol; a proposed CRH-norepinephrine positive-feedback loop "
      "drives hypercortisolism (Perrelli 2024, PMID 38927393).",
      "HRV and baroreflex sensitivity are validated non-invasive readouts of "
      "vagal/sympathetic balance. In Guillain-Barre syndrome, LF-HRV "
      "(p=0.027), HF-HRV (p=0.008), total power (p=0.015), and BRS slopes "
      "(p=0.034/0.011) are all significantly reduced (Tan 2019, "
      "PMID 29654380)."]),
]

ANIMAL_FLAG = ("Animal-data flag: Huzard 2019 (PMID 30448728) is rodent-only - "
               "treated as a mechanistic hypothesis only, not a human "
               "parameter source.")

# (rank, citation, count) for the top-papers table
PAPERS = [
    ("1", "Salzer, 2015 - \"Schwann cell myelination\" - Cold Spring Harb "
          "Perspect Biol", "PMID 26054742", "DOI 10.1101/cshperspect.a020529",
     "330 (21 influential)"),
    ("2", "Perrelli et al., 2024 - \"Stress and the CRH System, "
          "Norepinephrine, Depression, and Type 2 Diabetes\"",
     "PMID 38927393", "DOI 10.3390/biomedicines12061187", "29 (1 influential)"),
    ("3", "Shoemaker, 2017 - \"Recruitment strategies in efferent sympathetic "
          "nerve activity\"", "PMID 28871339",
     "DOI 10.1007/s10286-017-0459-x", "13 (0 influential)"),
    ("4", "Tan et al., 2019 - \"HRV and baroreflex sensitivity abnormalities "
          "in Guillain-Barre syndrome\"", "PMID 29654380",
     "DOI 10.1007/s10286-018-0525-z", "4 (1 influential)"),
    ("5", "Draghici & Taylor, 2018 - \"Baroreflex autonomic control in human "
          "spinal cord injury\"", "PMID 28844537", "DOI n/a",
     "n/a (rate-limited)"),
    ("6", "Asadi et al., 2022 - gut-microbiota-brain axis", "PMID 35421277",
     "DOI n/a", "n/a (rate-limited)"),
]

CONSTANTS = [
    ("Conduction velocities (Kandel)",
     ["Aa  80-120 m/s", "Ab  35-75 m/s", "Ad  5-30 m/s",
      "B (preganglionic autonomic)  3-15 m/s", "C (unmyelinated)  0.5-2 m/s"]),
    ("Membrane / action potential",
     ["resting -70 mV; threshold -55 mV; spike peak +30 to +40 mV",
      "AP duration 1-2 ms; refractory 1-2 ms; synaptic delay 0.5-1 ms"]),
    ("Autonomic latency asymmetry",
     ["vagal effect fast (<1 s, beat-to-beat)",
      "sympathetic slow (onset 1-5 s, peak 20-30 s)"]),
    ("HRV bands (Task Force 1996) & norms (Shaffer & Ginsberg 2017)",
     ["VLF <0.04 Hz; LF 0.04-0.15 Hz; HF 0.15-0.40 Hz",
      "Healthy norms: SDNN ~50 ms, RMSSD ~42 ms, LF/HF ~1.5-2.0"]),
    ("Baroreflex & heart rate",
     ["Baroreflex sensitivity ~10-20 ms/mmHg (healthy adults)",
      "Intrinsic HR ~100-110 bpm (full autonomic blockade)",
      "Resting HR 60-80 bpm reflects net vagal dominance"]),
]

IMPLEMENTATION = [
    "Merged to main as PR #1 (merge SHA 04521d5). Five files touched:",
    "  - nervous_system/autonomic.py",
    "  - nervous_system/nervous_system.py",
    "  - organs/vascular_system.py",
    "  - circuit.py",
    "  - canvas/display.py",
    "",
    "Delivered:",
    "  1. Dual autonomic effector pathways with vagal-fast / sympathetic-slow "
    "latency asymmetry.",
    "  2. Graded saturating sympathetic output (rate + recruitment), not "
    "on/off.",
    "  3. Baroreflex negative-feedback loop with emergent HRV diagnostics.",
    "  4. Per-fiber conduction-velocity delays.",
    "  5. Tunable HPA cortisol->CRH/ACTH feedback gain; detuning reproduces "
    "the Perrelli 2024 pathology.",
    "  6. GUI rendering of autonomic / HRV / HPA diagnostics in the Neural "
    "tab.",
    "",
    "Two bugs fixed during integration:",
    "  - a missing _autonomic_loop() AttributeError",
    "  - a baroreflex resting set-point bug",
]

GAPS = [
    "- Semantic Scholar citation counts for Draghici 2018 and Asadi 2022 are "
    "still pending (API rate-limited; retry after cooldown or with an "
    "x-api-key token).",
    "- Brain-to-liver/stomach/kidney autonomic latencies are under-quantified "
    "in humans - parameterized by fiber type rather than measured constants.",
    "",
    "Suggested follow-up research:",
    "  - age-stratified HRV norms",
    "  - vagal control of gastric secretion",
    "  - renal sympathetic / ADH coupling",
    "  - hepatic sympathetic glucose output",
    "  - cholinergic anti-inflammatory pathway (Tracey)",
]


# ---------------------------------------------------------------------------
# PDF build
# ---------------------------------------------------------------------------
class Report(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130)
        self.cell(0, 6, s("digi-soul - NervousSystem Research Basis"), align="L")
        self.cell(0, 6, s(REPORT_DATE), align="R")
        self.set_text_color(0)
        self.ln(8)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")
        self.set_text_color(0)


def section_heading(pdf, text):
    if pdf.get_y() > 245:
        pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(40, 55, 75)
    pdf.multi_cell(0, 9, s(text))
    pdf.set_text_color(0)
    pdf.ln(2)


pdf = Report()
pdf.set_auto_page_break(auto=True, margin=15)

# --- Title page ---
pdf.add_page()
pdf.ln(40)
pdf.set_font("Helvetica", "B", 22)
pdf.cell(0, 12, s("digi-soul"), align="C")
pdf.ln(16)
pdf.set_font("Helvetica", "B", 14)
pdf.set_text_color(40, 55, 75)
pdf.set_x(pdf.l_margin)
pdf.multi_cell(0, 9, s("Nervous System & Brain-Organ Coupling"), align="C")
pdf.set_font("Helvetica", "", 12)
pdf.set_text_color(90)
pdf.set_x(pdf.l_margin)
pdf.multi_cell(0, 7, s("Research Basis for the digi-soul NervousSystem Module"),
               align="C")
pdf.set_text_color(0)
pdf.ln(22)
pdf.set_font("Helvetica", "", 11)
pdf.set_text_color(60)
for label, val in [
    ("Date", REPORT_DATE),
    ("Prepared by", PREPARED_BY),
    ("Repository", REPO_PATH),
    ("Implementation", "PR #1, merge SHA 04521d5 (origin/main)"),
]:
    pdf.cell(0, 8, s(f"{label}:  {val}"), align="C")
    pdf.ln(8)
pdf.ln(12)
pdf.set_font("Helvetica", "I", 10)
pdf.set_text_color(110)
pdf.set_x(pdf.l_margin)
pdf.multi_cell(0, 6, s(
    "This report documents the peer-reviewed literature, physiological "
    "constants, and citation evidence that grounded the recent digi-soul "
    "NervousSystem upgrade. Research by dsg-bio-researcher; report compiled "
    "by dsg2."), align="C")
pdf.set_text_color(0)

# --- 1. Key findings ---
pdf.add_page()
section_heading(pdf, "1. Key Findings")
for title, bullets in KEY_FINDINGS:
    if pdf.get_y() > 245:
        pdf.add_page()
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6, s(title))
    pdf.set_font("Helvetica", "", 9.5)
    for b in bullets:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5.2, s("  - " + b))
    pdf.ln(2)
pdf.ln(1)
pdf.set_font("Helvetica", "I", 9)
pdf.set_text_color(150, 70, 40)
pdf.set_x(pdf.l_margin)
pdf.multi_cell(0, 5.2, s(ANIMAL_FLAG))
pdf.set_text_color(0)

# --- 2. Top papers table ---
pdf.add_page()
section_heading(pdf, "2. Top Papers")
pdf.set_font("Helvetica", "I", 9)
pdf.set_text_color(110)
pdf.multi_cell(0, 5, s("Citation counts via Semantic Scholar, retrieved "
                       "2026-06-28."))
pdf.set_text_color(0)
pdf.ln(2)

# table header
col_rank = 8
col_id = 40
col_cite = 28
pdf.set_font("Helvetica", "B", 8.5)
pdf.set_fill_color(40, 55, 75)
pdf.set_text_color(255)
pdf.cell(col_rank, 7, s("#"), fill=True)
pdf.cell(0, 7, s("Paper"), fill=True)
pdf.ln(7)
pdf.set_text_color(0)

fill = False
for rank, citation, pmid, doi, count in PAPERS:
    if pdf.get_y() > 255:
        pdf.add_page()
    pdf.set_fill_color(238, 242, 247)
    y0 = pdf.get_y()
    x0 = pdf.l_margin
    # rank cell
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(x0, y0)
    pdf.cell(col_rank, 6, s(rank))
    # citation block
    pdf.set_xy(x0 + col_rank, y0)
    pdf.set_font("Helvetica", "B", 9)
    pdf.multi_cell(0, 5, s(citation))
    pdf.set_x(x0 + col_rank)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(70)
    pdf.multi_cell(0, 4.6, s(f"{pmid}  |  {doi}  |  Citations: {count}"))
    pdf.set_text_color(0)
    pdf.ln(2)
    fill = not fill

# --- 3. Physiological constants ---
pdf.add_page()
section_heading(pdf, "3. Physiological Constants (model-ready)")
for title, rows in CONSTANTS:
    if pdf.get_y() > 248:
        pdf.add_page()
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6, s(title))
    pdf.set_font("Courier", "", 8.5)
    for r in rows:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, s("    " + r))
    pdf.ln(2)

# --- 4. Implementation outcome ---
pdf.add_page()
section_heading(pdf, "4. Implementation Outcome (what shipped)")
pdf.set_font("Helvetica", "", 9.5)
for line in IMPLEMENTATION:
    if line == "":
        pdf.ln(2.5)
        continue
    if pdf.get_y() > 262:
        pdf.add_page()
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5.4, s(line))

# --- 5. Known gaps / follow-up ---
pdf.ln(4)
section_heading(pdf, "5. Known Gaps / Follow-up")
pdf.set_font("Helvetica", "", 9.5)
for line in GAPS:
    if line == "":
        pdf.ln(2.5)
        continue
    if pdf.get_y() > 262:
        pdf.add_page()
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5.4, s(line))

pdf.output(OUTPUT)
print("WROTE", OUTPUT)
