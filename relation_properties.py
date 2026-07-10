from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Sequence, Set, Tuple

from modal_model import KripkeModel, World


Pair = Tuple[World, World]


@dataclass(frozen=True)
class PropertyCheck:
    holds: bool
    title: str
    message: str


def check_reflexive(model: KripkeModel) -> PropertyCheck:
    missing = sorted(
        ((world, world) for world in model.worlds if (world, world) not in model.relation),
        key=lambda pair: pair[0].subscript,
    )
    if not missing:
        return PropertyCheck(True, "Reflexividad", "La relación es reflexiva.")

    return PropertyCheck(
        False,
        "Reflexividad",
        "La relación no es reflexiva.\n\nFaltan:\n"
        + "\n".join(f"({a},{b})" for a, b in missing),
    )


def add_reflexive(model: KripkeModel) -> KripkeModel:
    relation = set(model.relation)
    relation.update((world, world) for world in model.worlds)
    return KripkeModel(model.worlds, frozenset(relation), model.valuation)


def missing_transitive_pairs(model: KripkeModel) -> Set[Pair]:
    relation = set(model.relation)
    missing: Set[Pair] = set()
    for x, y in relation:
        for y2, z in relation:
            if y == y2 and (x, z) not in relation:
                missing.add((x, z))
    return missing


def check_transitive(model: KripkeModel) -> PropertyCheck:
    missing = sorted(
        missing_transitive_pairs(model),
        key=lambda pair: (pair[0].subscript, pair[1].subscript),
    )
    if not missing:
        return PropertyCheck(True, "Transitividad", "La relación es transitiva.")

    return PropertyCheck(
        False,
        "Transitividad",
        "La relación no es transitiva.\n\nFaltan:\n"
        + "\n".join(f"({a},{b})" for a, b in missing),
    )


def add_transitive(model: KripkeModel) -> KripkeModel:
    relation = set(model.relation)
    while True:
        additions: Set[Pair] = set()
        snapshot = set(relation)
        for x, y in snapshot:
            for y2, z in snapshot:
                if y == y2 and (x, z) not in relation:
                    additions.add((x, z))
        if not additions:
            break
        relation.update(additions)
    return KripkeModel(model.worlds, frozenset(relation), model.valuation)


def check_serial(model: KripkeModel) -> PropertyCheck:
    sources = {source for source, _ in model.relation}
    missing_worlds = sorted(
        (world for world in model.worlds if world not in sources),
        key=lambda world: world.subscript,
    )
    if not missing_worlds:
        return PropertyCheck(True, "Serialidad", "La relación es serial.")

    return PropertyCheck(
        False,
        "Serialidad",
        "La relación no es serial.\n\nMundos sin sucesores:\n"
        + "\n".join(str(world) for world in missing_worlds),
    )


def density_witness(model: KripkeModel, x: World, y: World) -> World | None:
    relation = model.relation
    for z in sorted(model.worlds, key=lambda world: world.subscript):
        if (x, z) in relation and (z, y) in relation:
            return z
    return None


def check_dense(model: KripkeModel) -> PropertyCheck:
    missing = []
    for x, y in sorted(
        model.relation,
        key=lambda pair: (pair[0].subscript, pair[1].subscript),
    ):
        if density_witness(model, x, y) is None:
            missing.append((x, y))

    if not missing:
        return PropertyCheck(True, "Densidad", "La relación es densa.")

    return PropertyCheck(
        False,
        "Densidad",
        "La relación no es densa.\n\nRelaciones sin mundo intermedio:\n"
        + "\n".join(f"({a},{b})" for a, b in missing),
    )


def missing_euclidean_pairs(model: KripkeModel) -> Set[Pair]:
    relation = set(model.relation)
    successors: Dict[World, Set[World]] = {}
    for source, target in relation:
        successors.setdefault(source, set()).add(target)

    missing: Set[Pair] = set()
    for targets in successors.values():
        for y in targets:
            for z in targets:
                if (y, z) not in relation:
                    missing.add((y, z))
    return missing


def check_euclidean(model: KripkeModel) -> PropertyCheck:
    missing = sorted(
        missing_euclidean_pairs(model),
        key=lambda pair: (pair[0].subscript, pair[1].subscript),
    )
    if not missing:
        return PropertyCheck(True, "Euclideaneidad", "La relación es euclídea.")

    return PropertyCheck(
        False,
        "Euclideaneidad",
        "La relación no es euclídea.\n\nFaltan:\n"
        + "\n".join(f"({a},{b})" for a, b in missing),
    )


def add_euclidean(model: KripkeModel) -> KripkeModel:
    relation = set(model.relation)
    while True:
        successors: Dict[World, Set[World]] = {}
        for source, target in relation:
            successors.setdefault(source, set()).add(target)

        additions: Set[Pair] = set()
        for targets in successors.values():
            for y in targets:
                for z in targets:
                    if (y, z) not in relation:
                        additions.add((y, z))

        if not additions:
            break
        relation.update(additions)

    return KripkeModel(model.worlds, frozenset(relation), model.valuation)
