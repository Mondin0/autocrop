# Etapa 07 — Registro

## Implementación (Muse)

### Archivos de la etapa (sin tocar `app/`)

- `pyproject.toml`: `dependencies` pinneadas a
  `ultralytics==8.4.174`, `Pillow==12.3.0`, `torch==2.14.1`,
  `torchvision==0.29.1`, sin sufijo de plataforma (cada OS resuelve su
  wheel). Coinciden con lo instalado en `.venv` (verificado con
  `pip list`: mismos 4 pins), así que no hizo falta reinstalar el entorno
  del repo.
- `setup-mac.sh` (nuevo, ejecutable): verifica `python3.12` (error claro
  con `brew install python@3.12` / python.org, sin auto-instalar), exige
  `yolo11n.pt` con hash `0ebbc80d…7644ee1` vía `shasum -a 256` (fallback
  a `sha256sum`), crea `.venv` si falta, instala `.` (runtime) o
  `.[dev]` solo con flag explícito `--dev`, corre
  `.venv/bin/autocrop --help` y un humo sintético (JPEG blanco 640x480
  generado con Pillow en `mktemp -d`, exige `1 processed` + `1 review` y
  `review/blank.jpg`, con `trap` de limpieza). Nunca referencia
  originales reales.
- `tests/test_setup_mac.py` (nuevo, 9 tests): pins exactos sin sufijos,
  script existente/ejecutable, `bash -n` limpio, hint de instalación
  python3.12 sin auto-instalación, hash esperado, humo en temporales con
  `1 processed`/`1 review` sin `fotos/`, criterio `--dev`, pipeline
  intacto (`device="cpu"`, sin `mps`), sección Mac en README.
- `README.md`: sección Mac (requisito Python 3.12, `./setup-mac.sh` /
  `--dev`, qué hacer si falla, CPU sin MPS como mejora futura, nota de
  que ARM vs Linux puede diferir en píxeles de borde).
- Sin cambios en `app/` (`git status` no muestra nada bajo `app/`;
  `device="cpu"` intacto en `app/detector.py:117`).

### Wheels macOS ARM64 (contrato punto 1, sin sustituciones)

Verificado contra PyPI (`pypi.org/pypi/<pkg>/<ver>/json`): `torch 2.14.1`
y `torchvision 0.29.1` publican `cp312-macosx_14_0_arm64.whl`;
`ultralytics 8.4.174` es `py3-none-any` (puro Python, vale en ARM64);
`Pillow 12.3.0` publica 18 wheels macOS (incluye ARM64). Ningún pin
requiere sustitución.

### Tests primero (rojo real) y verde

- Corrida roja inicial: 9 failed — pins ausentes en pyproject,
  `setup-mac.sh` inexistente (`bash -n`: 127, fichero ausente) y README
  sin sección (fallos funcionales pendientes, no de importación).
- Ajuste de test documentado: la primera versión de
  `test_setup_mac_runs_help…` fallaba solo por la palabra `fotos` en un
  comentario del script; se reescribió el comentario (el script nunca
  toca originales) y se mantuvo la aserción estricta como guardia.
- Verde: `tests/test_setup_mac.py` 9 passed; suite completa
  `.venv/bin/python -m pytest` → 332 passed (323 baseline + 9), código 0
  real; `.venv/bin/python -m pip check` → `No broken requirements
  found`, código 0. `bash -n setup-mac.sh` → 0.

### Corrida real del script en copia limpia Linux (F1/F3, códigos reales)

- `cp -r app pyproject.toml README.md setup-mac.sh yolo11n.pt /tmp/ac07`
  (sin `.venv`/`.git`/`fotos/`) y `./setup-mac.sh` → `SCRIPT:0`:
  venv creado con `python3.12`, pins instalados desde caché
  (`torch==2.14.1`, `torchvision==0.29.1`, `ultralytics==8.4.174`,
  `pillow==12.3.0` en `pip list`), `--help` en 0, humo YOLO real
  `Done: 1 processed, 0 saved, 1 review, 0 skipped` + `setup-mac OK`.
  `pip check` en ese venv → 0. `ls /tmp | grep -c '^tmp\.'` → 0
  (trap limpió el temporal del humo).
