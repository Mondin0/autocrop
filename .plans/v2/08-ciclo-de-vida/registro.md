# Etapa V2-08 — Registro

## Implementación

- Modelo: `opencode/muse-spark-1.3-contributor-free` (el del encargo;
  coste input/output/cache_read 0 según catálogo; apto coding/agentic).
  Motivo: implementador por defecto OpenCode Muse según AGENTS.md.
  Sesión/comando: sesión OpenCode en
  `/home/gabriel-mondino/Desktop/proyectos/personal/autocrop`, sin
  subagentes (un proveedor distinto no puede asumirlos). Baseline
  preservado: `/tmp/v2-08-baseline.diff`, snapshot `/tmp/v2-08-initial`;
  no se tocó V1, otras etapas, dependencias ni commits.
- Archivos:
  - `app/jobs.py`: reclamación durable (`claim` atómico vía `LMOVE`
    queue→active en Redis y doble en memoria con igual contrato
    observable; `release` solo tras terminal persistido; `claimed`,
    `unqueue`), `reconcile()` (queued/processing reclamados → failed
    visible con `current=None`, `INTERRUPTED_ERROR` y `finished_at`;
    terminal reclamado conserva resultado y solo libera; fallos de
    carga/guardado conservan la reclamación), `_fail` con `finished_at`
    y liberación posterior al guardado, `submit`/`submit_file` que
    revierten objeto+estado+cola propios sin 202 ante fallos (con
    `unqueue` best-effort para el caso enqueue-que-ejecuta-y-luego-falla
    y aviso de reversión fallida), `cleanup` de completed+failed tras
    3 h exactas (`>` TTL; frontera inclusiva conserva), sellado de
    retención al primer encuentro para failed históricos sin
    `finished_at`, borrado de estado solo tras ambos objetos,
    idempotencia ante ausentes, aislamiento por trabajo con error
    registrado, y barrido de huérfanos `jobs/` con antigüedad > TTL vía
    `scan_prefix` (paginación S3 sin leer cuerpos; memoria con mtimes).
    Fallos de guardado de progreso/terminal nunca devuelven éxito:
    el de progreso aborta a failed visible y el de terminal propaga
    conservando la reclamación.
  - `app/worker.py`: `pump_once` intenta `cleanup()` antes de cada
    trabajo y en cada vuelta ociosa (nunca durante inferencia),
    reconcilia ante transitorios y propaga para esperar sin descartar;
    `main` reconcilia al arrancar.
  - `tests/test_lifecycle.py` (nuevo, 17 tests): F1 reinicio/FIFO y
    pump ante transitorio; F2 atomicidad de reclamación y fallos de
    estado/progreso/terminal; F3 frontera TTL, activos vigentes y failed
    históricos; F4 borrados fallidos con reintento, idempotencia y
    aislamiento; F5 limpieza entre trabajos sin hueco ocioso vía worker;
    F6 fallos de subida/guardado/encolado, reversión fallida registrada
    y barrido de huérfanos con prefijo/paginación; paridad Redis.
  - `tests/test_job_stores.py`: dobles extendidos a la nueva interfaz
    (`lmove`/`lrem`/`lrange`, `get_paginator`); aserciones intactas.
- Evidencia roja `/tmp/v2-08-red.log` (462 líneas):
  `.venv/bin/python -m pytest tests/test_lifecycle.py -q` → 16 FAILED
  funcionales por `NotImplementedError` con estructura mínima
  (importación OK) y `PYTEST_EXIT:1`; el test de frontera TTL ya
  pasaba como regresión.
- Evidencia verde `/tmp/v2-08-green.log` (comandos y códigos reales):
  `pytest tests/` → 497 passed, 1 skipped, `SUITE_EXIT:0`;
  `pip check` → sin roturas, `PIP_EXIT:0`; `git diff --check` →
  `DIFFCHECK_EXIT:0`; etapa → 17 passed, `STAGE_EXIT:0`;
  `pyproject.toml` sin diff (sin nuevas dependencias).
