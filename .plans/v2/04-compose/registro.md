# Etapa V2-04 — Registro

## Implementación

Delegación: el usuario encargó implementar únicamente V2-04 según AGENTS.md
y el contrato en `.plans/v2/04-compose/plan.md`. No se tocó V2-05 ni otra
etapa. Modelo `opencode/muse-spark-1.3-contributor-free`; motivo: asignado
por el usuario para esta implementación.

Archivos:

- `app/runtime.py` (nuevo): `Settings.from_env()` (5 vars `AUTOCROP_*` con
  defaults locales), `build_service()` (clientes reales Redis/S3 o
  `state`/`blobs` inyectados; `process_fn` por defecto intacto),
  `wait_for_ready()` (ping Redis + `head_bucket` RustFS con reintentos,
  `TimeoutError` que nombra el servicio caído; bucket ausente cuenta como
  servidor listo) y `ensure_bucket()` (crea solo ante 404/NoSuchBucket,
  propaga el resto). S3 en path-style (RustFS sin dominios solo responde
  así), región `us-east-1`.
- `app/serve.py` (nuevo): `create_local_app()` sirve
  `app.jobs.create_app`; el hook lifespan espera dependencias y asegura el
  bucket con logs; `app = create_local_app()` para
  `uvicorn app.serve:app`. Con `state`/`blobs` no crea clientes (tests).
- `app/worker.py` (nuevo): `pump_once()` (un `run_next` con el detector
  real; en cola vacía corre `cleanup()` de V2-03 y devuelve False) y
  `main()` que espera dependencias, construye el detector de la CLI V1
  (`yolo11n.pt`, 0.25, mismos defaults) y bombea en bucle con reintento
  logueado ante errores. `python -m app.worker`.
- `tests/test_compose.py` (nuevo, 17 tests F1–F6/T1 + imagen/entrypoints).
- `compose.yaml`: servicio V1 `autocrop` intacto; nuevos `api`/`worker`
  (mismo `build: .` e `image: autocrop:latest`), `redis:7-alpine` (AOF para
  persistencia) y `rustfs/rustfs:latest` (`/data`, consola desactivada).
  Solo `api` publica puerto, ligado a `127.0.0.1:${AUTOCROP_API_PORT:-8000}`;
  healthchecks en redis (`redis-cli ping`) y rustfs (`curl -f /health`);
  `depends_on` con `service_healthy`; volúmenes nombrados
  `redis-data`/`rustfs-data`.
- `.env.example`: 5 vars V2 documentadas (secreto placeholder explícitamente
  de demo local) + `AUTOCROP_INPUT_DIR/OUTPUT_DIR` de V1 que faltaban.
- `Dockerfile`: deps de servidor `fastapi python-multipart uvicorn redis
  boto3` explícitas (el `pip install --no-deps .` las omitía a propósito) y
  pin `ultralytics==8.4.174` (ver hallazgo 2). Sin cambios al manejo CPU de
  torch; CMD intacto.
- `pyproject.toml`: `uvicorn>=0.30 redis>=5.0 boto3>=1.34` en dependencias;
  `pyyaml>=6.0` en `dev` (los tests de etapa parsean `compose.yaml`).
- `README.md`: sección demo V2 (up/build, URL, endpoints curl, logs, down,
  `down -v`, credenciales demo, coexistencia V1).

Señal roja (tests primero, contra stubs con `NotImplementedError` y Compose
V1 sin tocar): `.venv/bin/python -m pytest tests/test_compose.py` →
15 FAILED (`KeyError`/`AssertionError` por servicios ausentes,
`NotImplementedError` en el cableado; solo pasaban `config` y el servicio
V1 intacto). Fallos funcionales, no de instalación/importación.

Comandos y resultados reales (desde `.venv`, más Docker):

- `.venv/bin/pip install 'uvicorn>=0.30' 'redis>=5.0' 'boto3>=1.34'
  'pyyaml>=6.0'` → uvicorn-0.54.0, redis-8.1.0, boto3-1.43.111 (+deps).
