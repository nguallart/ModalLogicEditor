from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, FrozenSet, List, Sequence, Tuple


class ModelParseError(ValueError):
    """Error de sintaxis o coherencia al interpretar un modelo."""


@dataclass(frozen=True, order=True)
class World:
    subscript: str

    def __post_init__(self) -> None:
        if not self.subscript:
            raise ValueError("El subíndice de un mundo no puede estar vacío.")

    @property
    def canonical(self) -> str:
        return f"w_{{{self.subscript}}}"

    @property
    def compact(self) -> str:
        return f"w{self.subscript}"

    def __str__(self) -> str:
        return self.canonical


@dataclass(frozen=True)
class KripkeModel:
    worlds: FrozenSet[World]
    relation: FrozenSet[Tuple[World, World]]
    valuation: Dict[str, FrozenSet[World]]

    def formatted_worlds(self) -> str:
        return ", ".join(str(world) for world in sorted(self.worlds))

    def formatted_relation(self) -> str:
        ordered = sorted(
            self.relation,
            key=lambda pair: (pair[0].subscript, pair[1].subscript),
        )
        return ", ".join(f"({a},{b})" for a, b in ordered)

    def formatted_valuations(self) -> str:
        lines: list[str] = []
        for literal in sorted(self.valuation):
            values = sorted(self.valuation[literal])
            if values:
                lines.append(
                    f"v({literal})={{{','.join(str(world) for world in values)}}}"
                )
            else:
                lines.append(f"v({literal})={{}}")
        return "\n".join(lines)

    def formatted(self) -> str:
        relation = self.formatted_relation()
        lines = [
            f"W = {{{self.formatted_worlds()}}}",
            f"R = {{{relation}}}" if relation else "R = ∅",
            "",
        ]
        if self.valuation:
            for line in self.formatted_valuations().splitlines():
                lines.append(line.replace("v(", "V(", 1))
        else:
            lines.append("No se ha declarado ninguna letra proposicional.")
        return "\n".join(lines)


_WORLD_RE = re.compile(
    r"""
    ^\s*
    w
    (?:
        _?\{(?P<braced>[^{}]+)\}
        |
        _?(?P<plain>[A-Za-z0-9]+)
    )
    \s*$
    """,
    re.VERBOSE,
)

_RELATION_PAIR_RE = re.compile(
    r"""
    [({]\s*
    (?P<left>w(?:_?\{[^{}]+\}|_?[A-Za-z0-9]+))
    \s*,\s*
    (?P<right>w(?:_?\{[^{}]+\}|_?[A-Za-z0-9]+))
    \s*[)}]
    """,
    re.VERBOSE,
)

_VALUATION_LINE_RE = re.compile(
    r"""
    ^\s*
    [vV]\s*\(\s*(?P<literal>[A-Za-z])\s*\)
    \s*=\s*
    (?P<container>
        \([^()]*\)
        |
        \{[^{}]*\}
    )
    \s*$
    """,
    re.VERBOSE,
)


def normalize_world(token: str) -> World:
    match = _WORLD_RE.fullmatch(token)
    if not match:
        raise ModelParseError(
            f"Nombre de mundo no válido: {token!r}. "
            "Use formas como w0, w_0 o w_{0}."
        )

    subscript = (match.group("braced") or match.group("plain")).strip()
    if not subscript:
        raise ModelParseError(f"El mundo {token!r} no tiene subíndice.")
    return World(subscript)


def is_valid_world_name(token: str) -> bool:
    try:
        normalize_world(token)
    except ModelParseError:
        return False
    return True


def _split_top_level_items(text: str) -> List[str]:
    stripped = text.strip()
    if not stripped:
        return []

    items: List[str] = []
    current: List[str] = []
    brace_depth = 0

    for char in stripped:
        if char == "{":
            brace_depth += 1
            current.append(char)
        elif char == "}":
            brace_depth -= 1
            if brace_depth < 0:
                raise ModelParseError("Hay una llave de cierre sin apertura.")
            current.append(char)
        elif brace_depth == 0 and (char == "," or char.isspace()):
            token = "".join(current).strip()
            if token:
                items.append(token)
                current.clear()
        else:
            current.append(char)

    if brace_depth != 0:
        raise ModelParseError("Hay una llave sin cerrar en los mundos.")

    token = "".join(current).strip()
    if token:
        items.append(token)

    return items


