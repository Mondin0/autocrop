# Etapa V2-05 — Registro

## Implementación

Archivos creados/modificados:

- `app/frontend.py` (nuevo): servidor stdlib (`http.server`) que sirve
  `frontend/index.html` en `GET /` y proxifica `/api/*` al servicio
  `api:8000` conservando método, ruta, query, cuerpo, códigos y
  respuestas; fallo de conexión responde 502. Sin dependencias nuevas.
- `frontend/index.html` (nuevo): página que envía ZIP con `FormData`
  (`file`) a `POST /api/jobs`, muestra trabajo aceptado, sondea
  `GET /api/jobs/{id}` cada 1000 ms mientras `queued`/`processing`,
  muestra estado, `current` no nulo y contadores `processed/total`,
  `saved`, `review`; en `completed` detiene el sondeo y ofrece
  descarga a `/result`; en `failed` detiene el sondeo y muestra
  `error`; errores de envío/consulta/descarga visibles y sin sondeo
  colgado; todo contra el origen del frontend (sin CORS/CDN/externos).
- `compose.yaml`: servicio `frontend` separado (misma build/imagen que
  `api`, `python -m app.frontend`, `127.0.0.1:${AUTOCROP_FRONTEND_PORT:-8080}:8080`,
  `FRONTEND_API_BASE=http://api:8000`, `depends_on api: service_started`).
  `api` conserva `127.0.0.1:${AUTOCROP_API_PORT:-8000}:8000` de V2-04.
- `.env.example`: `AUTOCROP_FRONTEND_PORT=8080`.
- `Dockerfile`: `COPY frontend ./frontend`.
- `tests/test_frontend.py` (nuevo, 13 tests): F1 (página, proxy con
  doble controlado, multipart, 404 en no contratadas), F2–F5 (contenido
  de la página y 502 ante API caída), T1 (Compose), T2 (sin
  YOLO/Redis/RustFS/fotos; flujo completo vía proxy contra API real
  con stores en memoria).
- `tests/test_compose.py`: `test_f2_only_api_publishes_loopback_port`
  ahora espera publicadores `{api, frontend}` en loopback. Motivo para
  revisión: el contrato V2-05 amplía V2-04 (frontend publica 8080);
  no se tocó plan ni registro de V2-04.
- Correcciones a tests propios antes de entregar (test mal calibrado,
  no implementación): F3 exigía literales `queued`/`processing` y la
  página los añadió con retorno explícito de sondeo; T2 prohibía la
  palabra `YOLO` hasta en el docstring y ahora solo revisa líneas de
  `import`/`from`.

Comandos y resultados reales:

- `.venv/bin/python -m pytest tests/test_frontend.py -q` (en rojo,
  con stub `NotImplementedError` y placeholder): 13 failed.
- `.venv/bin/python -m pytest tests/test_frontend.py` (tras
  implementar): `13 passed, 1 warning in 3.82s` (warning preexistente:
  `httpx` con `starlette.testclient` deprecado).
- `.venv/bin/python -m pytest` (suite completa):
  `444 passed, 1 skipped, 1 warning in 9.02s`.
- `.venv/bin/python -m pip check`: `No broken requirements found.`
- `git diff --check`: limpio (sin salida).
- `docker compose config`: exit 0; `frontend` con `host_ip: 127.0.0.1,
  target: 8080` y `api` con `host_ip: 127.0.0.1, target: 8000`.
- Humo en vivo (`AUTOCROP_FRONTEND_PORT=18081 .venv/bin/python -m
  app.frontend` + curl): `GET /` 200, `GET /health` 404,
  `GET /api/jobs/missing` sin API arriba 502.

Criterios cubiertos: F1–F5, T1–T2 mediante tests con dobles
controlados y cliente HTTP (sin YOLO, Redis/RustFS ni fotos reales).

Pendiente (para el director/entorno Linux con Compose): recorrido
manual en navegador desde `http://localhost:8080` (subir ZIP
sintético, observar avance, completar y descargar); no se ejecutó
`docker compose up --build` en esta sesión. V1 intacta; no se
modificaron plan ni registro de V2-04; no se implementaron etapas
futuras.

## Corrección H1 (revisión del director)

- **Ubicación:** `app/frontend.py` (`_proxy_api`: `rfile.read(length)`
  único y `resp.read()` + `wfile.write(body)` únicos);
  `frontend/index.html` (aceptaba `200` vía `!res.ok`, sin `label` ni
  `aria-live`/`role=status`).
