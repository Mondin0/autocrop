# Registro V2-12

## Implementación

Fecha: 2026-11-01. Etapa V2-12 (selección automática de sujetos y formaciones).

Modelo implementador solicitado y utilizado: `opencode/deepseek-v4.1-flash-free`
(aparece en `opencode models`; variante gratuita `-free` confirmada oficialmente).
No se sustituyó por otro proveedor ni se usaron flags para desactivar permisos.

Alcance ejecutado: solo código fuente, documentación y datos sintéticos generados
por los tests. No se leyeron, abrieron, listaron ni enviaron `Archivo.zip`,
`archivo1_crop.zip`, fotografías privadas ni rutas `/tmp/v212`; no se descargaron
modelos ni se agregaron dependencias.

### Archivos modificados

- `app/subject.py`: nuevo `select_target(image, boxes) -> (caja | None, motivo)`,
  constantes de calibración y helpers de validación, formación, nitidez y puntaje.
  `select_subject(boxes)` y su contrato histórico por área quedan intactos.
- `app/processor.py`: el pipeline usa `select_target`; las formaciones reciben
  `GROUP_RATIO` (3:2) cuando no hay `--ratio`; `ambiguous_subject` y `no_person`
  copian el original intacto a `review/` con el motivo en `review.log`.
- `tests/test_target_selection.py` (nuevo): contrato de `select_target` con
  imágenes sintéticas (sin pesos, sin red, sin fotos).
- `tests/test_processor_selection.py` (nuevo): integración del procesador y del
  ZIP compartido, proporción explícita, revisión idéntica, contadores y
  protección de sobrescritura.
- `README.md`: comportamiento de selección, motivos, límites y ejemplo Python.
- `.plans/v2/12-seleccion-fotografica/plan.md`: estado a `en revisión`.

### Tests primero y rojo funcional

Se agregó el stub importable `select_target` que lanza `NotImplementedError` y
se escribieron los tests antes de la lógica.

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 53 failed, 6 passed
```

Los fallos fueron funcionales: `NotImplementedError: V2-12 select_target is not
implemented yet` y aserciones del procesador que todavía seleccionaba por área
(p. ej. `('saved', ...) == ('review', 'no_valid_crop')`). No hubo fallos de
importación ni de instalación.

### Verde

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 59 passed

.venv/bin/python -m pytest
→ 610 passed, 1 skipped, 1 warning (StarletteDeprecationWarning de fastapi.testclient) in 53.45s

.venv/bin/python -m pip check
→ No broken requirements found.

git diff --check
→ sin salida (exit 0)
```

### Criterios cubiertos

- **F1:** sintético equivalente (formación de 3, persona aislada de fondo y
  espectador grande en primer plano): se conserva la envolvente completa de la
  formación, se excluye al espectador y la salida automática es 3:2. Validación
  visual con DSC06443.jpg pendiente del director.
- **F2:** sintético de jugador enfocado contra primer plano grande desenfocado:
  se elige el enfocado y se devuelve su detección completa. DSC06460/06461
  pendientes.
- **F3:** empate sintético simétrico → `ambiguous_subject`, copia idéntica a
  `review/` y línea en `review.log`. DSC06854.jpg pendiente.
- **F4:** persona única, ausencia de personas, ilegible, EXIF, margen, proporción
  explícita y `no_valid_crop` cubiertos por la suite existente más los tests
  nuevos de grupo sin recorte válido.
- **F5:** `process_folder`/`process_image` (CLI) y `process_archive` (web) usan la
  misma selección; el ZIP conserva `review/`, `review.log` y los contadores, sin
  cambios de interfaz.
- **F6:** no verificable localmente sin las fotografías privadas; pendiente del
  director.

### Reglas internas implementadas (calibración)

- **Formación:** dos detecciones pertenecen a la misma formación si su altura
  difiere como máximo 2× (`max ≤ min / 0.5`), su separación horizontal es
  `≤ 0.5 × ancho menor` y sus centros verticales distan `≤ 0.75 × alto menor`.
  Esto descarta personas aisladas del fondo y espectadores de otra escala.
- **Formación principal:** la de mayor cantidad de miembros; empate por suma de
  áreas y, si persiste, por orden de entrada (determinista). Con 2 o más
  miembros se devuelve la envolvente exacta como `group`; un cluster de un solo
  miembro pasa a selección individual.
- **Grupo:** `GROUP_RATIO = (3, 2)` siempre que no haya proporción explícita.
  Individual: `default_ratio` por orientación, como antes. `--ratio` prevalece.
- **Individual:** puntaje `0.5·nitidez + 0.25·área relativa + 0.25·centralidad`,
  con nitidez = varianza laplaciana dentro de la caja (borde de 1 px descartado)
  normalizada por el máximo del grupo de candidatos y centralidad =
  `1 - distancia al centro / semidiagonal`. El más nítido no gana por sí solo.
- **Ambigüedad:** si la diferencia entre el mejor y el segundo puntaje es
  `< 0.10`, se devuelve `(None, "ambiguous_subject")`. Un único box siempre es
  `individual`. Los errores de validación, detección o cálculo propagan
  `ValueError`/excepción y nunca se convierten en ambigüedad.

### Pendientes

- Inspección visual y calibración con DSC06443.jpg, DSC06460.jpg, DSC06461.jpg,
  DSC06854.jpg, DSC06444.jpg y las 12 fotos adicionales del ZIP, a cargo del
  director, localmente y fuera de OpenCode.
- Confirmar o ajustar la interpretación de "grupo usa 3:2 automático" para
  imágenes verticales y los umbrales `_NEAR_*`, pesos y `_AMBIGUITY_MARGIN`.
