# Etapa V2-10 — Registro

## Implementación

Método/modelo/sesión: implementador OpenCode Muse Spark 1.3 Free
(`opencode/muse-spark-1.3-contributor-free`), sesión coordinada con entrega
externa en `/tmp/v2-10-muse-delivery1.log`. Contrato V2-10 aprobado por el
usuario. Preflight reutilizado de `/tmp/v2-10-preflight.log` (SHA
`143f62053d3af9068ec55bf9dfaa1dc14c499bcc`, rama `main` limpia, disco 334G
libres, pesos `yolo11n.pt` hash
`0ebbc80d…7644ee1`, Compose v5.6.0, `.venv` Python 3.12.3, Playwright 1.64.0,
`pip check` limpio, puertos 8000/8080 libres). Diagnóstico MCP:
`opencode mcp --help` (subcomandos `list/add/auth/logout`) y
`opencode mcp list` → `context7 connected`, `engram connected`,
`playwright connected`. El recorrido navegador usó Playwright MCP real vía
`tools.playwright` (execute), no shell ni Chromium sustituto.

Alcance de archivos: etapa V2-10 (`tests/test_v210_acceptance.py`,
`tests/v210_support.py`), `plan.md` (estado), este registro. Sin cambios en
V1, V2-09, `.plans/v2/PLAN.md` ni README (sin error demostrado que lo exija).
`app/worker.py` quedó sin diff (reversión abajo).

### Tests primero (rojo → verde)

1. Se creó `tests/v210_support.py` como stub (`NotImplementedError`) y
   `tests/test_v210_acceptance.py` (12 tests + 1 skip F2). Primera corrida:
   `FAILED test_v210_isolated_override_uses_free_loopback_ports` con
   `NotImplementedError: V2-10: pendiente de implementación` (fallo
   funcional pendiente, no de instalación).
2. Tras implementar el helper, el propio test tenía la aserción invertida
   (esperaba conexión exitosa a un puerto libre → `ConnectionRefusedError`);
   se corrigió el test y quedó verde. Evidencia en log de entrega.
3. Regresión disparada por el primer import: `from tests import
   v210_support` hizo fallar el existente
   `tests/test_compose.py::test_packaging_test_deps_declared` con
   `Extra items in the left set: 'tests'`. No se alteró ninguna dependencia
   de producto: se cambió a carga por `importlib.util.spec_from_file_location`
   (`importlib` es stdlib) y el test de packaging volvió a verde.
4. Aislamiento de nombres (pedido posterior): test nuevo
   `test_v210_isolated_override_uniquifies_all_container_names` falló en rojo
   con `TypeError: write_isolated_override() got an unexpected keyword
   argument 'prefix'`; se agregó `prefix` al helper (nombres
   `autocrop-v210-*` para los 5 servicios) y quedó verde.
5. Corrección fuera de alcance revertida (director): el test auxiliar
   `test_v210_worker_emits_info_logs_by_default` y la línea
   `logging.basicConfig(level=logging.INFO)` en `app/worker.py` se
   retiraron. Motivo: F4 solo exige estado `failed` legible y avance del
   siguiente trabajo (ambos verificados por API); el contrato no exige logs
   INFO y el test no representaba ningún criterio F/T. `git diff
   app/worker.py` vacío confirmado.

### Validación con Compose real (proyecto aislado `v210test`)

- Override temporal `/tmp/v210-override.yaml` (puertos `!override`
  `127.0.0.1:36063→8000`, `127.0.0.1:53619→8080` + `container_name`
  `autocrop-v210-*`). Lección registrada: el primer override sin `!override`
  fusionaba listas y publicaba también 8000/8080; con `!reset` se vaciaban
  (reset = valor por defecto); con `!override` quedó solo loopback aislado.
  Los contenedores iniciales `autocrop-*` solo se crearon porque el preflight
  confirmó ausencia (puertos libres, `docker ps` sin autocrop); tras el
  pedido de nombres únicos se hizo `down` y `up` con `autocrop-v210-*`.
