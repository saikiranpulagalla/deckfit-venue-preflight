"""Fail-closed OOXML preservation for DeckFit's *font-size-only* mutation.

The accepted edit is an increase of explicit ``a:rPr/@sz`` values in approved
text shapes. Unrelated XML, archive parts, media bytes and package relationships
must remain semantically identical. XML is canonicalized to ignore harmless
namespace/attribute serialization changes; unknown differences are refused.

This is NOT a contrast checker or a universal Office compatibility guarantee.
"""
from __future__ import annotations

import re
import posixpath
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

NS_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
NS_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
SLIDE_PATTERN = re.compile(r'^ppt/slides/slide([1-9][0-9]*)\.xml$')
RUN_PROPERTIES = f'{{{NS_A}}}rPr'


def _normalized_xml(data: bytes) -> str:
    return ET.canonicalize(data.decode('utf-8-sig'), rewrite_prefixes=True)


def _logical_part_indices(zf: ZipFile) -> dict[str, int]:
    """Resolve logical presentation position through its OPC relationship ID."""
    ns_p = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
    ns_o = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    ns_r = '{http://schemas.openxmlformats.org/package/2006/relationships}'
    presentation = ET.fromstring(zf.read('ppt/presentation.xml'))
    relationships = ET.fromstring(zf.read('ppt/_rels/presentation.xml.rels'))
    rels = {e.get('Id'): e.get('Target') for e in relationships
            if e.tag == ns_r + 'Relationship'
            and e.get('Type') == 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide'
            and e.get('TargetMode', 'Internal') == 'Internal'}
    slides = presentation.find(ns_p + 'sldIdLst')
    if slides is None:
        raise ValueError('missing_logical_slide_list')
    result = {}
    for index, element in enumerate(slides):
        rid = element.get(ns_o + 'id')
        target = rels.get(rid)
        if not target:
            raise ValueError('missing_logical_slide_relationship')
        name = posixpath.normpath(posixpath.join('ppt', target))
        if SLIDE_PATTERN.fullmatch(name) is None or name in result:
            raise ValueError('ambiguous_logical_slide_part')
        result[name] = index
    return result


def _shape_ids(root: ET.Element) -> dict[int, ET.Element]:
    result = {}
    for shape in root.findall(f'.//{{{NS_P}}}spTree/{{{NS_P}}}sp'):
        props = shape.find(f'./{{{NS_P}}}nvSpPr/{{{NS_P}}}cNvPr')
        if props is None or props.get('id') is None:
            raise ValueError('unidentified_slide_shape')
        sid = int(props.get('id'))
        if sid in result:
            raise ValueError('duplicate_slide_shape_id')
        result[sid] = shape
    return result


def _approved_font_only_xml(source: bytes, output: bytes, slide_index: int,
                            allowed_targets: set[tuple[int, int]] | None,
                            expected_scales: dict[tuple[int, int], float] | None) -> bool:
    """Check permitted increases, then compare the full XML excluding them."""
    before = ET.fromstring(source)
    after = ET.fromstring(output)
    before_shapes, after_shapes = _shape_ids(before), _shape_ids(after)
    if before_shapes.keys() != after_shapes.keys():
        return False
    for sid, bs in before_shapes.items():
        if allowed_targets is not None and (slide_index, sid) not in allowed_targets:
            continue
        a_shape = after_shapes[sid]
        # Matching document tree and run order will be established by the
        # canonical full-slide comparison below after attributes are restored.
        before_runs = bs.findall(f'.//{{{NS_A}}}r')
        after_runs = a_shape.findall(f'.//{{{NS_A}}}r')
        if len(before_runs) != len(after_runs):
            return False
        for b_run, a_run in zip(before_runs, after_runs):
            br, ar = b_run.find(RUN_PROPERTIES), a_run.find(RUN_PROPERTIES)
            if (br is None) != (ar is None):
                return False
            if br is None:
                continue
            old, new = br.get('sz'), ar.get('sz')
            source_text = b_run.find(f'{{{NS_A}}}t')
            explicit_text = source_text is not None and bool((source_text.text or '').strip())
            scale = expected_scales.get((slide_index, sid)) if expected_scales else None
            # When exact scales are supplied, every applicable explicit-size
            # text run must be modified, not just the runs that happened to
            # differ. Preserve non-text/implicit-size runs unchanged.
            if old == new:
                if scale is not None and old is not None and explicit_text:
                    return False
                continue
            if old is None or new is None or not old.isdecimal() or not new.isdecimal():
                return False
            # Empty runs are not modified by DeckFit's font-only operation.
            if not explicit_text:
                return False
            old_i, new_i = int(old), int(new)
            if scale is not None and abs(new_i - round(old_i * scale)) > 1:
                return False
            # DeckFit's scale operation is 1.0 < scale <= 1.6; rounded
            # serialized values are allowed a one-unit quantization tolerance.
            if not (0 < old_i < new_i <= round(old_i * 1.6) + 1):
                return False
            ar.set('sz', old)
    return _normalized_xml(ET.tostring(before, encoding='utf-8')) == _normalized_xml(ET.tostring(after, encoding='utf-8'))


def package_integrity_reasons(source: Path, output: Path,
                              allowed_targets: set[tuple[int, int]] | None = None,
                              expected_scales: dict[tuple[int, int], float] | None = None) -> list[str]:
    """Return preservation failures; every non-font difference is disallowed.

    ``allowed_targets`` must be supplied for authorization-sensitive calls.
    A ``None`` target set retains older utility callers' permissive font-size
    scope, while the simulation/final verifier always supply precise targets.
    """
    try:
        with ZipFile(source) as before, ZipFile(output) as after:
            bn, an = before.namelist(), after.namelist()
            if len(bn) != len(set(bn)) or len(an) != len(set(an)) or set(bn) != set(an):
                return ['protected_package_part_inventory_changed']
            logical_before = _logical_part_indices(before)
            try:
                logical_after = _logical_part_indices(after)
            except (ET.ParseError, KeyError, ValueError):
                return ['protected_package_relationships_changed']
            if logical_before != logical_after:
                return ['protected_package_relationships_changed']
            reasons = []
            for name in sorted(set(bn)):
                a_bytes, b_bytes = before.read(name), after.read(name)
                if a_bytes == b_bytes:
                    continue
                match = SLIDE_PATTERN.fullmatch(name)
                if match:
                    if not _approved_font_only_xml(a_bytes, b_bytes, logical_before.get(name, -1),
                                                   allowed_targets, expected_scales):
                        reasons.append('unapproved_slide_appearance_or_structure_changed')
                elif name.endswith(('.xml', '.rels')):
                    if _normalized_xml(a_bytes) != _normalized_xml(b_bytes):
                        reasons.append('protected_package_relationships_changed' if name.endswith('.rels')
                                       else 'slide_navigation_order_changed' if name == 'ppt/presentation.xml'
                                       else 'protected_package_xml_changed')
                else:
                    reasons.append('protected_package_part_changed')
            return sorted(set(reasons))
    except (BadZipFile, ET.ParseError, UnicodeError, KeyError, ValueError, OSError, OverflowError):
        return ['protected_package_integrity_uninspectable']