- Medición anterior/nuevo sobre la misma muestra (T6) y verificación de que V1 y
  V2-10 permanecen sin cambios.

### Segunda entrega — correcciones R1/R2 (2026-11-01)

Se conserva íntegra la evidencia de la primera entrega y la sección Revisión.
Misma restricción de privacidad: no se accedió a ZIP, fotografías privadas ni
`/tmp/v212`; solo código y sintéticos. No se calibró contra corpus.

#### Regresiones rojas antes de corregir

Se agregaron primero los tests de R1/R2 y se ejecutaron con la implementación
anterior:

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 3 failed, 66 passed
```

Fallos por defecto real de agrupación (la implementación devolvía `group`):

- `test_compact_play_is_not_a_formation_and_keeps_focused_player`
- `test_pair_alone_is_not_a_formation`
- `test_overlapping_pair_is_not_a_formation`

Nota de transparencia: la primera corrida de los tests nuevos dio 5 fallos; dos
eran defectos del propio test, no del código: el fixture vertical usaba
separaciones de 40 px con umbral de 30 px (no formaba cluster) y una aserción
de límite comparaba contra el mínimo de los fondos. Corregidos ambos, el test
de imagen vertical quedó verde antes del fix porque solo verifica una conducta
ya correcta, y quedaron los 3 rojos funcionales de agrupación.

#### Correcciones

- **R1 — formación estructurada** (`app/subject.py`): un cluster próximo y de
  escala similar ya no basta. Se exige una fila de al menos 3 miembros con
  alturas dentro de 1.6×, anchos dentro de 2.5×, fondos alineados dentro de
  `0.25 × altura mediana` y huellas horizontales separadas (solapamiento
  tolerado solo hasta `0.1 × ancho menor`, para excluir oclusiones). Solo esos
  clusters pueden devolver `group`; jugadas compactas, parejas y detecciones
  superpuestas pasan a selección individual, donde decide la evidencia visual.
  Se conserva la envolvente del cluster de la formación principal y el caso de
  grupo con persona aislada.
- **R2 — tests**: `test_overlapping_pair_forms_a_group` se reemplazó por
  `test_overlapping_pair_is_not_a_formation`, con comentario que documenta la
  interpretación errónea anterior (el contrato no considera formación a dos
  cajas superpuestas). Se eliminó el helper tautológico `_inside` y se dejaron
  aserciones reales de límites (`selected[2] < spectator[0]`,
  `selected[3] == max(...)`). Se agregó
  `test_group_in_vertical_image_uses_landscape_three_two`, que verifica que en
  una imagen 800x1200 con `default_ratio == (2, 3)` el grupo automático sale
  apaisado 3:2.
- **Cobertura adicional**: propagación de errores del detector (`RuntimeError`
  y `ValueError`, sin copia a `review/`), detección fuera de la imagen como
  `ValueError` y no ambigüedad, error de `calculate_crop` propagado en lugar de
  `no_valid_crop`, y `select_target` con imágenes RGB de dimensión 0.

#### Verde

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 69 passed

.venv/bin/python -m pytest
→ 620 passed, 1 skipped, 1 warning (StarletteDeprecationWarning) in 49.64s

.venv/bin/python -m pip check
→ No broken requirements found.

git diff --check
→ sin salida (exit 0)
```

`README.md` actualizado con la regla de formación estructurada y la exclusión de
parejas y jugadas. Estado devuelto a `en revisión`; la etapa no se cierra.

#### Reglas internas actualizadas

- Candidato a formación: cluster por proximidad/escala (altura ≤ 2×, separación
  ≤ 0.5 × ancho menor, centros verticales ≤ 0.75 × alto menor).
- Formación válida: contiene una fila de ≥ 3 con altura ≤ 1.6×, ancho ≤ 2.5×,
  fondos dentro de ±0.25 × altura mediana y huecos horizontales no negativos
  salvo tolerancia de 0.1 × ancho menor.
- Formación principal: más miembros; empate por suma de áreas; empate por orden
  de entrada. Envoltura = cluster completo de esa formación.
- Grupo: `GROUP_RATIO = (3, 2)` incluso en imágenes verticales; `--ratio` vence.
- Selección individual, pesos, ambigüedad (0.10) y propagación de errores sin
  cambios respecto de la primera entrega.

#### Pendientes tras la corrección

- El director vuelve a medir localmente el corpus (no accesible aquí) para
  confirmar que bajó el sobregrupamiento y que F1/F2/F6 no retroceden.
- Calibrar si una formación de solo dos personas o de varias filas debe
  agruparse; hoy exige una fila de ≥ 3 y conserva grupo con aislado.
- Ajuste fino de `_FORMATION_*`, `_NEAR_*`, pesos y margen de ambigüedad según
  esa medición; sin garantía de rendimiento.

### Tercera entrega — correcciones R3/R4 (2026-11-01)

Los hallazgos R3/R4 que el director agregó al evaluar la segunda versión se
atendieron en la misma sesión, sin acceder a corpus, ZIP ni fotografías
privadas. Se conservan íntegras las entregas anteriores y la sección Revisión.

