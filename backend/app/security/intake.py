from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import re
import posixpath
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
import zlib
import xml.parsers.expat as expat


MAX_BYTES = 20 * 1024 * 1024
MAX_ENTRIES = 5000
MAX_UNCOMPRESSED = 150 * 1024 * 1024
MAX_SINGLE_ENTRY_UNCOMPRESSED = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200.0
MAX_SLIDES = 75
MAX_RELATIONSHIP_XML_BYTES = 2 * 1024 * 1024
MAX_SLIDE_XML_BYTES = 4 * 1024 * 1024
MAX_TOTAL_SLIDE_XML_BYTES = 24 * 1024 * 1024
MAX_SLIDE_TEXT_CHARACTERS = 300_000
MAX_SLIDE_TEXT_RUNS = 20_000
MAX_XML_DEPTH = 192  # Below the downstream lxml/libxml2 default nesting limit.
MAX_XML_ELEMENTS = 100_000
MAX_SVG_TEXT_BYTES = 512 * 1024
MAX_SVG_ATTRIBUTE_CHARACTERS = 64 * 1024
SUPPORTED_ZIP_CODECS = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}


def _bounded_xml(data: bytes, *, label: str) -> ET.Element:
    """Fail closed before ElementTree can expand DTD entities or deep trees.

    Expat's event handlers count depth and reject DTD declarations before
    materializing a potentially amplified ElementTree value. Accepted files
    are then parsed by ElementTree exactly as before.
    """
    parser = expat.ParserCreate()
    depth = 0
    elements = 0
    def begin(_tag, _attrs):
        nonlocal depth, elements
        depth += 1
        elements += 1
        if elements > MAX_XML_ELEMENTS:
            raise IntakeError(f'{label} element count exceeds safe processing limit')
        if depth > MAX_XML_DEPTH:
            raise IntakeError(f'{label} nesting exceeds safe processing depth')
    def end(_tag):
        nonlocal depth
        depth -= 1
    def forbid(*_args):
        raise IntakeError(f'{label} DTD/entities are not supported')
    parser.StartElementHandler = begin
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = forbid
    parser.EntityDeclHandler = forbid
    parser.ExternalEntityRefHandler = forbid
    try:
        parser.Parse(data, True)
        return ET.fromstring(data)
    except (expat.ExpatError, ET.ParseError) as exc:
        raise IntakeError(f'Malformed {label}') from exc


def _external_svg_url(value: str) -> bool:
    """Linear scan without overlapping unbounded regex quantifiers."""
    lower = value.casefold()
    offset = 0
    while True:
        pos = lower.find('url(', offset)
        if pos < 0:
            return False
        i = pos + 4
        while i < len(lower) and lower[i].isspace():
            i += 1
        if i < len(lower) and lower[i] in ('"', "'"):
            i += 1
        while i < len(lower) and lower[i].isspace():
            i += 1
        if lower.startswith(('http:', 'https:', 'file:', 'ftp:', '//'), i):
            return True
        offset = pos + 4


_REQUIRED_PACKAGE_PARTS = {
    "[content_types].xml",
    "_rels/.rels",
    "ppt/presentation.xml",
    "ppt/_rels/presentation.xml.rels",
}

_FORBIDDEN_EMBEDDED_PREFIXES = (
    "ppt/activex/",
    "ppt/embeddings/",
)
_FORBIDDEN_EMBEDDED_PARTS = {
    "ppt/vbaproject.bin",
}
_FORBIDDEN_RELATIONSHIP_SUFFIXES = {
    "/oleobject",
    "/package",
    "/activexcontrol",
    "/vbaproject",
}


class IntakeError(ValueError):
    pass


@dataclass(frozen=True)
class IntakeReport:
    sha256: str
    byte_size: int
    entries: int
    uncompressed_size: int
    slide_count: int
    has_external_relationships: bool


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _relationship_source_dir(relationship_part_name: str) -> str:
    # OPC relationship parts live beside the source part under a _rels directory.
    # Example: ppt/slides/_rels/slide1.xml.rels -> source ppt/slides/slide1.xml.
    if relationship_part_name == "_rels/.rels":
        return ""
    marker = "/_rels/"
    if marker not in relationship_part_name or not relationship_part_name.endswith(".rels"):
        raise IntakeError("Malformed relationship part path")
    prefix, rel_name = relationship_part_name.rsplit(marker, 1)
    source_name = rel_name[:-5]
    return posixpath.dirname(posixpath.join(prefix, source_name))


