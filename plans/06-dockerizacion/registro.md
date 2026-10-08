# Etapa 06 — Registro

## Implementación (Muse / OpenCode Zen)

### Archivos de la etapa (solo adiciones + docs; etapas 01–05 intactas)

- `Dockerfile` (nuevo): `python:3.12-slim`, `libgl1`+`libglib2.0-0`,
  `WORKDIR /app`, `HOME=/tmp/home` escribible (777), `torch`+`torchvision`
  del índice solo-CPU exclusivo (R2, sin `--extra-index`), luego
  `ultralytics`+`Pillow` de PyPI, `COPY yolo11n.pt` local (sin él el build
  falla, sin descargas), `pip install --no-deps .` + `pip check`,
  `CMD ["sleep", "infinity"]`.
- `compose.yaml` (nuevo): servicio y `container_name: autocrop`, sin puertos
  ni restart, `sleep infinity`, `user: ${AUTOCROP_UID:-1000}:${AUTOCROP_GID:-1000}`,
  `/input` readonly + `/output` escritura con `create_host_path: false`,
  fuentes `${AUTOCROP_INPUT_DIR:-./fotos}` / `${AUTOCROP_OUTPUT_DIR:-./output}`.
- `.dockerignore` (nuevo, corregido R1): allowlist estricta —
  `*` + `!Dockerfile !pyproject.toml !README.md !app/ !yolo11n.pt`,
  más `**/__pycache__/` y `*.pyc` (caches fuera incluso dentro de `app/`).
- `pyproject.toml`: `[project.scripts] autocrop = "app.cli:main"`
  (reutiliza `app.cli:main`; `python -m app.cli` intacto).
- `tests/test_packaging.py` (nuevo, 5 tests): declara script, entry point
  instalado resuelve a `app.cli.main`, binario `--help` y error sin args
  equivalen al módulo, `main(["--help"])` sale 0.
- `README.md`: sección Docker completa (requisitos, pesos, exports con rutas
  absolutas y UID/GID, `mkdir` salida, build/up, help, procesamiento,
  readonly/output/permisos, recreación ante cambio de mounts, `down`, CPU,
  nota de que empaquetar no mejora la selección).
- `PLAN.md`: índice etapa 06 + decisión Docker solicitada por usuario.
- Sin cambios en `app/crop.py`, `app/subject.py`, `app/processor.py`
  (salvo los previos de etapas 01–05, preservados sin revertir).

### Tests primero (T1) y nota de evidencia

- Corrida roja inicial (antes de declarar el script): 4 failed, 1 passed —
  `test_pyproject_declares…`, `test_installed_entry_point…` y los dos del
  binario (`.venv/bin/autocrop` inexistente: `FileNotFoundError`, fallo
  funcional pendiente, no import de módulo inexistente).
- Corrección de registro: en la sesión anterior los `EXIT:0` visibles tras
  `pytest … | tail` / `docker … | tail` eran el código de `tail`, no del
  comando. Abajo todos los códigos son reales (capturados con `; echo
  CODE:$?`, sin pipe). El fallo rojo observado queda registrado como tal;
  la suite actual está en verde (323 passed, código 0 real).
- Reajuste de tests de help: primera versión exigía `stdout` idéntico entre
  binario y módulo; falla solo por el nombre de programa (`usage: autocrop`
  vs `usage: cli.py`), diferencia esperada de argparse, no del contrato.
  Se cambió a equivalencia funcional (código 0 + mismos flags/descripción/
  default en ambos; mismo código y flags requeridos en stderr ante falta
  de args). Documentado para revisión.

### Build y contexto (códigos reales, caché normal)

- `docker build -t autocrop:latest .` → `BUILD_CODE:0` (61.7s con caché
  normal tras R2). Imagen: `autocrop:latest 2.46GB`.
- Contexto verificado con build mínimo de inspección (`busybox`, caché
  normal): `/ctx` contiene exactamente `Dockerfile README.md app
  pyproject.toml yolo11n.pt`; `/ctx/app/__pycache__`, `/ctx/.aws` y
  `/ctx/fotos_extra` (sondas creadas y luego eliminadas) no existen.
  Sondas removidas; `git status` sin restos.