- Criterios cubiertos: F1–F6 y T1–T2 a nivel unitario con reloj y
  almacenes controlados.
- Decisión con impacto en test previo (para revisión del director):
  la limpieza previa a cada trabajo se implementó en
  `worker.pump_once` (único consumidor productivo de `run_next`) en vez
  de dentro de `run_next`, para no alterar los conteos de `cleanup()`
  a nivel servicio que fijan los tests de V2-03
  (`test_f6_cleanup_deletes_only_expired` sigue verde sin cambios).
  F5 se verifica vía worker con cola ocupada.
- Pendientes (no bloquean la etapa): validación con Redis/RustFS reales,
  corpus fotográfico, lote grande, reinicio y expiración integrales
  (contrato los asigna a V2-10); cierre del director.

## Revisión

### Primera entrega — revisión del director

Confianza inicial estimada: 65 %. Suite verde no cubre pérdidas por Redis parcial ni barrera de reconciliación. Revisión del diff completo contra `/tmp/v2-08-initial`, tests nuevos y dobles previos (aserciones previas intactas).

Hallazgos pendientes:
- R1 — `app/jobs.py:_sweep_orphans`: ignora errores de `load` y toma el índice como prueba de ausencia. Reproducción independiente: queued antiguo, load falla, cleanup elimina su input (retained=False). Impacto: pérdida de entrada válida; F3/F6. Debe verificar ausencia de estado por UUID directamente y conservar objetos ante incertidumbre/lectura fallida, incluso si falta indexado.
- R2 — `app/jobs.py:_sweep_orphans`: borra cualquier clave antigua jobs/. Reproducción independiente jobs/foreign-name/file.txt eliminada. F6 aislamiento por prefijo/UUID. Restringir claves a objetos input.zip/output.zip de UUID válido; conservar claves ajenas, recientes y reclamadas.
- R3 — `app/worker.py:main/pump_once`, `app/jobs.py:reconcile`: errores al reconciliar se silencian y no existe barrera reintentable antes del siguiente consumo. F1/F2. Reconciliar antes de consumir al arrancar y tras errores; con lectura/guardado/liberación pendiente no consumir, esperar y reintentar cuando Redis vuelva. Regresión que ejecute ciclo worker, no solo invocación directa de reconcile.
- R4 — `app/jobs.py:submit/submit_file/_revert_new`: subida fuera del try no intenta reversión si publicó y luego falló; reversión elimina estado/input aunque enqueue pudo ser reclamado concurrentemente por el único worker. F6/F2. Regresiones para subida que escribe y falla, ambas rutas incl. HTTP no 202; intercalación enqueue→claim→error sin destruir objeto/estado reclamados; conservar evidencia y limpiar cuando corresponda.
- R5 — `tests/test_lifecycle.py`: falta fallo de borrado output después de input borrado, retención failed en frontera exacta y guardado failed fallido/reconcile repetido. F2/F3/F4, T2. Agregar regresiones antes de correcciones; evitar asserts de FIFO con payloads idénticos y acceso privado innecesario.

Los resultados de reproducción son observados por director; no constituyen implementación. Integración Redis real reservada explícitamente a V2-10. Todas las correcciones deben venir de Muse en misma sesión, con rojo/verde y evidencia preservada.

### Corrección R1–R5 — segunda entrega del implementador

- Modelo: `opencode/muse-spark-1.3-contributor-free`, corroborado en
  `/tmp/v2-08-model.json` (`cost: {input: 0, output: 0, cache_read: 0}`).
  Sesión exacta: `ses_ec3c64439ffeGB0GNnbO45W3gD`. Corrección de
  atribución de la primera entrega: hubo un subagente coordinador
  externo que invocó OpenCode CLI; el implementador Muse no fue
  sustituido por otro proveedor.
