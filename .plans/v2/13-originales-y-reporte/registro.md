# Registro — V2-13 Originales y reporte en el ZIP

## Implementación

Fecha: 2026-11-01. Etapa V2-13 ejecutada en el alcance exclusivo de
`process_archive()` y sus pruebas. No se modificaron V1, el motor de recorte,
el contrato HTTP ni la interfaz web. No se usaron fotografías del usuario: todas
las pruebas crean JPEG y ZIP sintéticos en directorios temporales.

### Archivos modificados

- `app/archive.py`: agrega `originals/<nombre-original>` copiando los JPEG
  extraídos con `ZipFile.write` (sin recomprimir ni modificar el original),
  genera `reporte.html` en la raíz y lo escribe en el ZIP. El reporte deriva el
  estado de la existencia del recorte en la salida y el motivo de `review.log`;
  no vuelve a ejecutar detección ni infiere motivos. Nombres y motivos se
  escapan con `html.escape` y las rutas relativas se codifican con
  `urllib.parse.quote`. Se mantienen el resumen, `review/`, `review.log`, el
  orden determinista de entradas y la publicación atómica existente.
- `tests/test_archive_report.py` (nuevo): suite focal de la etapa con lote
  mixto, todo guardado, todo en revisión, nombres con caracteres HTML, `: ` y
  salto de línea, motivos hostiles, nombres parecidos a salidas reservadas,
  igualdad byte a byte de originales, resolución de todos los enlaces y fallo de
  empaquetado sin ZIP parcial.
- `tests/test_archive.py`: `test_valid_zip_matches_process_folder` comparaba la
  igualdad exacta del ZIP con la salida de `process_folder()`. El contrato
  V2-13 agrega `originals/` y `reporte.html`, por lo que ahora compara las
  salidas heredadas y verifica aparte los originales y el reporte. No se
  debilitó ninguna aserción existente.
- `.plans/v2/13-originales-y-reporte/plan.md`: estado a `en revisión`.

### Tests primero y rojo funcional

Se escribió `tests/test_archive_report.py` antes de la lógica. La primera
ejecución falló por funcionalidad ausente (no por importación ni instalación):

```
.venv/bin/python -m pytest tests/test_archive_report.py -q
→ 7 failed
```

Los siete fallos corresponden a: falta de `originals/` (dos pruebas), falta de
`reporte.html` (cuatro pruebas) y ausencia de error al empaquetar un original
desaparecido (una prueba). Después de implementar:

```
.venv/bin/python -m pytest tests/test_archive_report.py -q
→ 7 passed
```

### Validaciones ejecutadas

```
.venv/bin/python -m pytest tests/test_archive.py tests/test_archive_report.py tests/test_progress.py tests/test_processor_selection.py tests/test_api_worker.py -p no:warnings
→ 71 passed, 1 skipped in 0.68s (exit 0)
```

```
.venv/bin/python -m pytest -p no:warnings
→ 636 passed, 1 skipped in 50.98s (exit 0)
```

```
.venv/bin/python -m pip check
→ No broken requirements found. (exit 0)
```

```
git diff --check
→ sin salida (exit 0)
```

Comprobación manual con ZIP sintético en `/tmp/opencode/v213` (sin fotos del
usuario): resumen `{'processed': 3, 'saved': 2, 'review': 1, 'skipped': 0}`,
originales con bytes idénticos a la entrada, todos los `href` presentes en el
ZIP, sin referencias externas (`http://`, `https://`, `url(`, `<script>`,
`<link>`, `<img>`, `src=`), nombres y motivos escapados, y enlaces con nombres
no ASCII codificados y resolubles (`revisi%C3%B3n...`). El HTML generado se
revisó como documento local.

### Corrección 1 — nombre con salto de línea

Hallazgo del director: `_review_reasons` dividía `review.log` por líneas
físicas y perdía el motivo de un JPEG válido cuyo nombre contiene `\n`.