- `docker compose -p v210test up -d --build`: imagen `autocrop:latest`
  construida (ID `9c11a4cefdde`, luego rebuild 20:06 == árbol tras la
  reversión). Volúmenes `v210test_redis-data`/`v210test_rustfs-data`, red
  `v210test_default`. `ss -ltn` confirma solo 127.0.0.1:36063/53619.
- F1 navegador (Playwright MCP, frontend real :53619): subida de
  `/tmp/v210/small.zip` → `estado: completed`,
  `procesadas 3/3 guardadas 0 revisión 3`, enlace
  `/api/jobs/75801b6e-…/result`. Screenshot en `/tmp/v210/`.
- F1 API: job `5e8a5806-…` completed 3/3; `result.zip` (2026 bytes,
  `testzip None`, `['review.log','review/','review/foto uno.jpg',
  'review/foto-dos.jpeg','review/foto_tres.JPG']`); `review.log` =
  `no_person` ×3; copias en review idénticas por sha256 a originales;
  `small.zip` intacto (`bbe0b4b3…663f44fe`).
- F3 navegador (misma sesión, sin reinicio): `over.zip` (501MiB, fixture
  existente, no regenerada) → `error=límite excedido: el ZIP supera 500
  MiB` en 8.0s; `invalid.zip` → `estado: failed | zip contains no JPEG in
  its root`; `nested.zip` → `estado: failed | unsafe entry name:
  'sub/a.jpg'`; reenvío `small.zip` → `completed 3/3` con descarga
  (`/api/jobs/0f9f95da-…/result`). Screenshot en `/tmp/v210/`.
- F3 API: inválido/anidado en `failed` visible; `unreadable.zip` →
  completed con `review.log` (`buena.jpg: no_person`, `roto.jpg:
  unreadable`); reenvío válido posterior completa sin reinicio.
- F5 grande: `big.zip` = 500876384 bytes (477.7 MiB), 62 JPEG raíz,
  sha `c008de9c…`. Upload API `202` en 19.400s; completed 62/62 (~50s
  proceso); descarga `200` (salida 499997574 bytes, `testzip None`, 64
  entradas con `review/`+`review.log`). Exceso API: `over.zip` (525336576
  bytes) → `413 {"detail":"upload exceeds 500 MiB"}` en 6.371s.
- Memoria (muestra acotada `memstats2.log`, 42 muestras api + 42 worker,
  timestamps 19:58:17→20:05:25 cubriendo upload+proceso del lote 477MiB):
  máx api 86.46MiB, máx worker 356.5MiB. Sin ZIP completo en RAM del
  servidor (archivo 477MiB ≫ picos), combinado con tests V2-07. Límite:
  muestreo cada ~7s, picos instantáneos pueden no verse; coste
  YOLO/decodificación incluido en worker. (Nota: `memstats.log` del primer
  muestreador conserva timestamps de flush poco fiables por buffer de pipe;
  no se usa como evidencia principal.)
- F4 reinicio worker mid-job (job `b1ed7f12-…` con big.zip): tras `docker
  restart`, estado `failed` con `worker interrupted before finishing; please
  submit the ZIP again` (progreso congelado 20/62); siguiente `small.zip`
  (`24a4f8a7-…`) completa 3/3. Segundo ciclo confirmó el mismo error
  legible (`88535059-…`, 0/62).
- F4 reinicio Compose con volúmenes: `down` (sin `-v`) + `up -d`; job
  `0f9f95da-…` sigue `completed` y su result descarga `200`, 2026 bytes,
  `testzip None`, 5 entradas. Pre/post restart conservado.
- F4 TTL/limpieza/reintento (registros de prueba, solo v210test): job
  `d6067b2a-…` envejecido vía `HSET finished_at` → result `410`; limpieza
  ociosa del worker lo borra → result `404`, job `404`, `EXISTS`=0. Retry:
  job `20f34ba5-…` envejecido + `docker stop rustfs` → cleanup falla
  (`EndpointConnectionError` en logs worker) y el registro se conserva
  (job `200`, result `410`); `docker start rustfs` → objetos
  `jobs/20f34ba5-…/input.zip|output.zip` ausentes (listado S3 vacío),
  result/job `404`, otros 19 IDs y 30 objetos `jobs/` intactos.
