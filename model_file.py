from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, Tuple

from modal_model import KripkeModel, ModelParseError, World, normalize_world


@dataclass(frozen=True)
class LoadedModelFile:
    model: KripkeModel
    positions: Dict[World, Tuple[float, float]]
    zoom: float | None = None
    offset: Tuple[float, float] | None = None


class ModelFileError(ValueError):
    def __init__(self, errors: Iterable[str]):
        self.errors = list(errors)
        super().__init__("\n\n".join(self.errors))


_HEADER_RE = re.compile(r"^MODALLOGIC\s+(?P<version>\d+)\s*$", re.I)
_W_RE = re.compile(r"^W\s*=\s*\{(?P<body>.*)\}\s*$", re.I)
_R_START_RE = re.compile(r"^R\s*=\s*\{(?P<body>.*)$", re.I)
_VAL_RE = re.compile(r"^[vV]\s*\(\s*(?P<atom>[A-Za-z])\s*\)\s*=\s*\{(?P<body>.*)\}\s*$")
_LAYOUT_RE = re.compile(
    r"^layout\s*\(\s*(?P<world>[^)]+)\s*\)\s*=\s*\(\s*"
    r"(?P<x>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*"
    r"(?P<y>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*\)\s*$",
    re.I,
)
_ZOOM_RE = re.compile(r"^zoom\s*=\s*(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$", re.I)
_OFFSET_RE = re.compile(
    r"^offset\s*=\s*\(\s*(?P<x>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*"
    r"(?P<y>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*\)\s*$",
    re.I,
)
_PAIR_RE = re.compile(r"\(\s*([^,()]+)\s*,\s*([^,()]+)\s*\)")


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def _split_names(body: str) -> list[str]:
    return [part.strip() for part in body.split(",") if part.strip()]