def parse_worlds(text: str) -> FrozenSet[World]:
    tokens = _split_top_level_items(text)
    if not tokens:
        raise ModelParseError("Debe declarar al menos un mundo.")

    worlds: set[World] = set()
    originals: dict[World, str] = {}

    for token in tokens:
        world = normalize_world(token)
        if world in worlds:
            raise ModelParseError(
                f"Mundo duplicado: {token!r} equivale a {originals[world]!r} "
                f"y ambos se normalizan como {world}."
            )
        worlds.add(world)
        originals[world] = token

    return frozenset(worlds)


def _ensure_only_separators(
    text: str,
    matches: Sequence[re.Match[str]],
    context: str,
) -> None:
    cursor = 0
    for match in matches:
        gap = text[cursor:match.start()]
        if gap.strip(" \t\r\n,;"):
            raise ModelParseError(
                f"Texto no reconocido en {context}: {gap.strip()!r}."
            )
        cursor = match.end()

    tail = text[cursor:]
    if tail.strip(" \t\r\n,;"):
        raise ModelParseError(
            f"Texto no reconocido en {context}: {tail.strip()!r}."
        )


def parse_relation(
    text: str,
    worlds: FrozenSet[World],
) -> FrozenSet[Tuple[World, World]]:
    if not text.strip():
        return frozenset()

    matches = list(_RELATION_PAIR_RE.finditer(text))
    if not matches:
        raise ModelParseError(
            "No se encontró ningún par de relación válido. "
            "Use, por ejemplo, (w0,w1), (w1,w2)."
        )

    _ensure_only_separators(text, matches, "la relación")
    relation: set[Tuple[World, World]] = set()

    for match in matches:
        source = normalize_world(match.group("left"))
        target = normalize_world(match.group("right"))

        missing = [world for world in (source, target) if world not in worlds]
        if missing:
            raise ModelParseError(
                "La relación menciona mundos no declarados: "
                + ", ".join(str(world) for world in missing)
                + "."
            )

        pair = (source, target)
        relation.add(pair)

    return frozenset(relation)


def _parse_world_collection(
    text: str,
    worlds: FrozenSet[World],
    context: str,
) -> FrozenSet[World]:
    inner = text[1:-1].strip()
    if not inner:
        return frozenset()

    result: set[World] = set()
    for token in _split_top_level_items(inner):
        world = normalize_world(token)
        if world not in worlds:
            raise ModelParseError(f"{context} menciona el mundo no declarado {world}.")
        result.add(world)
    return frozenset(result)


def parse_valuations(
    text: str,
    worlds: FrozenSet[World],
) -> Dict[str, FrozenSet[World]]:
    valuations: Dict[str, FrozenSet[World]] = {}

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        match = _VALUATION_LINE_RE.fullmatch(line)
        if not match:
            raise ModelParseError(
                f"Valuación no válida en la línea {line_number}: {line!r}. "
                "Use, por ejemplo, v(p)={w0,w1} o v(r)={}"
            )

        literal = match.group("literal")
        if literal == "T":
            raise ModelParseError(
                f"La letra 'T' está reservada para la tautología (línea {line_number})."
            )
        if literal == "w":
            raise ModelParseError(
                f"La letra 'w' no puede usarse como literal (línea {line_number})."
            )
        if literal in valuations:
            raise ModelParseError(f"La letra {literal!r} tiene más de una valuación.")

        valuations[literal] = _parse_world_collection(
            match.group("container"),
            worlds,
            context=f"V({literal})",
        )

    return valuations


def parse_model(
    worlds_text: str,
    relation_text: str,
    valuations_text: str,
) -> KripkeModel:
    worlds = parse_worlds(worlds_text)
    relation = parse_relation(relation_text, worlds)
    valuation = parse_valuations(valuations_text, worlds)
    return KripkeModel(worlds, relation, valuation)


def first_free_world(existing: FrozenSet[World] | set[World]) -> World:
    index = 0
    while World(str(index)) in existing:
        index += 1
    return World(str(index))