- `./setup-mac.sh --dev` en la misma copia → `DEV_CODE:0` (reinstala
  `.[dev]`, mismo humo verde).
- `./setup-mac.sh --help` en el repo → `HELP_CODE:0`, sin efectos.

### Rutas de error (F2/F4, códigos reales, sin pipes)

- Sin `yolo11n.pt` (solo script en `/tmp/ac07noweight`) → código 1:
  `error: yolo11n.pt no encontrado en …`.
- `yolo11n.pt` falso en `/tmp/ac07bad` → código 1:
  `error: el hash de yolo11n.pt difiere del esperado (0ebbc80d…)`.
- Sin `python3.12` (`PATH` reducido a stubs sin python) → código 1:
  `error: python3.12 no encontrado.` + `brew install python@3.12` /
  python.org. No auto-instala nada.
- `yolo11n.pt` del repo intacto antes/después (`0ebbc80d…7644ee1`).

### Criterios cubiertos y pendientes

- Cubiertos con evidencia real en Linux: F1 (venv+`--help` en 0 en copia
  limpia), F2 (falta/difiere → 1 con error claro), F3 (humo sintético
  `1 processed`/`1 review`, review generado, originales intactos), F4
  (error con cómo instalar python3.12), T1 (332 passed + `pip check`
  verdes en repo y en venv fresco), T2 (`bash -n` 0), T3 (`app/`
  intacto).
- Pendiente explícito (bloqueo conocido, no inventado): corrida real en
  Apple Silicon (`./setup-mac.sh` en Mac moderna). Lo verificado arriba
  es el mismo script y pins, pero resueltos contra wheels Linux; en Mac
  pip resolverá los wheels ARM64 verificados en PyPI. No se declara la
  etapa completada. MPS registrado como mejora futura, no implementado.
- Limpieza: `/tmp/ac07`, `/tmp/ac07bad`, `/tmp/ac07noweight`,
  `/tmp/ac07nopy` son temporales fuera del repo (pueden borrarse); el
  repo solo contiene los 5 cambios listados en `git status`.

### Correcciones de R1/R2 (Muse, 2026-10-08)

Entrega para nueva revisión; no se aprueban ni cierran los hallazgos de Astra.
Se preserva la evidencia anterior y no se modifica el contrato ni `app/`.

- **R1, F1–F4 y runtime/`--dev`:** se reemplazaron los cuatro tests que
  buscaban cadenas de comportamiento en `setup-mac.sh` por ejecuciones del
  script copiado a proyectos temporales, incluyendo rutas con espacios.
  Se conservan pins, ejecutabilidad, sintaxis, README y guardia CPU.
  Los 27 casos del archivo prueban Python ausente, pesos ausentes/hash
  inválido, hash correcto y fallback `sha256sum`, instalación exacta `.`
  versus `-e .[dev]`, creación/reutilización del entorno, ayuda del script
  sin efectos, ayuda CLI fallida, éxito y cuatro fallos del humo (CLI no
  cero, resumen sin processed/review y archivo review ausente).
  Se observan códigos, mensajes, argumentos y orden de llamadas, efectos
  y limpieza del temporal tanto en éxito como en fallos. `fotos/` y pesos
  tienen contenido centinela que debe permanecer intacto.
- Aislamiento de R1: PATH limitado a herramientas permitidas; dobles
  controlados para intérprete/creación de venv, pip, hash y CLI, con log
  de llamadas. Bash, `mktemp`, limpieza y generación JPEG con Pillow se
  ejecutan realmente; la CLI doble comprueba formato JPEG, tamaño 640x480
  y blanco. No hay red, descargas, instalación real ni carga de YOLO.
  Dobles de `brew`/`curl`/`wget` permiten detectar intentos prohibidos.
  Esta evidencia prueba el flujo del script, no una instalación real Mac.
