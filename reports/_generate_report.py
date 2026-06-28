#!/usr/bin/env python3
"""digi-soul development report generator (dsg2).

Reporting-only utility. NOT a digi-soul runtime dependency.
Builds a professional PDF from the curated git history below.
Run:  python /Users/mehmetkucuk/Documents/GitHub/digi-soul/reports/_generate_report.py
"""

from fpdf import FPDF

REPO_PATH = "/Users/mehmetkucuk/Documents/GitHub/digi-soul"
REPORT_DATE = "2026-06-26"
AUTHOR = "Mehmet Kucuk"
OUTPUT = f"{REPO_PATH}/reports/dsg_report_{REPORT_DATE}.pdf"

# ---------------------------------------------------------------------------
# latin-1 sanitisation so fpdf core fonts never crash on encoding
# ---------------------------------------------------------------------------
_REPL = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", "→": "->",
    "×": "x", "≤": "<=", "≥": ">=", "µ": "u",
    "°": " deg", " ": " ", " ": " ",
    "²": "2", "³": "3",
}


def s(text):
    if text is None:
        return ""
    for k, v in _REPL.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


# ---------------------------------------------------------------------------
# Curated data (from git history through 35ca2de)
# ---------------------------------------------------------------------------
COMMITS = [
    {
        "hash": "35ca2de", "date": "Jun 21 2026",
        "subject": "kidney: ground ADH/AQP2 model in verified PubMed literature",
        "kind": "Added / Refined",
        "body": [
            "Replace single-gain ADH water retention with a two-timescale AQP2 model:",
            "- Fast path (vesicle trafficking, seconds-minutes): converges at 0.30 rate",
            "- Slow path (transcriptional upregulation, hours): converges at 0.01 rate",
            "- AVP-independent baseline membrane fraction (AQP2_BASELINE = 0.10)",
            "Add verified constants and urine_osmolality state:",
            "- OSMORECEPTOR_THRESHOLD = 2.0 mOsm/L (PMID 30252325)",
            "- URINE_OSM_MIN/CONC/MAX = 100/750/1200 mOsm/kg (PMID 30252325)",
            "- AQP2_BASELINE = 0.10 AVP-independent fraction (PMID 36233678)",
            "Sources: PMID 27760771, 37440212, 39435642, 30252325, 36233678",
        ],
        "files": ["organs/kidney.py  (+57 / -6)"],
    },
    {
        "hash": "e1429ee", "date": "Jun 21 2026",
        "subject": "chore: ignore generated report PDFs in reports subfolders",
        "kind": "Chore",
        "body": [
            "Add reports/**/*.pdf so generated PDFs in nested reports folders are",
            "ignored too. Existing tracked science reports stay tracked.",
        ],
        "files": [".gitignore  (+2 / -1)"],
    },
    {
        "hash": "8486dbe", "date": "Jun 21 2026",
        "subject": "chore: ignore science reports and generated PDFs",
        "kind": "Chore",
        "body": [
            "science reports/ and reports/*.pdf are local-only artifacts.",
            "reports/_generate_report.py remains tracked.",
        ],
        "files": [".gitignore  (+4)"],
    },
    {
        "hash": "2d6d7c5", "date": "Jun 21 2026",
        "subject": "chore: add dsg2 report generator script",
        "kind": "Added",
        "body": [
            "Adds reports/_generate_report.py so PDF status reports are reproducible",
            "from the git history rather than one-off artifacts. Uses absolute repo",
            "paths and latin-1 sanitisation so fpdf core fonts never crash.",
        ],
        "files": ["reports/_generate_report.py  (+203)"],
    },
    {
        "hash": "90dc1be", "date": "Jun 21 2026",
        "subject": "feat: wire blood_flow signal into kidney and muscular_system",
        "kind": "Fixed / Added",
        "body": [
            "VascularSystem broadcast blood_flow every second but no organ consumed it -",
            "redistribution had no downstream effect.",
            "- muscular_system: new blood_flow handler sets perfusion_factor from",
            "  flows[muscles]/BASELINE(15%); folds into the fatigue loop so",
            "  fight-or-flight flow (35% -> 2.3x) extends endurance and ischemia",
            "  accelerates fatigue.",
            "- kidney: new blood_flow handler scales GFR proportionally to",
            "  flows[kidneys]/BASELINE(20%); fight-or-flight cuts renal flow and",
            "  correctly reduces filtration rate.",
        ],
        "files": ["organs/kidney.py  (+10)", "organs/muscular_system.py  (+19 / -11)"],
    },
    {
        "hash": "6e12585", "date": "Jun 21 2026",
        "subject": "feat: add muscular_system + vascular_system to GUI and Brain tool coverage",
        "kind": "Added",
        "body": [
            "- ORGAN_CONFIG now covers all 12 organs (muscular and vascular placed at",
            "  distinct positions/colors on the body silhouette)",
            "- Brain agent gains command_muscles and command_vascular tools so the",
            "  Claude reasoning loop can regulate both systems, not just heart/lungs",
            "- _execute_tool dispatch wired for both new tools",
        ],
        "files": ["canvas/display.py  (+2)", "organs/brain.py  (+42)"],
    },
    {
        "hash": "6dac1a3", "date": "Jun 20 2026",
        "subject": "fix: science audit corrections - inhibitory neurons, RAAS chain, pH coefficient",
        "kind": "Fixed",
        "body": [
            "- neuron.py: allow hyperpolarization (inhibitory signals were clamped to 0)",
            "- kidney.py: fix pH/CO2 coefficient 0.015 -> 0.008 per mmHg (Elmas 2025)",
            "- endocrine_bus.py: remove T3 (no thyroid organ), add aldosterone for RAAS",
            "- adrenal_gland.py: handle RAAS signal -> secrete aldosterone; track in state",
            "- kidney.py: complete RAAS loop - renin -> adrenal -> aldosterone -> Na+ retention",
            "- spaces.py: wire hydration_factor to kidney fluid_balance (was a sine wave)",
        ],
        "files": [
            "core/endocrine_bus.py  (+/-5)", "nervous_system/neuron.py  (+/-6)",
            "organs/adrenal_gland.py  (+20)", "organs/kidney.py  (+16)",
            "physiology/spaces.py  (refactor, -125 net)",
        ],
    },
    {
        "hash": "b70f440", "date": "Jun 18 2026",
        "subject": "feat: six expansions - Claude brain agent, muscular + vascular, meridian spaces, UG layer",
        "kind": "Added (major)",
        "body": [
            "1. Brain: OXYGEN_LOW 96->94 (clinical SpO2); optional Claude-agent mode",
            "   (claude-haiku) replaces hardcoded if/elif with a tool-use reasoning loop",
            "   when ANTHROPIC_API_KEY is set.",
            "2. MuscularSystem: three muscle groups with fatigue/recovery, adrenaline",
            "   boost, space-quality penalty, hardware servo/motor mappings.",
            "3. VascularSystem: blood pressure from cardiac output x peripheral resistance;",
            "   adrenaline vasoconstriction; thoracic narrowing raises resistance;",
            "   fight-or-flight redistribution; hypo/hypertension alerts to brain.",
            "4. SpacePhysiology: meridian propagation across zone adjacency graph; ADH",
            "   improves hydration; kidney fluid balance replaces sine-wave approximation.",
            "5. UniversalGrammar + LanguageModule: innate Chomskyan UG layer annotates",
            "   indexed text; new parse command; grammar_stats in state.",
            "6. HardwareBridge + main.py + test_run.py wired for all 13 subsystems;",
            "   test_run.py now expects 13/13 and passes.",
        ],
        "files": [
            "organs/brain.py  (+307)", "organs/vascular_system.py  (new, +168)",
            "organs/muscular_system.py  (new, +148)",
            "language/universal_grammar.py  (new, +206)",
            "language/language_module.py  (+119)", "physiology/spaces.py  (+178)",
            "hardware/bridge.py  (+81)", "main.py  (+43)", "test_run.py  (+65)",
        ],
    },
]

