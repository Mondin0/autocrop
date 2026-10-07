# Etapa 02 — Registro de ejecución y revisión

Contrato: [plan.md](plan.md). Estado vigente: ver `plan.md`.

## Implementación (Muse)

### Archivos modificados

- `app/subject.py` (nuevo): `select_subject()` pura, un recorrido lineal con
  validación incluida; mayor área, empate → primera, devuelve la tupla
  original. Sin imports de detector/Pillow/torch/ultralytics.
- `app/detector.py` (nuevo): `YOLODetector` con import lazy de ultralytics en
  el constructor, carga única por instancia, validación de
  weights/confidence/imagen antes de inferir, filtro clase 0 +
  `conf >= umbral` con orden conservado, tuplas float finitas en límites.
- `tests/test_subject.py` (nuevo, 37 casos) y `tests/test_detector.py`
  (nuevo, 73 casos): backend simulado vía `sys.modules["ultralytics"]`,
  sin pesos reales, red, GPU ni inferencia real.
  [Nota de corrección M2 (2026-10-07): métrica uniforme
  `.venv/bin/python -m pytest --collect-only -q` → `test_subject.py: 47`
  (21 funciones `def test`), `test_detector.py: 65` (39 funciones); total
  115 + 47 + 65 = 227, cuadra con la suite. Los "37/73" originales usaban
  otra cuenta; se conservan arriba como historia.]
- `pyproject.toml`: `dependencies = ["ultralytics", "Pillow"]`.
- `README.md`: uso de detector + subject + crop, origen/licencia AGPL-3.0 y
  descarga manual explícita de `yolo11n.pt`.
- No tocados: `app/crop.py`, `tests/test_crop*.py` ni su historial.

### Comandos y resultados reales

- Baseline (tras marcar en implementación):
  `.venv/bin/python -m pytest -q` → 115 passed (etapa 01 intacta).
- Fase roja: stubs `NotImplementedError` + suite completa →
  `tests/test_subject.py tests/test_detector.py` → 109 failed, 1 passed.
  Los 109 fallos son por comportamiento pendiente (95 `NotImplementedError`
  desde stubs; 14 `RuntimeError` con `match=` que el stub desnudo no
  satisface, ya que `NotImplementedError` es subclase sin mensaje). Cero
  errores de importación/instalación. El único pass en rojo es el test de
  higiene de imports (subproceso: importar `app.detector`/`app.subject` no
  carga `ultralytics` ni `torch`), propiedad que ya cumple el stub.
- Fase verde: 110 passed (nuevos). Full: `.venv/bin/python -m pytest` →
  225 passed (115 baseline + 110 nuevos, sin regresiones).
- `.venv/bin/python -m pip install -e '.[dev]'` → instala ultralytics 8.4.174,
  torch 2.14.1+cu130, Pillow 12.3.0 (Pillow se había adelantado solo para
  poder crear imágenes RGB en la fase roja).
- `.venv/bin/python -m pip check` → "No broken requirements found."
- Versiones efectivas: Python 3.12.3, Pillow 12.3.0, ultralytics 8.4.174,
  torch 2.14.1+cu130.

### Correcciones de expectativas durante la implementación

- `test_deterministic_repeated_calls`: los datos originales
  `(0,0,30,20)` vs `(1,1,31,21)` empataban en área (600 = 600); el código
  devolvió correctamente la primera según el plan (empate → primera). Se
  corrigió el test (segunda caja → `(1,1,32,21)`, área 620), no el código.
- `math.isfinite()` sobre `int` enormes lanza `OverflowError` (falla real
  detectada por `test_invalid_confidence_rejected[10**400]` en rojo con
  `OverflowError` en vez de `ValueError`). Fix en
  `app/detector.py:_validate_confidence`: comprobar finitud solo en
  `float`; los `int` solo pasan el chequeo de rango. La suite ya contenía la
  regresión antes del fix.

### Criterios cubiertos

- F1: filtro clase 0 + umbral (incl. bordes 0.24/0.25/0.9), orden y
  coordenadas originales, filas basura no-persona ignoradas.
- F2: `[]`/`None` en vacío; errores de carga/inferencia propagados, nunca
  presentados como ausencia.
- F3: una caja / mayor área / empate-primera; entradas no mutadas,
  repetibilidad.
- F4: `FileNotFoundError` vs `ValueError` en pesos, imagen RGB/dimensiones,
  umbral (incl. bool y `10**400`), cajas inválidas aunque no ganen,
  `RuntimeError` en respuesta desalineada o retenida inválida; YOLO no se
  invoca con entradas inválidas.
- F5: unión simulada `(400,300,600,500)` en 1000×800 1:1 m0.15 →
  `(370,270,630,530)`; ganadora intacta; vacío sin caja inventada;
  `(100,50,500,950)` 600×1000 3:2 → `None`.
