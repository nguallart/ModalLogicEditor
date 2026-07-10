# Editor gráfico didáctico de modelos de Kripke

Versión con edición textual y gráfica, valuaciones gráficas, zoom y evaluación
de fórmulas modales.

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Ejecución

```bash
python programa.py
```

## Controles gráficos

- **Clic en vacío:** crear mundo.
- **Arrastrar:** mover mundo.
- **Ctrl + botón derecho sobre un mundo:** iniciar una relación.
- **Siguiente clic en un mundo:** fijar el destino de la relación.
- **Botón derecho sobre un mundo:** menú para añadir/quitar literales o borrar.
- **Clic en una relación:** seleccionarla.
- **DEL:** borrar la relación o mundo seleccionado.
- **Esc:** cancelar.
- **+ / −:** acercar y alejar.
- **Ctrl + rueda:** zoom.

El zoom está limitado entre 40 % y 250 %.

## Fórmulas

Una consulta por línea:

```text
M,w_0 |= p&q
w_1 |= []p -> <>q
|= p | ~p
```

También se aceptan:

- `v` o `|` para disyunción;
- `~`, `!` o `¬` para negación;
- `[]` para necesidad;
- `<>` para posibilidad;
- `->` para implicación;
- `<->` para bicondicional.

La precedencia es:

1. `¬`, `□`, `◇`
2. `∧`
3. `∨`
4. `→`
5. `↔`


## Menús

### Ventana

- **Literales visibles:** muestra u oculta junto a cada mundo las letras que satisface.

### Propiedades > Comprobar

- Reflexividad
- Transitividad
- Serialidad
- Densidad
- Euclideaneidad

### Propiedades > Añadir

- Reflexividad
- Transitividad
- Euclideaneidad

Las operaciones de añadir calculan la clausura completa correspondiente.

## Archivos `.modallogic`

El menú **Archivo** permite guardar y cargar modelos de texto UTF-8 con cabecera
`MODALLOGIC 1`. Se conservan `W`, `R`, las valuaciones, las posiciones, el zoom y
el centro de la vista. Los comentarios comienzan por `#`. La carga valida el
archivo completo y muestra todos los errores antes de modificar el modelo actual.

## Marcos

El antiguo menú **Propiedades** se llama ahora **Marcos**. Incluye:

- **Comprobar**: reflexividad, transitividad, serialidad, densidad y euclideaneidad.
- **Añadir**: clausuras reflexiva, transitiva y euclídea.
- **Definiciones**: fórmula característica, condición sobre `R` y explicación de
  las propiedades habituales de los marcos.

## Constante lógica

`T` representa la tautología y es verdadera en todos los mundos. `¬T`, `~T` o
`!T` representan la contradicción. `T` está reservada y no puede usarse en `v(T)`.
