from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from modal_model import KripkeModel, ModelParseError, World, normalize_world


class FormulaSyntaxError(ValueError):
    pass


@dataclass(frozen=True)
class Formula:
    kind: str
    left: Optional["Formula"] = None
    right: Optional["Formula"] = None
    atom: Optional[str] = None


@dataclass(frozen=True)
class EvaluationRequest:
    world: Optional[World]
    formula: Formula

    @property
    def is_global(self) -> bool:
        return self.world is None


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    position: int


TOKEN_SPECS = (
    ("IFF", "<->"),
    ("IMPLIES", "->"),
    ("MODELS", "|="),
    ("BOX", "[]"),
    ("DIAMOND", "<>"),
    ("NOT", "¬"),
    ("NOT", "~"),
    ("NOT", "!"),
    ("AND", "&"),
    ("AND", "∧"),
    ("OR", "|"),
    ("OR", "∨"),
    ("LPAREN", "("),
    ("RPAREN", ")"),
    ("COMMA", ","),
)


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0

    while index < len(text):
        char = text[index]

        if char.isspace():
            index += 1
            continue

        matched = False
        for kind, symbol in TOKEN_SPECS:
            if text.startswith(symbol, index):
                tokens.append(Token(kind, symbol, index))
                index += len(symbol)
                matched = True
                break
        if matched:
            continue

        if char == "T":
            tokens.append(Token("TOP", char, index))
            index += 1
            continue

        if char == "M":
            tokens.append(Token("MODEL", char, index))
            index += 1
            continue

        if char == "v":
            before_ok = index == 0 or text[index - 1].isspace() or text[index - 1] == ")"
            after_ok = index + 1 == len(text) or text[index + 1].isspace() or text[index + 1] == "("
            if before_ok and after_ok:
                tokens.append(Token("OR", char, index))
                index += 1
                continue

        if char.isalpha():
            if char == "w":
                end = index + 1
                if end < len(text) and text[end] == "_":
                    end += 1
                if end < len(text) and text[end] == "{":
                    close = text.find("}", end + 1)
                    if close == -1:
                        raise FormulaSyntaxError("Falta cerrar una llave en el nombre del mundo.")
                    end = close + 1
                else:
                    while end < len(text) and text[end].isalnum():
                        end += 1
                tokens.append(Token("WORLD", text[index:end], index))
                index = end
                continue

            if len(char) == 1:
                tokens.append(Token("ATOM", char, index))
                index += 1
                continue

        raise FormulaSyntaxError(
            f"Símbolo no reconocido en la posición {index + 1}: {char!r}."
        )

    tokens.append(Token("EOF", "", len(text)))
    return tokens


class FormulaParser:
    def __init__(self, text: str):
        self.tokens = tokenize(text)
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def advance(self) -> Token:
        token = self.current
        self.index += 1
        return token

    def accept(self, kind: str) -> bool:
        if self.current.kind == kind:
            self.advance()
            return True
        return False

    def expect(self, kind: str, message: str) -> Token:
        if self.current.kind != kind:
            raise FormulaSyntaxError(message)
        return self.advance()

    def parse_request(self) -> EvaluationRequest:
        world: Optional[World] = None

        if self.accept("MODEL"):
            if self.accept("COMMA"):
                world_token = self.expect(
                    "WORLD",
                    "Después de 'M,' debe aparecer un mundo.",
                )
                try:
                    world = normalize_world(world_token.text)
                except ModelParseError as exc:
                    raise FormulaSyntaxError(str(exc)) from exc
            self.expect("MODELS", "Falta el símbolo '|='.")
        elif self.current.kind == "WORLD":
            world_token = self.advance()
            try:
                world = normalize_world(world_token.text)
            except ModelParseError as exc:
                raise FormulaSyntaxError(str(exc)) from exc
            self.expect("MODELS", "Falta el símbolo '|=' después del mundo.")
        elif self.accept("MODELS"):
            world = None
        else:
            raise FormulaSyntaxError(
                "La línea debe comenzar por 'M,w0 |=', 'w0 |=' o '|='."
            )

        formula = self.parse_iff()
        self.expect("EOF", "Hay texto sobrante después de la fórmula.")
        return EvaluationRequest(world=world, formula=formula)

    def parse_iff(self) -> Formula:
        left = self.parse_implies()
        if self.accept("IFF"):
            right = self.parse_implies()
            if self.current.kind == "IFF":
                raise FormulaSyntaxError(
                    "No encadene bicondicionales sin paréntesis."
                )
            return Formula("iff", left, right)
        return left

    def parse_implies(self) -> Formula:
        left = self.parse_or()
        if self.accept("IMPLIES"):
            right = self.parse_implies()
            return Formula("implies", left, right)
        return left

    def parse_or(self) -> Formula:
        formula = self.parse_and()
        while self.accept("OR"):
            formula = Formula("or", formula, self.parse_and())
        return formula

    def parse_and(self) -> Formula:
        formula = self.parse_unary()
        while self.accept("AND"):
            formula = Formula("and", formula, self.parse_unary())
        return formula

    def parse_unary(self) -> Formula:
        if self.accept("NOT"):
            return Formula("not", left=self.parse_unary())
        if self.accept("BOX"):
            return Formula("box", left=self.parse_unary())
        if self.accept("DIAMOND"):
            return Formula("diamond", left=self.parse_unary())
        if self.accept("LPAREN"):
            formula = self.parse_iff()
            self.expect("RPAREN", "Falta un paréntesis de cierre.")
            return formula
        if self.accept("TOP"):
            return Formula("top")
        if self.current.kind == "ATOM":
            atom = self.advance().text
            if atom == "w":
                raise FormulaSyntaxError("'w' está reservada para los mundos.")
            return Formula("atom", atom=atom)

        raise FormulaSyntaxError(
            f"Se esperaba una fórmula en la posición {self.current.position + 1}."
        )


