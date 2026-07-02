"""Remove a named worksheet from an .xlsx workbook using only the standard library."""

from __future__ import annotations

import argparse
import posixpath
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


DEFAULT_SHEET_NAME = "\u5185\u5bb9\u7cbe\u62c6\u8868"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
APP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", REL_NS)
ET.register_namespace("", PKG_REL_NS)
ET.register_namespace("", APP_NS)
ET.register_namespace("vt", VT_NS)
ET.register_namespace("", CONTENT_TYPES_NS)


def _q(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def _rels_path_for_part(part_path: str) -> str:
    directory = posixpath.dirname(part_path)
    filename = posixpath.basename(part_path)
    if directory:
        return posixpath.join(directory, "_rels", f"{filename}.rels")
    return posixpath.join("_rels", f"{filename}.rels")


def _resolve_target(owner_path: str, target: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(owner_path), target))


def _collect_related_parts(part_path: str, archive: dict[str, bytes], seen: set[str]) -> None:
    rels_path = _rels_path_for_part(part_path)
    if rels_path not in archive or rels_path in seen:
        return

    seen.add(rels_path)
    rels_root = ET.fromstring(archive[rels_path])
    for relationship in rels_root.findall(_q(PKG_REL_NS, "Relationship")):
        if relationship.attrib.get("TargetMode") == "External":
            continue
        target = relationship.attrib.get("Target")
        if not target:
            continue
        target_path = _resolve_target(part_path, target)
        if target_path in seen:
            continue
        seen.add(target_path)
        _collect_related_parts(target_path, archive, seen)


def _update_app_properties(xml_bytes: bytes, sheet_names: list[str]) -> bytes:
    root = ET.fromstring(xml_bytes)

    heading_pairs = root.find(_q(APP_NS, "HeadingPairs"))
    if heading_pairs is not None:
        vector = heading_pairs.find(_q(VT_NS, "vector"))
        if vector is not None:
            variants = vector.findall(_q(VT_NS, "variant"))
            if len(variants) >= 2:
                count_node = variants[1].find(_q(VT_NS, "i4"))
                if count_node is not None:
                    count_node.text = str(len(sheet_names))

    titles = root.find(_q(APP_NS, "TitlesOfParts"))
    if titles is not None:
        vector = titles.find(_q(VT_NS, "vector"))
        if vector is not None:
            vector.set("size", str(len(sheet_names)))
            for child in list(vector):
                vector.remove(child)
            for sheet_name in sheet_names:
                entry = ET.SubElement(vector, _q(VT_NS, "lpstr"))
                entry.text = sheet_name

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _update_content_types(xml_bytes: bytes, removed_parts: set[str]) -> bytes:
    if not removed_parts:
        return xml_bytes

    root = ET.fromstring(xml_bytes)
    removed_part_names = {f"/{part}" for part in removed_parts}
    for override in list(root.findall(_q(CONTENT_TYPES_NS, "Override"))):
        if override.attrib.get("PartName") in removed_part_names:
            root.remove(override)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def remove_sheet(source_path: Path, output_path: Path, sheet_name: str = DEFAULT_SHEET_NAME) -> bool:
    with zipfile.ZipFile(source_path, "r") as source_zip:
        infos = source_zip.infolist()
        archive = {info.filename: source_zip.read(info.filename) for info in infos}

    workbook_path = "xl/workbook.xml"
    workbook_rels_path = "xl/_rels/workbook.xml.rels"

    workbook_root = ET.fromstring(archive[workbook_path])
    sheets_node = workbook_root.find(_q(MAIN_NS, "sheets"))
    if sheets_node is None:
        raise ValueError("Workbook does not contain a sheets collection.")

    target_sheet = None
    for sheet in sheets_node.findall(_q(MAIN_NS, "sheet")):
        if sheet.attrib.get("name") == sheet_name:
            target_sheet = sheet
            break

    if target_sheet is None:
        if source_path.resolve() != output_path.resolve():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(source_path.read_bytes())
        return False

    remaining_sheet_names = [
        sheet.attrib.get("name", "")
        for sheet in sheets_node.findall(_q(MAIN_NS, "sheet"))
        if sheet is not target_sheet
    ]
    if not remaining_sheet_names:
        raise ValueError("Refusing to remove the only worksheet in the workbook.")

    rid = target_sheet.attrib.get(_q(REL_NS, "id"))
    sheets_node.remove(target_sheet)
    archive[workbook_path] = ET.tostring(workbook_root, encoding="utf-8", xml_declaration=True)

    removed_parts: set[str] = set()
    workbook_rels_root = ET.fromstring(archive[workbook_rels_path])
    if rid:
        for relationship in list(workbook_rels_root.findall(_q(PKG_REL_NS, "Relationship"))):
            if relationship.attrib.get("Id") != rid:
                continue
            target = relationship.attrib.get("Target")
            if target:
                worksheet_path = _resolve_target(workbook_path, target)
                removed_parts.add(worksheet_path)
                _collect_related_parts(worksheet_path, archive, removed_parts)
            workbook_rels_root.remove(relationship)
            break
    archive[workbook_rels_path] = ET.tostring(
        workbook_rels_root, encoding="utf-8", xml_declaration=True
    )

    if "docProps/app.xml" in archive:
        archive["docProps/app.xml"] = _update_app_properties(
            archive["docProps/app.xml"],
            remaining_sheet_names,
        )
    if "[Content_Types].xml" in archive:
        archive["[Content_Types].xml"] = _update_content_types(
            archive["[Content_Types].xml"],
            removed_parts,
        )

    for part in removed_parts:
        archive.pop(part, None)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as output_zip:
        for info in infos:
            data = archive.get(info.filename)
            if data is None:
                continue
            output_zip.writestr(info, data)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove a named worksheet from an .xlsx workbook."
    )
    parser.add_argument("xlsx_path", help="Source Excel workbook.")
    parser.add_argument(
        "-o",
        "--output",
        help="Output path. Defaults to in-place replacement.",
    )
    parser.add_argument(
        "--sheet-name",
        default=DEFAULT_SHEET_NAME,
        help="Worksheet name to remove. Defaults to 内容精拆表.",
    )
    args = parser.parse_args(argv)

    source_path = Path(args.xlsx_path).expanduser().resolve()
    if not source_path.is_file():
        raise SystemExit(f"[ERROR] Workbook not found: {source_path}")

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        removed = remove_sheet(source_path, output_path, args.sheet_name)
    else:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=source_path.suffix,
            dir=source_path.parent,
        ) as handle:
            temp_path = Path(handle.name)
        try:
            removed = remove_sheet(source_path, temp_path, args.sheet_name)
            if removed:
                temp_path.replace(source_path)
            else:
                temp_path.unlink(missing_ok=True)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    if removed:
        print(f"[SUCCESS] Removed worksheet: {args.sheet_name}")
    else:
        print(f"[INFO] Worksheet not found, workbook unchanged: {args.sheet_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
