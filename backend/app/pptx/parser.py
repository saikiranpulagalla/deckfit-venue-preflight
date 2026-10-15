from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

import fitz
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.enum.dml import MSO_FILL_TYPE

from app.domain.models import AnalysisCapability, MappingConfidence, MutationCapability, TextElement


MAX_STRUCTURAL_TEXT_ELEMENTS = 500
MAX_RENDERED_TEXT_SPANS = 10_000


class ParserLimitError(RuntimeError):
    pass


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().casefold()


def _font_key(name: str) -> str:
    name = (name or "").split("+")[-1]
    # PDF font names can append an actual style suffix to a family name. Do
    # not use substring matching: Sans, Sans Mono and Sans Condensed differ.
    name = re.sub(r"[-,](?:regular|bold|italic|oblique|bolditalic|boldoblique)$", "", name, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _font_matches(requested: str, rendered: str) -> bool:
    a, b = _font_key(requested), _font_key(rendered)
    return bool(a and b and a == b)


@dataclass
class ShapeRecord:
    slide_index: int
    shape_id: int
    text: str
    normalized_text: str
    role: str
    explicit_font_sizes_pt: list[float]
    mutation_capability: MutationCapability
    notes: list[str]
    normalized_bbox: tuple[float, float, float, float]
    requested_font_families: list[str] = field(default_factory=list)
    force_not_analyzable: bool = False
    unsupported_visible_content: bool = False


def _placeholder_role(shape) -> str | None:
    try:
        if not shape.is_placeholder:
            return None
        ptype = shape.placeholder_format.type
        if ptype in {PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE, PP_PLACEHOLDER.VERTICAL_TITLE}:
            return "TITLE"
        if ptype in {PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.DATE, PP_PLACEHOLDER.SLIDE_NUMBER}:
            return "FOOTER"
    except Exception:
        return None
    return None


def _role(shape, slide_h: float, explicit_sizes: list[float]) -> str:
    placeholder_role = _placeholder_role(shape)
    if placeholder_role:
        return placeholder_role
    name = (getattr(shape, "name", "") or "").lower()
    if "title" in name:
        return "TITLE"
    if "footer" in name:
        return "FOOTER"
    if getattr(shape, "has_text_frame", False):
        top_ratio = float(getattr(shape, "top", 0) or 0) / max(slide_h, 1.0)
        max_size = max(explicit_sizes, default=0.0)
        # Conservative V1: location alone suffices to protect a likely heading.
        # The font-size threshold previously allowed 18pt manual titles to be
        # mutated. Ambiguous top-area text is review-only rather than BODY.
        # Extremely top-aligned text is ambiguous even when small; preserve
        # conventional body blocks at 13-22% unless prominent or named TITLE.
        if top_ratio <= 0.12 or (top_ratio <= 0.22 and max_size >= 24.0):
            return "TITLE"
        if top_ratio >= 0.84 and max_size <= 18.0:
            return "FOOTER"
        return "BODY"
    return "OTHER"


def _shape_mutation_capability(shape) -> tuple[MutationCapability, list[str], list[float], list[str]]:
    notes: list[str] = []
    sizes: list[float] = []
    fonts: list[str] = []
    if not getattr(shape, "has_text_frame", False):
        return MutationCapability.NO_MUTATION, ["no_text_frame"], sizes, fonts
    if float(getattr(shape, "rotation", 0) or 0) % 360 != 0:
        return MutationCapability.NO_MUTATION, ["rotated_text"], sizes, fonts
    if shape.shape_type not in {MSO_SHAPE_TYPE.TEXT_BOX, MSO_SHAPE_TYPE.PLACEHOLDER, MSO_SHAPE_TYPE.AUTO_SHAPE}:
        return MutationCapability.NO_MUTATION, [f"unsupported_shape_type:{shape.shape_type}"], sizes, fonts

    auto_size = shape.text_frame.auto_size
    if auto_size not in {None, MSO_AUTO_SIZE.NONE}:
        notes.append(f"automatic_text_fitting:{auto_size}")

    for p in shape.text_frame.paragraphs:
        for run in p.runs:
            if run.text.strip():
                if run.font.size is None:
                    notes.append("inherited_or_unknown_font_size")
                else:
                    sizes.append(round(run.font.size.pt, 3))
                if run.font.name:
                    fonts.append(run.font.name)
                else:
                    notes.append("inherited_or_unknown_font_family")
    fonts = sorted(set(fonts))
    if not sizes:
        return MutationCapability.REVIEW_ONLY, sorted(set(notes + ["no_explicit_font_sizes"])), sizes, fonts
    # Any autofit or inherited typography is review-only. Automated mutation is
    # intentionally narrower than analysis because renderer-dependent fitting can
    # create silent layout changes after font scaling.
    if notes:
        return MutationCapability.REVIEW_ONLY, sorted(set(notes)), sizes, fonts
    return MutationCapability.SAFE_MUTATION, [], sizes, fonts


def _shape_bbox(shape, slide_w: float, slide_h: float) -> tuple[float, float, float, float]:
    return (
        float(shape.left) / slide_w,
        float(shape.top) / slide_h,
        float(shape.left + shape.width) / slide_w,
        float(shape.top + shape.height) / slide_h,
    )


def _table_text(shape) -> str:
    if not getattr(shape, "has_table", False):
        return ""
    texts: list[str] = []
    for row in shape.table.rows:
        for cell in row.cells:
            if (cell.text or "").strip():
                texts.append(cell.text)
    return "\n".join(texts)


def _group_text(shape) -> str:
    if shape.shape_type != MSO_SHAPE_TYPE.GROUP:
        return ""
    texts: list[str] = []
    for child in shape.shapes:
        if getattr(child, "has_text_frame", False) and (child.text or "").strip():
            texts.append(child.text)
        if getattr(child, "has_table", False):
            t = _table_text(child)
            if t:
                texts.append(t)
        if child.shape_type == MSO_SHAPE_TYPE.GROUP:
            t = _group_text(child)
            if t:
                texts.append(t)
    return "\n".join(texts)




def _shape_type_name(shape) -> str:
    st = getattr(shape, "shape_type", None)
    return getattr(st, "name", str(st)).lower().replace(" ", "_")


def _populated_visual_placeholder(shape) -> bool:
    element = shape._element
    return any(elem.tag.rsplit("}", 1)[-1] in {"blip", "graphicData", "oleObj", "videoFile", "audioFile"}
               for elem in element.iter()) or element.tag.rsplit("}", 1)[-1] in {"pic", "graphicFrame"}


def _has_unsupported_surface(shape) -> bool:
    """Any potentially painted shape surface is outside V1's text-only model.

    This must be the *same* test for populated and empty text frames:
    otherwise a thick opaque line around a populated textbox escapes coverage.
    Explicitly unpainted text frames are still eligible for supported analysis.
    """
    # DrawingML shape style references can paint a surface even when there is
    # no explicit spPr fill/line. An unresolved nonzero theme index is never
    # proof of an unpainted editable textbox.
    style = shape._element.find('{http://schemas.openxmlformats.org/presentationml/2006/main}style')
    if style is not None:
        for node in style:
            if node.tag.rsplit('}', 1)[-1] in {'fillRef', 'lnRef', 'effectRef'}:
                index = node.get('idx', '')
                if index != '0':
                    return True  # Unknown/invalid indices are also fail-closed.
    try:
        if shape.fill.type not in {None, MSO_FILL_TYPE.BACKGROUND}:
            return True
        if shape.line.fill.type not in {None, MSO_FILL_TYPE.BACKGROUND}:
            return True
    except (AttributeError, ValueError):
        return True  # Uncertain paint cannot be asserted harmless.
    return any(node.tag.rsplit('}', 1)[-1] in {
        'effectLst', 'effectDag', 'scene3d', 'sp3d', 'blipFill'
    } for node in shape._element.iter())


def _has_visible_empty_shape_surface(shape) -> bool:
    """Compatibility alias; both kinds of text shapes use identical checks."""
    return _has_unsupported_surface(shape)


def _background_kind(element) -> str | None:
    # p:bg / p:bgPr may be inherited from slide layout or master. Ordinary
    # solid background fills and theme bgRef are not image content.
    if element is None:
        return None
    for node in element.iter():
        if node.tag.rsplit("}", 1)[-1] not in {"bg", "bgPr"}:
            continue
        for child in node.iter():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag in {"blipFill", "blip", "gradFill", "pattFill", "grpFill"}:
                return tag
    return None


def _background_unknown(slide_index: int, scope: str, kind: str, shape_id: int) -> ShapeRecord:
    marker = f"[unsupported visible {scope} background {kind}]"
    return ShapeRecord(
        slide_index=slide_index, shape_id=shape_id, text=marker,
        normalized_text=normalize_text(marker), role="OTHER", explicit_font_sizes_pt=[],
        mutation_capability=MutationCapability.NO_MUTATION,
        notes=[f"unsupported_visible_{scope}_background_{kind}"],
        normalized_bbox=(0.0, 0.0, 1.0, 1.0),
        force_not_analyzable=True, unsupported_visible_content=True,
    )


def _potentially_visible_nontext_shape(shape) -> bool:
    """Conservatively identify visible shapes outside the supported text model.

    Empty placeholders are skipped because they are editing affordances rather
    than rendered slide content. Empty text boxes are skipped only if they
    have no visible fill, line or advanced effects. Everything
    else outside the supported text path is treated as visible/unknown so an
    opaque overlay, picture, chart, SmartArt/diagram, media object, connector,
    or decorative AutoShape cannot silently disappear from the analysis universe.
    """
    st = getattr(shape, "shape_type", None)
    if st in {MSO_SHAPE_TYPE.COMMENT, MSO_SHAPE_TYPE.SCRIPT_ANCHOR}:
        return False
    if st == MSO_SHAPE_TYPE.PLACEHOLDER:
        # A populated picture placeholder stays a PLACEHOLDER in python-pptx.
        # Inspect actual OOXML rather than trusting the editing placeholder type.
        return _populated_visual_placeholder(shape)
    if st == MSO_SHAPE_TYPE.TEXT_BOX and not (getattr(shape, "text", "") or "").strip():
        return _has_visible_empty_shape_surface(shape)
    return True


def _unsupported_visual_record(
    *,
    slide_index: int,
    shape,
    slide_w: float,
    slide_h: float,
    scope: str,
    synthetic_shape_id: int | None = None,
    text: str | None = None,
) -> ShapeRecord:
    kind = _shape_type_name(shape)
    marker = (text or "").strip() or f"[unsupported visible {scope} {kind}]"
    if scope == "slide" and marker and kind == "table":
        note = "unsupported_visible_table_text"
    elif scope == "slide" and marker and kind == "group":
        note = "unsupported_visible_group_text"
    else:
        note = f"unsupported_visible_{scope}_{kind}"
    return ShapeRecord(
        slide_index=slide_index,
        shape_id=synthetic_shape_id if synthetic_shape_id is not None else int(shape.shape_id),
        text=marker,
        normalized_text=normalize_text(marker),
        role="OTHER",
        explicit_font_sizes_pt=[],
        mutation_capability=MutationCapability.NO_MUTATION,
        notes=[note],
        normalized_bbox=_shape_bbox(shape, slide_w, slide_h),
        force_not_analyzable=True,
        unsupported_visible_content=True,
    )

def parse_pptx_shapes(source: Path) -> list[ShapeRecord]:
    prs = Presentation(str(source))
    slide_w = float(prs.slide_width)
    slide_h = float(prs.slide_height)
    out: list[ShapeRecord] = []

    def append_record(record: ShapeRecord) -> None:
        out.append(record)
        if len(out) > MAX_STRUCTURAL_TEXT_ELEMENTS:
            raise ParserLimitError(f"structural_text_element_limit_exceeded:{MAX_STRUCTURAL_TEXT_ELEMENTS}")

    def append_inherited_unknowns(slide, si: int) -> None:
        # Explicit layout/master visuals and text are rendered presentation
        # content but are outside V1's mutation/mapping model. Represent them
        # as unknown instead of letting them disappear from whole-deck coverage.
        # p:sld/@showMasterSp=0 suppresses inherited decorative shapes, not
        # background imagery (which is inventoried separately).
        if str(slide._element.get("showMasterSp", "1")).lower() in {"0", "false"}:
            return
        inherited = [
            ("layout", slide.slide_layout.shapes, -1_000_000),
            ("master", slide.slide_layout.slide_master.shapes, -2_000_000),
        ]
        for scope, shapes, prefix in inherited:
            for shape in shapes:
                # Placeholders on layouts/masters are templates; the concrete
                # slide placeholder is handled in slide.shapes when populated.
                if getattr(shape, "is_placeholder", False):
                    continue
                text = ""
                if getattr(shape, "has_text_frame", False):
                    text = shape.text or ""
                elif getattr(shape, "has_table", False):
                    text = _table_text(shape)
                elif shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                    text = _group_text(shape)
                if text.strip() or _potentially_visible_nontext_shape(shape):
                    append_record(_unsupported_visual_record(
                        slide_index=si,
                        shape=shape,
                        slide_w=slide_w,
                        slide_h=slide_h,
                        scope=scope,
                        synthetic_shape_id=prefix - int(shape.shape_id),
                        text=text,
                    ))

    for si, slide in enumerate(prs.slides):
        # LibreOffice's default PDF export omits p:sld/@show=0 slides. Hidden
        # content is neither a visible obstruction nor a mutation target.
        if str(slide._element.get('show', '1')).lower() in {'0', 'false'}:
            continue
        # Explicit slide background overrides the inherited layout/master
        # background. Treat image/gradient/pattern backgrounds as unknown.
        for scope, obj, shape_id in (
            ("slide", slide, -3_000_001),
            ("layout", slide.slide_layout, -3_000_002),
            ("master", slide.slide_layout.slide_master, -3_000_003),
        ):
            kind = _background_kind(obj._element)
            if kind:
                append_record(_background_unknown(si, scope, kind, shape_id))
            # Any explicit background also overrides the inherited ones.
            if any(child.tag.rsplit("}", 1)[-1] == "bg"
                   for child in obj._element.iter() if child is not obj._element):
                break
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                text = shape.text or ""
                if text.strip():
                    # The shape can carry both editable text and an unsupported
                    # opaque/complex painted surface; inventory both separately.
                    painted = _has_unsupported_surface(shape)
                    if painted:
                        append_record(_unsupported_visual_record(
                            slide_index=si, shape=shape, slide_w=slide_w,
                            slide_h=slide_h, scope="text_shape_surface",
                            synthetic_shape_id=-4_000_000-int(shape.shape_id),
                        ))
                    cap, notes, sizes, fonts = _shape_mutation_capability(shape)
                    if painted:
                        # In addition to blocking whole-deck VERIFIED, do not
                        # mutate text inside a visually unsupported surface.
                        cap = MutationCapability.NO_MUTATION
                        notes.append('unsupported_painted_text_shape_review_only')
                    append_record(ShapeRecord(
                        slide_index=si,
                        shape_id=shape.shape_id,
                        text=text,
                        normalized_text=normalize_text(text),
                        role=_role(shape, slide_h, sizes),
                        explicit_font_sizes_pt=sizes,
                        mutation_capability=cap,
                        notes=notes,
                        normalized_bbox=_shape_bbox(shape, slide_w, slide_h),
                        requested_font_families=fonts,
                    ))
                    continue

            # Unsupported visible content must remain represented in the analysis
            # universe instead of silently disappearing from coverage. This
            # includes non-text visual objects that could obscure supported text.
            unsupported_text = _table_text(shape) or _group_text(shape)
            if unsupported_text.strip() or _potentially_visible_nontext_shape(shape):
                append_record(_unsupported_visual_record(
                    slide_index=si,
                    shape=shape,
                    slide_w=slide_w,
                    slide_h=slide_h,
                    scope="slide",
                    text=unsupported_text,
                ))

        append_inherited_unknowns(slide, si)
    return out


def rendered_spans(pdf_path: Path) -> list[dict]:
    rows: list[dict] = []
    line_counter = 0
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            pw = page.rect.width
            ph = page.rect.height
            if pw <= 0 or ph <= 0:
                raise ParserLimitError("rendered_page_has_invalid_geometry")
            data = page.get_text("dict")
            for block in data.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    line_counter += 1
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        if not text.strip():
                            continue
                        if len(rows) >= MAX_RENDERED_TEXT_SPANS:
                            raise ParserLimitError(
                                f"rendered_text_span_limit_exceeded:{MAX_RENDERED_TEXT_SPANS}"
                            )
                        x0, y0, x1, y1 = span["bbox"]
                        rows.append({
                            "span_id": len(rows),
                            "line_id": line_counter,
                            "slide_index": page_index,
                            "text": text,
                            "normalized_text": normalize_text(text),
                            "font": span.get("font") or "",
                            "bbox": (x0, y0, x1, y1),
                            "normalized_bbox": (x0 / pw, y0 / ph, x1 / pw, y1 / ph),
                            "height_percent": max(0.0, (y1-y0) / ph * 100.0),
                        })
    return rows


def _span_center_inside_shape(span: dict, rec: ShapeRecord, tolerance: float = 0.01) -> bool:
    x0, y0, x1, y1 = span["normalized_bbox"]
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    sx0, sy0, sx1, sy1 = rec.normalized_bbox
    return (
        sx0 - tolerance <= cx <= sx1 + tolerance
        and sy0 - tolerance <= cy <= sy1 + tolerance
    )


def _union_bbox(spans: list[dict]) -> tuple[float, float, float, float] | None:
    if not spans:
        return None
    boxes = [s["normalized_bbox"] for s in spans]
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _rendered_font_mismatch(requested: list[str], rendered: list[str]) -> bool:
    if not requested:
        return False
    if not rendered:
        return True
    return any(not any(_font_matches(req, actual) for actual in rendered) for req in requested)


def map_elements(source: Path, pdf_path: Path) -> list[TextElement]:
    shapes = parse_pptx_shapes(source)
    spans = rendered_spans(pdf_path)
    if source.is_file() and pdf_path.is_file():
        prs = Presentation(str(source))
        visible = [i for i, slide in enumerate(prs.slides)
                   if str(slide._element.get('show', '1')).lower() not in {'0', 'false'}]
        with fitz.open(str(pdf_path)) as document:
            page_count = len(document)
        if page_count != len(visible):
            # A renderer/export mismatch is not a trustworthy geometry mapping.
            marker = '[unsupported rendered slide-page mapping]'
            shapes.append(ShapeRecord(
                slide_index=0, shape_id=-9_000_001, text=marker,
                normalized_text=normalize_text(marker), role='OTHER',
                explicit_font_sizes_pt=[], mutation_capability=MutationCapability.NO_MUTATION,
                notes=['rendered_slide_page_count_mismatch'],
                normalized_bbox=(0.0, 0.0, 1.0, 1.0),
                force_not_analyzable=True, unsupported_visible_content=True,
            ))
            page_of_slide = {}
        else:
            page_of_slide = {slide_idx: pdf_idx for pdf_idx, slide_idx in enumerate(visible)}
    else:
        # In-memory unit mapping harnesses provide synthetic shapes and spans
        # instead of on-disk artifacts. They already use aligned slide indices.
        page_of_slide = {rec.slide_index: rec.slide_index for rec in shapes}
    mapped: list[tuple[ShapeRecord, list[dict], list[dict], MappingConfidence]] = []

    for rec in shapes:
        if rec.force_not_analyzable:
            mapped.append((rec, [], [], MappingConfidence.UNMAPPED))
            continue
        candidates = [
            s for s in spans
            if page_of_slide.get(rec.slide_index) == s["slide_index"] and _span_center_inside_shape(s, rec)
        ]
        raw_claims = [
            s for s in candidates
            if s["normalized_text"] and s["normalized_text"] in rec.normalized_text
        ]
        raw_claims.sort(key=lambda s: int(s["span_id"]))
        exact = [s for s in raw_claims if s["normalized_text"] == rec.normalized_text]
        reconstructed = normalize_text(" ".join(s["text"] for s in raw_claims))

        if len(exact) == 1 and len(raw_claims) == 1:
            chosen = exact
            confidence = MappingConfidence.EXACT
        elif raw_claims and reconstructed == rec.normalized_text:
            chosen = raw_claims
            confidence = MappingConfidence.STRONG
        elif raw_claims:
            # Partial PDF extraction is evidence of uncertainty, not permission
            # to infer a measurement from the visible fragment.
            chosen = []
            confidence = MappingConfidence.PARTIAL
        else:
            chosen = []
            confidence = MappingConfidence.UNMAPPED
        mapped.append((rec, chosen, raw_claims, confidence))

    # A span plausibly claimed by multiple structural elements makes ownership
    # ambiguous even if only one of those elements reconstructs completely.
    owners: dict[int, int] = {}
    for _, _, raw_claims, _ in mapped:
        for span in raw_claims:
            sid = int(span["span_id"])
            owners[sid] = owners.get(sid, 0) + 1

    out: list[TextElement] = []
    for rec, chosen, raw_claims, confidence in mapped:
        ambiguous = any(owners.get(int(span["span_id"]), 0) > 1 for span in raw_claims)
        if ambiguous:
            confidence = MappingConfidence.AMBIGUOUS
            chosen = []

        rendered_fonts = sorted({str(s.get("font") or "") for s in chosen if s.get("font")})
        if chosen:
            height = min(s["height_percent"] for s in chosen)
            analysis_cap = AnalysisCapability.ANALYZABLE
            rendered_bbox = _union_bbox(chosen)
            line_count = len({int(s.get("line_id", s["span_id"])) for s in chosen})
        else:
            height = None
            analysis_cap = AnalysisCapability.NOT_ANALYZABLE
            rendered_bbox = None
            line_count = 0

        mutation_cap = rec.mutation_capability
        notes = list(rec.notes)
        if confidence not in {MappingConfidence.EXACT, MappingConfidence.STRONG}:
            mutation_cap = MutationCapability.NO_MUTATION
        if confidence == MappingConfidence.PARTIAL:
            notes.append("partial_rendered_text_reconstruction")
        if ambiguous:
            notes.append("ambiguous_rendered_span_ownership")
        if rec.unsupported_visible_content:
            notes.append("unsupported_visible_content")
            analysis_cap = AnalysisCapability.NOT_ANALYZABLE
            mutation_cap = MutationCapability.NO_MUTATION
        if chosen and _rendered_font_mismatch(rec.requested_font_families, rendered_fonts):
            notes.append("font_substitution_or_unverified")
            # The current renderer geometry may still be analyzable, but a saved
            # PPTX cannot be auto-repaired safely when its requested font is not
            # the font that generated the evidence.
            mutation_cap = MutationCapability.REVIEW_ONLY

        out.append(TextElement(
            element_id=f"s{rec.slide_index+1}-sh{rec.shape_id}",
            slide_index=rec.slide_index,
            shape_id=rec.shape_id,
            source_text=rec.text,
            normalized_text=rec.normalized_text,
            role=rec.role,
            rendered_height_percent=height,
            analysis_capability=analysis_cap,
            mutation_capability=mutation_cap,
            mapping_confidence=confidence,
            explicit_font_sizes_pt=rec.explicit_font_sizes_pt,
            requested_font_families=rec.requested_font_families,
            rendered_font_families=rendered_fonts,
            structural_bbox=rec.normalized_bbox,
            rendered_bbox=rendered_bbox,
            rendered_span_count=len(chosen),
            rendered_line_count=line_count,
            notes=sorted(set(notes)),
        ))
    return out