- **R2, F1/F4:** `setup-mac.sh` ahora ejecuta una comprobación de versión
  `(3, 12)` para el Python disponible y para `.venv/bin/python`; exige
  `pyvenv.cfg`, Python ejecutable y pip disponible antes de instalar.
  Usa `-B` en las comprobaciones para no escribir bytecode. Un `.venv`
  existente inválido no se recrea, borra ni repara; recibe `error:` claro.
  Regresiones: ejecutable llamado python3.12 que es 3.11/3.13, `.venv`
  de 3.11, Python ausente/no ejecutable, configuración ausente, pip ausente
  y `.venv` como archivo. Se verifican bytes, permisos, mtime y conjunto
  de archivos conservados, sin llamadas de creación ni instalación.
- **Tests primero, rojo real:** antes de editar producción,
  `.venv/bin/python -m pytest -q tests/test_setup_mac.py` → código 1,
  8 failed y 19 passed. Python 3.11/3.13 y venv 3.11/sin configuración
  se aceptaban; otros entornos inválidos fallaban sin diagnóstico claro.
  No fueron fallos de importación ni instalación. Ningún test se debilitó.
- **Verificación tras las correcciones:**
  `.venv/bin/python -m pytest -q tests/test_setup_mac.py` → código 0,
  27 casos verdes; `.venv/bin/python -m pytest` → código 0,
  350 passed. `.venv/bin/python -m pip check` → código 0,
  `No broken requirements found.`; `bash -n setup-mac.sh` → código 0;
  `git diff --check` → código 0; `git diff -- app` → vacío (T3).
  Como los cuatro archivos de esta entrega aún no están trackeados,
  también se ejecutó `git diff --no-index --check /dev/null <archivo>`
  para cada uno: código 1 por diferencias con `/dev/null`, sin diagnóstico
  de whitespace en ninguno (no se agregaron al índice).
- Archivos afectados por esta corrección: `setup-mac.sh`,
  `tests/test_setup_mac.py` y `plans/07-venv-mac/{plan,registro}.md`.
  No se alteran los cambios previos de README/pyproject ni los pins.
- **Pendientes:** nueva revisión de R1/R2 por Astra y corrida real de
  `./setup-mac.sh` en Apple Silicon (sin Mac disponible). Estado de etapa:
  `en revisión`, no completada; no se desarrollaron fases futuras.

## Revisión (Astra / coordinador)

Revisión de contrato, tests, script y diff realizada el 2026-10-08.
No se corrigió implementación durante esta revisión.

### Comprobaciones independientes

- `.venv/bin/python -m pytest -q`: código 0, 332 tests pasan.
- `.venv/bin/python -m pip check`: código 0, `No broken requirements found.`
- `bash -n setup-mac.sh`: código 0.
- `git diff --check`: código 0.
- `git diff -- app`: vacío; T3 conforme en esta etapa.
- Pins declarados coinciden con el contrato. La corrida en Mac sigue
  pendiente; los resultados Linux no prueban Apple Silicon.

### Hallazgos pendientes

**R1 — Alta: tests de comportamiento sustituidos por búsquedas de texto.**
Ubicación: `tests/test_setup_mac.py:56-87`.
Criterios afectados: F1–F4 y contrato de instalación runtime/`--dev`.
Los tests pasan si el hash o los comandos de humo aparecen en comentarios,
si se elimina el rechazo de pesos inválidos, o si se omite ejecutar la CLI.
El test de no auto-instalar tampoco lo garantiza: elimina la cadena de
Homebrew antes de inspeccionar, incluyendo una posible ejecución real.
La evidencia manual registrada es útil, pero no deja regresiones ejecutables.
Corrección esperada: ejecutar el script en copias temporales con comandos
controlados cuando haga falta, sin red ni instalación pesada, y verificar
códigos, mensajes, llamadas y efectos para Python ausente, pesos ausentes o
inválidos, instalación runtime/`--dev`, help fallido, humo fallido y éxito.
Conservar los tests de pins y sintaxis; reemplazar aserciones textuales de
comportamiento por checks observables. Verificar que originales no cambian
y que el temporal del humo se limpia también cuando falla.

