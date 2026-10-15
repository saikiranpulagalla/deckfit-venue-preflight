from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
from pptx import Presentation

from app.security.intake import sha256_path


class MutationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScaleMutation:
    slide_index: int
    shape_id: int
    scale: float


def _scale_shape(target, scale: float) -> int:
    changed = 0
    for p in target.text_frame.paragraphs:
        for run in p.runs:
            if run.text.strip():
                if run.font.size is None:
                    raise MutationError("Inherited/unknown font size cannot be mutated safely")
                run.font.size = int(round(run.font.size * scale))
                changed += 1
    return changed


def apply_scale_plan(source: Path, output: Path, mutations: list[ScaleMutation]) -> None:
    if not mutations:
        raise MutationError("No mutations supplied")
    if len({(m.slide_index, m.shape_id) for m in mutations}) != len(mutations):
        raise MutationError("Duplicate target in one repair plan")
    for m in mutations:
        if not (1.0 < m.scale <= 1.60):
            raise MutationError("Scale outside allowed range")

    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(output.parent, 0o700)
    except OSError:
        pass
    from zipfile import ZipFile
    from app.pptx.package_integrity import _logical_part_indices
    with ZipFile(source) as archive:
        parts = _logical_part_indices(archive)
    if any(name != f'ppt/slides/slide{index + 1}.xml' for name, index in parts.items()):
        original_hash = sha256_path(source)
        _apply_reordered_scale_plan(source, output, mutations)
        if sha256_path(source) != original_hash:
            raise MutationError('Invariant violation: source file changed')
        return
    shutil.copy2(source, output)
    original_hash = sha256_path(source)
    prs = Presentation(str(output))

    changed = 0
    for m in mutations:
        if not (0 <= m.slide_index < len(prs.slides)):
            raise MutationError("Target slide missing")
        slide = prs.slides[m.slide_index]
        target = next((s for s in slide.shapes if s.shape_id == m.shape_id), None)
        if target is None or not getattr(target, "has_text_frame", False):
            raise MutationError("Target shape missing or unsupported")
        changed += _scale_shape(target, m.scale)

    if changed == 0:
        raise MutationError("No explicit text run changed")
    prs.save(str(output))
    try:
        os.chmod(output, 0o600)
    except OSError:
        pass
    if sha256_path(source) != original_hash:
        raise MutationError("Invariant violation: source file changed")


def apply_scale_text(source: Path, output: Path, slide_index: int, shape_id: int, scale: float) -> None:
    apply_scale_plan(source, output, [ScaleMutation(slide_index=slide_index, shape_id=shape_id, scale=scale)])

# Explicit OOXML edit for presentations whose logical slide order differs from
# physical ZIP numbering. python-pptx can renumber slide relationship targets
# during save; a font-size-only operation must not change that navigation map.
def _apply_reordered_scale_plan(source: Path, output: Path, mutations: list[ScaleMutation]) -> None:
    from xml.etree import ElementTree as ET
    from zipfile import ZipFile
    from app.pptx.package_integrity import _logical_part_indices, NS_A, NS_P, RUN_PROPERTIES

    with ZipFile(source) as src:
        logical_parts = _logical_part_indices(src)
        by_index = {position: name for name, position in logical_parts.items()}
        mutations_by_part: dict[str, list[ScaleMutation]] = {}
        for m in mutations:
            if m.slide_index not in by_index:
                raise MutationError('Target slide missing')
            mutations_by_part.setdefault(by_index[m.slide_index], []).append(m)
        replacements: dict[str, bytes] = {}
        changed = 0
        for name, edits in mutations_by_part.items():
            slide = ET.fromstring(src.read(name))
            shapes = {}
            for shape in slide.findall(f'.//{{{NS_P}}}spTree/{{{NS_P}}}sp'):
                props = shape.find(f'./{{{NS_P}}}nvSpPr/{{{NS_P}}}cNvPr')
                if props is not None and props.get('id') is not None:
                    sid = int(props.get('id'))
                    if sid in shapes:
                        raise MutationError('Duplicate slide shape identity')
                    shapes[sid] = shape
            for edit in edits:
                target = shapes.get(edit.shape_id)
                if target is None:
                    raise MutationError('Target shape missing or unsupported')
                for run in target.findall(f'.//{{{NS_A}}}r'):
                    text_node = run.find(f'{{{NS_A}}}t')
                    if text_node is None or not (text_node.text or '').strip():
                        continue
                    properties = run.find(RUN_PROPERTIES)
                    old = properties.get('sz') if properties is not None else None
                    if not old or not old.isdecimal():
                        raise MutationError('Inherited/unknown font size cannot be mutated safely')
                    old_int = int(old)
                    if old_int <= 0:
                        raise MutationError('Invalid explicit font size')
                    # PPTX a:rPr/@sz uses hundredths of a point.
                    properties.set('sz', str(round(old_int * edit.scale)))
                    changed += 1
            replacements[name] = ET.tostring(slide, encoding='utf-8', xml_declaration=True)
        if changed == 0:
            raise MutationError('No explicit text run changed')
        staging = output.with_name(output.name + '.staging')
        try:
            with ZipFile(staging, 'w') as dst:
                for info in src.infolist():
                    dst.writestr(info, replacements.get(info.filename, src.read(info.filename)))
            os.replace(staging, output)
        finally:
            staging.unlink(missing_ok=True)
    try:
        os.chmod(output, 0o600)
    except OSError:
        pass