- **Impacto:** el proxy materializaba el cuerpo completo en memoria en
  ambas direcciones; V2-03 admite ZIP de hasta 500 MiB y exige carga
  por bloques, por lo que un lote grande podía agotar la RAM del
  contenedor frontend. Además la página aceptaba `200` en el envío
  aunque el contrato V2-03 devuelve `202` exacto, y los estados no se
  anunciaban accesiblemente.
- **Criterio afectado:** F1 (el proxy conserva respuestas; ahora sin
  materializarlas), F2 (aceptación ante HTTP 202 exacto), F5 (errores
  visibles), T2 (pruebas con dobles controlados).
- **Corrección mínima:** proxy reescrito con `http.client` en
  streaming: lee el cuerpo del cliente y escribe hacia la API en
  bloques de 64 KiB (`_CHUNK`), y reenvía la respuesta leyéndola y
  escribiéndola por bloques del mismo tamaño; preserva método, ruta,
  query, códigos y cabeceras `Content-Type`/`Content-Disposition`
  (`Content-Length` cuando la API la envía); responde 502 solo si el
  fallo ocurre antes de enviar la respuesta. Página: el envío solo
  acepta `res.status === 202` (cualquier otro, incluido `200`,
  muestra `envío falló: <código>`); `413` conserva su mensaje de
  límite; `label for="file"` asociado al input y `role="status"`
  + `aria-live="polite"` en estado, contadores y foto actual.
  Sin cambios a V1, a Compose ni a archivos de V2-04.

Regresiones agregadas (`tests/test_frontend.py`, 4 tests):

- `test_h1_proxy_streams_request_body_in_bounded_blocks`: 256 KiB
  contra stub que verifica digest; instrumenta `rfile.read`/`wfile.write`
  y exige picos ≤ 64 KiB.
- `test_h1_proxy_streams_response_body_in_bounded_blocks`: 320 KiB
  del stub con bytes exactos; exige escrituras ≤ 64 KiB.
- `test_h1a_page_accepts_only_202_on_submit`: exige `res.status === 202`,
  ausencia del patrón `!res.ok && res.status` y error visible.
- `test_h1b_page_labels_input_and_announces_status`: exige
  `label for="file"`, `aria-live` y `role="status"`.

Comandos y resultados reales:

- `.venv/bin/python -m pytest tests/test_frontend.py` (regresiones
  antes de corregir): `4 failed, 13 passed`; picos observados
  `{'read': 262144, 'write': 149}` y `{'read': 0, 'write': 327680}`
  (materialización completa demostrada, sin fallos de instalación).
- Ajuste a regresión propia durante la corrección: `h1a` exigía
  ausencia total de `!res.ok`, pero ese patrón es legítimo en los
  handlers de consulta/descarga (cualquier no-2xx es error); se
  precisó al patrón exacto del bug de envío. La versión inicial igual
  fallaba en rojo por el literal `=== 202` ausente.
- `.venv/bin/python -m pytest tests/test_frontend.py` (tras
  corregir): `17 passed, 1 warning in 4.37s`.
- `.venv/bin/python -m pytest` (suite completa):
  `448 passed, 1 skipped, 1 warning in 9.76s`.
- `.venv/bin/python -m pip check`: `No broken requirements found.`
- `git diff --check`: limpio. `docker compose config`: exit 0
  (2 publicaciones en `127.0.0.1`: api 8000, frontend 8080).
- Humo en vivo (`AUTOCROP_FRONTEND_PORT=18082 .venv/bin/python -m
  app.frontend` + curl): `GET /` 200, `GET /health` 404,
  `GET /api/jobs/x` sin API arriba 502.

## Corrección H2 (revisión del director)

- **Ubicación:** `.dockerignore` (allowlist sin `!frontend/`) frente a
  `Dockerfile` (`COPY frontend ./frontend`).
- **Impacto:** `docker compose up --build -d` fallaba en el `COPY`
  porque `frontend/` nunca llegaba al contexto de build; el servicio
  `frontend` no podía construirse ni servir la página.
- **Criterio afectado:** T1 (Compose ejecuta frontend y API en
  contenedores separados a partir de la imagen compartida).
- **Corrección mínima:** una línea `!frontend/` en `.dockerignore`,
  junto a `!app/`. Sin cambios a V1, a otros contratos ni a
  artefactos de V2-04.