Se agregó primero la regresión
`tests/test_archive_report.py::test_review_name_with_newline_keeps_reason`
(nombre `"foto\ncon salto.jpg"` que queda en revisión; exige motivo
`no_person`, enlaces resolubles y bytes):

```
.venv/bin/python -m pytest tests/test_archive_report.py::test_review_name_with_newline_keeps_reason -q
→ 1 failed
  AssertionError: assert [''] == ['no_person']
```

Solución mínima: `_review_reasons` recorre el texto de `review.log` con los
nombres revisados en el mismo orden en que `process_folder()` escribe los
registros y consume `nombre: motivo` sin dividir por saltos de línea. No se
cambió la validación ZIP, el formato de `review.log`, el motor ni otras áreas.

Validaciones después de la corrección:

```
.venv/bin/python -m pytest tests/test_archive_report.py::test_review_name_with_newline_keeps_reason tests/test_archive_report.py -p no:warnings -q
→ 8 passed (exit 0)
```

```
.venv/bin/python -m pytest tests/test_archive.py tests/test_archive_report.py tests/test_progress.py tests/test_processor_selection.py tests/test_api_worker.py -p no:warnings
→ 72 passed, 1 skipped in 0.71s (exit 0)
```

```
.venv/bin/python -m pytest -p no:warnings
→ 637 passed, 1 skipped in 50.95s (exit 0)
```

```
.venv/bin/python -m pip check
→ No broken requirements found. (exit 0)
```

```
git diff --check
→ sin salida (exit 0)
```

### Criterios cubiertos

- **F1:** todos los JPEG de la entrada aparecen una vez bajo `originals/` con
  bytes idénticos; recortes, `review/` y `review.log` siguen presentes.
- **F2:** una fila ordenada por nombre y un enlace al original por foto; los
  guardados enlazan su recorte y las revisiones muestran el motivo registrado y
  enlazan `review/<nombre>`.
- **F3:** HTML en español, `meta charset`, CSS embebido sin recursos externos,
  nombres/motivos escapados y enlaces relativos resolubles dentro del ZIP.
- **F4:** el resumen y las salidas existentes no cambian; un fallo durante el
  empaquetado no publica ZIP parcial ni deja temporales.
- **T1:** empaquetado ordenado, sin dependencias nuevas, sin recalcular recortes
  ni modificar originales; no se tocó V1.
- **T2:** rojo funcional observado, tests focales y suite completa verdes,
  `pip check` y `git diff --check` limpios desde `.venv`.

### Pendientes

- Sin pendientes.

## Revisión

### Entrega 1 — Hallazgo pendiente

- `app/archive.py::_review_reasons`: el parser divide `review.log` por líneas físicas. Un JPEG válido cuyo nombre contenga un salto de línea (permitido por la validación ZIP vigente) hace que el motivo registrado se pierda al construir el reporte.
- **Impacto / criterio:** F2. Para fotos que queden en revisión, el reporte debe explicar el motivo real. En este caso muestra el estado y enlace, pero deja vacío el motivo.
- **Corrección esperada:** agregar primero una regresión con nombre de JPEG que contenga `\n` y que quede en revisión; luego preservar/recuperar su motivo sin cambiar la validación existente ni omitir la foto. Ejecutar el test focal y actualizar evidencia.

### Corrección 1 — respuesta del implementador

- Se agregó la regresión solicitada y se confirmó el rojo funcional
  (`motivo` vacío en lugar de `no_person`).
- `_review_reasons` ahora consume los registros de `review.log` en el orden
  ordenado de las fotos revisadas, sin dividir por líneas físicas; conserva el
  motivo real de nombres con `\n` y mantiene intactos validación, motor, API y
  V1.
- Resultados posteriores: regresión y suite focal `8 passed`; conjunto focal
  `72 passed, 1 skipped`; suite completa `637 passed, 1 skipped`; `pip check` y
  `git diff --check` limpios. Detalle en la sección Implementación.