- Correcciones (solución mínima, sin dependencias, sin otra etapa ni
  V1, sin commits, sin evadir permisos):
  - R1/R2 — `app/jobs.py:_sweep_orphans` reescrito: ya no usa el
    índice como prueba de ausencia; por cada clave candidata verifica
    el estado con `load` directo del UUID. Fallo de lectura conserva
    el objeto; índice ausente no implica ausencia si `load` encuentra
    el registro. `_job_object_id` restringe la propiedad a
    `jobs/<uuid>/input.zip|output.zip` con UUID válido; layouts
    ajenos, recientes y reclamados se conservan.
  - R3 — barrera de reconciliación en `app/worker.py:pump_once`:
    reconcilia antes de consumir; si reconciliar falla o quedan
    reclamaciones pendientes (`PendingClaimsError` nuevo en
    `app/jobs.py`), no consume, registra y propaga para esperar y
    reintentar. Se mantiene la reconciliación al arrancar en `main` y
    tras errores transitorios.
  - R4 — `submit`/`submit_file` envuelven también la subida: si
    publica parcial y luego falla, `_revert_new` la elimina.
    `_revert_new` preserva estado y objeto cuando el id ya fue
    reclamado concurrentemente (o la reclamación es incierta);
    la ruta HTTP sigue sin devolver 202 ante estos fallos.
  - R5 — regresiones agregadas antes de corregir: fallo de borrado de
    output tras input borrado, frontera exacta de retención failed,
    guardado failed fallido con reconcile repetido; FIFO con payloads
    distinguibles y sin acceso privado (`_queue`/`_r` eliminados de los
    tests; el doble `_FakeRedis` es API propia del test).
- Ajustes a tests previos exigidos por el contrato corregido (para
  revisión): `test_f6_orphan_sweep_*` usan ahora huérfanos con UUID
  válido (R2 restringe la propiedad); el conteo de reconciliaciones
  del test de pump refleja la barrera previa al consumo.
- Evidencia roja `/tmp/v2-08-red-2.log` (233 líneas): 9 FAILED
  funcionales reales antes de la lógica correctiva
  (`ImportError` de `PendingClaimsError`, barrido que eliminaba lo
  válido/ajeno, consumo pese a barrera, parciales sin revertir,
  trabajo reclamado destruido).
- Evidencia verde `/tmp/v2-08-green-2.log`: etapa 29 passed
  (`STAGE_EXIT:0`); completa 509 passed, 1 skipped (`SUITE_EXIT:0`);
  `pip check` sin roturas (`PIP_EXIT:0`); `git diff --check` limpio;
  `pyproject.toml` sin diff.
- Logs íntegros externos del coordinador: `/tmp/v2-08-muse-2.jsonl` y
  `/tmp/v2-08-muse-2.stderr` (los genera el harness, no el
  implementador).
- Pendientes: cierre del director; validación con servicios reales y
  fotos en V2-10.

### Segunda entrega — revisión del director

R1/R2/R3 y fronteras R5 verificadas en código y regresiones nuevas. R4 parcial: el chequeo de claimed antes de unqueue deja una ventana de carrera. Reproducción independiente guardada en `/tmp/v2-08-director-r4.log`: unqueue intercala claim después del chequeo; `claimed_state_retained=False`, `claimed_input_retained=False`. Impacto F2/F6: destruye trabajo reclamado. Corrección: coordinar retirada de cola y decisión de reversión usando resultado de operación atómica, preservar reclamado o terminal si worker ganó; verificar también worker completado/liberado antes de respuesta perdida. Regresiones antes de implementación, memoria y adaptador Redis. Pendiente este único grupo R4; repetir suite y checks tras corregir.

### Corrección R4c (TOCTOU) — tercera entrega del implementador

- Modelo: `opencode/muse-spark-1.3-contributor-free`, coste corroborado
  en `/tmp/v2-08-model.json` (`cost: {input: 0, output: 0,
  cache_read: 0}`). Sesión exacta: `ses_ec3c64439ffeGB0GNnbO45W3gD`;
  coordinación externa vía CLI por subagente coordinador; implementador
  Muse no sustituido.