- T1: suite completa `.venv` → `544 passed, 1 skipped` en 48.20s,
  exit 0 (ver Revisión;
  log en `/tmp/v2-10-quality-tests.log`); `pip
  check` limpio; `docker compose config` OK (solo loopback +
  `container_name` únicos); `git diff --check` limpio.
- Skips/warnings exactos: skip único =
  `tests/test_archive.py:203: empty arcname not storable with zipfile`
  (preexistente). Sin skips V2-10 (ver Revisión, hallazgo 3). Warning único
  = `StarletteDeprecationWarning` por `starlette.testclient` con `httpx`
  (preexistente, sin cambio).
- F2 y dependientes BLOQUEADOS: sin ruta de corpus real indicada por el
  usuario; no se buscaron fotos privadas ni se descargó corpus. Sintéticos
  (sólidos/ruido) solo prueban plomería: todo cae en `review`
  (`no_person`); no hay evidencia de recorte real (`saved>0`) ni revisión
  visual. Ruta necesaria: carpeta o ZIP local con persona/recorte, sin
  persona, múltiples personas, EXIF/vertical y horizontal.

### Criterios

- F1 verificado (navegador+API reales, README contrastado en el recorrido).
- F2 pendiente bloqueado (falta corpus real).
- F3 verificado (inválido/anidado/ilegible/exceso frontend+API, reenvío OK).
- F4 verificado (reinicio worker/compose, TTL 410→404, retry con rustfs).
- F5 verificado (477MiB recorre+descarga íntegra, 413 en exceso, medición).
  Límite exacto (paso 3, log `/tmp/v2-10-exact-limit.log`): ZIP
  `/tmp/v210/exact500.zip` de exactamente 524288000 bytes (65 JPEG raíz,
  STORED, `testzip None`, sha
  `87a238ed…7938dc`; 64 blobs de ruido + `zzz-pad-0.jpg` con JPEG válido y
  relleno de ceros; primer intento dio 524287996 por nombre de 12 chars).
  Upload API multipart desde archivo → `202` en 28.37s; completed 65/65
  (~50s proceso, todo a review por sintéticos); descarga `200`,
  516162315 bytes, `testzip None`, 67 entradas con `review/`+`review.log`.
  Memoria: api 35.5→76.6→65.9MiB, worker 114→129→406MiB (sin ZIP completo
  en RAM; sin objetivo de rendimiento inventado).
- F6 verificado por el director: instrucciones del README contrastadas,
  evidencia en `/tmp/v210/` y logs registrados; contenedores, red y
  volúmenes propios eliminados, sin tocar recursos preexistentes.
- T1 verificado. T2 verificado (servicios/pesos CPU reales, solo loopback;
  dobles solo en unitarios). T3 pendiente del director.

### Limpieza

`docker compose -p v210test down` (sin `-v`; contenedores y red del
proyecto eliminados). `docker volume inspect v210test_redis-data
v210test_rustfs-data` mostró en ambos
`com.docker.compose.project=v210test`. Tras el `down` sin `-v`, el
coordinador ejecutó `docker volume rm v210test_redis-data
v210test_rustfs-data`, cuya salida fue ambos nombres (eliminados); luego
`docker volume ls --filter label=com.docker.compose.project=v210test` no
devolvió recursos (`down -v` no se usó en ningún momento; los volúmenes se
eliminaron explícitamente por nombre). No queda ningún recurso Docker
v210test (contenedores, red ni volúmenes). Este comando se registró en
`/tmp/v2-10-coordinator-review.log`. Recursos preexistentes intactos
(bridge/confluence/control-plane).
Artefactos `.playwright-mcp/` copiados a `/tmp/v210/` y eliminados del
worktree. Fixtures y resultados en `/tmp/v210/` (temporales, fuera de Git).
Imagen `autocrop:latest` conservada (coincide con el árbol).

## Revisión

