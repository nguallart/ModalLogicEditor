from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QInputDialog,
    QMenu,
    QMessageBox,
)

from modal_model import KripkeModel, World, first_free_world, is_valid_world_name, normalize_world


NODE_RADIUS = 34.0
ARROW_SIZE = 10.0
MIN_ZOOM = 0.40
MAX_ZOOM = 2.50
ZOOM_STEP = 1.15



class WorldItem(QGraphicsEllipseItem):
    def __init__(self, world: World, editor: "GraphEditor") -> None:
        super().__init__(-NODE_RADIUS, -NODE_RADIUS, NODE_RADIUS * 2, NODE_RADIUS * 2)
        self.world = world
        self.editor = editor

        self.setBrush(QBrush(QColor("#f8f8f8")))
        self.setPen(QPen(QColor("#222222"), 2))
        self.setZValue(10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setAcceptedMouseButtons(
            Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton
        )

        self.label = QGraphicsTextItem(self)
        self.label.setHtml(
            f"<div style='font-size:14pt; font-weight:600;'>"
            f"w<sub>{world.subscript}</sub></div>"
        )
        self.label.setDefaultTextColor(QColor("#111111"))
        self.label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)
        self._center_label()

        self.literal_left = QGraphicsTextItem(self)
        self.literal_right = QGraphicsTextItem(self)
        for literal_item in (self.literal_left, self.literal_right):
            literal_item.setDefaultTextColor(QColor("#5a2ca0"))
            literal_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            literal_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)
            literal_item.setZValue(12)

    def _center_label(self) -> None:
        bounds = self.label.boundingRect()
        self.label.setPos(-bounds.width() / 2, -bounds.height() / 2)

    def update_literals(self, literals: list[str], visible: bool) -> None:
        midpoint = (len(literals) + 1) // 2
        left = literals[:midpoint] if len(literals) > 4 else []
        right = literals[midpoint:] if len(literals) > 4 else literals

        self.literal_left.setPlainText(", ".join(left))
        self.literal_right.setPlainText(", ".join(right))

        left_bounds = self.literal_left.boundingRect()
        right_bounds = self.literal_right.boundingRect()

        self.literal_left.setPos(
            -NODE_RADIUS - left_bounds.width() - 10,
            -left_bounds.height() / 2,
        )
        self.literal_right.setPos(
            NODE_RADIUS + 10,
            -right_bounds.height() / 2,
        )

        self.literal_left.setVisible(visible and bool(left))
        self.literal_right.setVisible(visible and bool(right))

    def set_highlighted(self, highlighted: bool) -> None:
        self.setPen(
            QPen(QColor("#d11a2a") if highlighted else QColor("#222222"),
                 3 if highlighted else 2)
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.editor.update_edges_for(self.world)
            self.editor.remember_position(self.world, value)
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        self.setFocus()

        if self.editor.pending_source is not None:
            self.editor.finish_relation(self.world)
            event.accept()
            return

        if (
            event.button() == Qt.MouseButton.RightButton
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.editor.begin_relation(self.world)
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton:
            self.editor.show_world_menu(self, event.screenPos())
            event.accept()
            return

        super().mousePressEvent(event)


class RelationItem(QGraphicsPathItem):
    def __init__(self, source: World, target: World, editor: "GraphEditor") -> None:
        super().__init__()
        self.source = source
        self.target = target
        self.editor = editor
        self.arrow_head = QGraphicsPolygonItem(self)

        self.setZValue(1)
        self.setPen(QPen(QColor("#333333"), 2))
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.arrow_head.setBrush(QBrush(QColor("#333333")))
        self.arrow_head.setPen(Qt.PenStyle.NoPen)

    def set_selected_visual(self, selected: bool) -> None:
        color = QColor("#d11a2a") if selected else QColor("#333333")
        self.setPen(QPen(color, 3 if selected else 2))
        self.arrow_head.setBrush(QBrush(color))

    def set_geometry(self, path: QPainterPath, arrow: QPolygonF) -> None:
        self.setPath(path)
        self.arrow_head.setPolygon(arrow)

    def mousePressEvent(self, event) -> None:
        self.setFocus()
        self.editor.select_relation((self.source, self.target))
        event.accept()


class GraphScene(QGraphicsScene):
    empty_clicked = Signal(QPointF)

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        if item is None:
            self.empty_clicked.emit(event.scenePos())
            event.accept()
            return
        super().mousePressEvent(event)


class GraphEditor(QGraphicsView):
    model_changed = Signal(object)
    status_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.graph_scene = GraphScene(self)
        self.setScene(self.graph_scene)

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.TextAntialiasing
        )
        self.setSceneRect(-2000, -2000, 4000, 4000)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )

        self.model: Optional[KripkeModel] = None
        self.world_items: Dict[World, WorldItem] = {}
        self.relation_items: Dict[Tuple[World, World], RelationItem] = {}
        self.positions: Dict[World, QPointF] = {}

        self.pending_source: Optional[World] = None
        self.selected_relation: Optional[Tuple[World, World]] = None
        self.zoom_factor = 1.0
        self.literals_visible = False

        self.graph_scene.empty_clicked.connect(self.handle_empty_click)

    def set_model(self, model: KripkeModel) -> None:
        old_positions = dict(self.positions)
        self.model = model
        self.pending_source = None
        self.selected_relation = None

        self.graph_scene.clear()
        self.world_items.clear()
        self.relation_items.clear()
        self.positions.clear()

        worlds = sorted(model.worlds)
        count = max(len(worlds), 1)
        radius = max(140.0, 55.0 * count)

        for index, world in enumerate(worlds):
            item = WorldItem(world, self)
            self.graph_scene.addItem(item)

            if world in old_positions:
                position = old_positions[world]
            else:
                angle = (2.0 * math.pi * index / count) - math.pi / 2
                position = QPointF(
                    radius * math.cos(angle),
                    radius * math.sin(angle),
                )

            item.setPos(position)
            self.world_items[world] = item
            self.positions[world] = position

        for source, target in sorted(
            model.relation,
            key=lambda pair: (pair[0].subscript, pair[1].subscript),
        ):
            relation_item = RelationItem(source, target, self)
            self.graph_scene.addItem(relation_item)
            self.relation_items[(source, target)] = relation_item
            self.update_relation_path(source, target)

        self.refresh_literal_labels()

        if self.world_items:
            bounds = self.graph_scene.itemsBoundingRect().adjusted(-80, -80, 80, 80)
            self.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
            self.zoom_factor = self.transform().m11()


    def export_view_state(self) -> tuple[Dict[World, tuple[float, float]], float, tuple[float, float]]:
        positions = {world: (point.x(), point.y()) for world, point in self.positions.items()}
        center = self.mapToScene(self.viewport().rect().center())
        return positions, float(self.transform().m11()), (center.x(), center.y())

    def apply_view_state(
        self,
        positions: Dict[World, tuple[float, float]],
        zoom: float | None = None,
        offset: tuple[float, float] | None = None,
    ) -> None:
        for world, coordinates in positions.items():
            item = self.world_items.get(world)
            if item is None:
                continue
            point = QPointF(float(coordinates[0]), float(coordinates[1]))
            item.setPos(point)
            self.positions[world] = point
        for source, target in self.relation_items:
            self.update_relation_path(source, target)

        if zoom is not None and zoom > 0:
            current = self.transform().m11()
            if current > 0:
                self.scale(zoom / current, zoom / current)
            self.zoom_factor = self.transform().m11()
        if offset is not None:
            self.centerOn(float(offset[0]), float(offset[1]))

    def set_literals_visible(self, visible: bool) -> None:
        self.literals_visible = visible
        self.refresh_literal_labels()
        self.status_changed.emit(
            "Literales visibles." if visible else "Literales ocultos."
        )

    def refresh_literal_labels(self) -> None:
        if self.model is None:
            return
        by_world: Dict[World, list[str]] = {world: [] for world in self.model.worlds}
        for literal, worlds in self.model.valuation.items():
            for world in worlds:
                if world in by_world:
                    by_world[world].append(literal)

        for world, item in self.world_items.items():
            item.update_literals(
                sorted(by_world.get(world, [])),
                self.literals_visible,
            )

    def zoom_in(self) -> None:
        self._apply_zoom(ZOOM_STEP)

    def zoom_out(self) -> None:
        self._apply_zoom(1.0 / ZOOM_STEP)

    def _apply_zoom(self, factor: float) -> None:
        current = self.transform().m11()
        target = current * factor
        if target < MIN_ZOOM:
            factor = MIN_ZOOM / current
        elif target > MAX_ZOOM:
            factor = MAX_ZOOM / current
        self.scale(factor, factor)
        self.zoom_factor = self.transform().m11()
        self.status_changed.emit(f"Zoom: {self.zoom_factor * 100:.0f}%")

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._apply_zoom(ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / ZOOM_STEP)
            event.accept()
            return
        super().wheelEvent(event)

    def remember_position(self, world: World, point: QPointF) -> None:
        self.positions[world] = QPointF(point)

    def show_world_menu(self, item: WorldItem, screen_pos) -> None:
        menu = QMenu(self)
        literal_action = menu.addAction("Añadir o quitar literal")
        delete_action = menu.addAction("Eliminar mundo")
        chosen = menu.exec(screen_pos)
        if chosen == literal_action:
            self.edit_literal(item.world)
        elif chosen == delete_action:
            self.delete_selected_world(item.world)

    def edit_literal(self, world: World) -> None:
        if self.model is None:
            return

        text, accepted = QInputDialog.getText(
            self,
            f"Valuación en {world}",
            "Escriba p para añadirlo o ¬p / ~p para quitarlo:",
        )
        if not accepted:
            return

        raw = text.strip().replace(" ", "")
        if not raw:
            return

        remove = raw.startswith(("~", "¬"))
        literal = raw[1:] if remove else raw

        if len(literal) != 1 or not literal.isalpha() or literal == "w":
            QMessageBox.warning(
                self,
                "Literal no válido",
                "Use una sola letra proposicional distinta de w.",
            )
            return

        valuation = dict(self.model.valuation)

        if remove:
            if literal not in valuation or world not in valuation[literal]:
                self.status_changed.emit(
                    f"{world} no satisfacía {literal}; no se ha cambiado nada."
                )
                return
            values = set(valuation[literal])
            values.discard(world)
            valuation[literal] = frozenset(values)
            message = f"Se ha quitado {literal} de {world}."
        else:
            values = set(valuation.get(literal, frozenset()))
            if world in values:
                self.status_changed.emit(
                    f"{world} ya satisfacía {literal}; no se ha cambiado nada."
                )
                return
            values.add(world)
            valuation[literal] = frozenset(values)
            message = f"Se ha añadido {literal} a {world}."

        self.model = KripkeModel(
            worlds=self.model.worlds,
            relation=self.model.relation,
            valuation=valuation,
        )
        self.refresh_literal_labels()
        self.model_changed.emit(self.model)
        self.status_changed.emit(message)

    def begin_relation(self, source: World) -> None:
        self.clear_selection_visuals()
        self.pending_source = source
        self.world_items[source].set_highlighted(True)
        self.status_changed.emit(
            f"Origen seleccionado: {source}. Pulse otro mundo para crear la relación o Esc para cancelar."
        )

    def finish_relation(self, target: World) -> None:
        if self.model is None or self.pending_source is None:
            return

        source = self.pending_source
        self.pending_source = None
        self.world_items[source].set_highlighted(False)

        pair = (source, target)
        if pair in self.model.relation:
            self.status_changed.emit(f"La relación ({source},{target}) ya existe.")
            return

        relation = set(self.model.relation)
        relation.add(pair)
        self.model = KripkeModel(
            worlds=self.model.worlds,
            relation=frozenset(relation),
            valuation=self.model.valuation,
        )

        item = RelationItem(source, target, self)
        self.graph_scene.addItem(item)
        self.relation_items[pair] = item
        self.update_relation_path(source, target)

        reverse = (target, source)
        if reverse in self.relation_items and source != target:
            self.update_relation_path(*reverse)

        self.model_changed.emit(self.model)
        self.status_changed.emit(f"Relación añadida: ({source},{target}).")

    def select_relation(self, pair: Tuple[World, World]) -> None:
        self.cancel_pending_relation()
        self.clear_relation_selection()
        self.selected_relation = pair
        self.relation_items[pair].set_selected_visual(True)
        self.status_changed.emit(
            f"Relación seleccionada: ({pair[0]},{pair[1]}). Pulse DEL para borrarla."
        )

    def clear_relation_selection(self) -> None:
        if self.selected_relation in self.relation_items:
            self.relation_items[self.selected_relation].set_selected_visual(False)
        self.selected_relation = None

    def clear_selection_visuals(self) -> None:
        self.clear_relation_selection()
        for item in self.world_items.values():
            item.set_highlighted(False)

    def cancel_pending_relation(self) -> None:
        if self.pending_source is not None:
            item = self.world_items.get(self.pending_source)
            if item:
                item.set_highlighted(False)
            self.pending_source = None

    def handle_empty_click(self, scene_position: QPointF) -> None:
        if self.pending_source is not None:
            self.cancel_pending_relation()
            self.status_changed.emit("Creación de relación cancelada.")
            return
        self.clear_relation_selection()
        self.create_world_at(scene_position)

    def create_world_at(self, scene_position: QPointF) -> None:
        if self.model is None:
            return

        text, accepted = QInputDialog.getText(
            self,
            "Nuevo mundo",
            "Nombre del mundo:",
        )
        if not accepted:
            return

        candidate = text.strip()
        existing = set(self.model.worlds)

        if not candidate or not is_valid_world_name(candidate):
            world = first_free_world(existing)
        else:
            world = normalize_world(candidate)
            if world in existing:
                world = first_free_world(existing)

        worlds = set(self.model.worlds)
        worlds.add(world)
        self.model = KripkeModel(
            worlds=frozenset(worlds),
            relation=self.model.relation,
            valuation=self.model.valuation,
        )

        item = WorldItem(world, self)
        self.graph_scene.addItem(item)
        item.setPos(scene_position)
        self.world_items[world] = item
        self.positions[world] = QPointF(scene_position)

        self.model_changed.emit(self.model)
        self.status_changed.emit(f"Mundo creado: {world}.")

    def delete_selected_world(self, world: World) -> None:
        if self.model is None:
            return

        related = [pair for pair in self.model.relation if world in pair]
        affected_literals = [
            literal for literal, values in self.model.valuation.items()
            if world in values
        ]

        details = []
        if related:
            details.append(f"{len(related)} relación(es)")
        if affected_literals:
            details.append("las valuaciones de " + ", ".join(sorted(affected_literals)))

        extra = "\n\nTambién se eliminarán " + " y ".join(details) + "." if details else ""

        answer = QMessageBox.question(
            self,
            "Eliminar mundo",
            f"¿Desea eliminar {world}?{extra}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        worlds = set(self.model.worlds)
        worlds.remove(world)
        relation = {pair for pair in self.model.relation if world not in pair}
        valuation = {
            literal: frozenset(value for value in values if value != world)
            for literal, values in self.model.valuation.items()
        }

        self.model = KripkeModel(
            worlds=frozenset(worlds),
            relation=frozenset(relation),
            valuation=valuation,
        )
        self.set_model(self.model)
        self.model_changed.emit(self.model)
        self.status_changed.emit(f"Mundo eliminado: {world}.")

    def delete_selected_relation(self) -> None:
        if self.model is None or self.selected_relation is None:
            return

        pair = self.selected_relation
        relation = set(self.model.relation)
        relation.discard(pair)
        self.model = KripkeModel(
            worlds=self.model.worlds,
            relation=frozenset(relation),
            valuation=self.model.valuation,
        )

        item = self.relation_items.pop(pair, None)
        if item:
            self.graph_scene.removeItem(item)

        self.selected_relation = None
        reverse = (pair[1], pair[0])
        if reverse in self.relation_items and pair[0] != pair[1]:
            self.update_relation_path(*reverse)

        self.model_changed.emit(self.model)
        self.status_changed.emit(f"Relación eliminada: ({pair[0]},{pair[1]}).")

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Plus:
            self.zoom_in()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Minus:
            self.zoom_out()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_pending_relation()
            self.clear_relation_selection()
            self.status_changed.emit("Selección cancelada.")
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.selected_relation is not None:
                self.delete_selected_relation()
                event.accept()
                return
            focused = self.graph_scene.focusItem()
            if isinstance(focused, WorldItem):
                self.delete_selected_world(focused.world)
                event.accept()
                return
        super().keyPressEvent(event)

    def update_edges_for(self, world: World) -> None:
        if self.model is None:
            return
        for source, target in self.model.relation:
            if source == world or target == world:
                self.update_relation_path(source, target)

    def update_relation_path(self, source: World, target: World) -> None:
        relation_item = self.relation_items.get((source, target))
        source_item = self.world_items.get(source)
        target_item = self.world_items.get(target)
        if not relation_item or not source_item or not target_item:
            return

        if source == target:
            path, arrow = self._loop_geometry(source_item.scenePos())
        else:
            reverse_exists = self.model is not None and (target, source) in self.model.relation
            path, arrow = self._arrow_geometry(
                source_item.scenePos(),
                target_item.scenePos(),
                curved=reverse_exists,
                curve_sign=1 if source.subscript < target.subscript else -1,
            )

        relation_item.set_geometry(path, arrow)

    def _arrow_geometry(
        self,
        start: QPointF,
        end: QPointF,
        curved: bool,
        curve_sign: int,
    ) -> tuple[QPainterPath, QPolygonF]:
        vector = end - start
        length = math.hypot(vector.x(), vector.y())
        if length < 1:
            return QPainterPath(), QPolygonF()

        ux = vector.x() / length
        uy = vector.y() / length
        perp = QPointF(-uy, ux)

        start_edge = start + QPointF(ux * NODE_RADIUS, uy * NODE_RADIUS)
        end_edge = end - QPointF(ux * NODE_RADIUS, uy * NODE_RADIUS)

        path = QPainterPath(start_edge)
        if curved:
            midpoint = (start_edge + end_edge) / 2
            control = midpoint + perp * (45.0 * curve_sign)
            path.quadTo(control, end_edge)
            tangent = end_edge - control
        else:
            path.lineTo(end_edge)
            tangent = end_edge - start_edge

        arrow = self._arrow_polygon(end_edge, tangent)
        return path, arrow

    def _loop_geometry(self, center: QPointF) -> tuple[QPainterPath, QPolygonF]:
        start = QPointF(center.x() - NODE_RADIUS * 0.62, center.y() - NODE_RADIUS * 0.78)
        tip = QPointF(center.x() + NODE_RADIUS * 0.62, center.y() - NODE_RADIUS * 0.78)

        control1 = QPointF(center.x() - NODE_RADIUS * 1.15, center.y() - NODE_RADIUS * 2.15)
        control2 = QPointF(center.x() + NODE_RADIUS * 1.15, center.y() - NODE_RADIUS * 2.15)

        path = QPainterPath(start)
        path.cubicTo(control1, control2, tip)

        tangent = tip - control2
        arrow = self._arrow_polygon(tip, tangent)
        return path, arrow

    @staticmethod
    def _arrow_polygon(tip: QPointF, tangent: QPointF) -> QPolygonF:
        length = max(math.hypot(tangent.x(), tangent.y()), 1.0)
        tx = tangent.x() / length
        ty = tangent.y() / length
        normal = QPointF(-ty, tx)
        base = tip - QPointF(tx * ARROW_SIZE, ty * ARROW_SIZE)
        left = base + normal * (ARROW_SIZE * 0.55)
        right = base - normal * (ARROW_SIZE * 0.55)
        return QPolygonF([tip, left, right])