**R2 — Media: reutiliza `.venv` sin comprobar su intérprete.**
Ubicación: `setup-mac.sh:20-24,40-45`.
Criterio afectado: F1 y contrato de entorno Python 3.12.
Encontrar `python3.12` en PATH no asegura que `.venv/bin/python` sea 3.12:
si `.venv` ya existe con otra versión, instala y ejecuta allí; si está
incompleto, falla con un error de shell poco claro. El test de F4 solo busca
el nombre del ejecutable y no detecta este caso.
Corrección esperada: comprobar versión del Python disponible y del entorno
reutilizado; ante `.venv` incompatible o incompleto, fallar claramente sin
borrarlo ni modificarlo. Agregar regresión antes de corregir.

### Veredicto

No aprobada todavía. Volver a `en implementación` por R1/R2. La validación
real en Mac permanece pendiente y será necesaria para cerrar la etapa.

### Segunda revisión (2026-10-09, tras correcciones R1/R2)

Revisados `setup-mac.sh`, `tests/test_setup_mac.py` (27 casos), diff de
README/pyproject y la sección de correcciones del registro. No se corrigió
implementación durante esta revisión.

Comprobaciones independientes (códigos reales, sin pipes):

- `.venv/bin/python -m pytest`: código 0, suite completa verde.
- `tests/test_setup_mac.py` solo: 27 passed.
- `.venv/bin/python -m pip check`: código 0,
  `No broken requirements found.`
- `bash -n setup-mac.sh`: código 0. `git diff --check`: código 0.
- `git diff -- app`: vacío; T3 conforme.
- `sha256sum yolo11n.pt` → `0ebbc80d…7644ee1`, idéntico al hash embebido
  en el script (F2 anclado al archivo real del repo).
- Wheels ARM64 verificados contra PyPI (`/pypi/<pkg>/<ver>/json`):
  `torch`/`torchvision` 2.14.1/0.29.1 publican
  `cp312-macosx_14_0_arm64.whl`; `ultralytics` 8.4.174 es `py3-none-any`;
  `Pillow` 12.3.0 publica wheels macOS ARM64. Sin sustituciones.
- Compatibilidad shell: el script no usa construcciones de bash ≥ 4
  (solo `set -euo pipefail`, funciones, `command -v`, `trap`, heredoc),
  apto para el bash 3.2 de macOS.

R1 — resuelto. Los 4 tests textuales fueron reemplazados por ejecución
observable del script en copias temporales (incluye rutas con espacios):
códigos, mensajes `error:`, orden de llamadas (hash → venv → pip
`--version` → install → `--help` → humo), instalación exacta `.` vs
`-e .[dev]`, fallback `sha256sum`, 4 modos de fallo del humo, limpieza
del temporal incluso al fallar y preservación de `fotos/` + pesos con
centinela. Dobles solo en los bordes (intérprete/venv/pip/hash/CLI);
Bash, temporales y JPEG real con Pillow se ejecutan de verdad. El
doble de CLI valida formato/tamaño/contenido del JPEG de entrada.

R2 — resuelto. El script valida `(3, 12)` del Python disponible y del
`.venv` reutilizado, exige `pyvenv.cfg` + Python ejecutable + pip, y
ante entorno inválido falla con `error:` claro sin borrar, recrear ni
modificar nada (regresiones con bytes/permisos/mtime y conjunto de
archivos). Regresión previa real: 8 failed antes de corregir.

Observación menor, no bloqueante: ningún test ancla el hash embebido al
contenido de `yolo11n.pt` del repo (si los pesos se reemplazan sin
actualizar el script, la suite seguiría verde). Verificado manualmente
arriba; se deja como mejora opcional, no como hallazgo.

Veredicto: R1/R2 cerrados. Criterios F1–F4 y T1–T3 verificados en Linux.
La etapa sigue `en revisión` (no completada): el único pendiente es la
corrida real de `./setup-mac.sh` en Apple Silicon, que este entorno no
puede ejecutar.
