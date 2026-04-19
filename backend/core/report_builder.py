"""
report_builder.py
=================
NOTE: This file is now ONLY used if you want a standalone report separate from
the engine's built-in report.  For the main /run_check flow, the engine's
_build_report() already produces the correct colour-coded PDF — see main_patch.py.

If you do call this directly, it now uses the correct engine result structure:
  result dict keys: "reference", "similarity", "match_types", "uncited_total",
                    "table_matches", "image_matches"
  detail dict keys: "user_chunk_idx", "user_chunk", "ref_chunk",
                    "match_type", "similarity", "reference"

Highlighting strategy (mirrors engine._build_report exactly):
  1. Re-extract text from the student PDF.
  2. Re-split into chunks using the same _split_chunks() logic as the engine.
  3. Map each detail item to its chunk index (user_chunk_idx).
  4. For each paragraph, map every word to its chunk index.
  5. Walk word by word, opening/closing <font backColor="…"> spans on transitions.
  This is the only approach that reliably matches — it uses the same chunk
  boundaries the engine used, not sentence re-splitting or str.find().
"""

from __future__ import annotations

import os
import re
import xml.sax.saxutils as saxutils
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate, Frame, FrameBreak,
    HRFlowable, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from backend.core.pdf_utils import extract_text
from backend.core.nlp_utils  import remove_references

# ── Palette (matches engine._PALETTES exactly) ────────────────────────────────
_PALETTES = [
    (HexColor("#1a6a8a"), HexColor("#d4eaf5")),
    (HexColor("#c0622b"), HexColor("#fbe8da")),
    (HexColor("#2e7d32"), HexColor("#dcedc8")),
    (HexColor("#8e1c3e"), HexColor("#fce4ec")),
    (HexColor("#1a237e"), HexColor("#e8eaf6")),
    (HexColor("#4a148c"), HexColor("#f3e5f5")),
    (HexColor("#bf360c"), HexColor("#fbe9e7")),
    (HexColor("#004d40"), HexColor("#e0f2f1")),
]

def _pfg(i): return _PALETTES[i % len(_PALETTES)][0]
def _pbg(i): return _PALETTES[i % len(_PALETTES)][1]

def _c2h(c) -> str:
    return f"#{int(c.red*255):02x}{int(c.green*255):02x}{int(c.blue*255):02x}"

def _bg_hex(si: int, mt: str) -> str:
    if mt == "direct":     return _c2h(_pbg(si))
    if mt == "paraphrase": return "#fff9c4"
    return "#e0f7fa"

def _score_color(v: float):
    if v >= 60: return HexColor("#c0392b")
    if v >= 20: return HexColor("#f39c12")
    return HexColor("#27ae60")

_MT_PRIORITY = {"direct": 3, "paraphrase": 2, "semantic": 1}
_ROW_LABELS  = {"direct": "Publication", "paraphrase": "Student Paper", "semantic": "Internet Source"}

PAGE_W, PAGE_H = A4
_style_n = [0]

def _ps(base, **kw) -> ParagraphStyle:
    _style_n[0] += 1
    return ParagraphStyle(f"_s{_style_n[0]}", parent=base, **kw)