def parse_modallogic(text: str) -> LoadedModelFile:
    errors: list[str] = []
    lines = text.splitlines()
    significant = [(i + 1, _strip_comment(line)) for i, line in enumerate(lines)]
    significant = [(n, line) for n, line in significant if line]

    if not significant:
        raise ModelFileError(["El archivo está vacío."])

    header_line, header = significant[0]
    match = _HEADER_RE.fullmatch(header)
    if not match:
        errors.append(f"Línea {header_line}: falta la cabecera 'MODALLOGIC 1'.")
    elif match.group("version") != "1":
        errors.append(f"Línea {header_line}: versión no compatible: {match.group('version')}.")

    world_entries: list[tuple[int, str]] = []
    relation_entries: list[tuple[int, str, str]] = []
    valuation_entries: list[tuple[int, str, list[str]]] = []
    layout_entries: list[tuple[int, str, float, float]] = []
    zoom: float | None = None
    offset: tuple[float, float] | None = None
    seen_w = 0
    seen_r = 0

    index = 1
    while index < len(significant):
        line_number, line = significant[index]
        w_match = _W_RE.fullmatch(line)
        if w_match:
            seen_w += 1
            world_entries.extend((line_number, name) for name in _split_names(w_match.group("body")))
            index += 1
            continue

        r_match = _R_START_RE.fullmatch(line)
        if r_match:
            seen_r += 1
            body_parts = [r_match.group("body")]
            while "}" not in body_parts[-1] and index + 1 < len(significant):
                index += 1
                body_parts.append(significant[index][1])
            joined = " ".join(body_parts)
            if "}" not in joined:
                errors.append(f"Línea {line_number}: falta cerrar la declaración de R con '}}'.")
            else:
                body = joined.split("}", 1)[0]
                matches = list(_PAIR_RE.finditer(body))
                leftovers = _PAIR_RE.sub("", body).strip(" ,;\t")
                if leftovers:
                    errors.append(f"Línea {line_number}: contenido no válido en R: {leftovers!r}.")
                for pair in matches:
                    relation_entries.append((line_number, pair.group(1).strip(), pair.group(2).strip()))
            index += 1
            continue

        val_match = _VAL_RE.fullmatch(line)
        if val_match:
            atom = val_match.group("atom")
            valuation_entries.append((line_number, atom, _split_names(val_match.group("body"))))
            index += 1
            continue

        layout_match = _LAYOUT_RE.fullmatch(line)
        if layout_match:
            layout_entries.append((
                line_number,
                layout_match.group("world").strip(),
                float(layout_match.group("x")),
                float(layout_match.group("y")),
            ))
            index += 1
            continue

        zoom_match = _ZOOM_RE.fullmatch(line)
        if zoom_match:
            if zoom is not None:
                errors.append(f"Línea {line_number}: zoom está declarado más de una vez.")
            zoom = float(zoom_match.group("value"))
            if zoom <= 0:
                errors.append(f"Línea {line_number}: zoom debe ser mayor que cero.")
            index += 1
            continue

        offset_match = _OFFSET_RE.fullmatch(line)
        if offset_match:
            if offset is not None:
                errors.append(f"Línea {line_number}: offset está declarado más de una vez.")
            offset = (float(offset_match.group("x")), float(offset_match.group("y")))
            index += 1
            continue

        errors.append(f"Línea {line_number}: contenido no reconocido: {line!r}.")
        index += 1

    if seen_w != 1:
        errors.append("Debe existir exactamente una declaración de W.")
    if seen_r != 1:
        errors.append("Debe existir exactamente una declaración de R.")
    if not world_entries:
        errors.append("W no puede ser vacío.")

    worlds: set[World] = set()
    for line_number, raw in world_entries:
        try:
            world = normalize_world(raw)
        except ModelParseError as exc:
            errors.append(f"Línea {line_number}: {exc}")
            continue
        if world in worlds:
            errors.append(f"Línea {line_number}: mundo duplicado: {world}.")
        worlds.add(world)

    relation: set[tuple[World, World]] = set()
    for line_number, left_raw, right_raw in relation_entries:
        try:
            left = normalize_world(left_raw)
            right = normalize_world(right_raw)
        except ModelParseError as exc:
            errors.append(f"Línea {line_number}: {exc}")
            continue
        missing = [str(w) for w in (left, right) if w not in worlds]
        if missing:
            errors.append(f"Línea {line_number}: R usa mundo(s) no declarado(s): {', '.join(missing)}.")
            continue
        relation.add((left, right))

    valuations: dict[str, frozenset[World]] = {}
    for line_number, atom, names in valuation_entries:
        if atom == "T":
            errors.append(f"Línea {line_number}: T es una constante lógica reservada y no puede aparecer en v(T).")
            continue
        if atom in valuations:
            errors.append(f"Línea {line_number}: v({atom}) está declarada más de una vez.")
            continue
        values: set[World] = set()
        for raw in names:
            try:
                world = normalize_world(raw)
            except ModelParseError as exc:
                errors.append(f"Línea {line_number}: {exc}")
                continue
            if world not in worlds:
                errors.append(f"Línea {line_number}: v({atom}) usa el mundo no declarado {world}.")
                continue
            values.add(world)
        valuations[atom] = frozenset(values)

    positions: dict[World, tuple[float, float]] = {}
    for line_number, raw, x, y in layout_entries:
        try:
            world = normalize_world(raw)
        except ModelParseError as exc:
            errors.append(f"Línea {line_number}: {exc}")
            continue
        if world not in worlds:
            errors.append(f"Línea {line_number}: layout usa el mundo no declarado {world}.")
            continue
        if world in positions:
            errors.append(f"Línea {line_number}: layout({world}) está declarado más de una vez.")
            continue
        positions[world] = (x, y)

    if errors:
        raise ModelFileError(errors)

    model = KripkeModel(frozenset(worlds), frozenset(relation), valuations)
    return LoadedModelFile(model=model, positions=positions, zoom=zoom, offset=offset)


def serialize_modallogic(
    model: KripkeModel,
    positions: Dict[World, Tuple[float, float]],
    zoom: float | None = None,
    offset: Tuple[float, float] | None = None,
) -> str:
    worlds = sorted(model.worlds)
    lines = ["MODALLOGIC 1", "", "# Mundos", "W = {" + ", ".join(w.compact for w in worlds) + "}", "", "# Relación de accesibilidad", "R = {"]
    ordered_relation = sorted(model.relation, key=lambda pair: (pair[0].subscript, pair[1].subscript))
    for index, (source, target) in enumerate(ordered_relation):
        comma = "," if index < len(ordered_relation) - 1 else ""
        lines.append(f"  ({source.compact}, {target.compact}){comma}")
    lines.extend(["}", "", "# Valoraciones"])
    for atom in sorted(model.valuation):
        values = ", ".join(w.compact for w in sorted(model.valuation[atom]))
        lines.append(f"v({atom}) = {{{values}}}")
    lines.extend(["", "# Disposición visual"])
    for world in worlds:
        if world in positions:
            x, y = positions[world]
            lines.append(f"layout({world.compact}) = ({x:.3f}, {y:.3f})")
    if zoom is not None:
        lines.append(f"zoom = {zoom:.6f}")
    if offset is not None:
        lines.append(f"offset = ({offset[0]:.3f}, {offset[1]:.3f})")
    return "\n".join(lines).rstrip() + "\n"