#### Regresiones rojas antes de corregir

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 2 failed, 69 passed
```

- `test_small_textured_edge_cannot_force_ambiguity` (R3): una detección
  estrecha texturada del borde forzaba `ambiguous_subject` pese al
  protagonista enfocado.
- `test_two_row_formation_with_occlusions_and_duplicate_is_a_group` (R4): una
  formación real de dos filas con oclusiones parciales y una detección
  duplicada quedaba `ambiguous_subject` y no `group`.

#### Correcciones

- **R3 — relevancia** (`app/subject.py:_selection_scores`): una detección con
  área menor que `0.15 ×` el área mayor no es relevante de escena y puntúa 0,
  de modo que no puede ganar ni forzar empate solo por estar texturada. El
  resto del puntaje (nitidez 0.5, área 0.25, centralidad 0.25) y el margen de
  ambigüedad 0.10 no cambian.
- **R4 — formación tolerante** (`app/subject.py`): antes de evaluar una fila se
  fusionan detecciones duplicadas de la misma persona (`IoU >= 0.8`); se
  toleran oclusiones entre filas y cajas parciales; la separación se exige por
  distancia entre centros (`>= 0.2 ×` ancho menor) en lugar de prohibir todo
  solapamiento; se admiten alturas hasta 2× y anchos hasta 3×. La tolerancia de
  línea de apoyo sigue en `0.25 ×` altura mediana, que mantiene a las jugadas
  compactas fuera de `group`. Se conserva la envolvente completa del cluster.
- `README.md` actualizado con la tolerancia a filas/oclusiones/duplicados y la
  regla de relevancia.

#### Verde

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 71 passed

.venv/bin/python -m pytest
→ 622 passed, 1 skipped, 1 warning (StarletteDeprecationWarning) in 53.33s

.venv/bin/python -m pip check
→ No broken requirements found.

git diff --check
→ sin salida (exit 0)
```

Estado devuelto a `en revisión`; la etapa no se cierra.

#### Reglas internas actualizadas

- Formación válida: fila de ≥ 3 tras fusionar duplicados (IoU ≥ 0.8), alturas
  ≤ 2×, anchos ≤ 3×, fondos dentro de ±0.25 × altura mediana y centros
  consecutivos separados ≥ 0.2 × ancho menor. Las filas se evalúan por
  separado; la envolvente es la del cluster completo de la formación principal.
- Selección individual: candidatos con área < 0.15 × la mayor puntúan 0
  (no relevantes); el resto combina nitidez/área/centralidad con pesos 0.5/0.25/
  0.25 y margen de ambigüedad 0.10.
- Grupo: `GROUP_RATIO = (3, 2)` también en imágenes verticales; `--ratio` vence.

#### Pendientes tras R3/R4

- El director vuelve a medir localmente el corpus para confirmar 3:2, grupo por
  filas y protagonista en F2/F6.
- Calibrar `_RELEVANCE_AREA_FLOOR` (0.15), `_DUPLICATE_IOU` (0.8),
  `_FORMATION_CENTER_GAP` (0.2) y las tolerancias de altura/ancho si la muestra
  real lo requiere; sin garantía de rendimiento.
- Verificar que V1 y V2-10 siguen sin cambios.

### Cuarta entrega — correcciones R1/R3 (2026-11-01)

Hallazgos de la revisión local de la segunda entrega atendidos sin acceder a
corpus, ZIP, fotografías privadas ni `/tmp/v212`. Se conservan íntegras las
entregas anteriores y la sección Revisión.

#### Regresiones rojas antes de corregir

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 2 failed, 71 passed
```

- `test_play_of_three_with_mismatched_heights_is_not_a_group` (R1): tres
  jugadores próximos sobre la misma línea, a distancias muy distintas, se
  aceptaban como `group` porque la dispersión de altura era 2×.
- `test_irrelevant_edge_does_not_change_a_clear_individual_choice` (R3): la
  misma escena clara devolvía `individual` sin la detección diminuta del borde
  y `(None, "ambiguous_subject")` al añadirla. La detección se descartaba por
  área, pero su nitidez ya había fijado `max_focus`, reduciendo la evidencia del
  protagonista.

El fixture anterior de R3 (`test_small_textured_edge_cannot_force_ambiguity`) se
reemplazó por esta prueba de invariancia observable, porque no capturaba el
efecto de la normalización: pasaba aunque la detección irrelevante siguiera
bajando el foco relativo. El cambio está en el test, no en la implementación.

#### Correcciones

- **R3 — descartar antes de normalizar** (`app/subject.py:_selection_scores`):
  primero se seleccionan los candidatos con área `>= 0.15 ×` la mayor y solo
  sobre ellos se calcula y normaliza la nitidez. Los descartados puntúan 0 y ya
  no reducen la evidencia de los relevantes. Pesos (0.5/0.25/0.25) y margen de
  ambigüedad (0.10) sin cambios.
- **R1 — coherencia de escala** (`app/subject.py:_row_is_structured`): una fila
  válida exige alturas dentro de 1.35× y anchos dentro de 2× (antes 2× y 3×).
  Se mantienen: fila alineada por fondo (±0.25 × altura mediana), ≥ 3 miembros
  tras fusionar duplicados (IoU ≥ 0.8) y centros separados ≥ 0.2 × ancho menor.
  No se relaja ninguna otra condición ni se añaden excepciones por fotografía.
- **Documentación**: docstring de `select_target` y comentario de constantes
  alineados con las reglas finales; `README.md` actualizado. No se pide
  confirmación de grupos verticales ni de equipos de dos filas: el contrato ya
  los exige y ambos tienen tests propios.

#### Verde

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 73 passed

.venv/bin/python -m pytest
→ 624 passed, 1 skipped, 1 warning (StarletteDeprecationWarning) in 53.90s

.venv/bin/python -m pip check
→ No broken requirements found.

git diff --check
→ sin salida (exit 0)
```

Estado devuelto a `en revisión`; la etapa no se cierra.

