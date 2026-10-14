# Etapa V2-07 — Registro

## Implementación

- Modelo implementador: OpenCode Muse Spark 1.3 Free (`opencode/muse-spark-1.3-contributor-free`).
- Callers leídos antes de cambiar interfaces: `result_bytes()` solo lo usaba
  el endpoint `GET /api/jobs/{job_id}/result` y tests; `get()`/`put(bytes)`
  solo en `run_next()`/`result_bytes()`/`submit()` y tests; `put_file()` en
  `submit_file()` y tests; `run_next()` en `app/worker.py:pump_once` y tests.
  El proxy `app/frontend.py` ya reenvía por bloques (`_CHUNK` 64 KiB); sin cambios.

### Evidencia roja (tests primero, antes de producción)

- `tests/test_bounded_transfers.py` (nuevo, 9 tests F1–F4/T1–T2):
  `.venv/bin/python -m pytest tests/test_bounded_transfers.py -q` →
  **8 failed, 1 passed**. Fallos por funcionalidad pendiente
  (`AttributeError: 'S3BlobStore' object has no attribute 'get_file'`;
  el recorrido del worker seguía llamando `get()` vetado por el doble).
  El único verde era `test_f4_bytes_api_kept_for_callers` (API conservada,
  existe antes del cambio).

### Solución mínima (`app/jobs.py`)

- `MemoryBlobStore.get_file()` y `S3BlobStore.get_file()`: descarga a archivo
  por bloques de 1 MiB; S3 cierra el cuerpo en `finally` y borra el parcial
  si falla. `get()`/`put(bytes)`/`put_file()`/`result_bytes()` se conservan.
- `JobService.run_next()`: `get_file()` para la entrada y `put_file()` para
  la salida; sin `get()`/`Path.read_bytes()`/`put(bytes)` en producción.
- `JobService._require_completed()` (chequeo estado+vencimiento previo) +
  `result_to_file()`; `result_bytes()` lo reutiliza sin cambiar conducta.
- Endpoint de resultado: verifica antes de descargar, vuelca a temporal
  `mkstemp` aislado y responde `_ResultFileResponse` (subclase de
  `FileResponse` con `unlink` en `finally` de `__call__`): limpia al concluir,
  fallar o si `send` falla (desconexión). No usa `BackgroundTask` (solo corre
  tras envío exitoso); un test lo prohíbe por inspección de fuente.
- `tests/test_api_worker.py`: `test_storage_error_marks_failed…` ahora inyecta
  en `get_file(key, dest)` en vez de `get(key)` —motivo: `run_next()` ya no
  llama a `get()`; aserciones (`failed`, mensaje, 409) intactas.
- `README.md`: documenta que el servidor acota memoria pero la página usa
  `Response.blob()` (límite de memoria del cliente); para lotes grandes, `curl`.

### Evidencia verde

- `.venv/bin/python -m pytest tests/test_bounded_transfers.py tests/test_api_worker.py tests/test_job_stores.py -q` → 34 passed
  (tras un ajuste: el doble cuenta `put_file` de subida+salida; el test limpia
  el contador entre ambas fases).
- Suite completa `.venv/bin/python -m pytest` → **475 passed, 1 skipped**.
  Los 4 tests de `tests/test_frontend_browser.py` erroraban por entorno
  (`fixture 'page' not found`: faltaban `playwright` y `pytest-playwright`
  en `.venv` pese a estar declarado el extra dev); permitido por el encargo,
  se instaló extra dev + Chromium
  (`pip install playwright pytest-playwright>=0.7.0`,
  `python -m playwright install chromium`) y pasaron. Sin nuevas dependencias
  de producto (`pip check` limpio en ambos pasos).