- Causa: `_revert_new` decidía con un chequeo `claimed()` previo al
  `unqueue`; el worker podía reclamar entre ambos y el `delete`
  posterior destruía estado/input (e incluso un terminal completado y
  liberado).
- Corrección (`app/jobs.py`, sin dependencias, sin otra etapa ni V1,
  sin commits, sin evadir permisos): eliminado el chequeo previo
  (`_claimed_by_worker`); la decisión usa el resultado booleano del
  `unqueue` atómico (`_took_back_from_queue`): `True` retiró la única
  copia en cola y el worker jamás podrá reclamarla (reversión total
  segura); `False` implica que el worker pudo reclamar, completar o
  liberar (se preservan estado y objetos); fallo del propio `unqueue`
  también preserva. `MemoryStateStore.unqueue` retira todas las
  ocurrencias (LREM con count 0 ya lo hacía en Redis).
- Regresiones primero (`tests/test_lifecycle.py`, 4 tests `r4c`):
  reclamo dentro de `unqueue` y completado+liberado antes del ack
  perdido, en Memory y adaptador Redis, por `submit` y `submit_file`;
  HTTP nunca 202 con trabajo preservado; FIFO de los demás jobs
  intacto. Rojo funcional en `/tmp/v2-08-red-3.log` (114 líneas, 4
  FAILED con estado destruido) antes de la lógica correctiva.
- Verde en `/tmp/v2-08-green-3.log` (comandos y códigos reales): etapa
  33 passed (`STAGE_EXIT:0`); completa 513 passed, 1 skipped
  (`SUITE_EXIT:0`); `pip check` sin roturas; `git diff --check`
  limpio; `pyproject.toml` sin diff. Toda la evidencia anterior queda
  intacta.
- Criterios: grupo R4 completo (F2/F6); resto sin cambios.
- Logs externos del coordinador: `/tmp/v2-08-muse-3.jsonl` y
  `/tmp/v2-08-muse-3.stderr` (los genera el harness).
- Pendientes: cierre del director; servicios reales y fotos en V2-10.

### Segunda entrega — revisión del director

R1/R2/R3 y fronteras R5 verificadas en código y regresiones nuevas. R4 parcial: el chequeo de claimed antes de unqueue deja una ventana de carrera. Reproducción independiente guardada en `/tmp/v2-08-director-r4.log`: unqueue intercala claim después del chequeo; `claimed_state_retained=False`, `claimed_input_retained=False`. Impacto F2/F6: destruye trabajo reclamado. Corrección: coordinar retirada de cola y decisión de reversión usando resultado de operación atómica, preservar reclamado o terminal si worker ganó; verificar también worker completado/liberado antes de respuesta perdida. Regresiones antes de implementación, memoria y adaptador Redis. Pendiente este único grupo R4; repetir suite y checks tras corregir.

### Tercera entrega — revisión del director

La decisión basada en retirar cola elimina la carrera de R4 en memoria/Redis y preserva terminal liberado. Revisión de regresiones y ejecución independiente suite: salida 0 (log `/tmp/v2-08-director-suite.log`), pip check y diff check salida 0.

R4/F6 todavía pendiente: `app/jobs.py:_took_back_from_queue` devuelve False al fallar enqueue ANTES de insertar id y no intenta revertir nada. Reproducción independiente `/tmp/v2-08-director-enqueue-before.log`: tras TTL, retained_states=1, retained_blobs=1 y claim=None, AssertionError. Fuga permanente queued no reclamado. Distinguir encolado no ejecutado de trabajo tomado/completado mediante comprobaciones posteriores a retirada atómica, conservando ante incertidumbre; regresiones antes de corregir para enqueue antes de efecto, fallos de lectura/retirada y carreras previas, ambas rutas. Registrar reversión fallida y futuro barrido si falla borrado del objeto. No basta conservar todo como solución al TOCTOU.

### Corrección R4d (enqueue previo) — cuarta entrega del implementador