- `.venv/bin/python -m pytest tests/test_compose.py` → 17 passed.
- `.venv/bin/python -m pytest` → 426 passed, 1 skipped (base V2-03: 409+1).
- `.venv/bin/pip check` → No broken requirements found.
- `git diff --check` → limpio. `docker compose config --quiet` → OK.
- `docker compose up --build -d` → 5 contenedores; redis/rustfs `healthy`.
  Imágenes observadas: `rustfs/rustfs:latest`
  `sha256:1803faef…3fecb6a3c`, `redis:7-alpine` `sha256:858f009f…833b3499`.
- Ciclo real con ZIP sintético de 2 JPEG (sin fotos reales): POST →
  202 `queued` con UUID; estado `processing` con `current: a.jpg`;
  `completed` 2/2 (planos sintéticos → 0 saved/2 review, comportamiento
  correcto del motor); `GET result` → 200 con ZIP (`review/`,
  `review.log`, ambas fotos). Invariantes `processed == saved + review`.
- Puertos: solo `autocrop-api 127.0.0.1:8000->8000/tcp`; redis/rustfs sin
  mapeo al host; ningún `network_mode: host`.
- `docker compose down` + `up -d` → trabajo sigue `completed` y descargable
  (200). `docker compose down -v` → volúmenes eliminados, trabajo previo
  404. `docker exec autocrop autocrop --help` → CLI V1 operativa.

Hallazgos durante la implementación (no del director; se informan):

1. La imagen ya estaba rota para V2 antes de esta etapa: V2-03 declaró
   `fastapi`/`python-multipart` en `pyproject.toml` pero nunca los instaló
   en el Dockerfile (`pip check` fallaba). Se añadieron las 5 deps de
   servidor a la línea explícita, sin tocar el resguardo CPU de torch.
2. Drift de versión: el Dockerfile instalaba `ultralytics` sin pin y hoy
   resuelve 8.4.175 contra el pin `==8.4.174` (fallaba `pip check`). Se
   fijó el pin en el Dockerfile. Pillow/torch no dieron conflicto.

Criterios cubiertos: F1 (config valida, up levanta los 4+1 servicios),
F2 (loopback + red privada), F3 (ciclo real con motor V2-03 y stores
reales), F4 (persistencia down/up, borrado down -v, expiración V2-03 vía
cleanup en pasada idle), F5 (vars documentadas, placeholder sin secretos,
defaults funcionales), F6 (README con inicio/logs/detención, V1 intacta y
verificada con --help), T1 (misma imagen, healthchecks, depends
healthy), T2 (17 tests sin YOLO real ni fotos reales + ciclo real con
dobles sintéticos).

Pendiente (para el director/revisión): validación con fotografías reales
(solo sintéticas aquí); espera real de 3 h para expiración (cubierta por
tests unitarios V2-03 y test idle); fijar digests de redis/rustfs si se
quiere reproducibilidad estricta (`:latest`/`7-alpine` observados arriba).
Sin bloqueos de sandbox salvo el `read` de `.env` local (no necesitado;
`.env.example` no contiene secretos).

## Corrección (hallazgos del director, segunda entrega)

Modelo `opencode/muse-spark-1.3-contributor-free` (mismo asignado); motivo:
iterar la misma etapa sin tocar V2-05 ni autodeclarar completada.

Nota de orden: la primera corrección del Dockerfile (deps de servidor +
pin ultralytics, ver hallazgos 1–2 de Implementación) precedió a su
regresión porque `docker compose up --build` ya había fallado en
`pip check`; la regresión se añadió después y se demostró roja contra el
`Dockerfile` original (ver demo con `git stash` abajo).