- `.venv/bin/pip check` → `No broken requirements found`.
- `git diff --check` → limpio.
- Criterios: F1 (ciclo con doble que veta `get`/`put`/`Path.read_bytes`,
  ZIP byte a byte), F2 (404/409/410, frontera exacta TTL con reloj inyectado),
  F3 (error entrada/salida/preparación → `failed`/409 sin parcial; limpieza
  de temporal en éxito, 409 y `send` fallido a nivel ASGI), F4 (`result_bytes`,
  `get`/`put`, `submit(bytes)` y motor V1 intactos), T1 (sin materialización;
  S3 cierra cuerpos), T2 (rojo previo + suite/pip/diff).

### Archivos

- Modificados: `app/jobs.py`, `tests/test_api_worker.py`, `README.md`,
  `.plans/v2/07-transferencias-acotadas/plan.md` (estado).
- Creados: `tests/test_bounded_transfers.py`.

### Pendiente (para revisión/director)

- Benchmark con RustFS y archivo grande integrado en V2-10, no aquí.
- Cuota global de disco fuera de alcance del contrato.

### Entrega 2 — R1/R2


- Modelo implementador: OpenCode Muse Spark 1.3 Free (mismo que entrega 1).
- Se conserva toda la evidencia previa de este registro y la sección Revisión.

#### Evidencia roja (regresiones primero)

- `.venv/bin/python -m pytest tests/test_bounded_transfers.py -q` →
  **1 failed, 13 passed**: `test_f2_range_requests_ignored_with_full_200`
  (`assert 206 == 200` con `Range: bytes=0-2`; `bytes=bogus` daba 400).
  Regresión R1 demostrada a nivel HTTP antes del fix.
- Detección R2 sin editar producción (script `/tmp`, doble guardado del test
  contra variante `fh.write(body.read())` sin límite): `AssertionError:
  bounded transfer must read 1..1048576, got None`. La prueba reforzada
  rechaza la sustitución del director.

#### Solución mínima (`app/jobs.py`)

- R1: `_ResultFileResponse.__call__` filtra la cabecera `range` del scope
  antes de delegar a `FileResponse`: siempre 200 + ZIP completo, con el
  `finally` de limpieza intacto.
- R2: helper `_drop()` sustituye los 4 bloques `unlink` repetidos del endpoint
  (mismo comportamiento); el `except Exception` genérico ahora limpia y
  relanza en vez de informar errores de estado/Redis como 409 faltante.
- Tests reescritos en `tests/test_bounded_transfers.py` (14 tests, solo API
  pública `create_app`/stores): `_GuardedBody` rechaza `read()` sin `n` o con
  `n` desmedido y fuerza ≥3 bloques de ≤1 MiB; fallos parciales de
  lectura/escritura S3 con cierre y borrado del parcial; fallo parcial del
  worker con limpieza de temporal espiado y ausencia de blob de salida; ASGI
  real vía `create_app(svc)` con `send` fallido y cancelado, ambos con cleanup.
  Eliminados `inspect.getsource` y las tautologías (`or True`,
  `orig is not None`).

#### Evidencia verde

- `.venv/bin/python -m pytest tests/test_bounded_transfers.py tests/test_api_worker.py tests/test_job_stores.py` → **39 passed**.
- Suite completa `.venv/bin/python -m pytest` → **480 passed, 1 skipped**.
- `.venv/bin/pip check` → `No broken requirements found`.
- `git diff --check` → limpio.
- Sin nuevas dependencias de producto; planificación del director intacta
  (`.plans/v2/PLAN.md` y etapas 08–10 no tocadas).

#### Archivos entrega 2

- Modificados: `app/jobs.py`, `tests/test_bounded_transfers.py`.
- Sin cambios: `tests/test_api_worker.py`, `README.md` (de entrega 1).

## Revisión

### Primera revisión del director — 2026-10-14