def _esc(t: str) -> str:
    return saxutils.escape(str(t))


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def build_turnitin_pdf(
    student_pdf_name: str,
    student_pdf_path: str,
    all_results:      list,   # from check_plagiarism() — list of result dicts
    output_path:      str,
    all_details:      list | None = None,   # matched chunk detail dicts
    user_chunks:      list | None = None,   # all text chunks from student PDF
    uncited_mask:     list | None = None,   # bool mask — which chunks are uncited
) -> None:
    """
    Build the Turnitin-style report.

    If all_details / user_chunks / uncited_mask are not supplied, the function
    re-runs chunk matching via str.find() as a fallback — quality is lower
    but still better than the old approach.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Compute stats ─────────────────────────────────────────────────────────
    uncited_total_global = max(
        (r.get("uncited_total", 1) for r in all_results), default=1
    )
    matched_refs = [r for r in all_results if sum(r.get("match_types", {}).values()) > 0]

    for r in matched_refs:
        tc = max(r.get("uncited_total", uncited_total_global), 1)
        mt = r.get("match_types", {})
        d  = round(mt.get("direct",     0) / tc * 100, 1)
        p  = round(mt.get("paraphrase", 0) / tc * 100, 1)
        se = round(mt.get("semantic",   0) / tc * 100, 1)
        r["_st"] = {"d": d, "p": p, "se": se, "display_pct": round(min(d+p+se,100),1)}

    matched_refs.sort(key=lambda r: r["_st"]["display_pct"], reverse=True)
    src_idx = {r["reference"]: i for i, r in enumerate(matched_refs)}

    # Overall percentages
    if all_details:
        chunk_detail: dict[int, dict] = {}
        for d_item in all_details:
            ci   = d_item["user_chunk_idx"]
            prev = chunk_detail.get(ci)
            if prev is None or (_MT_PRIORITY.get(d_item["match_type"], 0) >
                                 _MT_PRIORITY.get(prev["match_type"], 0)):
                chunk_detail[ci] = d_item
        ov_counts = {"direct": 0, "paraphrase": 0, "semantic": 0}
        for cd in chunk_detail.values():
            ov_counts[cd["match_type"]] += 1
        max_media = max(
            (r.get("table_matches",0)+r.get("image_matches",0) for r in all_results),
            default=0,
        )
        ov_counts["direct"] += max_media
    else:
        chunk_detail = {}
        ov_counts = {"direct": 0, "paraphrase": 0, "semantic": 0}

    ut = max(uncited_total_global, 1)
    ov_d  = round(ov_counts["direct"]     / ut * 100, 1)
    ov_p  = round(ov_counts["paraphrase"] / ut * 100, 1)
    ov_se = round(ov_counts["semantic"]   / ut * 100, 1)
    ov_top = round(min(ov_d + ov_p + ov_se, 100.0), 1)
    if not ov_top:
        ov_top = max((r.get("similarity", 0) for r in all_results), default=0)

    # ── Extract and chunk student text ────────────────────────────────────────
    raw_text   = ""
    paragraphs = []
    if student_pdf_path:
        try:
            raw_text   = extract_text(student_pdf_path)
            raw_text   = remove_references(raw_text)
            paragraphs = [p for p in re.split(r'\n\s*\n', raw_text.strip()) if p.strip()]
        except Exception:
            pass

    # ── Build chunk_detail via str.find fallback if details not supplied ──────
    if not chunk_detail and all_details is None and matched_refs:
        chunk_detail = _build_chunk_detail_fallback(raw_text, all_results, src_idx)

    # ── ReportLab document setup ──────────────────────────────────────────────
    styles = getSampleStyleSheet()
    NR     = styles["Normal"]

    ML, MR, TOP, BOT = 1.5*cm, 1.5*cm, 2.5*cm, 1.5*cm
    GAP = 0.5*cm
    RW  = 6.5*cm
    LW  = PAGE_W - ML - MR - RW - GAP
    FH  = PAGE_H - TOP - BOT
    HDR_H = 1.2*cm
    SUM_W = PAGE_W - 2*1.4*cm

    rframe = Frame(ML+LW+GAP, BOT, RW, FH, id="R",
                   leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    lframe = Frame(ML, BOT, LW, FH, id="L",
                   leftPadding=4, rightPadding=4, topPadding=8, bottomPadding=4)
    full_f = Frame(ML, BOT, PAGE_W-ML-MR, FH, id="Full",
                   leftPadding=4, rightPadding=4, topPadding=8, bottomPadding=4)
    sum_f  = Frame(1.4*cm, BOT, SUM_W, FH, id="S",
                   leftPadding=6, rightPadding=6, topPadding=10, bottomPadding=4)

    doc = BaseDocTemplate(output_path, pagesize=A4)

    def _draw_first(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(HexColor("#1a252f"))
        canvas.rect(0, PAGE_H-HDR_H, PAGE_W, HDR_H, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(ML, PAGE_H-1.05*cm, os.path.basename(student_pdf_path or student_pdf_name))
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(HexColor("#aab7b8"))
        canvas.drawString(ML, PAGE_H-1.65*cm, "Plagiarism Detection Report")
        canvas.setFillColor(_score_color(ov_top))
        canvas.setFont("Helvetica-Bold", 20)
        canvas.drawRightString(PAGE_W-MR, PAGE_H-1.05*cm, f"{ov_top}%")
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(HexColor("#aab7b8"))
        canvas.drawRightString(PAGE_W-MR, PAGE_H-1.62*cm, f"D {ov_d}%  P {ov_p}%  Se {ov_se}%")
        sep = ML+LW+GAP/2
        canvas.setStrokeColor(HexColor("#d5d8dc"))
        canvas.setLineWidth(0.5)
        canvas.line(sep, BOT, sep, PAGE_H-TOP)
        canvas.restoreState()

    def _draw_later(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(HexColor("#1a252f"))
        canvas.rect(0, PAGE_H-HDR_H, PAGE_W, HDR_H, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(ML, PAGE_H-1.05*cm, os.path.basename(student_pdf_path or student_pdf_name))
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(HexColor("#aab7b8"))
        canvas.drawString(ML, PAGE_H-1.65*cm, "Plagiarism Detection Report")
        canvas.restoreState()

    doc.addPageTemplates([
        PageTemplate(id="First",   frames=[rframe, lframe], onPage=_draw_first),
        PageTemplate(id="Text",    frames=[full_f],          onPage=_draw_later),
        PageTemplate(id="Summary", frames=[sum_f],           onPage=_draw_later),
    ])

    story: list = []

    # ── RIGHT PANEL — Match Overview ──────────────────────────────────────────
    RW_inner = RW - 0.9*cm
    title_bar = Table([[
        Paragraph("<b>Match Overview</b>",
                  _ps(NR, fontSize=8.5, textColor=colors.white, leading=11)),
        Paragraph("×",
                  _ps(NR, fontSize=11, textColor=HexColor("#f5b7b1"),
                      alignment=TA_RIGHT, leading=11)),
    ]], colWidths=[RW_inner, 0.9*cm])
    title_bar.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), HexColor("#c0392b")),
        ("TOPPADDING",    (0,0),(-1,-1), 9),
        ("BOTTOMPADDING", (0,0),(-1,-1), 9),
        ("LEFTPADDING",   (0,0),(0,0), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(title_bar)
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"<b>{ov_top}%</b>",
        _ps(NR, fontSize=32, textColor=_score_color(ov_top), alignment=TA_CENTER, leading=36),
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<font color='#95a5a6' size='7'>D {ov_d}%  ·  P {ov_p}%  ·  Se {ov_se}%</font>",
        _ps(NR, fontSize=7, alignment=TA_CENTER, leading=9),
    ))
    story.append(Spacer(1, 15))

    BADGE_W = 0.6*cm
    ARR_W   = 0.5*cm
    PCT_W   = 1.1*cm
    NAME_W  = RW - BADGE_W - PCT_W - ARR_W - 0.2*cm

    for si, r in enumerate(matched_refs):
        st = r["_st"]
        dominant = max(r.get("match_types",{}), key=r.get("match_types",{}).get) \
                   if r.get("match_types") else "semantic"
        row_tbl = Table([[
            Paragraph(str(si+1),
                      _ps(NR, fontSize=7, textColor=colors.white,
                          alignment=TA_CENTER, leading=8)),
            [Paragraph(f"<b>{_esc(r['reference'])}</b>",
                       _ps(NR, fontSize=7, textColor=HexColor("#1a252f"), leading=8)),
             Paragraph(_ROW_LABELS.get(dominant, ""),
                       _ps(NR, fontSize=5.5, textColor=HexColor("#aab7b8"), leading=7))],
            Paragraph(f"<b>{st['display_pct']}%</b>",
                      _ps(NR, fontSize=9, textColor=HexColor("#2c3e50"),
                          alignment=TA_RIGHT, leading=10)),
            Paragraph("<b>&gt;</b>",
                      _ps(NR, fontSize=9, textColor=HexColor("#bdc3c7"),
                          alignment=TA_CENTER, leading=10)),
        ]], colWidths=[BADGE_W, NAME_W, PCT_W, ARR_W])
        row_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(0,0),  _pfg(si)),
            ("BACKGROUND",    (1,0),(-1,0), colors.white),
            ("VALIGN",        (0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",    (0,0),(-1,-1), 7),
            ("BOTTOMPADDING", (0,0),(-1,-1), 7),
            ("LEFTPADDING",   (1,0),(1,0),   8),
            ("LEFTPADDING",   (2,0),(-1,-1), 2),
            ("RIGHTPADDING",  (0,0),(-1,-1), 4),
            ("LINEBELOW",     (0,0),(-1,-1), 0.5, HexColor("#ecf0f1")),
        ]))
        story.append(row_tbl)

    story.append(FrameBreak())
    story.append(NextPageTemplate("Text"))

    # ── LEFT PANEL / FULL WIDTH — Highlighted Document Text ──────────────────
    _build_highlighted_text(
        story, paragraphs, chunk_detail, src_idx, NR,
        user_chunks=user_chunks,
        uncited_mask=uncited_mask,
    )

    # ── SUMMARY PAGE ─────────────────────────────────────────────────────────
    story.append(NextPageTemplate("Summary"))
    story.append(PageBreak())
    _build_summary_page(
        story, student_pdf_name, matched_refs, src_idx,
        ov_top, ov_d, ov_p, ov_se, uncited_total_global, NR, SUM_W,
    )

    doc.build(story)


# ══════════════════════════════════════════════════════════════════════════════
# HIGHLIGHTED TEXT BUILDER  (word-level, mirrors engine._build_report exactly)
# ══════════════════════════════════════════════════════════════════════════════

def _build_highlighted_text(
    story:       list,
    paragraphs:  list[str],
    chunk_detail:dict,
    src_idx:     dict,
    NR:          ParagraphStyle,
    user_chunks: list | None = None,
    uncited_mask:list | None = None,
    chunk_size:  int = 50,
    step:        int = 20,
) -> None:
    """
    Re-create the engine's word-level highlighting:

    The engine splits the document into 50-word chunks with a step of ~20 words
    (the same _split_chunks() logic).  chunk_detail maps chunk_index → detail.
    We replicate that index calculation here to know which colour to apply to
    each word in the rendered paragraph.
    """
    # If we have user_chunks we can compute step from len; otherwise use default
    if user_chunks:
        # Infer step from how many chunks there are vs total words
        total_words = sum(len(p.split()) for p in paragraphs)
        if total_words > 0 and len(user_chunks) > 0:
            step = max(int(total_words / len(user_chunks)), 8)

    para_style = ParagraphStyle(
        "ptext", parent=NR,
        fontSize=8.5, leading=13, spaceAfter=10,
        textColor=HexColor("#2c3e50"),
    )

    chunk_idx = 0

    for para_text in paragraphs:
        words    = para_text.split()
        word_mt  = [None] * len(words)

        for i in range(0, len(words), step):
            chunk_slice = words[i: i + chunk_size]
            if len(chunk_slice) >= 8:
                cd = chunk_detail.get(chunk_idx)
                if cd:
                    for w in range(i, min(i + len(chunk_slice), len(words))):
                        prev = word_mt[w]
                        if not prev or (_MT_PRIORITY.get(cd["match_type"], 0) >
                                        _MT_PRIORITY.get(prev["match_type"], 0)):
                            word_mt[w] = cd
            chunk_idx += 1

        # Reconstruct HTML with inline spans
        matches = list(re.finditer(r'\S+', para_text))
        if len(matches) != len(words):
            story.append(Paragraph(
                _esc(para_text).replace('\n', '<br/>'), para_style,
            ))
            continue

        html  = ""
        last  = 0
        cur   = None

        for i, m in enumerate(matches):
            mt    = word_mt[i]
            ws    = _esc(para_text[last:m.start()]).replace('\n', '<br/>')
            word  = _esc(para_text[m.start():m.end()])

            if mt != cur:
                if cur:
                    html += "</font>"
                html += ws
                if mt:
                    si     = src_idx.get(mt["reference"], 0)
                    bghex  = _bg_hex(si, mt["match_type"])
                    html += f'<font backColor="{bghex}">'
                cur = mt
            else:
                html += ws

            html += word
            last  = m.end()

        if cur:
            html += "</font>"
        html += _esc(para_text[last:]).replace('\n', '<br/>')

        story.append(Paragraph(html, para_style))


# ══════════════════════════════════════════════════════════════════════════════
# FALLBACK: build chunk_detail via str.find when details not available
# ══════════════════════════════════════════════════════════════════════════════

def _build_chunk_detail_fallback(
    raw_text:    str,
    all_results: list,
    src_idx:     dict,
    chunk_size:  int = 50,
    step:        int = 20,
) -> dict:
    """
    When all_details is not passed in, build a synthetic chunk_detail by
    finding each matched user_chunk in the raw text via str.find() and
    mapping it to the nearest chunk index.
    """
    if not raw_text:
        return {}

    words_flat  = raw_text.split()
    text_lower  = " ".join(words_flat).lower()
    chunk_detail: dict = {}

    for res in all_results:
        si = src_idx.get(res["reference"], 0)
        for m in res.get("sentence_matches", []):
            chunk = (m.get("user_chunk") or m.get("student_sentence", "")).strip()
            if not chunk or len(chunk.split()) < 5:
                continue
            phrase   = " ".join(chunk.lower().split()[:10])
            word_pos = text_lower.find(phrase)
            if word_pos < 0:
                continue
            # Map character position → word index → chunk index
            word_idx   = len(text_lower[:word_pos].split())
            chunk_idx  = word_idx // step
            mtype      = m.get("match_type", "semantic")
            prev       = chunk_detail.get(chunk_idx)
            if prev is None or (_MT_PRIORITY.get(mtype, 0) >
                                 _MT_PRIORITY.get(prev.get("match_type",""), 0)):
                chunk_detail[chunk_idx] = {
                    "user_chunk_idx": chunk_idx,
                    "user_chunk":     chunk,
                    "ref_chunk":      m.get("ref_chunk", ""),
                    "match_type":     mtype,
                    "similarity":     m.get("similarity", 0),
                    "reference":      res["reference"],
                }

    return chunk_detail


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY PAGE
# ══════════════════════════════════════════════════════════════════════════════

def _build_summary_page(
    story, student_pdf_name, matched_refs, src_idx,
    ov_top, ov_d, ov_p, ov_se, uncited_total, NR, SUM_W,
) -> None:
    story.append(Paragraph(
        "<b>Summary Analysis</b>",
        ParagraphStyle("sumhdr", parent=NR, fontSize=14,
                       textColor=HexColor("#1a252f"), spaceAfter=4, leading=18),
    ))
    story.append(Paragraph(
        f"Document: <b>{_esc(student_pdf_name)}</b>  ·  "
        f"Uncited chunks: <b>{uncited_total}</b>  ·  "
        f"Overall: <b>{ov_top}%</b>",
        ParagraphStyle("summeta", parent=NR, fontSize=8,
                       textColor=HexColor("#7f8c8d"), spaceAfter=10, leading=11),
    ))
    story.append(HRFlowable(width=SUM_W, thickness=1.0, color=HexColor("#c0392b")))
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        "<b>Overall Match Breakdown (across all references)</b>",
        ParagraphStyle("sumhdr2", parent=NR, fontSize=9,
                       textColor=HexColor("#2c3e50"), spaceAfter=6, leading=12),
    ))
    OV_COL = 1.6*cm
    ov_tbl = Table([[
        Paragraph(f"<b>{ov_top}%</b>",
                  _ps(NR, fontSize=18, textColor=HexColor("#2c3e50"))),
        Paragraph(f"<b>{ov_d}%</b><br/><font color='#7f8c8d' size='6'>Direct</font>",
                  _ps(NR, fontSize=9, textColor=HexColor("#1a6a8a"), leading=11)),
        Paragraph(f"<b>{ov_p}%</b><br/><font color='#7f8c8d' size='6'>Paraphrase</font>",
                  _ps(NR, fontSize=9, textColor=HexColor("#c0622b"), leading=11)),
        Paragraph(f"<b>{ov_se}%</b><br/><font color='#7f8c8d' size='6'>Semantic</font>",
                  _ps(NR, fontSize=9, textColor=HexColor("#2e7d32"), leading=11)),
    ]], colWidths=[OV_COL*1.5]*4)
    ov_tbl.setStyle(TableStyle([
        ("VALIGN",     (0,0),(-1,-1),"MIDDLE"),
        ("LINEAFTER",  (0,0),(2,0),   0.5, HexColor("#bdc3c7")),
        ("LEFTPADDING",(0,0),(-1,-1), 10),
    ]))
    story.append(ov_tbl)
    story.append(Spacer(1, 15))

    story.append(Paragraph(
        "<b>Per-Reference Breakdown</b>",
        ParagraphStyle("sumhdr3", parent=NR, fontSize=9,
                       textColor=HexColor("#2c3e50"), spaceAfter=6, leading=12),
    ))

    C = [0.5*cm, 6.0*cm, 2.0*cm, 2.0*cm, 2.0*cm, 2.0*cm]
    def hp(t, col): return Paragraph(f"<b>{t}</b>",
        _ps(NR, fontSize=7, textColor=col, alignment=TA_CENTER, leading=9))
    def vp(v, col):
        txt = f"{v}%" if v > 0 else "—"
        c   = col if v > 0 else HexColor("#bdc3c7")
        return Paragraph(txt, _ps(NR, fontSize=8, textColor=c, alignment=TA_CENTER, leading=10))

    hdr = Table([[
        Paragraph("", _ps(NR, fontSize=1)),
        Paragraph("<b>Reference PDF</b>", _ps(NR, fontSize=7, textColor=HexColor("#2c3e50"), leading=9)),
        hp("Total %", HexColor("#2c3e50")),
        hp("Direct",  HexColor("#1a6a8a")),
        hp("Paraph.", HexColor("#c0622b")),
        hp("Semantic",HexColor("#2e7d32")),
    ]], colWidths=C)
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), HexColor("#ecf0f1")),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
    ]))
    story.append(hdr)

    for si, r in enumerate(matched_refs):
        st = r["_st"]
        row = Table([[
            Paragraph("", _ps(NR, fontSize=1)),
            Paragraph(_esc(r["reference"]),
                      _ps(NR, fontSize=7, textColor=HexColor("#2c3e50"), leading=9)),
            vp(st["display_pct"], HexColor("#2c3e50")),
            vp(st["d"],           HexColor("#1a6a8a")),
            vp(st["p"],           HexColor("#c0622b")),
            vp(st["se"],          HexColor("#2e7d32")),
        ]], colWidths=C)
        row.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(0,0),   _pfg(si)),
            ("LINEBELOW",     (0,0),(-1,-1), 0.5, HexColor("#ecf0f1")),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]))
        story.append(row)