def parse_evaluation_request(text: str) -> EvaluationRequest:
    return FormulaParser(text).parse_request()


_PRECEDENCE = {
    "iff": 1,
    "implies": 2,
    "or": 3,
    "and": 4,
    "not": 5,
    "box": 5,
    "diamond": 5,
    "atom": 6,
    "top": 6,
}


def format_formula(formula: Formula, parent_precedence: int = 0) -> str:
    kind = formula.kind
    precedence = _PRECEDENCE[kind]

    if kind == "atom":
        result = formula.atom or ""
    elif kind == "top":
        result = "T"
    elif kind == "not":
        result = "¬" + format_formula(formula.left, precedence)
    elif kind == "box":
        result = "□" + format_formula(formula.left, precedence)
    elif kind == "diamond":
        result = "◇" + format_formula(formula.left, precedence)
    elif kind == "and":
        result = (
            format_formula(formula.left, precedence)
            + " ∧ "
            + format_formula(formula.right, precedence + 1)
        )
    elif kind == "or":
        result = (
            format_formula(formula.left, precedence)
            + " ∨ "
            + format_formula(formula.right, precedence + 1)
        )
    elif kind == "implies":
        result = (
            format_formula(formula.left, precedence + 1)
            + " → "
            + format_formula(formula.right, precedence)
        )
    elif kind == "iff":
        result = (
            format_formula(formula.left, precedence + 1)
            + " ↔ "
            + format_formula(formula.right, precedence + 1)
        )
    else:
        raise ValueError(f"Tipo de fórmula desconocido: {kind}")

    if precedence < parent_precedence:
        return f"({result})"
    return result


def format_world_rich(world: World) -> str:
    return f"w<sub>{world.subscript}</sub>"


def format_request_html(request: EvaluationRequest) -> str:
    formula_text = format_formula(request.formula)
    if request.world is None:
        return f"M ⊨ {formula_text}"
    return f"M,{format_world_rich(request.world)} ⊨ {formula_text}"


def satisfies(model: KripkeModel, world: World, formula: Formula) -> bool:
    kind = formula.kind

    if kind == "top":
        return True

    if kind == "atom":
        return world in model.valuation.get(formula.atom or "", frozenset())

    if kind == "not":
        return not satisfies(model, world, formula.left)

    if kind == "and":
        return satisfies(model, world, formula.left) and satisfies(
            model, world, formula.right
        )

    if kind == "or":
        return satisfies(model, world, formula.left) or satisfies(
            model, world, formula.right
        )

    if kind == "implies":
        return (not satisfies(model, world, formula.left)) or satisfies(
            model, world, formula.right
        )

    if kind == "iff":
        return satisfies(model, world, formula.left) == satisfies(
            model, world, formula.right
        )

    successors = [
        target for source, target in model.relation
        if source == world
    ]

    if kind == "box":
        return all(satisfies(model, target, formula.left) for target in successors)

    if kind == "diamond":
        return any(satisfies(model, target, formula.left) for target in successors)

    raise ValueError(f"Tipo de fórmula desconocido: {kind}")


def evaluate_request(model: KripkeModel, request: EvaluationRequest) -> bool:
    if request.world is not None:
        if request.world not in model.worlds:
            raise FormulaSyntaxError(
                f"El mundo {request.world} no pertenece al modelo."
            )
        return satisfies(model, request.world, request.formula)

    return all(satisfies(model, world, request.formula) for world in model.worlds)