#### Reglas internas finales

- Candidato: cluster por proximidad/escala (altura ≤ 2×, hueco ≤ 0.5 × ancho
  menor, centros verticales ≤ 0.75 × alto menor).
- Formación: fila de ≥ 3 tras fusionar duplicados (IoU ≥ 0.8), altura ≤ 1.35×,
  ancho ≤ 2×, fondos ±0.25 × altura mediana y centros consecutivos separados
  ≥ 0.2 × ancho menor. Filas evaluadas por separado; envolvente del cluster
  completo de la formación principal (más miembros, luego área).
- Individual: se descartan los candidatos con área < 0.15 × la mayor antes de
  normalizar nitidez; los relevantes combinan nitidez 0.5, área 0.25 y
  centralidad 0.25; diferencia < 0.10 entre los dos primeros es
  `ambiguous_subject`. Una sola detección siempre es `individual`.
- Grupo: `GROUP_RATIO = (3, 2)` también en imágenes verticales; `--ratio` vence.
- Errores de validación, detección o cálculo propagan excepción; nunca se
  convierten en ambigüedad.

#### Pendientes tras R1/R3

- El director vuelve a medir localmente F1/F2/F6 y controles; aquí no se pudo
  verificar visualmente ni calibrar contra el corpus.
- Ajustar si la muestra real lo requiere: `_FORMATION_HEIGHT_SPREAD` (1.35),
  `_FORMATION_WIDTH_SPREAD` (2.0), `_RELEVANCE_AREA_FLOOR` (0.15),
  `_DUPLICATE_IOU` (0.8), `_FORMATION_CENTER_GAP` (0.2) y el margen 0.10. Sin
  garantía de rendimiento.
- Verificar que V1 y V2-10 siguen sin cambios.

### Quinta entrega — corrección residual R3 (2026-11-01)

Hallazgo residual de la revisión local de la tercera entrega atendido sin
acceder a corpus, ZIP, fotografías privadas ni `/tmp/v212`. Se conservan
íntegras las entregas anteriores y la sección Revisión.

#### Regresión roja antes de corregir

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 1 failed, 74 passed
```

- `test_softer_textured_foreground_does_not_hide_a_sharper_target` (R3):
  primer plano de 237600 px² (≈3.3× el área del protagonista de 72000 px²)
  con desenfoque suave (radio 0.7, textura todavía visible), protagonista
  relevante moderadamente más definido (radio 0.5) y detección pequeña de
  borde (7200 px², 3 %, descartada por el piso de relevancia). La escena
  devolvía `(None, "ambiguous_subject")`; debe devolver el protagonista como
  `individual`, con y sin la detección de borde.

El fixture anterior usaba desenfoque absoluto (radio 3–4), que dejaba el
primer plano casi plano y no representaba el caso real: medía una diferencia
de foco que el ojo no necesita para decidir. El nuevo fixture conserva textura
y una diferencia moderada de nitidez.

#### Corrección

- **R3 — combinación foco/relevancia** (`app/subject.py`): pesos individuales
  pasan de nitidez 0.50 / área 0.25 / centralidad 0.25 a **0.60 / 0.20 /
  0.20**. La nitidez es la evidencia principal del sujeto buscado; área y
  centralidad quedan como desempate contextual, de modo que un primer plano
  grande pero moderadamente menos definido no supera a un protagonista
  claramente más nítido. No se cambia el piso de relevancia (0.15) ni el
  margen de ambigüedad (0.10), y no hay excepciones por fotografía.
- Regla general resultante: con área y centralidad iguales, dos candidatos solo
  se separan si la nitidez relativa difiere más de ≈17 % (0.10 / 0.60). Un
  empate razonable sigue ambiguo.
- **Documentación**: docstring de `select_target`, docstring de
  `_selection_scores`, comentario de constantes y `README.md` alineados con los
  pesos finales. No se pide confirmación de grupos verticales ni de equipos de
  dos filas: ambos ya tienen contrato y tests propios.

#### Regresión de empate razonable

Se agregó `test_comparable_focus_with_equal_relevance_stays_ambiguous`: dos
cajas del mismo tamaño en posiciones simétricas con nitidez casi igual
(radios 0.45 y 0.5) siguen devolviendo `ambiguous_subject`. Protege la
calibración contra elegir por ruido de medición.

#### Medición sintética de la calibración

Solo como evidencia de los parámetros (no como aserción de test): el caso
nuevo da margen ≈0.153 a favor del protagonista, y el empate razonable ≈0.049.
Límites conocidos: la varianza laplaciana depende del contenido (ropa, césped,
grano), no solo del desenfoque; se normaliza dentro de la misma imagen y no es
comparable entre fotos. Con un primer plano de ≈3.3× el área y ventaja de
centralidad de 0.1 a su favor, el protagonista necesita una nitidez relativa
≤≈0.57 para superar el margen; si está más centrado, el umbral se relaja.

#### Verde

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 75 passed

.venv/bin/python -m pytest
→ 626 passed, 1 skipped, 1 warning (StarletteDeprecationWarning) in 52.00s

.venv/bin/python -m pip check
→ No broken requirements found.

git diff --check
→ sin salida (exit 0)
```

Estado devuelto a `en revisión`; la etapa no se cierra.

#### Reglas internas finales

- Candidato: cluster por proximidad/escala (altura ≤ 2×, hueco ≤ 0.5 × ancho
  menor, centros verticales ≤ 0.75 × alto menor).