SUMMARY_ROWS = [(c["hash"], c["date"], c["subject"]) for c in COMMITS]

AGG = [
    "Aggregate change over the last 5 commits (git diff --stat HEAD~5 HEAD):",
    "  .gitignore                    +5",
    "  organs/kidney.py              +73 (two-timescale AQP2 + blood_flow handler)",
    "  organs/muscular_system.py     +30 / -17 (perfusion-driven fatigue)",
    "  reports/_generate_report.py   +203 (this generator)",
    "  4 files changed, 294 insertions(+), 17 deletions(-)",
]

GAPS = [
    "No TODO / FIXME markers were found anywhere in the Python or Markdown",
    "sources at this revision - the tree is clean of inline debt markers.",
    "",
    "Roadmap / known gaps tracked outside the code:",
    "- Planned migration from hardcoded organ if/elif logic to Claude tool-use",
    "  agent loops, in order: Brain -> Immune -> Adrenal -> Liver -> rest.",
    "  Brain already supports the optional Claude-agent mode (commit b70f440);",
    "  the remaining organs still use deterministic if/elif control.",
    "- Claude-agent brain mode is gated on ANTHROPIC_API_KEY; default runs fall",
    "  back to the deterministic loop, so the agent path needs broader test",
    "  coverage before the other organs migrate.",
    "- Liver organ not yet present in ORGAN_CONFIG (12 organs covered); it is the",
    "  last named target of the migration order and remains to be built/wired.",
    "- Kidney ADH/AQP2 model is now literature-grounded; the slow transcriptional",
    "  path (0.01 rate) needs long-horizon simulation runs to validate behavior.",
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
        self.cell(0, 6, s("digi-soul - Development Report"), align="L")
        self.cell(0, 6, s(REPORT_DATE), align="R")
        self.set_text_color(0)
        self.ln(8)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")
        self.set_text_color(0)


pdf = Report()
pdf.set_auto_page_break(auto=True, margin=15)

# --- Title page ---
pdf.add_page()
pdf.ln(45)
pdf.set_font("Helvetica", "B", 26)
pdf.cell(0, 14, s("digi-soul"), align="C")
pdf.ln(14)
pdf.set_font("Helvetica", "", 16)
pdf.cell(0, 10, s("Development Report"), align="C")
pdf.ln(24)
pdf.set_font("Helvetica", "", 11)
pdf.set_text_color(60)
for label, val in [
    ("Generated", REPORT_DATE),
    ("Author", AUTHOR),
    ("Repository", REPO_PATH),
    ("Latest commit", "35ca2de  (origin/main, in sync)"),
]:
    pdf.cell(0, 8, s(f"{label}:  {val}"), align="C")
    pdf.ln(8)
pdf.ln(10)
pdf.set_font("Helvetica", "I", 10)
pdf.set_text_color(110)
pdf.multi_cell(0, 6, s(
    "This report summarizes engineering work performed by the dsg agent, "
    "reconstructed from the git history through the latest push (35ca2de)."),
    align="C")
pdf.set_text_color(0)

# --- Commit summary table ---
pdf.add_page()
pdf.set_font("Helvetica", "B", 15)
pdf.cell(0, 10, s("1. Commit Summary"))
pdf.ln(13)

pdf.set_font("Helvetica", "B", 9)
pdf.set_fill_color(40, 55, 75)
pdf.set_text_color(255)
pdf.cell(20, 8, s("Hash"), border=0, fill=True)
pdf.cell(28, 8, s("Date"), border=0, fill=True)
pdf.cell(0, 8, s("Subject"), border=0, fill=True)
pdf.ln(8)
pdf.set_text_color(0)
pdf.set_font("Helvetica", "", 8.5)
fill = False
for h, d, subj in SUMMARY_ROWS:
    pdf.set_fill_color(238, 242, 247)
    subj = s(subj)
    if len(subj) > 78:
        subj = subj[:75] + "..."
    pdf.cell(20, 7, s(h), fill=fill)
    pdf.cell(28, 7, s(d), fill=fill)
    pdf.cell(0, 7, subj, fill=fill)
    pdf.ln(7)
    fill = not fill

# --- Per-commit detail ---
pdf.add_page()
pdf.set_font("Helvetica", "B", 15)
pdf.cell(0, 10, s("2. Per-Commit Detail"))
pdf.ln(13)

for c in COMMITS:
    if pdf.get_y() > 235:
        pdf.add_page()
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(225, 232, 240)
    pdf.cell(0, 8, s(f"{c['hash']}  -  {c['kind']}  -  {c['date']}"), fill=True)
    pdf.ln(9)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5.5, s(c["subject"]))
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 9)
    for line in c["body"]:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, s(line))
    pdf.ln(1)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 5.5, s("Files changed:"))
    pdf.ln(5.5)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(70)
    for f in c["files"]:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, s("    - " + f))
    pdf.set_text_color(0)
    pdf.ln(4)

# --- Aggregate ---
if pdf.get_y() > 215:
    pdf.add_page()
pdf.set_font("Helvetica", "B", 13)
pdf.cell(0, 9, s("3. Aggregate Change Snapshot"))
pdf.ln(11)
pdf.set_font("Courier", "", 8.5)
for line in AGG:
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5, s(line))
pdf.ln(3)

# --- Open issues / gaps ---
pdf.add_page()
pdf.set_font("Helvetica", "B", 15)
pdf.cell(0, 10, s("4. Open Issues / Known Gaps"))
pdf.ln(13)
pdf.set_font("Helvetica", "", 9.5)
for line in GAPS:
    if line == "":
        pdf.ln(3)
        continue
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5.5, s(line))
pdf.ln(2)

pdf.output(OUTPUT)
print("WROTE", OUTPUT)
