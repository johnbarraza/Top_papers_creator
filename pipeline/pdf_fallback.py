"""PDF fallback: compile LaTeX sections into an academic-style PDF using fpdf2.

Used when xelatex is not installed. Produces a clean, professional PDF with:
- Title page with author and date
- Abstract
- Numbered sections with proper formatting
- Embedded tables (parsed from .tex)
- Embedded figures (PDF figures converted to PNG via PyMuPDF)
- Double-spaced body text, serif font, 1-inch margins
"""

import re
from pathlib import Path

from fpdf import FPDF


# ---------------------------------------------------------------------------
# LaTeX text cleaning
# ---------------------------------------------------------------------------

_UNICODE_MAP = {
    "\u2013": "-", "\u2014": "--", "\u2015": "--",
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2026": "...", "\u2192": "->", "\u2190": "<-",
    "\u00d7": "x", "\u2264": "<=", "\u2265": ">=",
    "\u2260": "!=", "\u2248": "~=",
    "\u00b1": "+/-", "\u221e": "inf",
}


def _clean(text: str) -> str:
    """Strip LaTeX markup, returning plain text safe for fpdf (latin-1)."""
    # Remove \thanks{...} (may be nested)
    text = re.sub(r"\\thanks\{[^}]*\}", "", text)
    # Escaped percent -> literal %
    text = text.replace("\\%", "%")
    # LaTeX line breaks -> space
    text = text.replace("\\\\", " ")
    # Remove % comments (to end of line)
    text = re.sub(r"%[^\n]*", "", text)
    # Special characters
    text = text.replace("\\textquotesingle", "'")
    text = text.replace("\\&", "&")
    text = text.replace("\\$", "$")
    text = text.replace("\\#", "#")
    text = text.replace("\\~{}", "~")
    # \small, \large etc. (size commands)
    for cmd in ("small", "large", "Large", "LARGE", "huge", "Huge",
                "tiny", "scriptsize", "footnotesize", "normalsize"):
        text = text.replace(f"\\{cmd}", "")
    # Named commands with braces
    for cmd in ("textbf", "textit", "emph", "underline", "texttt",
                "textrm", "textsf", "textsc"):
        text = re.sub(rf"\\{cmd}\{{([^}}]*)\}}", r"\1", text)
    # Citations
    for cmd in ("cite", "citep", "citet", "textcite", "autocite",
                "parencite", "citeauthor", "citeyear"):
        text = re.sub(rf"\\{cmd}\{{([^}}]*)\}}", r"[\1]", text)
    # Footnotes, labels, refs
    text = re.sub(r"\\footnote\{[^}]*\}", "", text)
    text = re.sub(r"\\label\{[^}]*\}", "", text)
    # ~\ref{...} and ~\eqref{...} -> space + label (~ = non-breaking space)
    text = re.sub(r"~\\(?:eq)?ref\{([^}]*)\}", r" \1", text)
    text = re.sub(r"\\(?:eq)?ref\{([^}]*)\}", r"\1", text)
    # LaTeX tilde (non-breaking space) -> space
    text = text.replace("~", " ")
    # \href{url}{text} -> text
    text = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", text)
    # Inline math
    text = re.sub(r"\$([^$]+)\$", r"\1", text)
    # \command{text} -> text
    text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", text)
    # Remaining bare commands
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    # Stray braces
    text = re.sub(r"[{}]", "", text)
    # Whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Unicode -> ASCII
    for u, a in _UNICODE_MAP.items():
        text = text.replace(u, a)
    # Encode safety: drop chars that latin-1 can't handle
    text = text.encode("latin-1", errors="replace").decode("latin-1")
    return text


# ---------------------------------------------------------------------------
# PDF figure conversion
# ---------------------------------------------------------------------------

def _ensure_png(pdf_path: Path) -> Path | None:
    """Convert a single-page PDF figure to PNG. Returns PNG path or None."""
    png = pdf_path.with_suffix(".png")
    if png.exists():
        return png
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        pix = doc[0].get_pixmap(dpi=200)
        pix.save(str(png))
        doc.close()
        return png
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Academic PDF builder
# ---------------------------------------------------------------------------

