# Etapa V2-06 — Registro

## Implementación

Implementador: OpenCode Muse. Modelo YOLO sin cambios (`yolo11n.pt` local del
checkout; sin descarga ni cambio de dependencias, Dockerfile o código V1).

OpenCode Zen: `opencode/muse-spark-1.3-contributor-free` (listado con sufijo
`contributor-free`; elegido por petición del usuario y disponibilidad gratuita
confirmada). Una entrega de implementación, dos invocaciones de CLI en la
misma sesión (`ses_ed789a118ffe5OVvoua5uTg6Am`, continuación por duración).

Archivos tocados por esta etapa (cambio mínimo):

- `compose.yaml`: una línea, `profiles: ["v1"]` en el servicio `autocrop`.
- `README.md`: solo la sección "Demo local V2 con Docker Compose" (sin
  `.env`/`fotos/`/`output/` para V2; `down` vs `down -v` con `redis-data` y
  `rustfs-data`; V1 con `--profile v1`).
- `tests/test_compose_nodata.py`: nuevo, 9 tests F1–F4/T1 (+F5 lectura README).
- `.plans/v2/06-compose-sin-datos-host/plan.md`: estado.
- Tooling solo en `.venv` (no es dependencia del proyecto): `playwright
  1.63.0`, `pytest-playwright` y Chromium headless-shell 153.0.8010.12
  (descargado a `~/.cache/ms-playwright`). Artefactos E2E conservados en
  `/tmp/opencode/v2-06-e2e/` para limpieza del director.

### Evidencia roja (tests primero)

`.venv/bin/python -m pytest tests/test_compose_nodata.py -v` antes del fix:
**5 failed, 4 passed**. Fallos funcionales (no de instalación):

- `test_f1_default_services_are_v2_only`
- `test_f1_default_config_lists_only_v2`
- `test_f2_v1_service_behind_v1_profile_keeps_mounts`
- `test_f4_named_volumes_and_readme_down_semantics`
- `test_f5_readme_v2_needs_no_env_nor_host_dirs`

### Evidencia verde (tras el fix)

- Dirigidos: `.venv/bin/python -m pytest
  tests/test_compose_nodata.py tests/test_compose.py tests/test_frontend.py
  tests/test_frontend_browser.py -q` → EXIT=0, **53 passed**
  (log: `/tmp/opencode/v2-06-e2e/targeted2.log`).
- Suite completa: `.venv/bin/python -m pytest -q` → EXIT=0, **462 passed,
  1 skipped** (skip preexistente; log: `/tmp/opencode/v2-06-e2e/full.log`).
- `.venv/bin/python -m pip check` → `No broken requirements found.`
- `git diff --check` → limpio (`DIFFCHECK-OK`).
- `docker compose config` → EXIT=0 (salida completa en
  `/tmp/opencode/v2-06-e2e/compose-config.txt`).
- `docker compose config --services` → `api, frontend, redis, rustfs,
  worker` (sin `autocrop`); con `--profile v1` se suma `autocrop`.

### Validación contra el stack real (T2 + sin carpetas host)

1. `fotos/` (vacía) y `output/` (vacía, con `review/` vacía) movidas a
   `/tmp/opencode/v2-06-hostdirs/`; V2 arrancó sin ellas (`NODIRS-OK`).
2. `docker compose up -d --build` → 5 contenedores `Up` (api, frontend,
   worker, redis y rustfs healthy); ningún contenedor `autocrop`.
   Puertos solo en loopback: `127.0.0.1:8000`, `127.0.0.1:8080`.
3. ZIP sintético `/tmp/opencode/v2-06-e2e/lote.zip` (`roja.jpg` 640x480,
   `verde.jpg` 500x500, generados con PIL, en raíz del ZIP).
4. Playwright/Chromium contra `http://localhost:8080`: subida → `estado:
   completed`, `procesadas 2/2 guardadas 0 revisión 2` (sin personas en
   imágenes lisas: ambas a revisión, comportamiento esperado del motor) →
   descarga `resultado.zip` con `review.log`, `review/`, `review/roja.jpg`,
   `review/verde.jpg`; `testzip` None → **descarga íntegra (E2E_OK)**.
5. Recorrido API paralelo con `curl`: `POST /api/jobs` → 202 con `job_id`;
   `GET /api/jobs/{id}` → `completed` 2/2; `GET .../result` → ZIP válido
   (`review.log`, `review/`, ambos JPEG, `testzip` None).
6. `fotos/` y `output/` restauradas con `cp -r` desde
   `/tmp/opencode/v2-06-hostdirs/` a sus rutas originales. El director
   comprobó `diff -qr` sin diferencias; estaban vacías salvo `output/review/`,
   también vacía.

### Criterios

Cubiertos con evidencia: F1, F2, F3, F4, F5, T1 (tests), T2 (E2E manual).
Pendientes: ninguno.

## Revisión

Revisión independiente del director (GPT-6 Luna, medium):

- Inspeccionados el diff completo de Compose, README, tests y contrato frente a
  F1–F5/T1–T2. El cambio funcional de Compose se limita a añadir el perfil `v1`
  al servicio CLI; el arranque predeterminado contiene solo los cinco servicios
  V2. No se tocó Dockerfile, dependencias, código V1 ni modelo.
- Tests dirigidos independientes: `.venv/bin/python -m pytest
  tests/test_compose_nodata.py tests/test_compose.py tests/test_frontend.py
  tests/test_frontend_browser.py -q` → **53 passed**.
- Suite completa independiente: `.venv/bin/python -m pytest` → **462 passed,
  1 skipped**, warning existente de deprecación Starlette/httpx.
- `.venv/bin/python -m pip check` → sin dependencias rotas; `docker compose
  config --quiet` y `git diff --check` → exit 0.
- E2E independiente con `.venv/bin/python
  /tmp/opencode/v2-06-e2e/e2e.py` y Chromium contra el Compose activo:
  estado `completed`, 2/2; descarga íntegra con `review.log`, `review/` y dos
  JPEG (`ZipFile.testzip() is None`). Revisión y comparación de las carpetas
  preexistentes restauradas: `diff -qr fotos ...` y `diff -qr output ...`, sin
  diferencias.
- Hallazgos: **0**. Entregas: **1**. Comprobaciones independientes del
  director: **7** (tests dirigidos, suite completa, pip check, Compose config,
  diff check, E2E Playwright y comparación de las carpetas restauradas).
- Confianza estimada: primera entrega **82%** (la primera ejecución completa
  encontró el plugin Playwright ausente en `.venv`; se instaló desde el extra
  dev declarado y se repitió); final **94%** (criterios cubiertos y E2E real
  repetido por el director; no se usaron fotografías reales y los casos
  sintéticos terminaron correctamente en revisión, como se esperaba).
- Limpieza posterior verificada: `docker compose down -v`; contenedores y
  volúmenes del proyecto ausentes; imagen `autocrop:latest` eliminada;
  `pytest-playwright`, `playwright` y dependencias dedicadas desinstaladas de
  `.venv`; caché Chromium y temporales E2E eliminados. Las imágenes base
  Redis/RustFS (imágenes anteriores a esta etapa) y la caché BuildKit global
  se conservaron para no afectar otros proyectos; `docker buildx du` reportó
  4.26 GB reclaimable total (3.9 GB private, mezclada con builds previos), sin
  filtro seguro por proyecto en `buildx prune`. `fotos/` y `output/` están
  restauradas y sin diferencias de contenido.

Cierre: F1–F5 y T1–T2 verificados; no quedan hallazgos abiertos. Etapa
completada.