- Formación: fila de ≥ 3 tras fusionar duplicados (IoU ≥ 0.8), altura ≤ 1.35×,
  ancho ≤ 2×, fondos ±0.25 × altura mediana y centros consecutivos separados
  ≥ 0.2 × ancho menor. Filas evaluadas por separado; envolvente del cluster
  completo de la formación principal (más miembros, luego área).
- Individual: se descartan los candidatos con área < 0.15 × la mayor antes de
  normalizar nitidez; los relevantes combinan nitidez 0.60, área 0.20 y
  centralidad 0.20; diferencia < 0.10 entre los dos primeros es
  `ambiguous_subject`. Una sola detección siempre es `individual`.
- Grupo: `GROUP_RATIO = (3, 2)` también en imágenes verticales; `--ratio` vence.
- Errores de validación, detección o cálculo propagan excepción; nunca se
  convierten en ambigüedad.

#### Pendientes tras la quinta entrega

- El director vuelve a medir localmente F2 y controles; aquí no se pudo
  verificar visualmente ni calibrar contra el corpus.
- Si la muestra real lo exige, ajustar los pesos (0.60/0.20/0.20),
  `_RELEVANCE_AREA_FLOOR` (0.15) o `_AMBIGUITY_MARGIN` (0.10) con nueva
  evidencia sintética; sin garantía de rendimiento.
- Verificar que V1 y V2-10 siguen sin cambios.

### Sexta entrega — correcciones R5/R6 (2026-11-01)

Hallazgos residuales de la revisión local (R5 y R6) atendidos sin acceder a
corpus, ZIP, fotografías privadas ni `/tmp/v212`. Se conservan íntegras las
entregas anteriores y la sección Revisión, incluidas las notas nuevas del
director.

#### Regresiones rojas antes de corregir

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 2 failed, 75 passed
```

- `test_staggered_bottoms_beyond_tolerance_are_not_a_group` (R5): tres cajas
  próximas de igual altura y ancho con fondos escalonados 0.2×alto (extremos
  0.4×alto) se declaraban `group`, porque `_bottom_rows` encadenaba saltos
  consecutivos bajo la tolerancia de 0.25×alto.
- `test_group_envelope_includes_related_bodies_not_only_heads` (R6): fila de
  tres cajas cortas de cabeza/torso alineadas, con sus cuerpos (~3× altura)
  debajo/solapados en dos filas y un espectador aislado, devolvía `group` con
  la envolvente solo de las cabezas `(120,180,440,250)`, cortando cuerpos y
  extremidades. La asociación se rompía por la diferencia de altura >2×.

#### Correcciones

- **R5 — tolerancia anclada** (`app/subject.py:_bottom_rows`): cada `bottom`
  se compara con el primero de la fila en curso, no con el último. Así la
  dispersión total de una fila nunca supera la tolerancia declarada
  (0.25 × altura mediana) y una escalera de pasos pequeños no finge una línea
  de apoyo. No se relaja ninguna otra condición.
- **R6 — asociación geométrica de cuerpos** (`app/subject.py`): tras elegir la
  formación principal se calcula su envolvente y se expande con toda detección
  que comparta al menos el 10 % de la caja menor con una detección ya incluida
  (`_OCCLUSION_OVERLAP = 0.1`, cierre transitivo vía `_related_body` /
  `_envelope_with_related`). Esto mantiene juntas las cajas cortas de cabeza o
  torso con sus cuerpos y las dos filas que se ocluyen, sin inventar píxeles ni
  cajas: solo se unen rectángulos detectados. Una detección aislada o de otra
  escala no solapa y queda fuera. No se toca YOLO, el detector ni el recorte.
- **README**: se matiza la exclusión del espectador — garantizada por reglas
  para detecciones aisladas o de otra escala, no como promesa universal; una
  detección que solape realmente al equipo puede quedar dentro de la
  envolvente. Docstrings de `_bottom_rows` y `select_target` alineados con las
  reglas finales.

#### Criterios cubiertos

- Un `group` ya no se limita a la fila de cabezas/torso: contiene todos los
  cuerpos relacionados y conserva las dos filas del equipo (R6/F1).
- El espectador aislado/otra escala sigue fuera de la envolvente.
- La jugada compacta, la pareja, la fila con alturas dispares y los fondos
  escalonados siguen sin ser formación (R1/R5).
- Los casos individuales y la ambigüedad de F2 no cambian.

#### Verde

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 77 passed

.venv/bin/python -m pytest
→ 628 passed, 1 skipped, 1 warning (StarletteDeprecationWarning) in 51.74s

.venv/bin/python -m pip check
→ No broken requirements found.

git diff --check
→ sin salida (exit 0)
```

Estado devuelto a `en revisión`; la etapa no se cierra. `group`/`saved` es
clasificación de esta suite sintética, no aprobación visual de composición: la
validación del recorte sobre el corpus queda en manos del director.

#### Reglas internas finales

- Candidato: cluster por proximidad/escala (altura ≤ 2×, hueco ≤ 0.5 × ancho
  menor, centros verticales ≤ 0.75 × alto menor).
- Formación: fila de ≥ 3 tras fusionar duplicados (IoU ≥ 0.8), altura ≤ 1.35×,
  ancho ≤ 2×, fondos dentro de ±0.25 × altura mediana respecto del primer fondo
  de la fila y centros consecutivos separados ≥ 0.2 × ancho menor. Filas
  evaluadas por separado; formación principal por más miembros y luego área.
- Envolvente de grupo: cluster principal + cierre transitivo de detecciones con
  solape ≥ 0.1 × área de la caja menor (cabeza/torso con su cuerpo y filas que
  se ocluyen). Sin píxeles ni cajas inventadas.