- Línea de base previa independiente: `.venv/bin/python -m pytest tests/test_api_worker.py tests/test_job_stores.py tests/test_frontend.py -q` → 43 pruebas pasaron; warning preexistente Starlette/httpx.
- Primera entrega: OpenCode sesión `ses_ec3e53272ffe0745hM6E3Ar5m6`, proceso terminado con código 0; logs `/tmp/v2-07-muse/entrega-1.jsonl` y `.stderr`. Modelo listado por `opencode models`; precio Free confirmado en https://opencode.ai/v2/docs/console/models/ el 2026-10-14, elegido por petición expresa y aptitud para la etapa.
- Revisión independiente focal: tests de transferencias, API/worker, adaptadores y proxy → 52 pruebas pasaron. Lectura del diff completo de producción, README, test modificado y suite nueva; planificación previa 08–10 excluida de la entrega.
- **R1 — pendiente; F2, compatibilidad HTTP.** `app/jobs.py:385–394, 483–484`: heredar FileResponse activa semántica Range nueva. Comparación independiente con `HEAD:app/jobs.py`: `Range: bytes=0-2` cambia 200/cuerpo completo por 206/cuerpo parcial; Range inválido cambia 200 por 400. Impacto: el endpoint deja de garantizar ZIP íntegro y códigos existentes. Esperado: regresión pública HTTP antes del fix, ignorar Range como antes y conservar archivo completo/200, sin perder limpieza garantizada.
- **R2 — pendiente; F3/T1/T2, cobertura y aserciones.** `tests/test_bounded_transfers.py:148–182, 208–210, 227–284, 298`: la prueba S3 no limita `read(n)` y usa 40 KiB, por debajo del bloque; una sustitución temporal en memoria por `body.read()` sin límite conserva el test verde (1 passed). El test de desconexión instancia helper privado en vez de probar la API; faltan fallos parciales y comprobación de temporales del worker. Hay inspección de código fuente y una aserción `or True` que no verifican contratos. Impacto: futuros defectos de memoria/limpieza pasan inadvertidos. Esperado: cuerpo S3 que rechace lecturas no acotadas y fuerce varios bloques; fallo de lectura tras parcial y fallo de escritura con cierre/limpieza; pruebas públicas ASGI de API con send fallido/cancelado; comprobar temporales y ausencia de salida parcial ante fallos del worker; eliminar aserciones tautológicas/introspección. La prueba reforzada debe rechazar la sustitución sin límite sin editar producción para esa comprobación.
- Confianza del director en primera entrega: **76 %**, juicio basado en tests focales verdes y solución de archivos correcta en ruta habitual, limitado por la regresión HTTP demostrada y huecos de limpieza/memoria en aserciones.
- Se devuelve a implementación para corregir R1 y reforzar R2; no se cierra la etapa.

### Revisión final y cierre del director — 2026-10-14

- Segunda entrega recibida con salida 0, misma sesión OpenCode; logs `/tmp/v2-07-muse/entrega-2.jsonl` y `.stderr`. Inspeccionado diff final completo y todos los tests nuevos, incluyendo el cambio de inyección de fallo del test histórico sin debilitar sus aserciones. No se modificó el motor, V1, dependencias de producto, Compose ni proxy; este último conserva transmisión por bloques de 64 KiB.
- **R1 resuelto:** regresión HTTP agregada antes de la corrección (1 failed, 13 passed según log de Muse); filtrado de Range únicamente en el scope de entrega del archivo. La prueba pública verifica 200, ZIP entero y Content-Length tanto con Range válido como inválido. El finally de limpieza sigue cubierto.
- **R2 resuelto:** pruebas S3 con varios bloques y rechazo de read sin límite; fallo de lectura y escritura después de parcial, cierre de cuerpo y borrado; fallo parcial de publicación con limpieza del directorio del worker y eliminación de salida; send fallido y cancelación a través de la aplicación ASGI pública. Quitadas aserciones tautológicas y comprobaciones de fuente/helpers privados. El director volvió a sustituir get_file solo en memoria por una variante body.read() sin límite: la prueba ahora la rechaza con `AssertionError: bounded transfer must read 1..1048576, got None`. No se alteró producción para esta comprobación.

#### Comprobaciones finales independientes

