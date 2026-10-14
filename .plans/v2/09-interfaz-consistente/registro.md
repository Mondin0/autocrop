# Etapa V2-09 — Registro

## Implementación

Archivos modificados (solo V2-09; el resto del árbol ajeno se preservó intacto):

- `frontend/index.html`: generación/token por envío, botón deshabilitado
  mientras se acepta, selección vacía sin petición, sondeo inmediato y luego
  cada segundo con cadena `setTimeout` (sin solapamiento ni `setInterval`),
  errores legibles de HTTP/conexión/JSON inválido en carga/consulta/descarga,
  descarga ligada al UUID original con nombre propio, 410 vencido y 404
  ausente/limpiado, `textContent` para texto externo, aviso visible de
  JPEG en raíz + 500 MiB + 3 h + reenvío tras aceptación/fallo.
- `tests/test_v209_consistent.py` (nuevo, 16 tests): regresiones de navegador
  con doble API controlada + 2 tests estáticos (página y README).
- `README.md`: `--profile v1` en todos los comandos CLI Docker V1 (up,
  down, hub), arranque V2 sin carpetas host (ya existía), reinicio
  (interrumpidos fallan, sin reanudación), expiración/limpieza 3 h
  (410 vencido, 404 tras limpieza, retención de fallidos), diagnóstico por
  logs, redirección raíz API histórica a 8080 + puerto frontend
  personalizado. Párrafo preexistente de `Response.blob()` conservado
  verbatim e integrado con sección nueva de recuperación.

Comandos y resultados reales (desde `.venv`):

- Disponibilidad navegador: `.venv/bin/python -c` con playwright lanza
  Chromium (`chromium ok`); MCP Playwright (`npm exec @playwright/mcp`)
  corriendo como servidores 1252145/1269453/1284329.
- Diagnóstico timeout shell 120 s: sin procesos pytest/chromium colgados;
  fue acumulación de wall-time (16 tests navegador × arranque + esperas
  rojas de 8 s + sleeps hasta 5 s), no cuelgue. Mitigado con bloques,
  pruebas individuales con salida completa y validación directa vía MCP.
- Rojo funcional original (pytest, pre-implementación):
  `posts == 1` → `assert 2 == 1` (doble clic); estáticos página/README
  (`generation`/`setTimeout`/hints ausentes; `interrump` ausente);
  `wait_for_function` 8 s en selección vacía, JSON inválido, 500, conexión
  y aceptación con JSON roto.
- Rojo vía MCP Playwright (stub `/tmp/opencode/v209_stub.py`, API 44239/FE
  38105): F1 respuesta tardía A overwrite → `estado: completed`,
  `procesadas 99/5`, descarga `/api/jobs/job-A/result` sobre vista de B;
  F2 doble clic → `posts == 2`, botón habilitado; F2 solape →
  `max_concurrent == 3` con sondeos de 1,4 s.
- Verde vía MCP (mismo stub, puertos 33763/44303): F1 vista B intacta
  (`estado: processing`, `job-B-pic.jpg`, error vacío, descarga oculta);
  F2 `posts == 1` + botón deshabilitado + aceptación tras liberar;
  F2 `max_concurrent == 1` con 5 sondeos seriados.
- Suite etapa: 16/16 en verde (bloques A/B y casos F4/estáticos
  individuales con salida completa).
- Suites existentes: `tests/test_frontend.py` 18 passed,
  `tests/test_frontend_browser.py` 4 passed (sin regresiones).
- Suite completa (job `sh_13c7ae6b8001cM4OuQnAd3oVE4`,
  `/tmp/opencode/v209_fullsuite.log`): `exit=0`, 534 tests recolectados,
  1 skip condicional preexistente (docker CLI/links, ajeno a V2-09).
- `.venv/bin/python -m pip check`: `No broken requirements found`.
- `git diff --check`: rc=0.
- `docker compose config --services` sin perfil excluye `autocrop` (V1 no
  arranca por defecto, V2 sin carpetas host); con `--profile v1` lo incluye;
  puertos en `127.0.0.1:8000/8080`. Sin ejecutar CLI sobre originales.