(1) Empaquetado. Regresiones nuevas en `tests/test_compose.py` (stdlib
`ast`+`tomllib`, sin helpers privados): `test_packaging_runtime_deps_declared`
(imports de `app/` ⊆ `dependencies`), `test_packaging_test_deps_declared`
(imports de `tests/` ⊆ `dependencies`+`dev`),
`test_packaging_dockerfile_installs_declared_deps` (cada dependencia
declarada la instala la imagen: línea explícita o índice CPU para
torch/torchvision) y `test_packaging_dev_includes_test_transport`
(`httpx` en `dev`: lo exige starlette TestClient en runtime de tests).
Señal roja antes de corregir: 4 FAILED. Dos eran bug del propio test
(el parser no cortaba en `==`/`>=`; corregido, p. ej.
`ultralytics==8.4.174` se leía entero); uno genuino: `httpx` no estaba
declarado y llegaba por accidente vía otra dependencia. Corrección mínima:
`httpx>=0.27` en `dev` de `pyproject.toml` (+ install en `.venv`,
0.28.1 ya presente). Demo de la regresión Dockerfile:
`git stash push -- Dockerfile` (vuelve al original sin deps de servidor)
→ `test_packaging_dockerfile_installs_declared_deps` FAILED →
`git stash pop` → verde; el Dockerfile actual contiene la corrección.
Demostración en entorno limpio (el `.venv` poblado NO se invoca como
prueba de instalación): `python3 -m venv /tmp/opencode/v2clean`,
`pip install --index-url https://download.pytorch.org/whl/cpu torch
torchvision`, `pip install -e '.[dev]'` → `pip check` limpio;
`import app.serve` OK con rutas V2-03
(`/api/jobs`, `/api/jobs/{job_id}`, `/api/jobs/{job_id}/result`);
`torch 2.14.1+cpu`, `torch.version.cuda is None` (sin fuga CUDA:
el pin quedó satisfecho por el índice CPU); `pytest
tests/test_compose.py tests/test_api_worker.py tests/test_job_stores.py`
→ 47 passed. La imagen no se reconstruyó: solo cambió `dev` (httpx),
que el Dockerfile no instala.

(2) `GET /health` 404 en logs de la API. Investigación: la línea
(`172.21.0.1:42592 - "GET /health" 404`) tiene origen en el gateway de
Compose (petición originada en el host) y ninguno de los comandos de
validación pidió `/health` (solo `/api/jobs/*` y `/result`); nada de
nuestro conjunto la genera (healthchecks solo en redis/rustfs, sin
healthcheck en api/worker; el worker usa `JobService` directo, sin HTTP;
uvicorn no se autopregunta). Conclusión: request externo no solicitado,
rechazado correctamente con 404, coherente con el 404 de V2-03 para ids
desconocidos. El contrato no requiere ruta de salud en la API (T1:
healthchecks solo para Redis y RustFS; sin cambios al contrato HTTP), por
lo que no hay corrección de producción. Regresión:
`test_api_uncontracted_paths_are_404` fija `/health`, `/`, `/api` → 404;
añadir una ruta en el futuro deberá actualizarla deliberadamente.

Comandos y resultados reales (desde `.venv`):

- `.venv/bin/pip install 'httpx>=0.27'` → ya satisfecho (0.28.1).
- `.venv/bin/python -m pytest tests/test_compose.py` → 22 passed.
- `.venv/bin/python -m pytest` (suite completa) → 431 passed, 1 skipped.
- `.venv/bin/pip check` → No broken requirements found.
- `git diff --check` → limpio. `docker compose config --quiet` → OK.

Criterios: sin cambios en la cobertura F1–F6/T1–T2 registrada arriba; se
suma cobertura de regresión de empaquetado y de rutas no contratadas.
Pendientes del director/revisión (se mantienen): fotos reales, espera real
de 3 h, digests de redis/rustfs. La entrega deja `plan.md` en revisión,
sin autodeclarar completada. Sin bloqueos de sandbox.

## Revisión

Revisión independiente del director (GPT-6 Luna, medium), 2026-10-10:

- **F1:** `docker compose config --quiet` y `docker compose up -d --build`
  verificados de forma independiente. El build termina con `pip check` limpio;
  los servicios V2 inician.