- Sin pesos (Dockerfile real copiado a `/tmp/ac06_noweights` sin
  `yolo11n.pt`, raíz intacta): `docker build` → `NOWEIGHTS_CODE:1`,
  falla en `[9/10] COPY yolo11n.pt` por checksum BuildKit antes de
  instalar nada.
- `docker compose config` → `CONFIG_EXIT:0` (resuelve `container_name:
  autocrop`, `user: 1000:1000`, mounts `/input` ro y `/output`).

### Runtime real con inferencia YOLO (fotos sintéticas temporales, nunca `fotos/`)

- `docker compose up -d --build` (con `AUTOCROP_INPUT_DIR=/tmp/ac06/in`,
  `AUTOCROP_OUTPUT_DIR=/tmp/ac06/out`, `UID:GID 1000:1000`) → `UP_CODE:0`,
  `autocrop Up`.
- `docker exec autocrop autocrop --help` → `HELP_CODE:0` (F1).
- JPEG blanco 640x480 sintético, YOLO real: `RUN_CODE:0`,
  `Detected 0 person(s)`, `Review (blank.jpg: no_person)`,
  `Done: 1 processed, 0 saved, 1 review, 0 skipped` (F2, review válido
  sin depender de selección deportiva).
- Host: `review/blank.jpg` + `review.log` (`blank.jpg: no_person`); hash
  original idéntico antes/después
  (`4ee885dc…0856ea7`); propiedad `1000:1000` en ambos (F2/F3).
- `touch /input/should_fail` → `READONLY_CODE:1` (`Read-only file system`);
  `touch /output/write_ok` → `OUTPUT_WRITE_CODE:0`, `1000:1000` (F3).
- Opciones: `--ratio 1:1 --margin 0.2` → `OPT_CODE:0`, mismo resumen (F1).
- Sin red (`docker run --rm --network none …`): `NONET_CODE:0`, review
  generado, hash intacto; sin descarga de modelo (F4).
- CPU: `torch 2.14.1+cpu`, `torchvision 0.29.1+cpu`, `torch.version.cuda
  None` (`TORCHCHECK_CODE:0`) (T3).
- Pesos en imagen: `/app/yolo11n.pt` 5613764 bytes legible (F4).
- Errores (F5, códigos reales): input inexistente → `NOINPUT_CODE:1`
  (`error: input directory not found`); `--ratio bogus` →
  `BADRATIO_CODE:2` (argparse); `--input /input --output /input` →
  `CONFLICT_CODE:1` (`resolve to the same directory`), hash intacto.
- Misma carpeta host en `/input`+`/output` → `SAMEMOUNT_CODE:1`
  (`output would overwrite original image: /input/blank.jpg`), hash
  idéntico, sin archivos nuevos (F5).
- Salida inexistente + `up` → `MISSINGOUT_CODE:1`
  (`bind source path does not exist`), sin creación silenciosa (F6).

### Suite y pip check (T2, códigos reales)

- `.venv/bin/python -m pytest` → `PYTEST_CODE:0`, `323 passed`
  (318 baseline + 5 packaging). Instalación host solo vía `.venv`
  (`pip install -e '.[dev]'`).
- `.venv/bin/python -m pip check` → `PIPHOST_CODE:0`
  (`No broken requirements found`).
- En imagen `pip check` → `PIPCHECK_IMG_CODE:0`
  (`No broken requirements found`).

### Criterios cubiertos y pendientes

- Cubiertos con evidencia real: F1–F6, T1–T3.
- Sin bloqueos: ninguna comprobación quedó pendiente. No se publicaron
  imágenes ni se hizo commit. Contenedor propio detenido con
  `docker compose down` (`DOWN1_CODE:0`); el contenedor ajeno
  `autocrop-review-stage06` (de la revisión en paralelo) no se tocó.
- Tamaño/limitación: imagen 2.46GB (torch CPU + ultralytics); solo CPU,
  sin GPU/servicios web/interfaz.

### R3 (devolución docs, sin nuevos builds/tests)