- T1–T5: dos módulos nuevos, tests primero con fase roja registrada, sin
  pesos/red/GPU/inferencia real (fakes en el límite ultralytics), carga
  única sin descargas ni escrituras, type hints + docstrings, selección en
  un recorrido, deps y comandos reproducibles en `.venv`.

### Pendientes explícitos

- F6 y punto 5 del procedimiento (prueba real): PENDIENTES. Sin fotos ni
  pesos disponibles (el usuario está consiguiendo las 3 fotos); no se
  descargó `yolo11n.pt`, no se agregó inferencia real a la suite ni skips.
  Requiere: obtener pesos de fuente oficial, 3 JPEG autorizados (una
  persona clara / varias / sin personas), ejecutar en CPU con mismo
  modelo/umbral y registrar dimensiones, cajas, selección, tiempos,
  versiones y hash de pesos, más comprobación visual de escala y mayor área.

### Corrección H1/H2 (OverflowError → RuntimeError)

- Regresiones agregadas primero en `tests/test_detector.py` (backend
  simulado, imagen 64×64): `test_huge_int_box_is_runtime_error` (caja
  `[10**400, 0, 10**400+10, 10]`, clase 0, conf 0.9) y
  `test_huge_int_confidence_is_runtime_error` (caja válida,
  `conf=[10**400]`).
- Fase roja: ambas fallaron con
  `OverflowError: int too large to convert to float` (caja desde
  `_checked_box`, confianza desde `float(raw_conf)` en `detect_people`),
  confirmando H1/H2.
- Fix mínimo en `app/detector.py`: agregar `OverflowError` a los tres
  `except (TypeError, ValueError)` que envuelven `float()` — `_checked_box`
  (coords) y `detect_people` (`float(raw_class)` / `float(raw_conf)`) —
  relanzando `RuntimeError` descriptivo. Sin cambios de contrato; no tocados
  `app/crop.py`, `tests/test_crop*.py`, `app/subject.py`.
- Verificación: `.venv/bin/python -m pytest` → **227 passed**
  (225 + 2 regresiones); `.venv/bin/python -m pip check` →
  "No broken requirements found."
- Criterios: F4 cubierto para H1/H2 (retenida inválida con entero enorme →
  `RuntimeError`). F6 real sigue pendiente (pesos + 3 fotos).

### Prueba real F6

- Pesos: `yolo11n.pt` en root del repo (git-ignorado por `*.pt`),
  descargado explícitamente con `curl -sSL -o yolo11n.pt
  https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt`
  (fuente oficial Ultralytics, release `v8.3.0` del repo `ultralytics/assets`).
  Nada descargado desde el adaptador ni desde tests.
  SHA256: `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`
  (5613764 bytes).
- Versiones efectivas: Python 3.12.3, Pillow 12.3.0, ultralytics 8.4.174,
  torch 2.14.1+cu130. Mismo modelo y `confidence=0.25` en los 3 casos, CPU.
- Flujo por foto (script `/tmp/opencode/f6_validate.py`, fuera del repo):
  abrir → `ImageOps.exif_transpose` → `.convert("RGB")` →
  `YOLODetector(yolo11n.pt, confidence=0.25).detect_people()` →
  `select_subject()` → `calculate_crop(w, h, sel, (1, 1), 0.15)`.
  Originales de `fotos/` no movidos ni sobrescritos; anotaciones visuales
  como archivos NUEVOS en `/tmp/opencode/f6_annot/` (rojo = detectadas,
  verde = selección, cian = crop 1:1).
- `fotos/Lone_runner.jpg`: 500×667, 1 persona
  `[59.4, 242.8, 288.3, 608.0]` (área 83579.6), selección esa misma caja,
  crop 1:1 m0.15 `(0, 187, 475, 662)`, 2.97 s (primera inferencia, incluye
  calentamiento). Visual: caja ajustada al corredor, crop lo contiene. OK.
- `fotos/Group_of_runners_at_the_Vienna_City_Marathon_2026-05.jpg`:
  960×640, 11 personas (áreas 89637.6 máx … 1967.7 mín), selección
  `[681.1, 236.8, 907.2, 633.2]` = la de mayor área (corredor en primer
  plano a la derecha), crop 1:1 m0.15 `(444, 124, 960, 640)`, 0.15 s.
  Visual: cada caja cae sobre un corredor, selección = mayor área. OK.
- `fotos/Empty_road_mongolia.jpg`: 960×540, **5 detecciones pese a no
  haber personas** — FALSOS POSITIVOS registrados, no ocultos: cajas
  pequeñas sobre objetos/carteles lejanos al borde de la ruta
  (`[262.1, 308.6, 289.0, 362.3]` área 1442.0,
  `[10.8, 306.8, 34.2, 368.8]` área 1450.8,
  `[864.7, 311.2, 882.5, 351.8]` área 722.8,
  `[505.9, 307.8, 515.0, 328.5]` área 188.0,
  `[491.7, 304.5, 501.1, 328.6]` área 226.9). Selección por regla de área:
  `[10.8, 306.8, 34.2, 368.8]`, crop 1:1 m0.15 `(0, 297, 81, 378)`,
  0.07 s. Según el plan, un falso positivo aislado NO cambia la regla de
  área ni autoriza heurísticas; la evaluación general de precisión
  pertenece a la etapa 04.