- Individual: se descartan los candidatos con área < 0.15 × la mayor antes de
  normalizar nitidez; los relevantes combinan nitidez 0.60, área 0.20 y
  centralidad 0.20; diferencia < 0.10 entre los dos primeros es
  `ambiguous_subject`. Una sola detección siempre es `individual`.
- Grupo: `GROUP_RATIO = (3, 2)` también en imágenes verticales; `--ratio` vence.
- Errores de validación, detección o cálculo propagan excepción; nunca se
  convierten en ambigüedad.

#### Pendientes tras la sexta entrega

- El director valida visualmente el recorte F1 y el resto de la muestra; aquí no
  se pudo verificar composición ni acceder al corpus.
- Calibrar si la muestra real lo exige `_OCCLUSION_OVERLAP` (0.10), las
  tolerancias de formación o el margen 0.10 con nueva evidencia sintética, sin
  excepciones por fotografía y sin garantía de rendimiento.
- Confirmar que V1 y V2-10 siguen sin cambios.

### Séptima entrega — corrección R7 (sexta invocación CLI real, 2026-11-01)

Esta entrega corresponde a la **sexta invocación CLI real** del implementador;
las iteraciones internas de las entregas anteriores no cuentan como
invocaciones. Se atendió exclusivamente R7. Se conservan íntegras las entregas
anteriores y la sección Revisión (incluidos R5/R6), y no se accedió a corpus,
ZIP, fotografías privadas ni `/tmp/v212`.

#### Contexto preservado

El director validó visualmente **F1 y F2 PASS**. Por indicación explícita no se
tocaron las reglas de formación, la asociación geométrica R6 ni los tests que ya
pasan; el cambio se limita a la decisión de ambigüedad individual.

#### Regresión roja antes de corregir

```
.venv/bin/python -m pytest tests/test_target_selection.py::test_dominant_sharp_subject_beats_a_slightly_sharper_smaller_one
→ 1 failed
```

Observado: `(None, "ambiguous_subject")` para un sujeto de 200000 px² (2.65× el
secundario de 75600 px²), mejor colocado y con 90 % del foco del secundario;
ambos nítidos. Scores medidos en la corrida roja: ganador 0.8998, segundo
0.8163, diferencia 0.0834 < 0.10. Reproduce el diagnóstico abstracto del
director (ganador ~0.879, segundo ~0.816, diferencia ~0.062, área ~2.9×, foco
~85 %): un sujeto dominante no debe quedar ambiguo frente a un secundario algo
más nítido pero 2–3× menor.

#### Corrección

- **R7 — ambigüedad consciente del contexto** (`app/subject.py`):
  `_selection_scores` devuelve además el foco normalizado de cada candidato.
  `_context_dominates` recupera la parte estable del puntaje
  (`score - 0.60 × foco`, es decir tamaño 0.20 + centralidad 0.20) y resuelve
  como `individual` cuando, con diferencia de score bajo el margen 0.10, el
  líder:
  1. supera al segundo en contexto estable por al menos `_CONTEXT_DOMINANCE`
     (0.10, el mismo margen de empate), y
  2. conserva al menos `_MIN_DOMINANT_FOCUS` (80 %) del foco del candidato más
     nítido.
- El margen de ambigüedad sigue en 0.10 y no se agregaron excepciones por
  fotografía. Un empate real con tamaño y posición comparables sigue ambiguo
  aunque el foco difiera; un líder grande pero muy desenfocado (foco < 80 % del
  más nítido) tampoco se rescata. Sin candidato relevante con foco medible
  (imagen plana) la regla no se aplica y se mantiene la ambigüedad.
- **Documentación**: docstring de `select_target` y `README.md` describen la
  regla y sus dos condiciones.

#### Justificación y límites

- El foco (varianza laplaciana) depende del contenido y es la señal más
  ruidosa; tamaño y posición son más estables. Exigir que el líder gane ambos
  contextos por el margen completo evita elegir por una diferencia menor.
- El umbral 80 % tolera diferencias de textura/ropa sin aceptar un primer plano
  claramente desenfocado: con igual relevancia, una diferencia relativa de foco
  mayor al ~17 % ya resuelve por score, y la regla solo actúa cuando el score ya
  favorece al líder.
- No se modifican pesos (0.60/0.20/0.20), piso de relevancia (0.15), reglas de
  formación, asociación por oclusión ni el margen 0.10.

#### Verde

```
.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py
→ 78 passed

.venv/bin/python -m pytest
→ 629 passed, 1 skipped, 1 warning (StarletteDeprecationWarning) in 50.08s

.venv/bin/python -m pip check
→ No broken requirements found.

git diff --check
→ sin salida (exit 0)
```

Estado devuelto a `en revisión`; la etapa no se cierra. El director hará la
validación privada local del control F6.

#### Pendientes tras R7

- Validación privada local del control F6 y confirmación de que los demás
  controles no cambian (no accesible aquí).
- Si la muestra real lo exige, recalibrar `_CONTEXT_DOMINANCE` (0.10) o
  `_MIN_DOMINANT_FOCUS` (0.80) con nueva evidencia sintética, sin excepciones
  por fotografía.
- Confirmar que V1 y V2-10 siguen sin cambios.

## Revisión

### Primera revisión del director — 2026-11-01

Delegación limitada a código y sintéticos tras rechazo automático de acceso a fotos privadas. Modelo gratuito confirmado en https://opencode.ai/v2/docs/console/models/ y sesión efectiva `ses_e686f4140ffencpj3r3spo2avp`. La instrucción de implementar el plan aprobó el contrato.

