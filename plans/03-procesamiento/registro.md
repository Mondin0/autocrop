# Etapa 03 — Registro de ejecución y revisión

Contrato: [plan.md](plan.md). Estado vigente: ver `plan.md`.

## Implementación (Muse)

Archivos creados: `app/processor.py` (`default_ratio`, `process_image`,
`process_folder`), `app/cli.py` (`build_detector`, `main`), suites
`tests/test_processor.py` (46 tests) y `tests/test_cli.py` (28 tests).
  [Nota (2026-10-07): conteo por funciones; `--collect-only -q` da 53 + 21
  por parametrización; total 74, cuadra con 227 + 74 = 301.]
`README.md` solo agrega uso CLI. Sin dependencias nuevas, sin `models.py`,
sin flags extra. Baseline intacto: no se tocó `crop.py`, `detector.py`,
`subject.py` ni tests previos.

Comandos y resultados reales (todo con `.venv/bin/python`):
- Baseline: `python -m pytest` → `227 passed`.
- Fase roja: `python -m pytest tests/test_processor.py tests/test_cli.py -v` →
  `74 failed`, todos por `NotImplementedError` (stubs mínimos para importar).
- Fase verde: mismos tests → `74 passed`.
- Final: `python -m pytest` → `301 passed` (227 + 74); `python -m pip check` →
  `No broken requirements found`.
- Pasada real: `sha256sum yolo11n.pt` →
  `0ebbc80d…63ae6417644ee1`; `rm -rf /tmp/opencode/out03 && python -m app.cli
  --input fotos --output /tmp/opencode/out03` (3,6 s, CPU) → `Done: 3
  processed, 3 saved, 0 review, 0 skipped`; `review.log` vacío (0 bytes).
  Por archivo: Empty_road 5 detecciones, sujeto
  `(10.78, 306.82, 34.17, 368.83)`, crop `(0, 296, 123, 378)`, salida 123×82;
  Group 11 detecciones, sujeto `(681.06, 236.80, 907.17, 633.23)`, crop
  `(186, 124, 960, 640)`, salida 774×516; Lone 1 detección, sujeto
  `(59.39, 242.84, 288.28, 607.99)`, crop `(14, 186, 332, 663)`, salida
  318×477. Proporciones exactas (1.5, 1.5, 2/3). Versiones: ultralytics
  8.4.174, Pillow 12.3.0, torch 2.14.1. Originales intactos (mtimes
  anteriores a la corrida; suite además compara hash antes/después).
- Falsos positivos: `Empty_road_mongolia.jpg` (carretera vacía) produjo 5
  detecciones de cajas pequeñas y se guardó recortada en vez de ir a review.
  Se registra sin ocultar ni forzar a revisión, según F6.

Criterios cubiertos: F1–F5 y T1–T5 por suite (stub, tmp_path, EXIF 6,
corrupto, .txt/.png, hash, idempotencia, log exacto, resumen, CLI con
`build_detector` stubbeado, errores argparse); F6 por pasada real.
Decisión para revisión: `process_folder` no captura excepciones del
detector/selección (p. ej. `RuntimeError` de backend); solo las fotos
ilegibles/sin persona/sin crop van a review. Un backend roto debe fallar
ruidoso, no silencioso.

Pendiente (para Astra): revisión de contrato, tests, código y evidencia real.

## Revisión (Astra)

Inspección 2026-10-07 sobre el diff vs `f26f43a` (etapas 01–02): solo
archivos nuevos `app/processor.py`, `app/cli.py`, `tests/test_processor.py`
(46 tests), `tests/test_cli.py` (28 tests), carpeta `plans/03-procesamiento/`;
modificados `PLAN.md` (1 línea: índice etapa 03) y `README.md` (uso CLI).
`app/crop.py`, `detector.py`, `subject.py` y tests previos intactos
(`git status` limpio salvo lo listado; suite 301 = 227 + 74).

Criterios: F1–F5 verificados por suite con stub (`detect_people`), cajas
fijas, `tmp_path`, EXIF 6 generado en-test, corrupto, `.txt`/`.png`,
hash antes/después, idempotencia, `review.log` exacto, resumen y CLI con
`build_detector` stubbeado; F6 por pasada real re-ejecutada (ver abajo).
T1: `processor.py` no importa `cli`/`argparse`, `cli.py` fina; T2: 227
baseline preservados; T3: sin YOLO/red/GPU en suite; T4: orden por nombre,
sin reloj/azar, hash intacto; T5: type hints + docstrings + `.venv`.

Aserciones: no tautológicas (tamaños de salida hardcodeados, log/resumen
exactos, `calculate_crop` invocado en un test solo como chequeo de
consistencia junto al tamaño fijo `(260, 260)`). Sin dependencia de
privados (solo `default_ratio`, `process_image`, `process_folder`,
`calculate_crop`, `build_detector`, `main`). Sin debilitar tests previos.

Hallazgos:
- H1 (menor, docs; T5): `README.md` aún decía "el futuro procesador (etapa
  03, sin definir)". Corregido a "(etapa 03) asume…". Sin test (no es
  defecto de código).
- H2 (evaluado, aceptado sin cambio; F5): `process_folder` no captura
  excepciones del detector/selección (`RuntimeError` de backend) y falla el
  lote ruidoso. Se acepta: "foto problemática" = dato (ilegible/sin
  persona/sin crop → review); backend roto debe fallar, no silenciarse.
  Ningún test exige lo contrario.
- Observación (sin cambio): `process_image` con ruta inexistente propaga
  `FileNotFoundError` desde `copy2` (no hay fuente que copiar a review);
  caso fuera de contrato, comportamiento sano. Symlink roto se ignora sin
  contar; despreciable.

Re-verificación real (todo `.venv/bin/python`):
- `python -m pytest` → `301 passed in 0.79s`; `python -m pip check` →
  `No broken requirements found`.
- `rm -rf /tmp/opencode/out03b && python -m app.cli --input fotos --output
  /tmp/opencode/out03b` (3,3 s CPU) → `Done: 3 processed, 3 saved, 0
  review, 0 skipped`, exit 0; `review.log` 0 bytes; mismas cajas/crops que
  la evidencia de implementación (Empty_road 5 detecciones sujeto
  `(10.78, 306.82, 34.17, 368.83)` crop `(0,296,123,378)` salida 123×82;
  Group 11 detecciones crop `(186,124,960,640)` salida 774×516; Lone 1
  detección crop `(14,186,332,663)` salida 318×477); proporciones exactas
  3/2, 3/2, 2/3 (`Fraction`); `yolo11n.pt` sha
  `0ebbc80d…63ae6417644ee1`; ultralytics 8.4.174, Pillow 12.3.0, torch
  2.14.1+cu130; originales con mtimes previos a la corrida.
- Falsos positivos `Empty_road` registrados, no forzados a revisión (F6).

Cierre: F1–F6 y T1–T5 verificados, sin hallazgos pendientes. Estado →
`completada`. Etapa 04 no iniciada.