Revisión independiente del director (2026-10-14): diff completo inspeccionado.
Solo cambian este contrato/registro y los dos tests/helpers V2-10; no hay
cambios de producto, V1, V2-09, índice global ni README. `app/worker.py` no
tiene diff. Hallazgos 1–5 de calidad de tests quedaron corregidos como se
describe abajo. El director confirmó en `/tmp/v2-10-exact-limit.log` y con
`stat`/`sha256sum` el ZIP exacto de 524288000 bytes (`87a238ed…257938dc`):
65 entradas JPEG válidas, API real respondió 202 en 28.37s, job completó
65/65, ZIP de salida respondió 200 en 5.03s y `testzip()` fue limpio.
La muestra observada llegó a 405.7 MiB en worker y 65.86 MiB en API; no se
trata como pico absoluto. El stack y volúmenes `v210test` ya no existen.

Comprobaciones independientes del director, sobre el árbol final:

- `.venv/bin/python -m pytest` → `544 passed, 1 skipped, 1 warning` en
  50.08s; log `/tmp/v2-10-director-suite.log`. El único skip preexistente
  es `tests/test_archive.py:203` (zipfile no almacena arcname vacío); el
  warning Starlette/httpx también es preexistente.
- `.venv/bin/python -m pip check` → `No broken requirements found.`
- `docker compose config` → exit 0; API y frontend publican solo en
  `127.0.0.1` (`8000`, `8080`). Log `/tmp/v2-10-director-compose.log`.
- `git diff --check` → exit 0.
- Hash/tamaño del ZIP exacto corroborados; `docker ps -a` y volúmenes por
  etiqueta no muestran recursos `v210test`.

Matriz final tras revisión: F1 verificado; F2 bloqueado por falta de corpus
real y de inspección visual; F3 verificado; F4 verificado; F5 verificado,
incluido el tamaño exacto; F6 verificado. T1 y T2 verificados. T3 no se puede
cerrar hasta resolver F2; V2 permanece en revisión y no se actualiza el
índice global.

### Hallazgos del director sobre calidad de tests (resueltos)

1. `test_v210_preflight_evidence_reused` dependía del artefacto externo
   `/tmp/v2-10-preflight.log` (contenido del coordinador, no del repo):
   eliminado junto con la constante `PREFLIGHT`. La validación de entorno
   queda en este registro, no en pytest.
2. `test_v210_no_unchecked_diff` duplicaba T1 y era débil: `git diff` omite
   archivos untracked (los tests nuevos nunca se revisaban): eliminado. T1
   se verifica con comandos directos (`diff --check` limpio confirmado).
3. `test_v210_real_photos_blocked` convertía F2 (validación manual
   pendiente) en un skip pytest: eliminado. F2 queda bloqueado solo en el
   texto de este registro; sin ruta de corpus no hay nada automatizable.
4. `test_v210_api_rejects_oversize_before_accepting` no verificaba el
   límite: publicaba 32 bytes y aceptaba 202/400/413/422, y construía un
   `bytes` de 500 MiB en unit tests. Ahora usa
   `JobService(..., max_upload_bytes=32)`, publica 33 bytes por TestClient,
   exige `413` exacto, `state.ids()` vacío y blob store sin objetos.
   `test_v210_invalid_and_nested_rejected` omitía el caso anidado real:
   ahora `nested.zip` lleva JPEG raíz válido `b.jpg` + `sub/nested.jpg`
   (bytes JPEG reales generados con PIL en memoria), exige `ValueError`
   con `unsafe entry name` y que la salida no exista (sin globs fuera de
   contrato). Resolución final del hallazgo 4 con JPEG reales confirmada en
   corrida dirigida antes del full suite.

Suite etapa: 9 passed, 0 skipped. Secuencia real: test dirigido
`test_v210_invalid_and_nested_rejected` con JPEG PIL en verde primero,
luego full suite sobre el árbol final
(`/tmp/v2-10-quality-tests.log`): `544 passed, 1 skipped, 1 warning`,
exit 0. Skip único: `tests/test_archive.py:203` (preexistente, arcname
vacío no almacenable con zipfile). Warning único: `StarletteDeprecationWarning`
(preexistente, `starlette.testclient` con `httpx`; sin cambio de alcance).
Sin skips V2-10: F2 bloqueado por falta de corpus real (texto, no pytest).