- La etapa permanece `en revisión` para la verificación del director.

### Revisión independiente y cierre

- **F1–F4, T1–T2 verificados.** Se inspeccionó el diff completo: el ZIP
  conserva sus salidas previas y agrega los originales byte por byte y el
  reporte; no hay cambios a V1, motor, API o dependencias. Las regresiones
  cubren los estados, enlaces, escapes, nombres reservados, fallo sin salida
  parcial y el salto de línea corregido.
- Se volvió a ejecutar independientemente
  `.venv/bin/python -m pytest tests/test_archive.py tests/test_archive_report.py
  -p no:warnings -q`: salida 0. La regresión cubre `\n` en nombre y motivo
  `no_person` recuperado. `git diff --check`: salida 0.
- Se abrió el reporte sintético local en navegador y se revisó captura completa:
  tabla legible con resumen, foto, estado, motivo y enlaces; caracteres HTML
  aparecen como texto. Todos los enlaces resuelven a entradas del ZIP. El
  servidor temporal se cerró al terminar la revisión.
- El hallazgo F2 de la entrega 1 queda corregido; no quedan hallazgos abiertos.
  Estado de etapa: completada.

### Cambio de contrato — salida plana para Lightroom

Se reemplaza el contrato previo de V2-13 a pedido del usuario: originales y
recortes juntos en la raíz, recortes con sufijo `-crop`, sin carpeta/copias de
revisión y reporte limitado a las fotos en revisión. La etapa vuelve a revisión;
la evidencia histórica anterior se conserva como registro de la primera versión
del contrato.

#### Implementación

- `app/archive.py`: los originales se escriben en la raíz sin alterar bytes;
  cada recorte se empaqueta como `<base>-crop<ext>`. El empaquetado omite
  `review/` y `review.log`, y el HTML lista únicamente las fotos revisadas con
  su motivo y enlace al original. Las colisiones entre el nombre de un recorte
  y cualquier original (sin distinguir mayúsculas) se rechazan antes del
  procesamiento.
- Tests ajustados en `tests/test_archive_report.py`, `tests/test_archive.py`,
  `tests/test_api_worker.py` y `tests/test_processor_selection.py` para
  estructura, bytes originales, nombres, motivos, ausencia de carpetas de
  revisión y colisiones.
- Tests primero: `.venv/bin/python -m pytest tests/test_archive_report.py -q`
  → 8 fallos funcionales al contrastar el contrato nuevo con la implementación
  anterior; luego suite focal de empaquetado → `32 passed, 1 skipped`.
- Suite candidata final: `.venv/bin/python -m pytest -p no:warnings` →
  `638 passed, 1 skipped`.
- `.venv/bin/python -m pip check` → `No broken requirements found`.
- `git diff --check` → sin salida (exit 0).

#### Revisión

- Pendiente de revisión independiente del contrato actualizado. No se modificó
  V1, el motor, el contrato HTTP ni dependencias.

#### Revisión independiente y cierre del contrato actualizado

- **F1–F4, T1–T2 verificados.** El ZIP mantiene originales en la raíz y agrega
  los recortes con sufijo `-crop`; el reporte lista solo las fotos en revisión,
  con motivo y enlace al original. La implementación escapa contenido HTML,
  ordena entradas y rechaza colisiones antes de procesar.
- Verificación independiente: `.venv/bin/python -m pytest
  tests/test_archive_report.py tests/test_archive.py -q` → pruebas focales
  aprobadas; `.venv/bin/python -m pytest -p no:warnings` → `638 passed, 1
  skipped`; `git diff --check` → limpio.
- Validación práctica reportada por el usuario: se procesó manualmente un ZIP
  de un evento de fútbol con fotos variadas, para que el fotógrafo importe el
  conjunto en Lightroom y evalúe los recortes según su criterio. Esta valida el
  flujo de uso real; no se afirma una inspección independiente de ese ZIP.
- No quedan hallazgos abiertos. Estado de etapa: completada.
