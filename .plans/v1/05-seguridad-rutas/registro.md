# Etapa 05 — Registro de ejecución y revisión

Contrato: [plan.md](plan.md). Estado vigente: ver `plan.md`.

## Implementación (Big Pickle)

### Ejecución

Tests añadidos primero en `tests/test_processor.py` y `tests/test_cli.py`.
La primera corrida roja (`.venv/bin/python -m pytest tests/test_processor.py
tests/test_cli.py -q`) mostró siete fallos de comportamiento esperado: carpetas
equivalentes, destinos de archivo y construcción temprana del detector. En la
revisión se agregó una regresión roja para un hard link de salida usado por
`process_folder`; el lote también llegaba a sobrescribir el original porque
llama a `_execute` directamente. El control quedó aplicado antes de procesar
cada foto.

Validación final:

- `.venv/bin/python -m pytest` → `311 passed in 1.35s`.
- `.venv/bin/python -m pip check` → `No broken requirements found`.
- Sin dependencias nuevas ni corrida YOLO real.

Archivos de esta etapa: `PLAN.md`, `app/processor.py`, `app/cli.py`,
`tests/test_processor.py`, `tests/test_cli.py` y esta carpeta de plan.
Cubiertos F1–F4 y T1–T2. No quedan criterios de implementación pendientes.

### Corrección R1–R3 (Muse)

Tests primero en `tests/test_processor.py` (7 regresiones, solo
`process_folder` con temporales y detector stub, sin YOLO real):

- `test_folder_rejects_log_alias_to_original[symlink|hardlink]` (R1):
  `out/review.log` como alias de `in/a.jpg`; exige `FileExistsError`,
  hash intacto, detector sin llamadas, sin `out/a.jpg` ni `out/review`.
- `test_folder_rejects_cross_output_alias_to_other_original[symlink|hardlink]`
  (R2): `out/a.jpg` como alias de `in/b.jpg`; exige hashes de ambos
  originales, sin detector, sin `out/b.jpg`, `review/` ni log.
- `test_folder_rejects_cross_review_alias_to_other_original[symlink|hardlink]`
  (R2): `out/review/a.jpg` como alias de `in/b.jpg`; mismas exigencias.
- `test_folder_late_conflict_writes_nothing` (R3): `out/b.jpg` como hard
  link a `in/b.jpg` con `a.jpg` previa; exige `FileExistsError`, hashes de
  ambos originales, salida previa `out/a.jpg` y `review.log` (`old\n`)
  intactos, detector sin llamadas y `out/review` no creado.

Corrida roja real antes de implementar
(`.venv/bin/python -m pytest tests/test_processor.py -q -k "log_alias or
cross_output or cross_review or late_conflict"`): 7 fallos por
funcionalidad pendiente (el lote procesaba y escribía en todos los casos;
en R3 generaba `out/a.jpg` antes de rechazar `b.jpg`). Sin debilitar
pruebas previas.

Implementación mínima en `app/processor.py` (biblioteca estándar,
`process_image` sin cambios, sigue protegiendo su original con
`_reject_original_destination`):

- Nuevo `_reject_batch_destinations`: indexa todos los originales JPEG del
  lote por ruta resuelta y por `(st_dev, st_ino)` (una pasada O(n)), y
  verifica cada destino `output/<nombre>`, `review/<nombre>` y
  `output/review.log` contra todos ellos por igualdad canónica o
  `stat()` compartido (symlink y hard link, mismo u otro nombre).
  Rechaza con `FileExistsError`.
- `process_folder` recolecta el lote JPEG y valida todos los destinos
  antes de crear directorios, escribir archivos o invocar al detector;
  el control por entrada dentro del bucle se eliminó por quedar cubierto
  por la validación previa (R3: un rechazo no deja salidas parciales ni
  toca salidas/log previos).
- Aclaración de esta garantía agregada al contrato de `plan.md` (etapa
  local), autorizada por Astra en el registro. CLI F3 sin cambios: solo
  exige validar igualdad de carpetas antes de construir el detector.

Validación final real:

- `.venv/bin/python -m pytest` → `318 passed in 1.13s`.
- `.venv/bin/python -m pip check` → `No broken requirements found`.
- `git diff --check` → sin errores.
- Sin dependencias nuevas ni fotos reales.

Criterios cubiertos F1–F4 y T1–T2 más R1–R3. Pendiente: revisión de Astra
(hallazgos R1–R3 no cerrados por Muse).

## Revisión (Astra)

### Revisión de la entrega — 2026-10-08

Inspeccionados AGENTS.md, PLAN.md, contrato, registro, diff completo de la
etapa, callers y rutas de escritura del procesador y CLI. No se modificaron
`app/` ni `tests/`, ni las etapas anteriores.

Comprobaciones ejecutadas:

- `.venv/bin/python -m pytest` → `311 passed in 1.19s`.
- `.venv/bin/python -m pip check` → `No broken requirements found.`
- `git diff --check` → sin errores.
- Scripts de reproducción con `TemporaryDirectory`, JPEG sintéticos de
  Pillow, detector stub y comparación SHA-256; sin YOLO ni fotos reales.
  El sandbox falló al iniciar (`bwrap: loopback: Failed RTM_NEWADDR`);
  las comprobaciones se ejecutaron con escalación autorizada.

Verificado: igualdad canónica de carpetas (incluidos relativos y symlinks),
rechazo de alias al propio archivo en ambas APIs, validación de carpetas en
CLI antes de construir detector, y salida hija válida. Los controles usan
biblioteca estándar y no introducen dependencias ni cambian el crop.
La suite verde no cubre los siguientes defectos.