- `README.md`: comando Docker principal ahora copiable en dos líneas
  (mínimo válido + ejemplo con `--ratio 3:2 --margin 0.15`, sin brackets);
  requisito versión arbitraria reemplazado por capacidad
  (`bind.create_host_path: false`), con Docker 29.8.2 / Compose 5.6.0 como
  entorno probado. Impacto: instrucciones ejecutables, criterio F6.
- `PLAN.md`: decisión simplificada a
  «Reutiliza selección/crop y protecciones vigentes».
- Esta devolución solo toca documentación; resto de la evidencia intacto.

## Revisión (coordinador)


### Revisión final y hallazgos resueltos

- **R1 — `.dockerignore` (T3), resuelto.** La lista inicial dejaba entrar configuraciones privadas y fotos en carpetas distintas de `fotos/` al contexto del daemon. Corrección esperada: permitir únicamente los archivos necesarios y excluir caches. Muse aplicó allowlist; inspección real del contexto registrada arriba y revisión del archivo confirman resolución.
- **R2 — `Dockerfile`, instalación de dependencias (T3), resuelto.** Mezclar índice CPU con PyPI no garantizaba que nuevas versiones mantuvieran torch CPU. Corrección esperada: instalar torch/torchvision exclusivamente del índice CPU antes del resto. Muse corrigió; imagen final confirma `torch 2.14.1+cpu`, `torch.version.cuda is None`.
- **R3 — `README.md`, ejemplos/requisitos Docker (F6), resuelto.** Brackets de opciones hacían el ejemplo no copiable y Docker29+ imponía un requisito sin justificación. Corrección esperada: comando real y requisito por capacidad Compose. Muse corrigió ambos. Coordinador corrigió además un paréntesis editorial residual; sin cambio funcional.
- **Evidencia de tests (T1), revisada.** Fallos iniciales por ausencia de declaración/ejecutable son funcionales de empaquetado. Cambio de test help justificado por nombre de programa argparse. Los códigos mostrados después de pipes no se toman como éxito; evidencia final usa códigos capturados directamente.

### Comprobaciones independientes del coordinador

- Inspección completa de Dockerfile, compose.yaml, .dockerignore, tests/test_packaging.py, diff pyproject/README/PLAN y contrato. Reutiliza app.cli:main, no añade parser ni cambia pipeline.
- `.venv/bin/python -m pytest`: **323 passed in 1.12s**, código 0. `.venv/bin/python -m pip check`: **No broken requirements found**, código 0.
- `cmp /tmp/autocrop-before-docker.diff /tmp/autocrop-after-docker.diff`: código 0. Cambios previos de app, tests existentes y etapa04 preservados exactamente.
- Imagen final `autocrop:latest` ID `807d49678be7`: **2.46GB** en disco / **563MB** contenido comprimido.
- Runtime independiente en contenedor `autocrop-review-stage06`, `--network none`, UID/GID1000, mounts temporales `/tmp/autocrop-review-yyc6x20g/input` readonly y output escribible. `docker exec ... autocrop --help`: 0. Inferencia real JPEG blanco128x96 con ratio1:1/margin0.2: 0, summary1processed/0saved/1review. Aserciones verifican copia review idéntica al original, hash original sin cambios y propiedad UID1000.
- `touch /input/no-write`: 1, Read-only file system. Conflicto input/output ambos `/input`: 1, mensaje breve sin traceback. `python -m pip check` en imagen: 0. Assert torch.version.cuda None: 0. Contenedor independiente eliminado al terminar.
- Evidencia de Muse complementa prueba de dos bind mounts a misma carpeta, input inexistente, argumento inválido, construcción sin pesos, salida inexistente y ciclo Compose up/down. Verificada coherencia con contrato y código; no se repiten pruebas sin causa.
- `git diff --check`: código 0 antes del cierre; documentación final revisada. No quedan hallazgos ni comprobaciones pendientes.

**Cierre:** criterios F1–F6 y T1–T3 verificados; etapa06 completada. No se implementó la siguiente etapa. No se evalúa nuevamente calidad deportiva del crop: esta iteración solo empaqueta el pipeline existente; validación real sintética verifica integración e inferencia.
