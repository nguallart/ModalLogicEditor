from __future__ import annotations

import html
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QTextBrowser,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from formula_logic import (
    FormulaSyntaxError,
    evaluate_request,
    format_request_html,
    parse_evaluation_request,
)
from graphics_editor import GraphEditor
from modal_model import KripkeModel, ModelParseError, parse_model
from model_file import ModelFileError, parse_modallogic, serialize_modallogic
from relation_properties import (
    add_euclidean,
    add_reflexive,
    add_transitive,
    check_dense,
    check_euclidean,
    check_reflexive,
    check_serial,
    check_transitive,
)


class ModelEditorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Editor didáctico de modelos de Kripke")
        self.resize(1450, 900)
        self.current_model: KripkeModel | None = None
        self._setup_menus()

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        title = QLabel("Editor de modelos de Kripke")
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        main_layout.addWidget(title)

        subtitle = QLabel(
            "Edite el modelo mediante texto o gráficamente y evalúe fórmulas modales."
        )
        subtitle.setWordWrap(True)
        main_layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 6, 0)

        self.worlds_edit = self._make_editor(82)
        left_layout.addWidget(
            self._make_group(
                "Mundos",
                "Ejemplo: w0, w_1, w_{2}, w_origen",
                self.worlds_edit,
            )
        )

        self.relation_edit = self._make_editor(82)
        left_layout.addWidget(
            self._make_group(
                "Relación R",
                "Ejemplo: (w0,w1), (w1,w2)",
                self.relation_edit,
            )
        )

        self.valuations_edit = self._make_editor(100)
        left_layout.addWidget(
            self._make_group(
                "Valuaciones",
                "Una por línea: v(p)={w0,w1}; v(r)={}",
                self.valuations_edit,
            )
        )

        buttons = QHBoxLayout()
        clear_button = QPushButton("Limpiar")
        clear_button.clicked.connect(self.clear_model)
        buttons.addWidget(clear_button)

        example_button = QPushButton("Cargar ejemplo")
        example_button.clicked.connect(self.load_example)
        buttons.addWidget(example_button)

        validate_button = QPushButton("Validar y dibujar")
        validate_button.setDefault(True)
        validate_button.clicked.connect(self.validate_and_draw)
        buttons.addWidget(validate_button)
        left_layout.addLayout(buttons)

        self.summary_edit = QPlainTextEdit()
        self.summary_edit.setReadOnly(True)
        self.summary_edit.setMaximumHeight(145)
        left_layout.addWidget(
            self._make_group(
                "Modelo normalizado",
                "Resumen del último modelo válido.",
                self.summary_edit,
            )
        )

        self.formulas_edit = self._make_editor(140)
        self.formulas_edit.setPlaceholderText(
            "M,w_0 |= p&q\n"
            "w_1 |= []p -> <>q\n"
            "|= p | ~p"
        )
        left_layout.addWidget(
            self._make_group(
                "Fórmulas",
                "Una consulta por línea. Use &, | o v, ->, <->, [], <> y ~ o ¬.",
                self.formulas_edit,
            )
        )

        evaluate_button = QPushButton("Evaluar fórmulas")
        evaluate_button.clicked.connect(self.evaluate_formulas)
        left_layout.addWidget(evaluate_button)

        self.results_widget = QWidget()
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.addStretch(1)

        results_scroll = QScrollArea()
        results_scroll.setWidgetResizable(True)
        results_scroll.setMinimumHeight(180)
        results_scroll.setWidget(self.results_widget)

        left_layout.addWidget(
            self._make_group(
                "Resultados",
                "✓ verdadero, ✗ falso y ⚠ error sintáctico.",
                results_scroll,
            )
        )

        left_scroll.setWidget(left_panel)
        splitter.addWidget(left_scroll)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 0, 0, 0)

        toolbar = QHBoxLayout()
        help_label = QLabel(
            "Clic vacío: crear mundo · Arrastrar: mover · "
            "Ctrl + botón derecho: iniciar relación · "
            "Botón derecho: literales · DEL: borrar · Esc: cancelar"
        )
        help_label.setWordWrap(True)
        toolbar.addWidget(help_label, 1)

        zoom_out = QPushButton("−")
        zoom_out.setToolTip("Alejar")
        zoom_out.clicked.connect(self.zoom_out)
        toolbar.addWidget(zoom_out)

        zoom_in = QPushButton("+")
        zoom_in.setToolTip("Acercar")
        zoom_in.clicked.connect(self.zoom_in)
        toolbar.addWidget(zoom_in)

        right_layout.addLayout(toolbar)

        self.graph_editor = GraphEditor()
        self.graph_editor.model_changed.connect(self.sync_text_from_graph)
        self.graph_editor.status_changed.connect(self.set_status)
        right_layout.addWidget(self.graph_editor, 1)

        splitter.addWidget(right_panel)
        splitter.setSizes([560, 890])

        self.status_label = QLabel("Listo.")
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        self.load_example()
        self.validate_and_draw()

    @staticmethod
    def _make_editor(minimum_height: int) -> QPlainTextEdit:
        editor = QPlainTextEdit()
        editor.setMinimumHeight(minimum_height)
        editor.setTabChangesFocus(True)
        return editor

    @staticmethod
    def _make_group(title: str, help_text: str, widget) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        help_label = QLabel(help_text)
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(help_label)
        layout.addWidget(widget)
        return group


    def _setup_menus(self) -> None:
        file_menu = self.menuBar().addMenu("Archivo")

        load_action = QAction("Cargar modelo…", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self.load_model_file)
        file_menu.addAction(load_action)

        save_action = QAction("Guardar modelo…", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_model_file)
        file_menu.addAction(save_action)

        window_menu = self.menuBar().addMenu("Ventana")
        self.literals_action = QAction("Literales visibles", self)
        self.literals_action.setCheckable(True)
        self.literals_action.setChecked(False)
        self.literals_action.toggled.connect(self.toggle_literals_visible)
        window_menu.addAction(self.literals_action)

        frames_menu = self.menuBar().addMenu("Marcos")
        check_menu = frames_menu.addMenu("Comprobar")
        add_menu = frames_menu.addMenu("Añadir")

        checks = [
            ("Reflexividad", check_reflexive),
            ("Transitividad", check_transitive),
            ("Serialidad", check_serial),
            ("Densidad", check_dense),
            ("Euclideaneidad", check_euclidean),
        ]
        for label, function in checks:
            action = QAction(label, self)
            action.triggered.connect(
                lambda checked=False, fn=function: self.run_property_check(fn)
            )
            check_menu.addAction(action)

        additions = [
            ("Reflexividad", add_reflexive),
            ("Transitividad", add_transitive),
            ("Euclideaneidad", add_euclidean),
        ]
        for label, function in additions:
            action = QAction(label, self)
            action.triggered.connect(
                lambda checked=False, fn=function, name=label: self.run_property_add(fn, name)
            )
            add_menu.addAction(action)

        frames_menu.addSeparator()
        definitions_action = QAction("Definiciones…", self)
        definitions_action.triggered.connect(self.show_frame_definitions)
        frames_menu.addAction(definitions_action)

    def save_model_file(self) -> None:
        self.validate_and_draw()
        if self.current_model is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar modelo",
            "modelo.modallogic",
            "Modelos de lógica modal (*.modallogic)",
        )
        if not filename:
            return
        if not filename.lower().endswith(".modallogic"):
            filename += ".modallogic"
        positions, zoom, offset = self.graph_editor.export_view_state()
        try:
            with open(filename, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(serialize_modallogic(self.current_model, positions, zoom, offset))
        except OSError as exc:
            QMessageBox.critical(self, "No se pudo guardar", str(exc))
            return
        self.set_status(f"Modelo guardado en {filename}.")

    def load_model_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Cargar modelo",
            "",
            "Modelos de lógica modal (*.modallogic);;Todos los archivos (*)",
        )
        if not filename:
            return
        try:
            with open(filename, "r", encoding="utf-8") as handle:
                loaded = parse_modallogic(handle.read())
        except UnicodeDecodeError:
            QMessageBox.critical(self, "Archivo no válido", "El archivo no está codificado en UTF-8.")
            return
        except OSError as exc:
            QMessageBox.critical(self, "No se pudo cargar", str(exc))
            return
        except ModelFileError as exc:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("Archivo no válido")
            box.setText(f"Se encontraron {len(exc.errors)} error(es).")
            box.setDetailedText("\n\n".join(exc.errors))
            box.exec()
            return

        self.current_model = loaded.model
        self.sync_text_from_graph(loaded.model)
        self.graph_editor.set_model(loaded.model)
        self.graph_editor.apply_view_state(loaded.positions, loaded.zoom, loaded.offset)
        self.graph_editor.set_literals_visible(self.literals_action.isChecked())
        self.summary_edit.setPlainText(loaded.model.formatted())
        self.set_status(f"Modelo cargado desde {filename}.")

    def show_frame_definitions(self) -> None:
        definitions = [
            ("Reflexividad", "[]p -> p", "∀x (xRx)", "Un marco es reflexivo cuando todo mundo es accesible desde sí mismo."),
            ("Irreflexividad", "No definible en lógica modal básica", "∀x ¬xRx", "Un marco es irreflexivo cuando ningún mundo es accesible desde sí mismo."),
            ("Serialidad", "[]p -> <>p", "∀x ∃y (xRy)", "Un marco es serial cuando cada mundo tiene al menos un sucesor."),
            ("Simetría", "p -> []<>p", "∀x∀y (xRy -> yRx)", "Un marco es simétrico cuando toda flecha puede recorrerse también en sentido contrario."),
            ("Transitividad", "[]p -> [][]p", "∀x∀y∀z ((xRy ∧ yRz) -> xRz)", "Un marco es transitivo cuando todo camino de dos pasos dispone también de una flecha directa entre sus extremos."),
            ("Euclideaneidad", "<>p -> []<>p", "∀x∀y∀z ((xRy ∧ xRz) -> yRz)", "Un marco es euclídeo cuando dos sucesores de un mismo mundo quedan relacionados entre sí en la dirección indicada."),
            ("Densidad", "[][]p -> []p", "∀x∀z (xRz -> ∃y (xRy ∧ yRz))", "Un marco es denso cuando cada flecha puede descomponerse en dos pasos mediante algún mundo intermedio."),
            ("Funcionalidad", "<>p -> []p", "∀x∀y∀z ((xRy ∧ xRz) -> y=z)", "Un marco es funcional cuando cada mundo tiene como máximo un sucesor."),
            ("Convergencia", "<>[]p -> []<>p", "∀x∀y∀z ((xRy ∧ xRz) -> ∃u (yRu ∧ zRu))", "Un marco es convergente cuando dos caminos que salen del mismo mundo pueden volver a encontrarse."),
        ]

        dialog = QDialog(self)
        dialog.setWindowTitle("Definiciones de marcos")
        dialog.resize(760, 480)
        layout = QVBoxLayout(dialog)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        names = QListWidget()
        browser = QTextBrowser()
        splitter.addWidget(names)
        splitter.addWidget(browser)
        splitter.setSizes([220, 540])
        layout.addWidget(splitter, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        for name, *_ in definitions:
            names.addItem(name)

        def show_definition(row: int) -> None:
            if row < 0:
                return
            name, formula, condition, explanation = definitions[row]
            browser.setHtml(
                f"<h2>{html.escape(name)}</h2>"
                f"<h3>Fórmula modal característica</h3><p><code>{html.escape(formula)}</code></p>"
                f"<h3>Condición sobre R</h3><p><code>{html.escape(condition)}</code></p>"
                f"<h3>Definición</h3><p>{html.escape(explanation)}</p>"
                "<p><i>La fórmula caracteriza a los marcos en los que es válida para toda valoración.</i></p>"
            )

        names.currentRowChanged.connect(show_definition)
        names.setCurrentRow(0)
        dialog.exec()

    def toggle_literals_visible(self, checked: bool) -> None:
        if hasattr(self, "graph_editor"):
            self.graph_editor.set_literals_visible(checked)

    def run_property_check(self, function) -> None:
        if self.current_model is None:
            self.validate_and_draw()
        if self.current_model is None:
            return

        result = function(self.current_model)
        icon = (
            QMessageBox.Icon.Information
            if result.holds
            else QMessageBox.Icon.Warning
        )
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(result.title)
        box.setText(result.message)
        box.exec()

    def run_property_add(self, function, name: str) -> None:
        if self.current_model is None:
            self.validate_and_draw()
        if self.current_model is None:
            return

        updated = function(self.current_model)
        added_count = len(updated.relation) - len(self.current_model.relation)
        self.current_model = updated
        self.graph_editor.set_model(updated)
        self.sync_text_from_graph(updated)

        QMessageBox.information(
            self,
            f"Añadir {name.lower()}",
            f"Se han añadido {added_count} relación(es)."
            if added_count
            else f"La relación ya cumplía {name.lower()}.",
        )

    def load_example(self) -> None:
        self.worlds_edit.setPlainText("w0, w_1, w_{2}, w_origen")
        self.relation_edit.setPlainText(
            "(w0,w_1), (w_1,w_{2}), (w_{2},w_{2}), {w_origen,w0}"
        )
        self.valuations_edit.setPlainText(
            "v(p)={w0,w_1}\n"
            "v(q)=(w_{2})\n"
            "v(r)={}"
        )
        self.formulas_edit.setPlainText(
            "M,w_0 |= p&q\n"
            "w_1 |= []p -> <>q\n"
            "|= p | ~p"
        )
        self.set_status("Ejemplo cargado.")

    def clear_model(self) -> None:
        self.worlds_edit.setPlainText("w0")
        self.relation_edit.clear()
        self.valuations_edit.clear()
        self.formulas_edit.clear()
        self.validate_and_draw()
        self.clear_results()

    def validate_and_draw(self) -> None:
        try:
            model = parse_model(
                self.worlds_edit.toPlainText(),
                self.relation_edit.toPlainText(),
                self.valuations_edit.toPlainText(),
            )
        except ModelParseError as error:
            self.summary_edit.setPlainText(f"ERROR\n\n{error}")
            self.status_label.setStyleSheet("font-weight: bold; color: #b00020;")
            self.set_status(f"Error: {error}")
            return

        self.current_model = model
        self.summary_edit.setPlainText(model.formatted())
        self.graph_editor.set_model(model)
        self.graph_editor.set_literals_visible(self.literals_action.isChecked())
        self.status_label.setStyleSheet("font-weight: bold; color: #167a2e;")
        self.set_status(
            f"Modelo válido: {len(model.worlds)} mundos y "
            f"{len(model.relation)} relaciones."
        )

    def sync_text_from_graph(self, model: KripkeModel) -> None:
        self.current_model = model
        self.worlds_edit.setPlainText(model.formatted_worlds())
        self.relation_edit.setPlainText(model.formatted_relation())
        self.valuations_edit.setPlainText(model.formatted_valuations())
        self.summary_edit.setPlainText(model.formatted())

    def clear_results(self) -> None:
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def evaluate_formulas(self) -> None:
        if self.current_model is None:
            self.validate_and_draw()
            if self.current_model is None:
                return

        self.clear_results()
        lines = [
            line.strip()
            for line in self.formulas_edit.toPlainText().splitlines()
            if line.strip()
        ]

        if not lines:
            self._add_result(
                "⚠ No se ha introducido ninguna fórmula.",
                "#9a6700",
            )
            return

        for line in lines:
            try:
                request = parse_evaluation_request(line)
                result = evaluate_request(self.current_model, request)
                mark = "✓" if result else "✗"
                color = "#167a2e" if result else "#b00020"
                self._add_result(
                    f"{mark} {format_request_html(request)}",
                    color,
                    rich=True,
                )
            except FormulaSyntaxError as error:
                self._add_result(
                    f"⚠ {html.escape(line)}<br>"
                    f"<span style='font-weight:normal;'>"
                    f"{html.escape(str(error))}</span>",
                    "#9a6700",
                    rich=True,
                )

    def _add_result(self, text: str, color: str, rich: bool = False) -> None:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextFormat(
            Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText
        )
        label.setText(
            f"<div style='color:{color}; font-size:12pt; font-weight:600;'>"
            f"{text}</div>"
            if rich else text
        )
        label.setStyleSheet(
            "padding: 8px; border: 1px solid palette(mid); border-radius: 4px;"
        )
        self.results_layout.insertWidget(self.results_layout.count() - 1, label)

    def zoom_in(self) -> None:
        self.graph_editor.setFocus()
        self.graph_editor.zoom_in()

    def zoom_out(self) -> None:
        self.graph_editor.setFocus()
        self.graph_editor.zoom_out()

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Editor de modelos de Kripke")

    window = ModelEditorWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