Regresión agregada (`tests/test_frontend.py`):

- `test_h2_docker_context_includes_frontend_page`: evalúa la
  allowlist (último patrón que casa decide) y exige que
  `frontend/index.html` y `app/frontend.py` estén incluidos, que el
  `Dockerfile` copie `frontend`, y que la allowlist siga excluyendo
  `.env` y `fotos/a.jpg`.

Comandos y resultados reales:

- `.venv/bin/python -m pytest tests/test_frontend.py -q -k h2`
  (antes de corregir): `1 failed` (`frontend/index.html` excluido
  por `['*', '!Dockerfile', '!pyproject.toml', '!README.md',
  '!app/', '!yolo11n.pt', ...]`, sin fallos de instalación).
- `.venv/bin/python -m pytest tests/test_frontend.py` (tras
  corregir): `18 passed, 1 warning in 4.32s`.
- `.venv/bin/python -m pytest` (suite completa):
  `449 passed, 1 skipped, 1 warning in 9.77s`.
- `.venv/bin/python -m pip check`: `No broken requirements found.`
- `git diff --check`: limpio. `docker compose config`: exit 0.
- `docker compose up --build`: no ejecutado. Motivo registrado, sin
  inventar resultado: el build completo depende de red y demora
  (pull de bases + `pip install` de torch CPU/ultralytics, cientos de
  MB); daemon comprobado reachable (`docker info` OK). Sigue pendiente
  el recorrido manual en navegador desde `http://localhost:8080`.

## Corrección navegador (revisión del director, Playwright aprobado)

- **Ubicación:** `tests/test_frontend_browser.py` (nuevo, 4 tests con
  fixture `page` en Chromium); `pyproject.toml` ya declara
  `pytest-playwright>=0.7.0` en `dev` (cambio preexistente del
  director en el árbol de trabajo, conservado sin modificar).
- **Impacto:** F2–F5 quedaban cubiertos solo vía cliente HTTP y texto
  de la página; la revisión del director dejó pendiente la
  verificación interactiva F2–F5. Ahora hay interacción real del HTML
  en Chromium (envío de archivo, estado/progreso/terminal, descarga,
  error visible y reintento) contra dobles controlados, sin Compose
  ni fotos reales. Se conservan todas las pruebas API/proxy existentes.
- **Criterio afectado:** T2 (navegador controlado) cubriendo F2–F5.
- **Corrección:** solo tests nuevos; ningún defecto en
  `app/frontend.py` ni `frontend/index.html` (verde real al primer
  intento, sin rojo inventado y sin fix necesario).

Tests (`_Api` scripted: modos `progress`/`failed`/`boom`):

- `test_browser_submit_accepts_job_and_polls` (F2): sube ZIP
  sintético, acepta 202, verifica multipart `file` en el stub y que
  el sondeo arranca.
- `test_browser_progress_completed_and_download` (F3+F4): `a.jpg` y
  `1/2` visibles, `#download` con `href` a `/result`, descarga real
  (`job-1.zip`, bytes exactos) y sondeo detenido tras completar.
- `test_browser_failed_shows_error_without_download` (F4): `motor
  roto` visible y sin descarga.
- `test_browser_query_error_visible_then_retry` (F5): `consulta
  falló` visible, sondeo detenido y reintento que completa.

Dependencia y entorno (datos del director, verificados):

- `pytest-playwright 0.10.0`, `playwright 1.63.0` (vía
  `.venv/bin/python -m pip show pytest-playwright playwright`).
- Chromium `chromium-1243` + `chromium_headless_shell-1243` en
  `~/.cache/ms-playwright/` (más `ffmpeg-1011`).
- Comando exacto de instalación de Chromium no recuperable de
  historial/metadata verificable (`~/.zsh_history` sin rastros);
  consta como suministrado por el director. Comando propio de
  Playwright que verifica el navegador:
  `.venv/bin/python -m playwright install --dry-run chromium`
  (informa ubicaciones ya satisfechas, sin descargar nada).

Comandos y resultados reales:

- `.venv/bin/python -m pytest tests/test_frontend_browser.py`:
  `4 passed in 10.50s` (primer intento, sin defecto).
- `.venv/bin/python -m pytest tests/test_frontend.py
  tests/test_frontend_browser.py` (etapa): `22 passed in 14.45s`.
