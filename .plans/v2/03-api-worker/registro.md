# Etapa V2-03 — Registro

## Implementación

Delegación: el usuario encargó implementar únicamente V2-03 según AGENTS.md y el
contrato aprobado en `.plans/v2/03-api-worker/plan.md` (aprobación del contrato
registrada en el plan el 2026-10-10). No se pidió aprobación del contrato ni
V2-04; no se tocó V1 ni archivos de V2-04 (`git status` solo muestra
`app/jobs.py`, `tests/test_api_worker.py`, `pyproject.toml` y este plan).

Archivos:

- `app/jobs.py` (nuevo): `JobService` (submit/get/run_next/result_bytes/cleanup),
  `create_app()` con `POST /api/jobs` (202, multipart `file`, lectura por bloques
  de 1 MiB con límite 500 MiB → 413 y temporal descartado), `GET /api/jobs/{id}`
  (200/404) y `GET /api/jobs/{id}/result` (200 ZIP exacto / 409 / 410 / 404),
  `MemoryStateStore`/`MemoryBlobStore` (dobles con la misma interfaz),
  `RedisStateStore`/`S3BlobStore` (adaptadores finos sin dependencias nuevas;
  validación con servicios reales pendiente de etapa posterior).
- `tests/test_api_worker.py` (nuevo, 15 tests F1–F6/T1 más errores de
  almacenamiento y campo `file`).
- `pyproject.toml`: agregadas `fastapi>=0.115` y `python-multipart>=0.0.18`
  (únicas dependencias nuevas; Redis/S3 se inyectan como clientes, sin
  dependencias duras).

Señal roja (tests primero, contra `app/jobs.py` mínimo con
`NotImplementedError`): `.venv/bin/python -m pytest tests/test_api_worker.py -q`
→ 15 FAILED, causa `NotImplementedError` en `app/jobs.py:29` (fallo funcional
por lógica pendiente, no de instalación/importación).

Comandos y resultados reales (desde `.venv`):

- `.venv/bin/pip install 'fastapi>=0.115' 'python-multipart>=0.0.18'` → instaló
  fastapi-0.143.0, starlette-1.7.0, pydantic-2.14.0, python-multipart-0.0.32.
- `.venv/bin/python -m pytest tests/test_api_worker.py` → 15 passed in 0.56s.
- `.venv/bin/python -m pytest` (suite completa) → 399 passed, 1 skipped in 9.53s.
- `.venv/bin/pip check` → No broken requirements found.

Criterios cubiertos: F1 (202/UUID/`queued`, 413 por límite medido en recepción,
campo `file` exigido), F2 (ciclo queued→processing→completed, invariantes
`processed == saved + review` y `processed <= total`, campos exactos V2-02,
404), F3 (un trabajo por `run_next` en orden FIFO, claves `jobs/{uuid}/…`
aisladas, `completed` solo tras publicar el ZIP en el blob), F4 (`failed` con
mensaje legible, sin ZIP parcial: resultado 409 y objeto de salida eliminado),
F5 (bytes exactos del ZIP solo hasta 3 h desde `finished_at`; 409/410/404
acordados), F6 (`cleanup()` elimina estado+objetos solo de completados vencidos
y respeta el límite), T1 (el `process_fn` por defecto es `app.archive.process_archive`
—verificado por identidad— con su callback; cola/estado en el store y ZIPs en
el blob), T2 (todo con ZIP sintéticos, detector controlado y `process_fn`
inyectable; sin YOLO ni fotos reales; un test usa el motor real con detector
controlado).

Pendiente (para el director/revisión): validación con Redis y RustFS reales y
Compose (deferida por el plan); `RedisStateStore`/`S3BlobStore` están
implementados pero solo ejercitados vía dobles. Sin bloqueos de permisos o
sandbox durante la implementación.

## Corrección (hallazgos del director, misma sesión)

(1) F1 streaming: regresión nueva en `tests/test_api_worker.py` —
`test_f1_upload_streams_temp_to_store_without_full_bytes` (doble `ChunkedBlobs`
sin `put()` útil, solo transferencia por bloques desde archivo, más veto a
`Path.read_bytes` vía monkeypatch) y `test_f1_oversize_discards_temp_input`
(temporal eliminado tras 413, sin estado ni blobs). Señal roja antes del cambio:
`.venv/bin/python -m pytest tests/test_api_worker.py tests/test_job_stores.py`
→ 2 failed, 23 passed; el test de streaming falló con
`AssertionError: upload path materialized whole file via read_bytes` en
`tests/test_api_worker.py:389` (la ruta llamaba `Path(tmp_name).read_bytes()`).
Cambio mínimo en `app/jobs.py`: `JobService.submit_file(path)` (tamaño por
`os.path.getsize`, transferencia vía `blobs.put_file`), `put_file` por bloques
en `MemoryBlobStore` y vía `upload_file` en `S3BlobStore`, y la ruta
`POST /api/jobs` ahora llama `submit_file(tmp_name)`; el `finally` existente
sigue borrando el temporal también al exceder el límite (cubierto por el test).