class AcademicPDF(FPDF):
    """FPDF subclass with academic paper styling."""

    def __init__(self):
        super().__init__(format="letter")
        self.set_margins(25.4, 25.4, 25.4)  # 1 inch
        self.set_auto_page_break(auto=True, margin=25.4)
        self._section_num = 0
        self._subsection_num = 0

    # -- Title page ----------------------------------------------------------

    def title_page(self, title: str, author: str, date: str,
                   jel: str = "", keywords: str = ""):
        self.add_page()
        self.ln(40)
        self.set_font("Times", "B", 16)
        self.multi_cell(0, 9, title, align="C")
        self.ln(12)
        if author:
            self.set_font("Times", "", 12)
            self.multi_cell(0, 7, author, align="C")
            self.ln(4)
        if date:
            self.set_font("Times", "I", 11)
            self.multi_cell(0, 7, date, align="C")
        self.ln(15)
        if jel:
            self.set_font("Times", "B", 10)
            self.cell(0, 6, f"JEL Codes: ", new_x="END")
            self.set_font("Times", "", 10)
            self.cell(0, 6, jel, new_x="LMARGIN", new_y="NEXT")
        if keywords:
            self.set_font("Times", "B", 10)
            self.cell(0, 6, f"Keywords: ", new_x="END")
            self.set_font("Times", "", 10)
            self.multi_cell(0, 6, keywords)

    # -- Abstract ------------------------------------------------------------

    def abstract(self, text: str):
        self.ln(10)
        self.set_font("Times", "B", 12)
        self.cell(0, 8, "Abstract", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_font("Times", "I", 11)
        # Indent abstract
        old_l = self.l_margin
        self.set_left_margin(old_l + 12)
        self.set_right_margin(self.r_margin + 12)
        self.multi_cell(0, 6, text)
        self.set_left_margin(old_l)
        self.set_right_margin(25.4)
        self.ln(6)

    # -- Section / subsection ------------------------------------------------

    def section(self, title: str):
        self._section_num += 1
        self._subsection_num = 0
        self.ln(8)
        self.set_font("Times", "B", 14)
        self.cell(0, 9, f"{self._section_num}. {title}",
                  new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def subsection(self, title: str):
        self._subsection_num += 1
        self.ln(5)
        self.set_font("Times", "B", 12)
        self.cell(0, 8,
                  f"{self._section_num}.{self._subsection_num} {title}",
                  new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def subsubsection(self, title: str):
        self.ln(3)
        self.set_font("Times", "BI", 11)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    # -- Body text -----------------------------------------------------------

    def body_text(self, text: str):
        self.set_font("Times", "", 11)
        try:
            self.multi_cell(0, 6.5, text)  # ~double-spaced at 11pt
        except Exception:
            pass

    def item(self, text: str):
        self.set_font("Times", "", 11)
        try:
            self.multi_cell(0, 6, f"  - {text}")
        except Exception:
            pass

    # -- Table ---------------------------------------------------------------

    def table_from_tex(self, tex: str, name: str = ""):
        cap = re.search(r"\\caption\{([^}]+)\}", tex)
        caption = _clean(cap.group(1)) if cap else name

        self.ln(6)
        self.set_font("Times", "BI", 10)
        self.multi_cell(0, 5, caption)
        self.ln(2)

        tab = re.search(
            r"\\begin\{tabular\}\{[^}]*\}(.*?)\\end\{tabular\}",
            tex, re.DOTALL,
        )
        if not tab:
            return

        body = tab.group(1)
        body = re.sub(r"\\(hline|toprule|midrule|bottomrule|cline\{[^}]*\})",
                       "", body)
        body = re.sub(r"\\multicolumn\{\d+\}\{[^}]*\}\{([^}]*)\}", r"\1", body)

        rows = [r.strip() for r in body.split("\\\\") if r.strip()]
        if not rows:
            return

        # Calculate column widths
        all_cells = []
        for row in rows:
            cells = [_clean(c.strip()) for c in row.split("&")]
            all_cells.append(cells)

        n_cols = max(len(r) for r in all_cells) if all_cells else 1
        col_w = (self.w - self.l_margin - self.r_margin) / n_cols

        # Draw horizontal line
        x0 = self.l_margin
        self.line(x0, self.get_y(), x0 + col_w * n_cols, self.get_y())
        self.ln(1)

        for i, cells in enumerate(all_cells):
            if i == 0:
                self.set_font("Times", "B", 8)
            else:
                self.set_font("Times", "", 8)
            for j, cell in enumerate(cells):
                w = col_w
                self.cell(w, 4.5, cell[:30], align="R" if j > 0 else "L")
            self.ln()
            if i == 0:
                self.line(x0, self.get_y(), x0 + col_w * n_cols, self.get_y())
                self.ln(0.5)

        self.line(x0, self.get_y(), x0 + col_w * n_cols, self.get_y())
        self.ln(4)

    # -- Figure --------------------------------------------------------------

    def figure(self, img_path: Path, caption: str = ""):
        self.ln(6)
        try:
            # Fit to page width - margins
            avail_w = self.w - self.l_margin - self.r_margin - 10
            self.image(str(img_path), x=self.l_margin + 5, w=avail_w)
        except Exception:
            self.set_font("Times", "I", 10)
            self.cell(0, 6, f"[Figure: {img_path.name}]",
                      new_x="LMARGIN", new_y="NEXT")
        if caption:
            self.set_font("Times", "I", 9)
            self.multi_cell(0, 5, f"Figure: {caption}")
        self.ln(4)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compile_pdf(paper_dir: Path) -> bool:
    """Build main.pdf from LaTeX sections in paper_dir."""

    main_tex = paper_dir / "main.tex"
    if not main_tex.exists():
        print("  [pdf] main.tex not found.")
        return False

    print("  [pdf] Generating academic PDF via Python (fpdf2)...")

    content = main_tex.read_text(encoding="utf-8")

    # -- Extract metadata ---------------------------------------------------
    def _extract(pattern, default=""):
        m = re.search(pattern, content, re.DOTALL)
        return _clean(m.group(1)) if m else default

    title = _extract(r"\\title\{(.+?)\}", "Untitled")

    # Extract author — strip \small, \href{mailto:...}{text}, email lines
    author_raw = _extract(r"\\author\{(.+?)\}", "")
    author = re.sub(r"\\?mailto:\S+", "", author_raw).strip()

    date = _extract(r"\\date\{(.+?)\}", "")
    jel = _extract(r"JEL Codes?[}:]\s*([A-Z][0-9]{2}(?:,\s*[A-Z][0-9]{2})*)")
    # Keywords: match until next blank line, \clearpage, \input, or \\
    kw_match = re.search(
        r"Keywords?[}:]\s*(.+?)(?=\\\\|\n\s*\n|\\clearpage|\\input|\\section)",
        content, re.DOTALL,
    )
    keywords = _clean(kw_match.group(1)) if kw_match else ""

    # -- Get section files in order -----------------------------------------
    # Only match \input{sections/...} to avoid appendix figures
    inputs = re.findall(r"\\input\{(sections/[^}]+)\}", content)
    section_files = []
    for inp in inputs:
        if not inp.endswith(".tex"):
            inp += ".tex"
        f = paper_dir / inp
        if f.exists():
            section_files.append(f)

    if not section_files:
        # No \input{sections/...} found — main.tex contains all content
        # Use main.tex itself as the single section file
        section_files = [main_tex]

    # -- Build PDF ----------------------------------------------------------
    pdf = AcademicPDF()

    # Title page
    pdf.title_page(title, author, date, jel, keywords)

    # Process sections
    for sec_file in section_files:
        tex = sec_file.read_text(encoding="utf-8")

        # If it's the abstract, handle separately
        if "abstract" in sec_file.stem.lower():
            abstract_text = _clean(tex)
            abstract_text = re.sub(
                r"\\begin\{abstract\}|\\end\{abstract\}", "", abstract_text
            ).strip()
            pdf.abstract(abstract_text)
            pdf.add_page()
            continue

        # Start new page for each major section
        if sec_file.stem.startswith("01"):
            pass  # first section continues after abstract
        else:
            pdf.add_page()

        _render_section(pdf, tex, paper_dir)

    # -- Append tables -------------------------------------------------------
    tables_dir = paper_dir / "tables"
    if tables_dir.exists():
        # Include tables from subdirectories too (00_clean/, 02_robustness/)
        table_files = sorted(tables_dir.rglob("*.tex"))
        if table_files:
            pdf.add_page()
            pdf._section_num += 1
            pdf.set_font("Times", "B", 14)
            pdf.cell(0, 9, "Appendix: Tables", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(6)
            for tf in table_files:
                pdf.table_from_tex(
                    tf.read_text(encoding="utf-8"), tf.stem
                )
                pdf.ln(6)

    # -- Append figures ------------------------------------------------------
    figures_dir = paper_dir / "figures"
    if figures_dir.exists():
        fig_pdfs = sorted(figures_dir.glob("*.pdf"))
        fig_pngs = sorted(figures_dir.glob("*.png"))

        # Convert PDF figures to PNG
        for fp in fig_pdfs:
            png = _ensure_png(fp)
            if png and png not in fig_pngs:
                fig_pngs.append(png)
        fig_pngs = sorted(set(fig_pngs))

        if fig_pngs:
            pdf.add_page()
            pdf._section_num += 1
            pdf.set_font("Times", "B", 14)
            pdf.cell(0, 9, "Appendix: Figures", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(6)
            for img in fig_pngs:
                pdf.figure(img, img.stem.replace("_", " ").title())

    # -- Save ---------------------------------------------------------------
    pdf_path = paper_dir / "main.pdf"
    try:
        pdf.output(str(pdf_path))
        print(f"  [pdf] Generated: {pdf_path}")
        return True
    except Exception as e:
        print(f"  [pdf] Failed: {e}")
        return False


def _render_section(pdf: AcademicPDF, tex: str, paper_dir: Path):
    """Parse LaTeX and render into the PDF document."""

    # Remove preamble
    tex = re.sub(r"\\documentclass.*?\n", "", tex)
    tex = re.sub(r"\\usepackage.*?\n", "", tex)
    tex = re.sub(r"\\begin\{document\}", "", tex)
    tex = re.sub(r"\\end\{document\}", "", tex)

    # --- Extract and render table/figure environments as blocks first ---
    # We replace them with placeholders so the line-by-line pass skips them.
    env_counter = [0]
    env_blocks = {}

    def _extract_env(match):
        env_counter[0] += 1
        key = f"__ENV_{env_counter[0]}__"
        env_blocks[key] = match.group(0)
        return key

    # Extract table and figure environments (including nested content)
    tex = re.sub(
        r"\\begin\{(table|figure)\}.*?\\end\{\1\}",
        _extract_env, tex, flags=re.DOTALL,
    )
    # Also extract equation/align environments
    tex = re.sub(
        r"\\begin\{(equation|align)\*?\}.*?\\end\{\1\*?\}",
        _extract_env, tex, flags=re.DOTALL,
    )

    lines = tex.split("\n")
    para_lines = []  # accumulate paragraph text

    def _flush_para():
        if para_lines:
            text = _clean(" ".join(para_lines))
            if text:
                pdf.body_text(text)
            para_lines.clear()

    for line in lines:
        s = line.strip()

        # Empty line = paragraph break
        if not s:
            _flush_para()
            continue

        if s.startswith("%"):
            continue

        # Skip layout commands
        if s in ("\\maketitle", "\\clearpage", "\\newpage",
                 "\\tableofcontents", "\\appendix", "\\centering",
                 "\\noindent"):
            _flush_para()
            continue
        if s.startswith(("\\label{", "\\thispagestyle",
                         "\\renewcommand")):
            continue

        # Environment placeholder -> render the block
        if s.startswith("__ENV_") and s.endswith("__"):
            _flush_para()
            block = env_blocks.get(s, "")
            _render_env_block(pdf, block, paper_dir)
            continue

        # Section headers
        m = re.match(r"\\section\*?\{([^}]+)\}", s)
        if m:
            _flush_para()
            pdf.section(_clean(m.group(1)))
            continue

        m = re.match(r"\\subsection\*?\{([^}]+)\}", s)
        if m:
            _flush_para()
            pdf.subsection(_clean(m.group(1)))
            continue

        m = re.match(r"\\subsubsection\*?\{([^}]+)\}", s)
        if m:
            _flush_para()
            pdf.subsubsection(_clean(m.group(1)))
            continue

        # \paragraph{title}
        m = re.match(r"\\paragraph\{([^}]+)\}", s)
        if m:
            _flush_para()
            pdf.ln(3)
            pdf.set_font("Times", "B", 11)
            title_text = _clean(m.group(1))
            # Rest of line after \paragraph{...}
            rest = s[m.end():].strip()
            pdf.cell(0, 7, title_text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
            if rest:
                para_lines.append(rest)
            continue

        # Abstract
        if "\\begin{abstract}" in s:
            _flush_para()
            continue
        if "\\end{abstract}" in s:
            _flush_para()
            continue

        # Standalone \input (not inside table env)
        m = re.match(r"\\input\{([^}]+)\}", s)
        if m:
            _flush_para()
            inp = m.group(1)
            if not inp.endswith(".tex"):
                inp += ".tex"
            fpath = paper_dir / inp
            if fpath.exists():
                pdf.table_from_tex(fpath.read_text(encoding="utf-8"),
                                   fpath.stem)
            continue

        # Standalone \includegraphics (not inside figure env)
        m = re.match(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", s)
        if m:
            _flush_para()
            _render_figure(pdf, m.group(1), "", paper_dir)
            continue

        # \item
        if s.startswith("\\item"):
            _flush_para()
            text = _clean(re.sub(r"^\\item\s*", "", s))
            pdf.item(text)
            continue

        # \printbibliography
        if "\\printbibliography" in s:
            _flush_para()
            pdf.section("References")
            bib_path = paper_dir / "references.bib"
            if bib_path.exists():
                _render_bibliography(pdf, bib_path)
            else:
                pdf.set_font("Times", "I", 10)
                pdf.cell(0, 6, "[See references.bib for full bibliography]",
                         new_x="LMARGIN", new_y="NEXT")
            continue

        # \noindent\textbf{...} lines (JEL codes, keywords)
        if s.startswith("\\noindent"):
            _flush_para()
            text = _clean(s.replace("\\noindent", ""))
            if text:
                pdf.set_font("Times", "", 11)
                try:
                    pdf.multi_cell(0, 6.5, text)
                except Exception:
                    pass
            continue

        # Skip stray begin/end that weren't captured as blocks
        if re.match(r"\\(begin|end)\{", s):
            _flush_para()
            continue

        # Regular text line — accumulate into paragraph
        para_lines.append(s)

    _flush_para()


def _render_env_block(pdf: AcademicPDF, block: str, paper_dir: Path):
    """Render a table or figure environment block."""

    # Determine type
    is_table = block.startswith("\\begin{table}")
    is_figure = block.startswith("\\begin{figure}")
    is_equation = "\\begin{equation" in block or "\\begin{align" in block

    if is_equation:
        # Render equation as indented italic text
        inner = re.sub(r"\\begin\{(equation|align)\*?\}", "", block)
        inner = re.sub(r"\\end\{(equation|align)\*?\}", "", inner)
        inner = re.sub(r"\\label\{[^}]*\}", "", inner)
        text = _clean(inner).strip()
        if text:
            pdf.ln(4)
            pdf.set_font("Times", "I", 11)
            old_l = pdf.l_margin
            pdf.set_left_margin(old_l + 15)
            pdf.multi_cell(0, 6.5, text)
            pdf.set_left_margin(old_l)
            pdf.ln(4)
        return

    # Extract caption (may span multiple lines)
    cap_match = re.search(
        r"\\caption\{((?:[^{}]|\{[^{}]*\})*)\}", block, re.DOTALL
    )
    caption = _clean(cap_match.group(1)) if cap_match else ""

    # Extract notes from minipage
    notes = ""
    mini_match = re.search(
        r"\\begin\{minipage\}.*?\n(.*?)\\end\{minipage\}",
        block, re.DOTALL,
    )
    if mini_match:
        notes = _clean(mini_match.group(1))

    if is_table:
        # Find \input{tables/...}
        inp_match = re.search(r"\\input\{([^}]+)\}", block)
        if inp_match:
            inp = inp_match.group(1)
            if not inp.endswith(".tex"):
                inp += ".tex"
            fpath = paper_dir / inp
            if fpath.exists():
                tex_content = fpath.read_text(encoding="utf-8")
                # Use caption from the section, not from the table file
                pdf.ln(4)
                if caption:
                    pdf.set_font("Times", "B", 10)
                    try:
                        pdf.multi_cell(0, 5, caption)
                    except Exception:
                        pass
                    pdf.ln(2)
                pdf.table_from_tex(tex_content, fpath.stem)
                if notes:
                    pdf.set_font("Times", "I", 8)
                    try:
                        pdf.multi_cell(0, 4, notes)
                    except Exception:
                        pass
                pdf.ln(4)
                return
        # No \input — try rendering tabular directly from block
        if "\\begin{tabular}" in block:
            pdf.ln(4)
            if caption:
                pdf.set_font("Times", "B", 10)
                try:
                    pdf.multi_cell(0, 5, caption)
                except Exception:
                    pass
                pdf.ln(2)
            pdf.table_from_tex(block, "table")
            if notes:
                pdf.set_font("Times", "I", 8)
                try:
                    pdf.multi_cell(0, 4, notes)
                except Exception:
                    pass
            pdf.ln(4)
        return

    if is_figure:
        # Find \includegraphics{...}
        fig_match = re.search(
            r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", block
        )
        if fig_match:
            _render_figure(pdf, fig_match.group(1), caption, paper_dir)
        return


def _render_figure(pdf: AcademicPDF, figname: str, caption: str,
                   paper_dir: Path):
    """Render a single figure with optional caption."""
    if not figname.endswith((".pdf", ".png", ".jpg")):
        figname += ".pdf"
    fig_path = paper_dir / figname
    png = fig_path.with_suffix(".png")
    if not png.exists():
        png_result = _ensure_png(fig_path)
        if png_result:
            png = png_result
    if png.exists():
        pdf.figure(png, caption)
    elif caption:
        pdf.set_font("Times", "I", 9)
        try:
            pdf.multi_cell(0, 5, f"[Figure: {figname}] {caption}")
        except Exception:
            pass


def _render_bibliography(pdf: AcademicPDF, bib_path: Path):
    """Parse a .bib file and render basic bibliography entries."""
    content = bib_path.read_text(encoding="utf-8", errors="replace")
    entries = re.findall(
        r"@\w+\{([^,]+),.*?author\s*=\s*\{([^}]+)\}.*?"
        r"title\s*=\s*\{([^}]+)\}.*?year\s*=\s*\{(\d{4})\}",
        content, re.DOTALL | re.IGNORECASE,
    )
    pdf.set_font("Times", "", 10)
    for key, author, title, year in sorted(entries, key=lambda e: e[1]):
        entry_text = f"{_clean(author)} ({year}). {_clean(title)}."
        try:
            pdf.multi_cell(0, 5, entry_text)
            pdf.ln(2)
        except Exception:
            pass
    if not entries:
        pdf.set_font("Times", "I", 10)
        pdf.cell(0, 6, "[Bibliography entries not parsed]",
                 new_x="LMARGIN", new_y="NEXT")