#### R1 — Alta: el log puede truncar un original

- Ubicación: `app/processor.py:198`, escritura de `review.log`.
- Reproducción: crear `out/review.log` como hard link a `in/a.jpg` y procesar
  el lote. Termina normalmente; el hash de `a.jpg` cambia porque el log vacío
  trunca la foto. Un symlink al original tiene el mismo riesgo.
- Impacto: pérdida del original incluso con carpetas distintas.
- Criterio afectado: objetivo de protección de originales y regla de
  PLAN.md/AGENTS.md «nunca modificar imágenes originales»; la validación
  actual omite una ruta de escritura del propio procesador.
- Corrección esperada: validar también el destino del log contra los
  originales antes de cualquier escritura y rechazar con `FileExistsError`.
  Muse debe agregar primero regresiones para symlink y hard link, verificando
  hashes y ausencia de cambios en salidas y log.

#### R2 — Alta: un destino puede sobrescribir otra foto del lote

- Ubicación: `app/processor.py:182`, control limitado al `entry` actual.
- Reproducción: dos originales `in/a.jpg` y `in/b.jpg`, con `out/a.jpg`
  como hard link a `in/b.jpg`. El lote termina normalmente pero cambia el
  hash de `b.jpg` y después procesa esa foto ya recortada.
- Impacto: pérdida de un original y procesamiento de contenido modificado.
- Criterio afectado: protección de originales del objetivo y de PLAN.md;
  F2 cubre solo alias al propio archivo y resulta insuficiente para el lote.
- Corrección esperada: comparar los destinos de salida, revisión y log
  contra todos los originales del lote, incluyendo alias con nombres
  diferentes. Agregar regresiones de alias cruzados por symlink/hard link
  antes de corregir, conservando los hashes de todos los originales.

#### R3 — Media: rechazo tardío deja salidas creadas

- Ubicación: `app/processor.py:168–185`, creación de carpetas y validación
  dentro del bucle de procesamiento.
- Reproducción: `out/b.jpg` es hard link a `in/b.jpg`, con `a.jpg` ordenada
  antes. Se genera `out/a.jpg` y se crea `out/review` antes de rechazar
  `b.jpg` con `FileExistsError`.
- Impacto: una ejecución rechazada deja un lote parcialmente escrito;
  también puede sobrescribir salidas previas antes de encontrar el conflicto.
- Criterio afectado: aceptación acordada para esta iteración «en los
  rechazos […] no se crean ni sobrescriben salidas». El plan local no lo
  expresa plenamente para conflictos de archivo en un lote.
- Corrección esperada: validar todos los destinos del lote antes de crear
  directorios o procesar fotos. Agregar una regresión con conflicto en la
  segunda foto y una salida previa, comprobando que nada se crea ni cambia.
  Aclarar esa garantía en el contrato local sin debilitar la aceptación.

Entrega no aprobada. Estado devuelto a **en implementación** para Muse;
R1–R3 pendientes. No se ejecutó YOLO real porque el contrato no lo requiere.

### Revisión de correcciones y cierre — 2026-10-08

Implementación delegada como un encargo completo a OpenCode Zen, modelo
`opencode/muse-spark-1.3-contributor-free`, sesión
`ses_ee2ae3d38ffekT43RgRdAy33UB`. El subagente gestionó la ejecución;
el revisor controló su salida y revisó la entrega. Evidencia de ejecución
en `/tmp/autocrop-muse-stage05-output.jsonl` (archivo temporal local).
Confirmado en esa salida: siete regresiones fallaron antes de modificar
producción y luego pasaron. No se debilitaron las pruebas existentes.

Inspeccionados el diff de producción y tests, contrato y registro. El índice
de rutas resueltas e identidades `(st_dev, st_ino)` compara todos los destinos
contra todos los originales JPEG del lote en tiempo lineal; la comprobación
se realiza antes de `mkdir`, detector y escrituras. No se agregaron
dependencias ni cambios de selección o encuadre.

- **R1 cerrado:** el log se valida contra todos los originales; regresiones
  de symlink y hard link comprueban rechazo, hash intacto y ausencia de
  directorios/salidas nuevos.
- **R2 cerrado:** salida y revisión se comparan contra todo el lote;
  regresiones con alias cruzados de ambos tipos conservan todos los hashes.
- **R3 cerrado:** prevalidación completa antes de cualquier escritura;
  regresión con conflicto en la segunda foto conserva salida previa y log,
  no crea `review/` y no llama al detector.

Validación independiente del revisor:

- `.venv/bin/python -m pytest` → `318 passed in 1.33s`.
- `.venv/bin/python -m pip check` → `No broken requirements found.`
- `git diff --check` → sin errores.
- Script temporal adicional: salida padre válida conserva original; CLI
  rechaza salida symlink a entrada sin construir detector ni traceback;
  `process_image` rechaza review con hard link al original sin crear una
  salida inexistente ni llamar al detector. Todas las aserciones pasaron.

F1–F4 y T1–T2 verificados. Aclarada la redacción de CLI en el contrato para
expresar F3 (igualdad de carpetas antes de construir detector).
No quedan hallazgos pendientes. Etapa **completada**; etapas anteriores
preservadas y ninguna etapa siguiente iniciada. Sin corrida YOLO real,
conforme al contrato. La comprobación cubre alias preexistentes; no se
evaluaron modificaciones concurrentes del sistema de archivos.