5. `test_v210_isolated_override_uses_free_loopback_ports` (T2) asignaba
   los dos puertos con llamadas secuenciales a `free_loopback_port()`: al
   cerrar el primer socket antes de abrir el segundo, el SO podía devolver
   el mismo puerto para API y frontend; además la aserción con `or`
   permitía que un puerto fuese 8000/8080. Ahora abre ambos sockets a la
   vez, exige `api_port != fe_port` y afirma individualmente que cada uno
   difiere de 8000 y 8080 (solo test, sin tocar producto). Test dirigido en
   verde, exit 0, stdout/stderr íntegro en
   `/tmp/v2-10-port-regression.log`.

6. El procedimiento de la etapa exige aceptar el límite exacto antes de
   comprobar exceso. La prueba grande previa de 477.7 MiB era cercana pero
   no satisfacía esa frontera. Resuelto con la validación integrada exacta
   descrita arriba; el exceso de 501 MiB siguió dando 413 por frontend y
   API. No hubo cambio de producción ni de tests por este hallazgo.

### Ampliación a 2 GiB exactos (aprobada por el usuario; implementador)

Mapa de límites auditado extremo a extremo:
- API streaming (`app/jobs.py::create_app`): multipart por bloques de 1MiB
  a tempfile, compara `size > max`; `submit_file` usa `os.path.getsize`.
  Sin copias del ZIP en RAM.
- `process_archive` (`app/archive.py`): stat del ZIP contra
  `MAX_INPUT_BYTES`; tope descomprimido declarado y en streaming contra
  `MAX_TOTAL_UNCOMPRESSED` (2GiB, sin cambios).
- FastAPI multipart spool: Starlette vuelca a disco desde ~1MB; sin tope
  propio que interfiera.
- Frontend proxy (`app/frontend.py`): reenvía cuerpo/respuesta por bloques
  de 64KiB sin tope de tamaño; `HTTPConnection(..., timeout=30)` persiste
  como límite conocido (ver abajo).
- Compose: sin topes; storage en volumen RustFS + disco host.
  Worker/descarga: worker reutiliza `process_archive`; descarga por
  `FileResponse` desde tempfile, sin tope.
- Overflow/unidades: contadores Python enteros arbitrarios, sin pérdida;
  `Content-Length` vía `int()`; ZIP <4GiB sin ZIP64; `file.size` exacto.
- Cambio: `MAX_UPLOAD_BYTES`/`MAX_INPUT_BYTES` = `2*1024**3` ==
  2147483648; mensajes 413/archivo y textos `frontend/index.html` a
  "2 GiB". Sin cambios de streaming/tempfiles. Alcance: `app/archive.py`,
  `app/jobs.py`, `frontend/index.html`, tests V2-10 y README (su "500 MiB"
  habría quedado falsa; razón explícita). Revertidos por director:
  `.plans/v2/PLAN.md`, `tests/test_archive.py`,
  `tests/test_v209_consistent.py` (0 diff; sus asserts "500 MiB" fallarán
  hasta decisión del director).

Regresión tests-primero: `test_v210_upload_limit_constants` y
`test_v210_frontend_states_2gib_limit` en rojo con el límite viejo, en
verde tras el cambio. Frontera exacta/+1 con config pequeña en HTTP
(32/33 bytes → 202/413); sin 2GiB en RAM ni archivo gigante en unit tests.