- `.venv/bin/python -m pytest` (suite completa):
  `453 passed, 1 skipped, 1 warning in 21.25s`.
- `.venv/bin/python -m pip check`: `No broken requirements found.`
- `git diff --check`: limpio.

## Revisión

Revisión independiente del director (GPT-6 Luna, medium), 2026-10-10:

- **H1 — Corregido:** `app/frontend.py` antes acumulaba la carga y la
  respuesta completas en memoria. Las regresiones nuevas dieron rojo
  (4 fallidas) y midieron picos de lectura/escritura mayores que 64 KiB.
  Tras la corrección, ambas direcciones transmiten en bloques de 64 KiB;
  repetí los tests y pasaron.
- **H1a/H1b — Corregidos:** el formulario ahora acepta únicamente HTTP 202;
  input y estados tienen etiquetas/anuncios accesibles. La primera
  aserción para 202 inspeccionaba toda la página y confundía el manejo
  válido de errores en consulta/descarga; se acotó y se dejó constancia.
- **H2 — Corregido:** `docker compose up --build -d` falló inicialmente
  porque `.dockerignore` excluía `frontend/` del contexto aunque
  `Dockerfile` lo copiaba. La regresión específica falló antes del cambio;
  `!frontend/` corrigió el contexto. El build y arranque posteriores
  terminaron correctamente.
- **F1:** `GET /` por `localhost:8080` respondió 200. A través del proxy,
  un ZIP JPEG sintético recibió 202, llegó a `completed` (1/1, 0 guardadas,
  1 revisión) y el resultado se descargó con 200; contenía `review.log`,
  `review/` y la imagen sintética.
- **F2–F5:** la primera comprobación interactiva quedó pendiente porque la
  skill de Browser no encontró navegadores (`agent.browsers.list()` devolvió
  `[]`). Se instaló pytest-playwright y Chromium en `.venv`; las cuatro
  pruebas nuevas de `tests/test_frontend_browser.py` ejecutaron el HTML real
  en Chromium contra API/frontend locales controlados. Verifiqué envío
  multipart y sondeo, foto y contadores de progreso, descarga con bytes
  exactos y detención del sondeo, error terminal sin descarga y error de
  consulta visible con reintento. Ejecución independiente: 4 pruebas nuevas
  verdes (incluidas en 22 pruebas de etapa y 453 de suite).
- **T1:** `docker compose config --quiet` y `docker compose up --build -d`
  pasaron; `docker compose ps` mostró API en `127.0.0.1:8000`, frontend en
  `127.0.0.1:8080` y Redis/RustFS sin puertos publicados. `docker compose
  down` dejó el stack detenido y conservó los volúmenes.
- **T2:** pruebas HTTP y Chromium contra dobles sin YOLO, Redis/RustFS ni
  fotos reales; 22 pruebas de etapa, suite completa independiente: 453
  passed, 1 skipped; `pip check` y `git diff --check` sin errores.

Hallazgos corregidos: **4** (proxy en memoria; aceptación HTTP 200;
accesibilidad básica; frontend fuera del contexto Docker). El primer
test de H1a tuvo un falso positivo por alcance global y se precisó antes
de la entrega corregida. Hubo **4 entregas** de Muse, incluida la suite de
navegador. V2-05 queda **completada**: F1–F5 y T1–T2 tienen evidencia, el
stack Compose se construyó y arrancó, y las interacciones JavaScript se
verificaron con Chromium.

### Cierre del director

- Revisión independiente final: `.venv/bin/python -m pytest
  tests/test_frontend.py tests/test_frontend_browser.py` → `22 passed`
  (1 warning de deprecación preexistente en Starlette/httpx).
- Suite completa independiente: `.venv/bin/python -m pytest` → `453
  passed, 1 skipped, 1 warning`.
- `.venv/bin/python -m pip check` → `No broken requirements found.`
- `git diff --check` → limpio.
- Playwright instalado en el entorno local: `pytest-playwright 0.10.0`,
  `playwright 1.63.0`, Chromium 1243.
- Confianza del director: **69 %** en la primera entrega (los cuatro
  hallazgos demostrados por regresiones y el fallo inicial de build)
  y **94 %** en la etapa final (pruebas de navegador independientes y
  recorrido Compose confirmado; limita el resto el no ejecutar el flujo
  visual con un ZIP real y fotografía).