- `.venv/bin/python -m pytest -o addopts='' -q tests/test_bounded_transfers.py tests/test_api_worker.py tests/test_job_stores.py tests/test_frontend.py /tmp/v2-07-review/test_director_acceptance.py` → **62 passed**, 1 warning. Incluye 57 pruebas del repositorio y 5 casos adicionales del director: autorización antes de vencer con eliminación concurrente de objetos, rechazo previo a obtener objeto, dos descargas simultáneas con temporales aislados y desconexión al enviar cabeceras/cuerpo. Todos comparan resultados observables y limpieza; el script de revisión está conservado en `/tmp/v2-07-review/test_director_acceptance.py`.
- `.venv/bin/python -m pytest -o addopts='' -q -rs` → **480 passed, 1 skipped, 1 warning**, 28.15 s. Skip previo: `tests/test_archive.py:203`, un nombre de entrada vacío no se puede almacenar con zipfile. Warning previo: deprecación de httpx en Starlette TestClient. Navegador Chromium incluido; no se omitieron pruebas de esta etapa.
- `.venv/bin/python -m pip check` → `No broken requirements found.`
- `git diff --check` → limpio.

#### Criterios contrastados con evidencia

| Criterio | Evidencia observada |
| --- | --- |
| F1 | Ciclo de subida/worker/descarga con dobles que vetan get/put(bytes)/Path.read_bytes; comparación exacta del resultado. Tests históricos con process_archive y detector controlado conservan resumen/progreso y contenido. |
| F2 | MIME y nombre de descarga, códigos 404/409/410, TTL exacto, objeto ausente y Range ignorado; caso independiente de autorización antes del vencimiento que termina después de la limpieza de objetos. |
| F3 | Temporales eliminados en éxito, preparación fallida, publicación parcial, send fallido y cancelación; S3 cierra cuerpo y elimina parcial tras errores de lectura/escritura. Dos solicitudes simultáneas usan temporales distintos. |
| F4 | result_bytes/get/put/submit(bytes) siguen disponibles y compatibles; suite V1 verde, sin cambios en motor o contratos/evidencia V1. |
| T1 | Lectura S3 de 1 MiB, carga a RustFS desde archivo, FileResponse por bloques; producción no usa bytes completos para ZIP. Guardas verificadas mediante sustitución deliberadamente incorrecta. Proxy revisado sin necesidad de cambios. |
| T2 | Evidencia roja inicial y regresión roja de R1; revisión de aserciones, suite de etapa/completa y pip/diff independientes desde .venv. |

- Entregas: **2**. Hallazgos de revisión corregidos: **2**. Comprobaciones independientes del director: **9 grupos** (línea de base, tests focales de primera entrega, comparación Range con baseline, sustitución sin límite inicial, tests focales finales con 5 casos extra, rechazo de sustitución final, suite completa, pip check y diff check). Lectura/revisión documental y de código adicional a esos grupos.
- Confianza estimada por el director: **76 % en la primera entrega; 94 % en la etapa final**. Son juicios, no probabilidades medidas. La primera estaba limitada por R1/R2; la final tiene todos los criterios verificados y está limitada por no ejecutar RustFS/ZIP cercano a 500 MiB, comprobación expresamente reservada para V2-10. Tampoco se promete RAM fija de YOLO o cuotas de disco; el navegador conserva Response.blob(), documentado en README.
- Se considera crítica por integridad del ZIP y limpieza de archivos: supera el umbral del 90 % para esta clase de etapa. Por instrucción explícita del usuario, no se prepara ni inicia ni solicita aprobación de V2-08 en esta sesión; su contrato pendiente previo permanece intacto.

**Cierre:** F1–F4 y T1–T2 verificados; R1/R2 resueltos, sin hallazgos abiertos ni comprobaciones exigidas pendientes de V2-07. Etapa completada. Se conservan logs de revisión y herramientas dev en .venv; no se levantó Docker, no se crearon recursos Docker ni se tocaron originales. No se hizo commit ni publicación automática.