- Modelo: `opencode/muse-spark-1.3-contributor-free`, coste corroborado
  en `/tmp/v2-08-model.json` (`cost: {input: 0, output: 0,
  cache_read: 0}`). Sesión exacta: `ses_ec3c64439ffeGB0GNnbO45W3gD`;
  coordinación externa vía CLI por subagente coordinador; implementador
  Muse no sustituido.
- Causa: con `unqueue False` la entrega 3 conservaba siempre, también
  cuando el enqueue falló antes de insertar (estado+blob propios sin
  cola ni reclamo: fuga permanente, retained_states=1,
  retained_blobs=1).
- Corrección (`app/jobs.py`, sin dependencias, sin otra etapa ni V1,
  sin commits, sin evadir permisos): tras el retiro atómico con
  resultado `False`, `_worker_may_own` distingue con comprobaciones
  posteriores (sin TOCTOU: ya no es posible un reclamo futuro porque el
  id está ausente de la cola y nadie más lo conoce): reclamo presente
  o estado terminal prueban intervención del worker (se conserva);
  lectura de reclamaciones/estado fallida conserva y registra; solo un
  estado legible no terminal sin reclamo demuestra que el enqueue no
  tuvo efecto (reversión total). `_took_back_from_queue` pasa a
  tri-estado: el fallo de la propia retirada (`None`) conserva porque
  el worker aún podría reclamar. El fallo al borrar el objeto registra
  reintento futuro del barrido de huérfanos.
- Regresiones primero (`tests/test_lifecycle.py`, 4 tests `r4d`):
  fallo antes de insertar en Memory/Redis por `submit` y
  `submit_file`, HTTP sin 202 ni fuga, incertidumbre de
  retirada/lectura que conserva y registra, borrado de objeto fallido
  con recuperación posterior por barrido; carreras y FIFO previos
  siguen verdes. Rojo funcional en `/tmp/v2-08-red-4.log` (3 FAILED
  por fuga permanente) antes de corregir.
- Verde en `/tmp/v2-08-green-4.log` (comandos y códigos reales): etapa
  37 passed (`STAGE_EXIT:0`); completa 517 passed, 1 skipped
  (`SUITE_EXIT:0`); `pip check` sin roturas; `git diff --check`
  limpio; `pyproject.toml` sin diff. Evidencia anterior intacta.
- Corrección factual del rojo-2 (con el log existente
  `/tmp/v2-08-red-2.log`, sin inventar evidencia): contiene 9 FAILED,
  de los cuales 8 son funcionales (aserciones de comportamiento:
  `assert 1 == 2`, eliminaciones/retenciones indebidas, `DID NOT
  RAISE`, estado destruido) y 1 es de importación
  (`test_r3_barrier_blocks_consume_while_claims_pending`,
  `ImportError: PendingClaimsError`), que NO cuenta como rojo
  funcional según AGENTS.md. La mención de "9 FAILED funcionales" en
  la entrega 2 queda corregida a 8 funcionales + 1 importación.
- Criterios: rama R4/F6 restante completa; resto sin cambios.
- Logs externos del coordinador: `/tmp/v2-08-muse-4.jsonl` y
  `/tmp/v2-08-muse-4.stderr` (los genera el harness).
- Pendientes: cierre del director; servicios reales y fotos en V2-10.

### Cierre del director — 2026-10-14

Cuatro entregas de Muse en la misma sesión `ses_ec3c64439ffeGB0GNnbO45W3gD`, mediante el mismo coordinador creado sin historial. Cinco grupos de hallazgos R1–R5 resueltos; R4 requirió completar dos ventanas adicionales (carrera durante retirada y encolado no ejecutado). Sin hallazgos pendientes de esta etapa. Revisión del diff completo de archivos afectados respecto del snapshot inicial, pruebas nuevas completas y extensión de dobles; el contrato solo cambió de estado hasta este cierre. Cambios previos de V2-07, README, índice y otras carpetas preservados. El director no implementó código productivo.