Correcciones de expectativas documentadas (tests, no contrato):

1. `_wait_accepted` esperaba texto `trabajo aceptado: <id>`, pero el
   contrato exige consultar inmediatamente al aceptar y el primer sondeo
   reemplaza esa línea transitoria (verificado: `estado: processing` sin id
   tras aceptar). Ahora espera aceptación registrada en el doble + actividad
   visible; cada test exige además su contenido específico.
2. Asserts `"job-B" in #status` → estados/contadores de B (`processing`,
   `3/5`) porque el sondeo no repite el UUID; la pertenencia al trabajo
   actual la prueban valores distintivos (99/5 de A ausente, descarga
   oculta, nombre `job-A.zip` con bytes A tras cambiar a B).
3. Simulación de fallo de conexión: un corte aguas arriba lo convierte el
   proxy en HTTP 502, así que el fallo real del navegador (fetch rechaza)
   se simula tumbando el frontend (`live_v9_ctrl` + `_kill/_revive`);
   verificado mensaje, detención, botón habilitado y reenvío tras revivir.

Criterios cubiertos: F1 (tardías ignoradas en carga/consulta/descarga),
F2 (sin duplicados ni solape; reenvío tras fallo/aceptación), F3 (vacía,
JSON roto, HTTP/conexión visibles y detienen lo que corresponde), F4
(UUID/nombre, 410/404, sin descarga en queued/processing/failed, sin
pestaña de error, límites comprensibles), F5 (perfiles, recuperación,
retención, logs, memoria cliente, puertos), T1 (JS nativo, accesibilidad y
`textContent` conservados), T2 (regresiones primero, verde completo, checks).

Pendientes y limitaciones reales: revisión del director (hallazgos
pendientes de registrar abajo); validación integral con fotos reales,
lote grande y expiración corresponde a V2-10, no a esta etapa; la suite
completa `-q` no imprimió línea de resumen (solo puntos), vale `exit=0`.

## Revisión

Revisión inicial del implementador (previa al director): diff limitado a
`frontend/index.html`, `README.md`, `tests/test_v209_consistent.py` y esta
etapa; cambios ajenos del árbol intactos; cobertura existente sin debilitar
(ningún test previo tocado); todos los retornos tras `setSending(true)`
rehabilitan el envío; sin ramas para estados API inexistentes; sin
framework ni rediseño. Sin hallazgos propios pendientes.

## Revisión (iteración 1 — hallazgo del director)

Hallazgo: `frontend/index.html`, `poll(jobId, gen)`, bloque
`catch (err)` de `await res.json()` sin comprobar `gen === generation`.
Si la consulta A espera su body, el usuario envía B y A resuelve JSON
inválido, A muestra error y detiene el sondeo de B. Impacto: vista del
trabajo actual corrompida por respuesta tardía + sondeo detenido.
Criterios afectados: F1 (aislamiento de tardías) y F3 (error visible donde
corresponde). Corrección esperada: guardar error y parar polling solo si
`gen === generation`, con regresión controlada previa.

Diagnóstico: el doble inicial bloqueaba antes de enviar headers, por lo que
`await fetch()` esperaba y el guard post-fetch descartaba A sin alcanzar el
`catch` (falso verde). Se añadió al doble la acción `headers_first`: envía
status 200 + `Content-Length` con flush, bloquea solo el body, y señala
`done` tras enviarlo. Así `await res.json()` espera mientras B avanza y A
alcanza el `catch` con generación obsoleta.

Evidencia roja (pre-producción, sin tocar producción):

- pytest controlado, salida completa:
  `assert _text(page, "#error") == ""` →
  `AssertionError: assert 'respuesta in...ar el trabajo' == ''`
  (`respuesta inválida al consultar el trabajo` sobre la vista de B).
- MCP Playwright interactivo (stub `/tmp/opencode/v209_stub.py`,
  API 46489/FE 39837, A headers retenidos tras compuerta `relM`, B en
  processing visible, error baseline `""`): tras liberar el body,
  `{"status":"estado: processing","error":"respuesta inválida al consultar
  el trabajo"}`. Rojo independiente confirmado.