def _validate_internal_relationship_target(target: str, relationship_part_name: str) -> str:
    raw = (target or "").strip()
    if not raw:
        raise IntakeError("PPTX contains unsafe relationship target")
    if "\\" in raw:
        raise IntakeError("PPTX contains unsafe relationship target")
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme or parsed.netloc or parsed.path.startswith("/"):
        raise IntakeError("PPTX contains unsafe relationship target")
    decoded = urllib.parse.unquote(parsed.path)
    if "\\" in decoded or decoded.startswith("/"):
        raise IntakeError("PPTX contains unsafe relationship target")
    source_dir = _relationship_source_dir(relationship_part_name)
    resolved = posixpath.normpath(posixpath.join(source_dir, decoded))
    if resolved == ".." or resolved.startswith("../") or resolved.startswith("/"):
        raise IntakeError("PPTX contains unsafe relationship target")
    return resolved


_OPC_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_SLIDE_REL_TYPE = _OFFICE_REL_NS + "/slide"


def _parse_relationships(
    data: bytes, relationship_part_name: str | None = None,
    *, known_parts: set[str] | None = None,
) -> dict[str, tuple[str, str, bool]]:
    """Parse a bounded OPC relationship part without accepting ambiguous identities.

    Other parsers may resolve duplicate relationship IDs differently. Validate
    the OPC structure before either python-pptx or LibreOffice interprets it.
    """
    try:
        root = _bounded_xml(data, label="relationship XML")
    except (ET.ParseError, IntakeError) as exc:
        raise IntakeError("Malformed relationship XML") from exc
    if root.tag != "{" + _OPC_REL_NS + "}Relationships" or root.attrib:
        raise IntakeError("Invalid OPC relationship root")
    rows: dict[str, tuple[str, str, bool]] = {}
    for elem in root:
        if elem.tag != "{" + _OPC_REL_NS + "}Relationship":
            raise IntakeError("Invalid OPC relationship element")
        if set(elem.attrib) - {"Id", "Type", "Target", "TargetMode"} or list(elem):
            raise IntakeError("Invalid OPC relationship attributes")
        rid = elem.get("Id", "")
        rel_type = elem.get("Type", "")
        target = elem.get("Target", "")
        mode = elem.get("TargetMode", "Internal")
        if (not re.fullmatch(r"(?:[^\W\d]|_)[\w.-]*", rid, re.UNICODE)
                or not rel_type or not target.strip() or mode not in {"Internal", "External"}):
            raise IntakeError("Invalid OPC relationship fields")
        if rid in rows:
            raise IntakeError("Duplicate OPC relationship ID")
        external = mode == "External"
        if not external and relationship_part_name is not None:
            resolved = _validate_internal_relationship_target(target, relationship_part_name)
            if known_parts is not None and resolved.casefold() not in known_parts:
                raise IntakeError("PPTX contains dangling internal relationship")
        rows[rid] = (rel_type, target, external)
    return rows


def _relationship_flags(
    data: bytes, relationship_part_name: str | None = None,
    *, known_parts: set[str] | None = None,
) -> tuple[bool, bool]:
    rows = _parse_relationships(data, relationship_part_name, known_parts=known_parts)
    external = any(is_external for _kind, _target, is_external in rows.values())
    forbidden_embedded = any(
        any(kind.casefold().endswith(suffix) for suffix in _FORBIDDEN_RELATIONSHIP_SUFFIXES)
        for kind, _target, _is_external in rows.values()
    )
    return external, forbidden_embedded