Verificación criterio por criterio:
- F1: tests de reinicio sobre stores compartidos, reclamado queued/processing fallido, terminal reclamado conservado, FIFO con payloads distinguibles; barrera previa en pump_once y arranque main inspeccionados.
- F2: Redis LMOVE LEFT→RIGHT atómico y paridad memoria; fallos al guardar processing/progreso/completed/failed conservan reclamación o persisten failed antes de liberar. Reconciliación repetida y bloqueo de consumo mientras quedan reclamaciones. Retirada de cola atómica en reversión y preservación si worker ganó/completó.
- F3: frontera inclusiva completed/failed, HTTP 200→410→404, activos conservados, retención iniciada para failed histórico; lecturas fallidas no convierten objetos válidos en huérfanos.
- F4: fallos de input/output y state-delete, objetos ausentes, reintento y aislamiento entre trabajos; regresión output fallido después de borrar input.
- F5: pump_once limpia antes de cada consume y vuelta ociosa; cola sin hueco ocioso y borrado antes de nueva inferencia cubiertos. Limpieza no se introduce durante inferencia.
- F6: submit y submit_file, upload/save/enqueue antes/después de efecto, HTTP sin 202, aislamiento FIFO, reclamación durante reversión y terminal antes de respuesta perdida; incertidumbre conserva y registra; rollback de objeto fallido termina en barrido posterior. Huérfanos >TTL únicamente jobs/<UUID>/input.zip|output.zip, estado verificado directamente, reclamación protegida, objetos recientes/ajenos conservados y listado S3 paginado sin cuerpos.
- T1: no nuevas dependencias ni servicios; reaprovecha Redis/RustFS y motor existente. Errores legibles y registrados.
- T2: evidencia roja funcional preservada de las cuatro entregas; rojo2 distingue ocho fallos funcionales y un ImportError que no cuenta como evidencia funcional. Tests con reloj/stores controlados. Checks independientes siguientes.

Comandos independientes del director (todos salida 0):
- `.venv/bin/python -m pytest tests/ -q` → 517 passed, 1 skipped; `/tmp/v2-08-director-final-suite.log`. Conteo corroborado sobre marcas de resultado, pues addopts=-q más -q suprime el resumen. Skip histórico de nombre ZIP vacío no construible con zipfile (`tests/test_archive.py:test_rejects_dangerous_names`), no relacionado con ciclo de vida.
- `.venv/bin/python -m pytest tests/test_lifecycle.py -o addopts='' -q -r s` → 37 passed; `/tmp/v2-08-director-stage.log`.
- `.venv/bin/python -m pip check` → No broken requirements found; `/tmp/v2-08-director-final-pip.log`.
- `git diff --check` → limpio; `/tmp/v2-08-director-final-diffcheck.log`.
- Probes independientes por `.venv/bin/python` sobre R1/R2/R3/R4 → asserts verdes, `/tmp/v2-08-director-final-probes.log`: load fallido conserva entrada queued; clave ajena conservada; claim intercalado en unqueue conserva estado/input; enqueue antes de efecto sin fuga; reconcile fallido impide consumo. Las reproducciones rojas anteriores permanecen en registro y logs.

Confianza del director (juicio, no probabilidad medida): primera entrega **65 %**, etapa final **93 %**. La primera no cubría fallos parciales que podían perder datos; la final cubre criterios y carreras con ejecución independiente, pero no sube por faltar validación con Redis/RustFS reales, reinicio de contenedores y expiración integrada, asignada explícitamente a V2-10. Etapa crítica por integridad de entradas/resultados. Solo se admite un worker; inferencias largas pueden retrasar borrado físico, no disponibilidad de descarga. Ante incertidumbre de reversión se conservan datos y se registra el fallo, conforme al alcance sin alta disponibilidad.

Estado: completada para el contrato V2-08. Pendientes de aceptación integral V2-10: servicios reales, fotos autorizadas/revisión visual, lote grande, reinicio y expiración integrales. No se declara V2 cerrada; por instrucción explícita del usuario no se inicia ni prepara otra etapa. V1 permanece intacta.