**Evidencia local:** Archivo.zip contiene 850 JPEG. Muestra: cinco casos fijos más 12 índices redondeados equiespaciados sobre nombres JPEG ordenados excluyendo los cinco. Controles DSC06434, DSC06524, DSC06608, DSC06686, DSC06766, DSC06844, DSC06921, DSC07004, DSC07082, DSC07159, DSC07236, DSC07314 (todos .jpg). Originales, hashes, cajas, comparativas y tiempos fuera de Git en `/tmp/v212/baseline.json` y `/tmp/v212/first.json`. Margen 0.15, Python 3.12.3/Linux x86_64; yolo11n.pt SHA256 0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1. Detección total anterior 2.821795 s; selección anterior mediana de 100 recorridos 0.00009186 s/lote. No garantía de rendimiento.

- **R1 abierto** — `app/subject.py:_same_formation/select_target`: proximidad y escala bastan para agrupar parejas/jugadas. Evaluación local produce 14/17 group; F2 termina no_valid_crop en ambos casos y 6/12 controles pasan de saved a review. Impacto: falla protagonista y composición; F2/F6/T3. Corrección: exigir evidencia suficiente de formación, regresión sintética de jugada compacta antes del fix, sin excepciones por archivo.
- **R2 abierto** — `tests/test_target_selection.py:test_overlapping_pair_forms_a_group` codifica falsa formación; `_inside` compara tupla4 con tuplas2 y no comprueba nada. `tests/test_processor_selection.py:test_group_photo_uses_automatic_three_two` usa imagen ya horizontal y no detecta ausencia del cambio. Impacto: tests verdes no garantizan T3/F1/F4. Corrección: justificar cambio del test erróneo, retirar aserción tautológica y probar ratio automático de grupo en imagen vertical.

Hallazgos remitidos a la misma sesión. F1 visual preliminar: recorte conserva equipo; F2 y F6 impiden cierre. Primera entrega: confianza estimada 45 %, por reglas de formación excesivas pese a suite verde.

### Evaluación de la segunda versión en curso

Pruebas independientes de primera entrega: `.venv/bin/python -m pytest tests/test_target_selection.py tests/test_processor_selection.py tests/test_subject.py tests/test_processor.py tests/test_archive.py` → 198 passed, 1 skipped en 0.54 s.

- **R3 abierto** — `app/subject.py:_selection_scores`: foco normalizado respecto del máximo permite que una detección estrecha texturada del borde fuerce empate. En segundo caso F2, margen de puntaje ~0.035 causa ambiguous_subject aunque protagonista es claro. F2/T3. Agregar regresión sintética triple (protagonista relevante/enfocado, primer plano grande borroso y borde pequeño texturado), corregir relevancia sin elegir solo nitidez.
- **R4 abierto** — `app/subject.py:_row_is_structured`: prohibición casi absoluta de solapamiento rechaza formaciones reales de dos filas y cajas parciales/duplicadas. Evaluación segunda `/tmp/v212/second.json`: 0/17 group; ambas fotos de equipo pasan a ambiguous, un F2 saved y otro ambiguous, controles 6 saved/6 ambiguous. F1/F2/F6/T3. Agregar regresión de formación con oclusiones/filas y cajas parciales, sin excepciones fotográficas. La detección original sigue siendo la misma.

Inspección de los recortes F1 y control DSC06444 de primera versión confirma cuerpos, cabezas y extremidades completas y 1278×852 (3:2). No basta: esa versión falla jugadas y segunda pierde formación. Hallazgos remitidos a misma sesión.

### Evaluación tras ampliación de oclusiones/foco (misma segunda entrega)

`/tmp/v212/third.json`: F1 y DSC06444 recuperan group/saved, pero F2 vuelve a group/no_valid_crop en ambos casos. Controles: 9 saved/3 ambiguous. **R1 y R3 siguen abiertos**: fila de tres jugadores de alturas muy diferentes se acepta tras subir dispersión a 2×. `_selection_scores` descarta área pequeña después de calcular max_focus, por lo que el candidato excluido sigue reduciendo evidencia de foco del protagonista; segundo F2 mantiene margen ~0.038 aun sin agrupación. Corregir ambos con regresiones más representativas antes de cerrar. No hay excepciones por archivo.

### Evaluación de tercera entrega en curso

`/tmp/v212/fourth.json`: F1 y control de formación group/saved, F2 primero individual/saved pero segundo ambiguous; exploratorio ambiguous. Controles 7 saved/5 ambiguous. R1 agrupación obligatoria ahora corregida, pendiente confirmación final. **R3 aún abierto**: normalización ya excluye candidato irrelevante, pero evidencia moderada de foco no supera margen 0.10 (~0.092 en segundo F2). Regresión requerida con primer plano ~3× área, menos nítido pero no absolutamente borroso, protagonista relevante moderadamente más definido y borde excluido; calibración general de pesos, sin excepción fotográfica ni ajustar por nombre.

- **R5 abierto** — `app/subject.py:_bottom_rows`: compara cada bottom con último de fila; una cadena de saltos menores que tolerancia puede superar tolerancia en sus extremos y declararse alineada, contradiciendo docstring/reglas. T3/F1. Regresión antes del fix con tres cajas cercanas de igual altura y bottoms en escalera (saltos 0.2h, rango 0.4h con tolerancia 0.25h), motivo distinto de group. Corrección mínima: anclar tolerancia al inicio de fila. README debe evitar promesa universal de que cualquier espectador se excluye: solo aislado/otra escala bajo heurística actual.