- **F2/T1:** `docker compose ps` muestra solo la API enlazada a
  `127.0.0.1:8000`; Redis y RustFS están `healthy` sin puertos del host.
  El Compose declara dependencias `service_healthy` y healthchecks para ambos.
- **F3:** ZIP JPEG sintético enviado por HTTP: `POST /api/jobs` → 202;
  trabajo `completed`, 1/1 procesada, descarga 200 con `review.log`,
  `review/` y el original de revisión. Se respetó el contrato V2-03 sin
  inferencia de fotos reales.
- **F4:** reinicié con `docker compose down` y `up -d`; el mismo trabajo siguió
  `completed` y su resultado devolvió 200. La primera entrega también verificó
  `down -v` (volúmenes eliminados y trabajo previo 404); no se repitió porque
  borraría los volúmenes persistentes de la comprobación independiente.
- **F5:** inspeccioné `.env.example` y `compose.yaml`: variables referenciadas
  documentadas, credenciales identificadas como valores de demo, sin secretos
  reales. `Settings.from_env()` permite sobrescribir la configuración.
- **F6:** inspección de README y diff confirma comandos de inicio, logs y
  detención; la configuración del servicio V1 permanece y la primera entrega
  verificó `docker exec autocrop autocrop --help`.
- **T2:** 22 tests de etapa con dobles y ZIP sintético; no necesitan YOLO ni
  fotos reales. La suite completa también pasó.

Hallazgos corregidos: **3** de implementación/empaquetado: faltaban
dependencias de servidor en la imagen, `ultralytics` resolvía 8.4.175 frente
al pin 8.4.174 de `pyproject.toml`, y faltaban declaraciones runtime/dev para
imports de la app y transporte de tests. La segunda entrega incorporó
regresiones; la prueba del Dockerfile falló al restaurar temporalmente su
versión original y volvió a pasar al restaurar la corrección. El `GET
/health` 404 observado provenía de una petición externa al gateway; no es una
ruta del contrato. Se añadió una regresión que conserva el 404 en rutas no
contratadas. La primera edición del Dockerfile precedió a su regresión por el
fallo del primer build; el registro conserva ese orden y la demostración roja
posterior.

Comprobaciones independientes del director:

- `.venv/bin/python -m pytest tests/test_compose.py -q` → 22 passed.
- `.venv/bin/python -m pytest -q` → 431 passed, 1 skipped.
- `.venv/bin/python -m pip check` → sin requisitos rotos.
- `docker compose config --quiet` y `git diff --check` → sin errores.
- `docker compose up -d --build` → build con `pip check` limpio; Redis y
  RustFS saludables, API ligada a loopback, sin puertos internos publicados.
- Smoke HTTP independiente con ZIP JPEG sintético → 202, `completed`,
  descarga 200 con `review/` y `review.log`.
- `down`/`up` independiente → mismo job completado y descargable (200); luego
  `docker compose down` dejó los contenedores detenidos y los volúmenes
  conservados.

Las dos entregas usaron el modelo gratuito `opencode/muse-spark-1.3-contributor-free`;
la tarifa Free también figura en la tabla oficial de [OpenCode Zen](https://docs.opencode.ai/docs/zen/).
Confianza estimada del director: primera entrega **74%** (tests unitarios y
suite verdes, pero el build real falló dos veces por dependencias/versión);
etapa final **94%** (criterios cubiertos, entorno limpio y stack/ciclo/persistencia
verificados de forma independiente). No sube más porque la comprobación de
procesamiento usó una imagen sintética y las imágenes RustFS/Redis usan tags
actualizables. Hubo **2 entregas**, **3 hallazgos corregidos** y **7 grupos de
comprobaciones independientes** listados arriba. No quedan hallazgos abiertos.

Cierre: F1–F6 y T1–T2 verificados. V2-04 queda **completada**. Aunque supera
el umbral para etapas críticas, no se preparó ni implementó V2-05 por petición
explícita del usuario.
