from docx import Document as DocxDocument
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from typing import Optional
from lxml import etree
from docx.oxml.ns import qn


class DocumentParser:
    """
    Service for reading .docx documents, extracting paragraph and run-level
    formatting, applying formatting to translated text, clearing background
    shading, and saving results.

    Follows the same service pattern as GlossaryService.
    """

    # OOXML namespace for the w: prefix
    _NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read_document(self, path: str) -> DocxDocument:
        """Open a .docx file and return a python-docx Document object."""
        return DocxDocument(path)

    def extract_paragraphs(self, doc: DocxDocument) -> list[dict]:
        """
        Extract every paragraph from *doc* along with full run-level
        formatting information.

        Returns a list of dicts.  Each dict has:
          - ``text``      — full paragraph text
          - ``alignment`` — integer value of WD_ALIGN_PARAGRAPH or None
          - ``runs``      — list of run dicts (see _extract_run_data)
        """
        paragraphs = []
        for para in doc.paragraphs:
            runs_data = [self._extract_run_data(run) for run in para.runs]
            paragraphs.append({
                "text": para.text,
                "alignment": para.alignment.value
                              if para.alignment is not None else None,
                "runs": runs_data,
            })
        return paragraphs

    def apply_formatting(
        self,
        para,
        runs_data: list[dict],
        text: str,
    ) -> None:
        """
        Replace the content of *para* with *text* while:
          - Setting the font to Times New Roman 12pt
          - Preserving the original paragraph alignment
          - Applying any **bold** / *italic* / underline / highlight / color
            that existed in the original runs (union across all runs).

        Parameters
        ----------
        para :
            A python-docx ``Paragraph`` object (from the same document
            that ``extract_paragraphs`` was called on).
        runs_data : list[dict]
            The list of run dicts returned by ``extract_paragraphs`` for
            this paragraph.
        text : str
            The translated text to place in the paragraph.
        """
        # 1. Remove every existing run from the paragraph.
        run_elements = [r._element for r in para.runs]
        for el in run_elements:
            el.getparent().remove(el)

        # 2. Add a single new run with the translated text.
        new_run = para.add_run(text)

        # 3. Apply default font.
        new_run.font.name = "Times New Roman"
        new_run.font.size = Pt(12)

        # 4. Preserve original alignment -- already on the paragraph,
        #    nothing to do.

        # 5. Apply formatting union from original runs.
        self._apply_run_formatting(new_run, runs_data)

    def clear_background_shading(self, doc: DocxDocument) -> None:
        """
        Remove ``<w:shd>`` elements from every paragraph and run in the
        document.  This is required by immigration-bureau scan
        specifications that forbid gray background shading.

        Handles both paragraph-level (``<w:pPr><w:shd>``) and run-level
        (``<w:rPr><w:shd>``) shading.
        """
        for para in doc.paragraphs:
            self._clear_shading_from_element(para._element, self._NS + 'pPr')
            for run in para.runs:
                self._clear_shading_from_element(
                    run._element, self._NS + 'rPr'
                )

    def save_document(self, doc: DocxDocument, path: str) -> None:
        """Save the document to *path*."""
        doc.save(path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_run_data(run) -> dict:
        """
        Return a serialisable dict describing one run's formatting.

        Returns keys:
          text, bold, italic, underline, font_name, font_size (Pt),
          highlight (int | None), color (hex str | None)
        """
        font = run.font
        highlight = None
        if font.highlight_color is not None:
            highlight = font.highlight_color.value  # e.g. 7 for YELLOW

        color = None
        if font.color is not None and font.color.rgb is not None:
            color = str(font.color.rgb).upper()

        return {
            "text": run.text,
            "bold": bool(font.bold) if font.bold is not None else False,
            "italic": bool(font.italic) if font.italic is not None else False,
            "underline": (
                bool(font.underline)
                if font.underline is not None
                else False
            ),
            "font_name": font.name,
            "font_size": font.size.pt if font.size is not None else None,
            "highlight": highlight,
            "color": color,
        }

    @staticmethod
    def _apply_run_formatting(run, runs_data: list[dict]) -> None:
        """
        Inspect the union of formatting across all *runs_data* entries and
        apply the active properties to *run*.

        - **bold**: True if ANY original run was bold.
        - *italic*: True if ANY original run was italic.
        - underline: True if ANY original run was underlined.
        - highlight: taken from the first run that carried one.
        - color: taken from the first run that carried one.
        """
        # Determine which properties are "active" across all runs.
        has_bold = any(rd.get("bold") for rd in runs_data)
        has_italic = any(rd.get("italic") for rd in runs_data)
        has_underline = any(rd.get("underline") for rd in runs_data)
        has_highlight = any(
            rd.get("highlight") is not None for rd in runs_data
        )
        has_color = any(rd.get("color") is not None for rd in runs_data)

        if has_bold:
            run.font.bold = True
        if has_italic:
            run.font.italic = True
        if has_underline:
            run.font.underline = True

        if has_highlight:
            for rd in runs_data:
                h = rd.get("highlight")
                if h is not None:
                    try:
                        run.font.highlight_color = WD_COLOR_INDEX(h)
                    except (ValueError, KeyError):
                        pass
                    break

        if has_color:
            for rd in runs_data:
                c = rd.get("color")
                if c is not None:
                    try:
                        run.font.color.rgb = RGBColor.from_string(c)
                    except (ValueError, AttributeError):
                        pass
                    break

    @staticmethod
    def _clear_shading_from_element(element, container_tag: str) -> None:
        """
        Find the XML child element named *container_tag* (e.g. ``w:pPr`` or
        ``w:rPr``) inside *element* and remove any ``<w:shd>`` child from
        it.
        """
        NS = DocumentParser._NS
        container = element.find(container_tag)
        if container is not None:
            shd = container.find(NS + 'shd')
            if shd is not None:
                container.remove(shd)