- Chequeo visual F6: en los 3 casos dimensiones coinciden con la foto,
  todas las cajas dentro de límites y selección == caja de mayor área
  (verificado por script con asserts + inspección de las anotaciones).
  Las cajas pertenecen al sistema de coordenadas de la fotografía. APROBADO.
- Bugs: ninguno de escala/carga/filtrado. `app/` y `tests/` intactos.
  Suite completa tras la prueba: `.venv/bin/python -m pytest` →
  **227 passed**.

## Revisión (Astra)

### Corroboración 1 — suite verde, 2 hallazgos bloqueantes (F4)

Verificado por coordinador: `.venv/bin/python -m pytest` → **225 passed**;
`pip check` → No broken requirements; `pyproject.toml` declara
`ultralytics`+`Pillow`; `README.md` documenta `yolo11n.pt` y AGPL-3.0;
`app/crop.py` y `tests/test_crop*.py` intactos; sin `models.py`.

- **H1 — OverflowError en caja retenida con entero enorme**
  (`app/detector.py:_checked_box`, F4): backend simulado con caja
  `[10**400, 0, 10**400+10, 10]`, clase 0, conf 0.9 en imagen 64×64 lanza
  `OverflowError: int too large to convert to float` por `float(value)`
  (solo captura `TypeError`/`ValueError`). El contrato exige `RuntimeError`
  descriptivo para detección retenida con caja inválida. Corrección esperada:
  capturar también `OverflowError` (o validar finitud solo en `float`,
  patrón R9 de etapa 01) y lanzar `RuntimeError`; agregar regresión roja
  primero.
- **H2 — OverflowError en confianza retenida con entero enorme**
  (`app/detector.py:detect_people`, F4): mismo caso con caja válida y
  `conf=[10**400]` lanza `OverflowError` desde `float(raw_conf)` en vez de
  `RuntimeError` por confianza retenida inválida (igual aplica a
  `float(raw_class)`). Corrección esperada: misma que H1, con regresión
  roja primero.
- **F6 pendiente no bloqueante de esta iteración**: prueba real CPU con
  `yolo11n.pt` + 3 fotos (el usuario las está consiguiendo). No se cierra la
  etapa hasta completarla; no descargar pesos ni agregar inferencia real a
  la suite.

Estado vuelve a **en implementación** hasta corregir H1/H2.

### Corroboración 2 — H1/H2 resueltos, F6 pendiente

Verificado por coordinador tras el fix: `.venv/bin/python -m pytest` →
**227 passed**; `pip check` → No broken requirements; sondas propias con
caja `[10**400,…]` y `conf=[10**400]` → ambas `RuntimeError`. Diff mínimo
(3 `except` + 2 regresiones); `app/crop.py`, `tests/test_crop*.py`,
`app/subject.py` e historial intactos. H1/H2 cerrados. La etapa queda
**en revisión** con F6 pendiente (prueba real CPU con `yolo11n.pt` + 3
fotos del usuario); no se cierra ni se inicia etapa 03.

### Cierre — F6 corroborado, etapa completada

Corroboración propia con `.venv`: `yolo11n.pt` (5613764 bytes,
SHA256 `0ebbc80d…644ee1`, coincide), suite **227 passed**, re-inferencia
CPU sobre `Lone_runner.jpg` → 1 persona `[59.4, 242.8, 288.3, 608.0]` y
`Empty_road_mongolia.jpg` → 5 detecciones (falsos positivos ya registrados,
no bloquean ni cambian la regla de área). F1–F6 y T1–T5 verificados; sin
hallazgos pendientes. `plan.md` pasa a **completada**. Etapa 03 no iniciada.

- Re-inferencia del caso grupal (nota M3, 2026-10-07; solo append numérico,
  cierre intacto): `fotos/Group_of_runners_at_the_Vienna_City_Marathon_2026-05.jpg`
  960×640 RGB (EXIF→RGB), mismo `yolo11n.pt`, `confidence=0.25`, CPU →
  11 personas (áreas 89637.6 máx … 1967.7 mín), selección
  `[681.1, 236.8, 907.2, 633.2]` = la de mayor área, crop 1:1 m0.15
  `(444, 124, 960, 640)`, 1.76 s. Coincide con la prueba real F6; anotación
  existente en `/tmp/opencode/f6_annot/` reutilizada (no se generaron nuevas
  ni se movieron fotos).