Evidencia integrada (`/tmp/v2-10-2g-validation.log`, stack v210test
reconstruido): `exact2g.zip` = 2147483648 bytes exactos (266 JPEG raíz,
STORED determinista, `testzip None`, sha `84bed3f6…`). Upload API
multipart desde archivo → `202` en 113.56s (`518f2422`; otro envío
`ea97ad16` completó 266/266 tras corte del cliente). Poll → `completed`
266/266 (todo a review, sintéticos). Descarga `200`, 2137209053 bytes,
`testzip None`, 268 entradas con `review/`+`review.log`. Exceso
`over2g.bin` (2147483649, sparse) por API → `413 {"detail":"upload
exceeds 2 GiB"}` en 60.69s. Exceso como ZIP válido `over2g.zip`
(2147483649 bytes, sha `284fda7a…51ecc10`, `testzip None`, 266 entradas;
fixture del coordinador por reflink/copia de `exact2g.zip` + un byte
trailing) por API multipart desde archivo → `413 {"detail":"upload
exceeds 2 GiB"}` exacto en 64.12s, sin job aceptado (`jobs:ids` vacío);
log `/tmp/v2-10-2g-valid-over-api.log`; fixture eliminada tras la prueba. Playwright MCP en frontend: exceso →
`límite excedido: el ZIP supera 2 GiB` en 54s; `small.zip` → `completed
2/2` con descarga (F1 intacto). Memoria (solo upload/API):
`/tmp/v2-10-2g-mem.log`, 13 muestras 23:56:12–23:58:03: API máx 99.74MiB,
worker máx 135.1MiB; la ventana terminó durante el upload, antes del
procesamiento de los 266 JPEG, así que worker inactivo/descarga no medidos
aquí. El pico del worker durante procesamiento 2GiB NO fue medido; no se
le atribuye. Los 405.7MiB corresponden al lote de 477.7MiB de la sección
previa, no a esta prueba (sin copia del ZIP en RAM en ambos casos).
Límite que persiste: timeout 30s del proxy < 113s de aceptación 2GiB; un
envío válido de 2GiB por UI probablemente 502 (no medido por UI; README ya
recomienda `curl` para lotes grandes). Sin fix (fuera del mínimo
aprobado); hallazgo para el director.
Limpieza: `down` sin `-v` + `volume rm` por nombre; sin recursos v210test;
externos intactos.

Hallazgo proxy (auditoría; resuelto): `app/frontend.py` usaba
`HTTPConnection(..., timeout=30)` para todo, pero el upload exacto de 2GiB
a la API midió 113.56s hasta el 202 → la UI en el límite habría devuelto
502 antes de la respuesta. Regresión
`test_v210_proxy_upload_timeout_supports_2gib` (stub de HTTPConnection,
sin red ni ZIP gigante): el rojo funcional se observó en sesión
(`{'timeout': 30}` < 300 en la aserción; los fallos previos fueron de
harness del stub, no de producto). `/tmp/v2-10-2g-proxy-tests.log`
conserva las corridas verdes. Fix mínimo:
`proxy_timeout = 600 if length else 30` (solo peticiones con cuerpo;
streaming por bloques de 64KiB intacto, sin buffer en RAM; GET y resto
conservan 30s). Verde: v210 (10 passed) + `test_frontend.py` + 4 browser
(`test_frontend_browser.py`), exit 0; log
`/tmp/v2-10-2g-proxy-tests.log`. README sin cambios (ya recomienda `curl`
para lotes grandes). Streaming intacto verificado por suites existentes.

Validación final posterior al cambio: suite completa exit 1,
`3 failed, 544 passed, 1 skipped, 1 warning` en 63.65s, log
`/tmp/v2-10-2g-final-suite.log`. Fallos ajenos sin corregir (alcance):
`tests/test_archive.py::test_rejects_compressed_limit` espera el texto
obsoleto "500 MiB";
`tests/test_v209_consistent.py::test_upload_errors_readable_and_allow_retry[chromium]`
y `tests/test_v209_consistent.py::test_page_hints_single_job_and_safe_rendering`
esperan texto "500". No se modificaron tests de V2-01/V2-09 por alcance
indicado; decisión del director pendiente. `pip check` exit 0, `docker
compose config` exit 0, `git diff --check` exit 0. Proxy tests focalizados
exit 0: 30 passed + 1 warning y 4 browser passed (11.51s) en
`/tmp/v2-10-2g-proxy-tests.log`. Plan en revisión por F2; suite completa
no verde.

Pendientes ajenos: `test_f3_asgi_send_failure_cleans_temp` /
`test_f3_asgi_cancelled_cleans_temp` solo fallan si
`test_v209_consistent.py` corre antes (interferencia preexistente en árbol
limpio); en orden de suite pasan (exit 0).