- **R6 abierto (F1, crítico de composición)** — `app/subject.py:_formation_clusters/select_target`: inspección visual de `/tmp/v212/candidate/DSC06443.jpg` revela selección de fila de cabezas/torso cortas, excluye detecciones corporales por diferencia de escala >2× y corta extremidades. group/saved no significa F1 aprobado; afirmaciones anteriores sobre group en versiones tercera/cuarta eran clasificación, no aprobación visual de esas salidas. La primera versión sí conservaba composición completa. Corrección: regresión pública con fila superior de cajas parciales cortas y detecciones corporales ~3×altura solapadas/relacionadas más otra fila; incluir toda envolvente del equipo y excluir espectador aislado. No cambiar YOLO, no inventar cuerpos ni excepciones por foto.

### Revisión de composición e integración tras R5/R6

F1: `/tmp/v212/final/DSC06443.jpg` incluye visualmente todas las cabezas, cuerpos y extremidades; caja completa de cada detección del equipo contenida por envolvente y crop. Espectador aislado no determina envolvente; 1278×852, 3:2. DSC06444 también conserva equipo. F2: ambas imágenes finales eligen detección azul/amarillo derecha completa, verificado por igualdad de caja y contención por crop, más inspección visual independiente. R1–R6 corregidos en código, sujeto a resultado final de suite; la regresión de escalera fue reproducida independientemente antes del fix.

- **R7 abierto (F6)** — `app/subject.py:_AMBIGUITY_MARGIN/select_target`: en DSC06524 el protagonista nítido y dominante pasa de saved a ambiguous pese a ganar por tamaño/posición. Score ganador~0.879, segundo~0.816, área~2.9× y foco~85% del secundario. La diferencia moderada de textura no debe inutilizar una selección dominante. Regresión sintética requerida de ambos nítidos (principal grande/relevante frente a secundario menor algo más nítido); calibrar ambigüedad general y conservar empate real. No excepción por archivo. Los controles de duelos realmente inciertos pueden ir a revisión según F3; no se exige guardar todos. Hallazgo enviado a misma sesión, sexta invocación CLI.

T6 medido antes de este ajuste menor: selector anterior/nuevo sobre mismas imágenes/cajas precargadas, 11 repeticiones, medianas 0.00008447 s / 0.180923 s por lote de 17; inferencia separada anterior2.821795s. Coste observado ~10.6ms/foto de selección añadida, no garantía. Detalles `/tmp/v212/final.json`.

### Entrega candidata final y revisión del director — 2026-11-01

R7 se corrigió con regresión sintética: una persona dominante y nítida vence a
un rival menor algo más nítido; los empates reales siguen en revisión. La nueva
calibración compara contexto estable (área y centralidad) además del foco.
DSC06524 vuelve a `saved`; inspección visual confirma al portador del balón
completo y con composición útil.

Verificaciones de la entrega final:

```
.venv/bin/pytest -q tests/test_target_selection.py tests/test_processor_selection.py
→ 78 passed
.venv/bin/pytest -q
→ 628 passed, 1 skipped, warning deprecado de Starlette
.venv/bin/pip check
→ No broken requirements found
git diff --check
→ exit 0
```

La validación local reproducible `/tmp/v212/validate.py` pasó las aserciones de
F1/F2, sus cajas y proporción de grupo 3:2. Resultados: DSC06443/06444 group;
DSC06460/06461 individual; DSC06854 individual (exploratorio, sin requisito de
ambigüedad). Inspección visual previa del candidato final confirma formación
completa en F1 y selección del jugador azul/amarillo derecho en F2. Muestra
F6: DSC06434, DSC06524, DSC06608, DSC06686, DSC06766, DSC06844, DSC06921,
DSC07004, DSC07082, DSC07159, DSC07236, DSC07314; tras R7, 9 saved y 3
`ambiguous_subject` (DSC06608, DSC06686, DSC07236), sin regresión restante
observada. DSC06444 también conserva el equipo completo.

La muestra volvió a medir selección anterior/nueva en 0.0000720/0.148089 s por
lote de 17; el coste observado es ~8.7 ms/foto. Inferencia local medida por
separado: 2.821795 s/lote. Son mediciones de esta muestra y entorno, no una
garantía de rendimiento. CLI y `process_archive` compartieron resultados en
ZIP de integración previo a R7; los tests finales cubren integración ZIP,
revisión idéntica, motivos, contadores, proporción explícita y no sobrescritura.

#### Revisión

- R1–R7: corregidos en `app/subject.py`, cada uno con regresión sintética;
  las iteraciones y evidencias intermedias se conservan arriba.
- F1: aprobado por aserciones geométricas/crop y revisión visual de DSC06443 y
  DSC06444; formación completa a 3:2, espectador aislado excluido.
- F2: aprobado en DSC06460/06461; detección completa del jugador azul/amarillo
  elegida y composición visual verificada.
- F3/F4: ambiguo sintético conserva original y motivo; compatibilidad de
  individuales, no-persona, EXIF, margen, ratios, JPEG ilegible y
  `no_valid_crop` cubierta por suite.
- F5: mismo motor para CLI/web; integración ZIP y contadores comprobados.
- F6: 12 controles inspeccionados por selección y composición; DSC06524 fue el
  hallazgo R7 y quedó corregido. Tres escenas inciertas van a revisión conforme
  a F3; no quedó regresión conocida.
- T1–T6: separación y pesos locales conservados; tests sintéticos sin pesos;
  suite, `pip check`, `git diff --check` y medición anterior/nueva completados.

Sin hallazgos pendientes. Etapa cerrada por el director.