Corrección aplicada (menor diff, solo el `catch`):

```js
} catch (err) {
  if (gen !== generation) {
    return;
  }
  stopPolling();
  showError("respuesta inválida al consultar el trabajo");
  return;
}
```

Evidencia verde:

- Regresión `test_stale_invalid_json_poll_does_not_stop_current`: passed.
- MCP mismo escenario tras el fix: `{"status":"estado: processing",
  "current":"foto actual: job-B-pic.jpg","error":""}` con sondeos B
  avanzando (`polls` 6 y creciendo).
- Suite etapa `tests/test_v209_consistent.py`: 17/17 en verde (7+10).
- Existentes `tests/test_frontend.py` + `tests/test_frontend_browser.py`:
  22/22 en verde. `git diff --check`: rc=0. Sin suite completa repetida
  (cambio de 3 líneas sobre base ya validada con exit=0).

La etapa vuelve a `en revisión`; no se declara completada.

## Revisión (iteración 2 — hallazgos F5/T1/T2 del director)

Hallazgo 1: `README.md` presentaba `./autocrop-run` como atajo V1, pero
`autocrop-run:30` ejecutaba `docker compose up` sin `--profile v1` mientras
`compose.yaml` pone `autocrop` bajo `profiles: ["v1"]`. En checkout limpio
el servicio no arranca y luego falla `docker exec autocrop`. Impacto: atajo
V1 roto de fábrica. Criterios: F5 (operar V1 con su perfil), T2 (regresión
primero). Corrección esperada: llamada Compose con profile v1 + regresión
README/wrapper previa con rojo.

Hallazgo 2: `README.md:179` añadía `--profile v1` al comando Docker Hub
(`-f compose.yaml -f compose.hub.yaml up -d`), que levanta el stack V2
(API/worker/frontend+Redis/RustFS). Con profile v1 se activa además el
servicio V1, que requiere `fotos/`/`output/` del host y contradice el
arranque V2 sin carpetas. Fue error de implementación de esta misma etapa,
no del contrato (no se cambia el contrato). Impacto: doc V2 inconsistente.
Criterios: F5, T2. Corrección esperada: comando Hub sin profile + test que
exija perfiles solo en instrucciones realmente V1.

Hallazgo 3 (calidad de test, T1): `test_page_hints_single_job_and_safe_rendering`
exigía tokens internos (`generation`, `setTimeout`, ausencia de
`setInterval`); F1/F2 ya se validan en navegador. Corrección: conservar
solo hints observables (JPEG/raíz, 500, tres horas) y texto seguro
(`textContent`, botón deshabilitado).

Evidencia roja (pre-producción, assertions a archivos/Compose sin Docker):

- `test_wrapper_starts_v1_service_before_exec` FAILED:
  `el wrapper debe arrancar el perfil v1 antes de docker exec autocrop`.
- `test_readme_covers_profiles_recovery_and_limits` FAILED (bloque Hub con
  `--profile`).

Correcciones (solo `autocrop-run`, `README`, tests asociados):

- `autocrop-run:30`: `docker compose --profile v1 up -d --quiet-pull`.
- `README.md:179`: `docker compose -f compose.yaml -f compose.hub.yaml up -d`.
- Test README: bloque Hub V2 sin `--profile`; bloques `up -d --build` con
  `autocrop --input` (instrucciones realmente V1) con `--profile v1`. El
  bloque V2 sin CLI queda excluido a propósito (sin perfil, verificado
  contra `docker compose config`).

Evidencia verde:

- `bash -n autocrop-run`: ok. Tests readme/wrapper/page_hints: 3 passed.
- `docker compose -f compose.yaml -f compose.hub.yaml config --services`
  excluye `autocrop`; con `--profile v1` lo incluye.
- `git diff --check`: rc=0. Sin suite completa (la ejecuta el director).
- Alcance verificado: solo `autocrop-run`, `README.md`,
  `tests/test_v209_consistent.py` y plan/registro 09; visual sin tocar.