(2) T2 adaptadores: nuevo `tests/test_job_stores.py` (8 tests) con clientes
controlados `FakeRedis` (bytes como redis-py) y `FakeS3`: FIFO push/pop,
round trip de estado (incluye `None` y `finished_at`), ids, TTL/cleanup vía
`JobService` con `RedisStateStore`, put/get/delete/exists y propagación de
error no-404 en `S3BlobStore`, `put_file` desde disco y ciclo HTTP completo con
Redis+S3. Señal roja antes del cambio: `test_s3_put_file_uploads_from_disk` →
`AttributeError: 'S3BlobStore' object has no attribute 'put_file'`; los tests de
`RedisStateStore` ya pasaban con la implementación existente (sin cambios para
ellos). No se borraron adaptadores (T1 los requiere).

Comandos y resultados reales (desde `.venv`, tras el cambio):

- `.venv/bin/python -m pytest tests/test_api_worker.py tests/test_job_stores.py`
  → 25 passed in 0.66s.
- `.venv/bin/python -m pytest` (suite completa) → 409 passed, 1 skipped.
- `.venv/bin/pip check` → No broken requirements found.

`git status` confirma que solo cambiaron `app/jobs.py`,
`tests/test_api_worker.py`, `tests/test_job_stores.py`, `pyproject.toml` y los
planes de V2-03; V1 y V2-04 intactos. La entrega dejó `plan.md` en revisión,
sin autodeclarar completada. Sin bloqueos de permisos o sandbox.

## Revisión

Revisión independiente del director (GPT-6 Luna, medium), 2026-10-10:

- **F1:** verificado `POST /api/jobs` con multipart, UUID/202, nombre de campo,
  límite medido durante lectura por bloques y descarte del temporal en 413.
  La primera entrega materializaba el temporal con `Path.read_bytes()`; se
  corrigió con regresión antes del cambio y `submit_file`/`put_file`.
- **F2:** verificado estado público exacto, progreso V2-02, contadores,
  transiciones y 404 para id desconocido.
- **F3:** verificado FIFO, aislamiento por UUID y publicación del objeto antes
  de `completed`; el test integrado usa Redis/S3 controlados.
- **F4:** verificados ZIP inválido y fallo de procesamiento, estado `failed`,
  mensaje legible y respuesta 409 sin salida parcial descargable.
- **F5:** verificados bytes exactos, 409 en estados no descargables, 404,
  410 después de tres horas y disponibilidad en el límite exacto.
- **F6:** verificada limpieza de blobs y estado solo después del TTL, incluyendo
  stores controlados. La ejecución con servicios y Compose queda para etapas
  posteriores conforme al contrato.
- **T1/T2:** verificado el uso de `process_archive()`/callback y pruebas de
  endpoints, stores Redis/S3 controlados y ciclo completo sin inferencia YOLO.

Hallazgos corregidos: **2**. (1) `app/jobs.py:create_job` materializaba la
carga completa en RAM (F1); se agregó regresión roja que prohíbe `read_bytes`,
se corrigió el traspaso por archivo y se probó 413 con temporal eliminado.
(2) los adaptadores persistentes no tenían cobertura (T2); se añadieron
pruebas de FIFO/estado/TTL para Redis y CRUD/upload/error para S3, además de un
ciclo API completo. La segunda entrega incluyó ambos tests antes de sus cambios;
su evidencia roja fue 2 failed / 23 passed.

Comprobaciones independientes del director:

- `.venv/bin/python -m pytest tests/test_api_worker.py tests/test_job_stores.py -q`
  → 25 passed.
- `.venv/bin/python -m pytest -q` → 409 passed, 1 skipped.
- `.venv/bin/python -m pip check` → No broken requirements found.
- `git diff --check` → sin errores.
- Inspección del diff completo y de los criterios F1–F6/T1–T2; alcance limitado
  a V2-03, sin cambios a V1 ni V2-04.

Cierre: todos los criterios del contrato están verificados; no quedan hallazgos
abiertos. V2-03 queda **completada**. La implementación trata entrada/salida y
limpieza de resultados, por lo que es crítica para integridad de datos. Confianza
estimada del director: primera entrega **76%** (F1 funcionaba en el test básico,
pero incumplía streaming y los adaptadores no tenían evidencia); etapa final
**93%** (criterios cubiertos, regresiones rojas/ verdes y ejecución independiente;
no sube más porque no se probaron servicios Redis/RustFS reales, explícitamente
fuera de esta etapa). Hubo **2 entregas**, **2 hallazgos corregidos** y **5
comprobaciones independientes** listadas arriba; el contrato dejó claras las
conductas principales, aunque el requisito de streaming necesitó una corrección.