def _logical_slides(zf: zipfile.ZipFile, file_names: set[str]) -> int:
    """Resolve the slide list through unique, typed presentation relationships."""
    try:
        root = _bounded_xml(zf.read("ppt/presentation.xml"), label="presentation XML")
    except (KeyError, ET.ParseError, IntakeError) as exc:
        raise IntakeError("Malformed presentation slide inventory") from exc
    ns = "{" + _PRESENTATION_NS + "}"
    if root.tag != ns + "presentation":
        raise IntakeError("Invalid presentation XML root")
    slide_lists = root.findall(ns + "sldIdLst")
    if len(slide_lists) != 1:
        raise IntakeError("Presentation requires one logical slide list")
    entries = list(slide_lists[0])
    if not entries or len(entries) > MAX_SLIDES:
        raise IntakeError("Logical slide count outside processing limits")
    rels = _parse_relationships(
        zf.read("ppt/_rels/presentation.xml.rels"),
        "ppt/_rels/presentation.xml.rels", known_parts=file_names,
    )
    ids: set[str] = set()
    rids: set[str] = set()
    targets: set[str] = set()
    for slide in entries:
        if slide.tag != ns + "sldId":
            raise IntakeError("Invalid logical slide entry")
        slide_id = slide.get("id", "")
        rid = slide.get("{" + _OFFICE_REL_NS + "}id", "")
        if not slide_id.isdecimal() or int(slide_id) < 256 or not rid:
            raise IntakeError("Invalid logical slide identity")
        if str(int(slide_id)) in ids or rid in rids or rid not in rels:
            raise IntakeError("Duplicate or missing logical slide relationship")
        kind, target, external = rels[rid]
        if external or kind != _SLIDE_REL_TYPE:
            raise IntakeError("Logical slide relationship has wrong type")
        resolved = _validate_internal_relationship_target(target, "ppt/_rels/presentation.xml.rels")
        if not re.fullmatch(r"ppt/slides/slide\d+\.xml", resolved, re.IGNORECASE):
            raise IntakeError("Logical slide relationship has wrong target")
        if resolved.casefold() not in file_names or resolved.casefold() in targets:
            raise IntakeError("Missing or duplicate logical slide target")
        ids.add(str(int(slide_id)))
        rids.add(rid)
        targets.add(resolved.casefold())
    return len(entries)


def _relationship_has_external_target(data: bytes) -> bool:
    # Retained as a narrow helper for tests/compatibility.
    return _relationship_flags(data)[0]


def _canonical_package_name(info: zipfile.ZipInfo) -> str:
    raw = info.filename
    if "\\" in raw:
        raise IntakeError("Package contains non-canonical ZIP path")
    is_dir = info.is_dir()
    candidate = raw[:-1] if is_dir and raw.endswith("/") else raw
    if not candidate or candidate.startswith("/"):
        raise IntakeError("Unsafe ZIP path")
    parts = candidate.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise IntakeError("Package contains non-canonical ZIP path")
    canonical = "/".join(parts)
    if raw != canonical + ("/" if is_dir else ""):
        raise IntakeError("Package contains non-canonical ZIP path")
    return canonical


def _refuse_visual_compatibility_content(root: ET.Element) -> None:
    # python-pptx omits mc:AlternateContent from shape iteration. Preserving
    # such XML (and unchanged rendered text) does not establish visual coverage.
    # Until branch semantics are modeled, refuse every wrapper in slide/layout/
    # master parts, including hidden slides and empty/metadata-only branches.
    # The tree has already passed the existing byte/depth/element bounds.
    tag = "{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent"
    if next(root.iter(tag), None) is not None:
        raise IntakeError("Unsupported presentation compatibility content (mc:AlternateContent)")


def _count_slide_text(data: bytes) -> tuple[int, int]:
    try:
        root = _bounded_xml(data, label="slide XML")
    except (ET.ParseError, IntakeError) as e:
        raise IntakeError(f"Malformed slide XML: {e}") from e
    _refuse_visual_compatibility_content(root)
    chars = 0
    runs = 0
    for elem in root.iter():
        local = elem.tag.rsplit("}", 1)[-1].casefold()
        if local == "t" and elem.text:
            chars += len(elem.text)
        elif local == "r":
            runs += 1
    return chars, runs