La etapa vuelve a `en revisión`; no se declara completada.

## Cierre iteración 2 — verificación final post-iteración (F5/T1/T2)

Archivo de etapa entero en su estado actual
(`tests/test_v209_consistent.py`, 18 tests: 15 navegador + 3 estáticos,
incluye regresión JSON-invalid-stale y tests README/wrapper):

- Suite etapa entera: 18/18 passed, `exit=0`
  (log `/tmp/opencode/v209_stage_final.log`, sin `F`/fallos).
- `bash -n autocrop-run`: sintaxis ok, rc=0.
- `tests/test_cli.py` (cobertura CLI vinculada al wrapper): 22 passed.
- `git diff --check`: rc=0. Suite completa global no ejecutada (la corre
  el director de forma independiente; la base ya validó exit=0 y este
  cierre solo toca wrapper/README/tests de etapa).
- `plan.md` se mantiene `en revisión`; no se marca completada.

## Revisión final del director

Diff de V2-09 revisado completo: `frontend/index.html`,
`tests/test_v209_consistent.py`, `autocrop-run`, `README.md` y este plan y
registro. Los cambios preexistentes de V2-07/08 y sus planes se conservaron.

Verificación de criterios:

- **F1:** regresiones de navegador muestran completed, failed y JSON inválido
  tardíos de A sin alterar B; demora de descarga conserva UUID/nombre de A.
  Revisé el guard de generación tras `fetch`, `res.json` y sus errores.
- **F2:** doble clic registra un solo POST, se habilita el reenvío tras
  aceptación/error, y la medición con consulta de 1,4 s mantiene una sola
  consulta activa.
- **F3:** pruebas controladas cubren selección vacía, JSON roto, HTTP y
  conexión en carga/estado/descarga, con mensajes visibles y recuperación.
- **F4:** pruebas mantienen contadores/campos, descarga por UUID, 410/404,
  estados sin descarga y texto externo inocuo; la página informa límites y
  retención.
- **F5:** comandos V1 activan `v1`, incluido el wrapper; Docker Hub V2 no lo
  activa. README explica reinicio, fallidos, expiración/limpieza, logs,
  redirección/puerto y límite de memoria del navegador.
- **T1:** JavaScript nativo, labels y regiones accesibles conservadas,
  `textContent` para contenido externo, sin dependencias ni rediseño.
- **T2:** regresiones nuevas tuvieron evidencia roja funcional antes de
  corregir y quedaron verdes; Playwright MCP de OpenCode se usó en las
  secuencias de concurrencia y respuestas tardías.

Comprobaciones independientes del director, después de la iteración final:

- `.venv/bin/python -m pytest -q`: terminó al 100 %, un skip condicional,
  código de salida 0. Log: `/tmp/autocrop-v2-09-director-final.log`.
- `.venv/bin/python -m pip check`: `No broken requirements found`.
- `git diff --check`: rc=0.
- `bash -n autocrop-run`: rc=0.
- `docker compose config --services` y el overlay Docker Hub V2 excluyen
  `autocrop`; la configuración con `--profile v1` lo incluye.

Los cuatro hallazgos del director quedaron corregidos: JSON inválido de
sondeo obsoleto (F1/F3), wrapper V1 sin perfil (F5), perfil V1 añadido por
error al comando Docker Hub V2 (F5) y aserciones de test acopladas a nombres
internos (T1/T2). No quedan hallazgos pendientes. La validación con fotos,
lote grande y expiración real corresponde a V2-10 y no bloquea esta etapa.

**Cierre:** V2-09 completada. La etapa trata consistencia de interfaz y
documentación de una demo local; no afecta seguridad ni integridad de
archivos originales.

Archivos finales de la etapa: `frontend/index.html`,
`tests/test_v209_consistent.py` (nuevo), `autocrop-run`, `README.md`,
`.plans/v2/09-interfaz-consistente/plan.md` y `registro.md`. Cambios
preexistentes ajenos intactos.