def validate_pptx(path: Path) -> IntakeReport:
    if path.suffix.lower() != ".pptx":
        raise IntakeError("Only .pptx is supported")
    size = path.stat().st_size
    if size <= 0 or size > MAX_BYTES:
        raise IntakeError("File size outside processing limits")
    if not zipfile.is_zipfile(path):
        raise IntakeError("PPTX is not a valid ZIP package")

    total = 0
    external = False
    slide_count = 0
    slide_xml_total = 0
    slide_text_chars = 0
    slide_text_runs = 0
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise IntakeError("Too many package entries")
        normalized_names: set[str] = set()
        file_names: set[str] = set()
        for info in infos:
            name = _canonical_package_name(info)
            folded = name.casefold()
            if folded in normalized_names:
                raise IntakeError("Duplicate package entry")
            normalized_names.add(folded)
            if info.is_dir():
                continue
            file_names.add(folded)
            if info.compress_type not in SUPPORTED_ZIP_CODECS:
                raise IntakeError("Unsupported PPTX ZIP compression method")
            if info.flag_bits & 0x1:
                raise IntakeError("Encrypted package entries are not supported")
            if info.file_size > MAX_SINGLE_ENTRY_UNCOMPRESSED:
                raise IntakeError("Package entry exceeds processing limit")
            if info.file_size and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
                raise IntakeError("Package entry compression ratio exceeds processing limit")
            total += info.file_size
            if total > MAX_UNCOMPRESSED:
                raise IntakeError("Uncompressed package exceeds processing limits")

            if folded in _FORBIDDEN_EMBEDDED_PARTS or any(
                folded.startswith(prefix) for prefix in _FORBIDDEN_EMBEDDED_PREFIXES
            ):
                raise IntakeError("PPTX contains embedded active/package content unsupported in competition V1")

            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name, flags=re.IGNORECASE):
                slide_count += 1
                if slide_count > MAX_SLIDES:
                    raise IntakeError(f"Slide count exceeds processing limit ({MAX_SLIDES})")
                if info.file_size > MAX_SLIDE_XML_BYTES:
                    raise IntakeError("Slide XML exceeds processing limit")
                slide_xml_total += info.file_size
                if slide_xml_total > MAX_TOTAL_SLIDE_XML_BYTES:
                    raise IntakeError("Combined slide XML exceeds processing limit")

            if folded.endswith(".rels") and info.file_size > MAX_RELATIONSHIP_XML_BYTES:
                raise IntakeError("Relationship XML exceeds processing limit")

        missing = sorted(_REQUIRED_PACKAGE_PARTS - file_names)
        if missing:
            raise IntakeError(f"PPTX missing required OOXML part: {missing[0]}")

        # Validate every compressed member, not just XML we happen to read.
        # ZipFile.open() checks deflate streams and CRC at EOF. Stream in bounded
        # chunks; never materialize a whole image or 150 MB archive in RAM.
        decompressed_total = 0
        for info in infos:
            if info.is_dir():
                continue
            expanded = 0
            try:
                with zf.open(info) as member:
                    while True:
                        block = member.read(1024 * 1024)
                        if not block:
                            break
                        expanded += len(block)
                        decompressed_total += len(block)
                        if expanded > MAX_SINGLE_ENTRY_UNCOMPRESSED or decompressed_total > MAX_UNCOMPRESSED:
                            raise IntakeError('PPTX expanded payload exceeds processing limits')
            except (zipfile.BadZipFile, zlib.error, RuntimeError, EOFError, OSError, ValueError) as exc:
                raise IntakeError('PPTX contains corrupt compressed package member') from exc
        # Slide text inspection happens only after every compressed stream has
        # passed integrity verification, so a damaged slide deflate stream is
        # reported as a controlled IntakeError instead of an internal 500.
        for info in infos:
            if info.is_dir() or not re.fullmatch(r'ppt/slides/slide\d+\.xml', info.filename, flags=re.IGNORECASE):
                continue
            chars, runs = _count_slide_text(zf.read(info))
            slide_text_chars += chars
            slide_text_runs += runs
            if slide_text_chars > MAX_SLIDE_TEXT_CHARACTERS:
                raise IntakeError('Slide text character limit exceeded')
            if slide_text_runs > MAX_SLIDE_TEXT_RUNS:
                raise IntakeError('Slide text run limit exceeded')
        # Parse the mandatory OPC content-type manifest and check required
        # XML/relationship/presentation declarations before allocating state.
        ns = '{http://schemas.openxmlformats.org/package/2006/content-types}'
        try:
            raw_types = zf.read('[Content_Types].xml')
            if len(raw_types) > MAX_SLIDE_XML_BYTES:
                raise IntakeError('Content-type manifest exceeds processing limit')
            content_types_root = _bounded_xml(raw_types, label="content-type XML")
        except (KeyError, ET.ParseError, IntakeError) as exc:
            raise IntakeError('Malformed PPTX content-type manifest') from exc
        if content_types_root.tag != ns + 'Types':
            raise IntakeError('Invalid PPTX content-type manifest root')
        defaults = {}
        overrides = {}
        for item in content_types_root:
            if item.tag == ns + 'Default':
                extension, mime = item.get('Extension', '').lower(), item.get('ContentType', '')
                if not extension or not mime or extension in defaults:
                    raise IntakeError('Duplicate/invalid content-type default')
                defaults[extension] = mime
            elif item.tag == ns + 'Override':
                part, mime = item.get('PartName', ''), item.get('ContentType', '')
                if not part.startswith('/') or not mime or part.casefold() in overrides:
                    raise IntakeError('Duplicate/invalid content-type override')
                overrides[part.casefold()] = mime
            else:
                raise IntakeError('Invalid content-type manifest element')
        if defaults.get('rels') != 'application/vnd.openxmlformats-package.relationships+xml':
            raise IntakeError('Missing OPC relationships content type')
        required_types = {
            '/ppt/presentation.xml': 'application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml',
        }
        # Every slide and core PowerPoint component requires its appropriate
        # override; generic XML media-type defaults do not establish part kind.
        ooxml_parts = (
            (r'ppt/slides/slide\d+\.xml', 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml'),
            (r'ppt/slidelayouts/slidelayout\d+\.xml', 'application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml'),
            (r'ppt/slidemasters/slidemaster\d+\.xml', 'application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml'),
            (r'ppt/theme/theme\d+\.xml', 'application/vnd.openxmlformats-officedocument.theme+xml'),
        )
        for part in file_names:
            for pattern, content_type in ooxml_parts:
                if re.fullmatch(pattern, part, flags=re.IGNORECASE):
                    required_types['/' + part] = content_type
                    break
        for part, mime in required_types.items():
            if overrides.get(part) != mime:
                raise IntakeError('Missing mandatory PPTX content-type override')
        for part in overrides:
            if part[1:] not in file_names:
                raise IntakeError('Content type references missing package part')
        for name in file_names:
            if name != '[content_types].xml' and ('/' + name) not in overrides and name.rsplit('.', 1)[-1].lower() not in defaults:
                raise IntakeError('Missing package part content type')

        # A relationship may target a ZIP entry occurring later in archive order.
        # Resolve only after all canonical file names are collected.
        for info in infos:
            if info.is_dir() or not info.filename.casefold().endswith(".rels"):
                continue
            has_external, has_forbidden_embedded = _relationship_flags(
                zf.read(info), info.filename, known_parts=file_names
            )
            external = external or has_external
            if has_forbidden_embedded:
                raise IntakeError("PPTX contains embedded active/package content unsupported in competition V1")

        missing = sorted(_REQUIRED_PACKAGE_PARTS - file_names)
        if missing:
            raise IntakeError(f"PPTX missing required OOXML part: {missing[0]}")

        # The slide/layout/master/theme relationship graph can be structurally
        # valid while a referenced XML part is malformed. Parse these bounded
        # OOXML parts at intake, before allocating a durable session. Avoid
        # parsing embedded binaries or non-presentation payloads.
        inspected_xml_total = 0
        for info in infos:
            folded = info.filename.casefold()
            # OPC permits layout/master parts outside conventional directories.
            # Resolve their declared kind too, or renaming a valid part bypasses
            # the compatibility refusal. Keep the same aggregate XML budget.
            visual_part = overrides.get('/' + folded, defaults.get(folded.rsplit('.', 1)[-1])) in {
                'application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml',
                'application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml',
            }
            if not (visual_part or (folded.startswith(("ppt/slidelayouts/", "ppt/slidemasters/", "ppt/theme/"))
                    and folded.endswith(".xml"))):
                continue
            if info.file_size > MAX_SLIDE_XML_BYTES:
                raise IntakeError("Referenced presentation XML exceeds processing limit")
            inspected_xml_total += info.file_size
            if inspected_xml_total > MAX_TOTAL_SLIDE_XML_BYTES:
                raise IntakeError("Referenced presentation XML workload exceeds processing limit")
            try:
                root = _bounded_xml(zf.read(info), label="layout/master/theme XML")
            except (ET.ParseError, IntakeError) as exc:
                raise IntakeError("PPTX contains malformed layout/master/theme XML") from exc
            if visual_part or folded.startswith(("ppt/slidelayouts/", "ppt/slidemasters/")):
                _refuse_visual_compatibility_content(root)

        # Embedded SVG can contain its own URL-bearing attributes independently
        # of OOXML .rels. We never fetch external media when rendering untrusted
        # documents; refuse external references rather than attempting an SVG
        # sanitizer. This does not assert LibreOffice dereferences such URLs.
        for info in infos:
            if info.is_dir() or not info.filename.casefold().startswith('ppt/media/') or not info.filename.casefold().endswith('.svg'):
                continue
            if info.file_size > 2 * 1024 * 1024:
                raise IntakeError('Embedded SVG exceeds safe inspection size')
            try:
                svg = _bounded_xml(zf.read(info), label='SVG XML')
            except (ET.ParseError, IntakeError) as exc:
                raise IntakeError('Malformed or unsupported embedded SVG media') from exc
            inspected_text = 0
            for element in svg.iter():
                for key, value in element.attrib.items():
                    inspected_text += len(value)
                    if (len(value) > MAX_SVG_ATTRIBUTE_CHARACTERS
                            or inspected_text > MAX_SVG_TEXT_BYTES):
                        raise IntakeError('Embedded SVG text workload exceeds limits')
                    key_name = key.rsplit('}', 1)[-1].casefold()
                    trimmed = value.strip().casefold()
                    if key_name in {'href', 'src'} and trimmed.startswith(('http:', 'https:', 'file:', 'ftp:', '//')):
                        raise IntakeError('Embedded SVG contains unsupported external reference')
                    if key_name in {'style', 'filter', 'fill', 'stroke', 'clip-path', 'mask'} and _external_svg_url(value):
                        raise IntakeError('Embedded SVG contains unsupported external reference')
                if element.text:
                    inspected_text += len(element.text)
                    if inspected_text > MAX_SVG_TEXT_BYTES:
                        raise IntakeError('Embedded SVG text workload exceeds limits')
                    if element.tag.rsplit('}', 1)[-1].casefold() == 'style' and (
                        '@import' in element.text.casefold() or _external_svg_url(element.text)
                    ):
                        raise IntakeError('Embedded SVG contains unsupported external stylesheet')

        # Validate relationship *IDs referenced by document XML*, not only
        # relationship Targets. A presentation can reference rId999 even when
        # every existing .rels Target is valid; python-pptx fails later.
        for source_part in ["ppt/presentation.xml", *sorted(
            name for name in file_names if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        )]:
            source_dir, source_name = posixpath.split(source_part)
            rel_part = posixpath.join(source_dir, "_rels", source_name + ".rels")
            try:
                root = _bounded_xml(zf.read(source_part), label="document XML")
            except (KeyError, ET.ParseError) as exc:
                raise IntakeError("PPTX contains malformed referenced document XML") from exc
            referenced = {
                value for element in root.iter() for key, value in element.attrib.items()
                if key.startswith("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}")
                and key.rsplit("}", 1)[-1] in {"id", "embed", "link"}
            }
            if referenced:
                if rel_part.casefold() not in file_names:
                    raise IntakeError("PPTX missing referenced relationship part")
                try:
                    rel_root = _bounded_xml(zf.read(rel_part), label="referenced relationship XML")
                except (KeyError, ET.ParseError) as exc:
                    raise IntakeError("Malformed referenced relationships") from exc
                defined = {el.attrib.get("Id") for el in rel_root.iter()
                           if el.tag.rsplit("}", 1)[-1] == "Relationship"}
                if not referenced.issubset(defined):
                    raise IntakeError("PPTX references missing relationship ID")

        # Report the presentation's logical slides, not orphaned ZIP parts.
        # The latter are still subjected to all input-size and XML checks.
        slide_count = _logical_slides(zf, file_names)

    return IntakeReport(
        sha256=sha256_path(path),
        byte_size=size,
        entries=len(infos),
        uncompressed_size=total,
        slide_count=slide_count,
        has_external_relationships=external,
    )
