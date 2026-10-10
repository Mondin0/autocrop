# Etapa 03 — Procesamiento de imágenes y CLI

Estado: completada

Dependencias: [etapa 01 completada](../01-crop/plan.md),
[etapa 02 completada](../02-deteccion/plan.md).
Implementación: Muse. Revisión: Astra.

## Objetivo

Cerrar el MVP usable: una CLI que recorre una carpeta con JPEG, y por cada
foto abre, orienta (EXIF), detecta personas con el `YOLODetector` real,
selecciona por mayor área, calcula el recorte y guarda el JPEG recortado en
una carpeta de salida. Cuando no hay persona o no existe recorte válido,
copia el original a `output/review/` con el motivo registrado, sin fallar el
lote y sin modificar jamás los originales.

Esta etapa agrega I/O real (apertura, guardado, carpetas, CLI). Las
decisiones generales siguen en [PLAN.md](../PLAN.md); el ciclo de
trabajo, en [AGENTS.md](../../../AGENTS.md).

## Alcance y entregables

- `app/processor.py`: apertura + orientación EXIF + conversión RGB,
  proporción automática, orquestación detectar → seleccionar → calcular →
  guardar/copiar, y `review.log`.
- `app/cli.py`: CLI con `argparse`, ejecutable como `python -m app.cli`.
- `tests/test_processor.py` y `tests/test_cli.py`: tests unitarios previos a
  la implementación, con detector falso (stub con método `detect_people`) y
  carpetas temporales; YOLO real solo en la pasada de validación.
- Actualizar `README.md` con uso de la CLI. Sin dependencias nuevas de
  ejecución (stdlib + Pillow + ultralytics ya declarados).

No crear `models.py`: el resultado de `process_image()` es una tupla
`(estado, detalle)` con estados `"saved" | "review" | "skipped"`; no hay
clases de resultado, ni registro de procesadores, ni plugins.

## Exclusiones

Clasificación por foco/nitidez (Fase 2), XMP/Lightroom (Fase 3), RAW
(Fase 4), GUI/desktop (Fase 5), optimización de lotes de miles de fotos
(Fase 6), recursion en subcarpetas, entrenamiento, tracking y nuevas
estrategias de selección pertenecen a etapas/fases futuras. Tampoco
implementar conversión de formatos (salida siempre JPEG) ni control de
calidad configurable.

No cambiar contratos ni implementaciones de `calculate_crop()`,
`YOLODetector` ni `select_subject()`. Preservar todos los tests y el
historial de las etapas 01 y 02 (baseline: 227 tests).

## Contratos públicos

### Procesador

```python
def default_ratio(width: int, height: int) -> tuple[int, int]: ...
def process_image(
    image_path: pathlib.Path,
    output_dir: pathlib.Path,
    review_dir: pathlib.Path,
    detector: object,  # duck-typed: .detect_people(Image) -> list de cajas
    ratio: tuple[int, int] | None,  # None = automática
    margin: float,
) -> tuple[str, str]: ...
def process_folder(
    input_dir: pathlib.Path,
    output_dir: pathlib.Path,
    detector: object,
    ratio: tuple[int, int] | None,
    margin: float,
) -> dict[str, int]: ...
```

- `default_ratio`: `(3, 2)` si `width > height`, `(2, 3)` si
  `height > width`, `(1, 1)` si son iguales. Dimensiones no enteras
  positivas o booleanos: `ValueError`.
- `process_image`:
  - Abre con Pillow, aplica `ImageOps.exif_transpose`, convierte a RGB.
    Archivo ilegible o que Pillow no puede decodificar: `("review",
    "unreadable")`, sin lanzar.
  - Detecta con `detector.detect_people(imagen)`, selecciona con
    `select_subject()`. Sin personas: copia el original a `review_dir` con
    `shutil.copy2` y devuelve `("review", "no_person")`.
  - Calcula con `calculate_crop()` usando dimensiones de la imagen ya
    orientada y `ratio or default_ratio(w, h)`. `None` geométrico: copia a
    `review_dir`, devuelve `("review", "no_valid_crop")`.
  - Éxito: recorta y guarda JPEG con el mismo nombre base en `output_dir`
    (`quality=95`), devuelve `("saved", str(ruta_salida))`.
  - Crea `output_dir` y `review_dir` si no existen (`mkdir(parents=True,
    exist_ok=True)`). Sobrescribe salidas previas del mismo nombre.
  - Nunca modifica ni mueve el original. La imagen en memoria no se muta
    de forma observable (trabajar sobre copias/recortes).
- `process_folder`:
  - Recorre solo el nivel dado (no recursivo); extensiones `.jpg`/`.jpeg`
    insensibles a mayúsculas, ordenadas por nombre para determinismo.
    Otros archivos: `("skipped", ...)` interno, se informa por consola y
    NO van a `review/` ni al log.
  - `review_dir` es siempre `output_dir / "review"`.
  - Escribe `output_dir / "review.log"` con una línea `nombre: motivo` por
    cada archivo en revisión (sobrescribe el log en cada corrida).
  - Devuelve resumen `{"processed": n, "saved": n, "review": n,
    "skipped": n}`. Nunca falla el lote por una foto problemática; solo
    falla (excepción) ante `input_dir` inexistente/no-directorio o errores
    de escritura de carpetas.
- Validación de entradas (ambas funciones): rutas no-`Path`/inexistentes
  según caso, `ratio` con la misma regla que etapa 01 (tupla de 2 enteros
  positivos, sin booleanos), `margin` número finito no negativo (misma regla
  que etapa 01). Inválidos: `ValueError`. `detector` sin método
  `detect_people`: `ValueError` temprano, antes de tocar archivos.

### CLI

```bash
python -m app.cli --input DIR --output DIR [--ratio W:H] [--margin F]
```

- `--input` (requerido): carpeta existente; si no existe o no es
  directorio: error con mensaje y salida distinta de cero, sin crear nada.
- `--output` (requerido): se crea si no existe.
- `--ratio` (opcional): formato `W:H` con enteros positivos
  (`"3:2"` → `(3, 2)`). Formato inválido: error de argparse (salida 2).
  Ausente: proporción automática por imagen. Explícito: rige todo el lote
  sin invertir por orientación.
- `--margin` (opcional, default `0.15`): float finito `>= 0`. Inválido:
  error de argparse.
- El detector se construye una vez con `yolo11n.pt` del directorio actual
  (ruta `Path("yolo11n.pt")`, la misma documentada en README) y
  `confidence=0.25`. Sin flags de modelo/umbral en esta etapa.
- Consola por archivo, formato de [PLAN.md](../PLAN.md):
  `Processing IMG_001.jpg / Detected N person(s) / Selected subject bbox:
  (...) / Crop: (...) | Review (...: motivo) / Saved ...`. Al final,
  línea de resumen `Done: X processed, Y saved, Z review, W skipped`.
- Salida `0` aunque todo vaya a revisión; distinta de cero solo por
  argumentos inválidos o `input`/`output` inutilizables.

## Decisiones de integración y entorno

- La orientación EXIF vive aquí (apertura), no en el detector: el contrato
  de etapa 02 ("imagen ya orientada") queda satisfecho por construcción.
- `processor.py` no importa `cli`/`argparse`; `cli.py` es fina (parseo +
  construcción del detector + llamada a `process_folder`).
- Salida siempre JPEG `quality=95`, mismo nombre base. `review/` recibe
  copias bit-idénticas (`copy2`), nunca recortes parciales.
- Sin dependencias nuevas: `argparse`, `pathlib`, `shutil` son stdlib;
  Pillow ya es dependencia.
- Registrar versiones efectivas en la pasada real (mismas que etapa 02).

## Criterios funcionales

- **F1:** lote con stub que devuelve 1 caja → todos `saved`, dimensiones
  del JPEG iguales al crop calculado, proporción exacta, original intacto.
- **F2:** stub vacío → `review/no_person` con copia idéntica y línea en
  `review.log`; stub con caja imposible (p. ej. alta en 600×1000 con 3:2)
  → `review/no_valid_crop`. El lote termina en `0`.
- **F3:** ratio auto según orientación (3 casos) y `--ratio` explícito
  aplicado sin invertir (horizontal pedido en vertical también horizontal).
- **F4:** EXIF orientation 6 (rotada 90°) → dimensiones y cajas en el
  sistema ya orientado; JPEG corrupto → `review/unreadable` sin caída;
  no-JPEG → `skipped` con aviso, fuera de `review/` y del log.
- **F5:** validación de entradas según contratos (`ValueError` vs error de
  argparse vs fallo de lote), `review.log` con formato exacto, resumen
  final consistente, segunda corrida idempotente (sobrescribe).
- **F6:** pasada real con `yolo11n.pt` en CPU sobre las 3 fotos F6 en un
  `output/` temporal: resultados registrados (cajas, selección, crop,
  tiempos); los falsos positivos de `Empty_road` se registran, no se
  ocultan ni fuerzan a revisión.

## Criterios técnicos

- **T1:** separación apertura/orientación (processor), detección (etapa
  02), geometría (etapa 01), parseo (cli); solo dos módulos nuevos.
- **T2:** tests escritos primero, fase roja por funcionalidad pendiente,
  fase verde y suite completa registrada; ninguna regresión (baseline 227).
- **T3:** tests sin YOLO real, sin red ni GPU (stub con `detect_people`);
  la pasada real no forma parte de la suite ni se reemplaza con skips.
- **T4:** determinismo (orden por nombre, sin reloj/azar), originales
  intactos (comparar hash antes/después con stub), sin descargas ni
  escrituras fuera de `output_dir`.
- **T5:** type hints, docstrings, comandos reproducibles en `.venv`.

## Casos de prueba vinculados

### Procesador con stub — F1, F2, F4; T1, T2, T3

- Stub 1 caja en 1000×800, auto → `saved`, tamaño de salida igual al crop
  esperado `(370,270,630,530)` con 1:1 m0.15 (viene de etapa 01).
- Stub vacío → `review/no_person`; stub caja imposible → `review/no_valid_crop`.
- Ratio auto 3 orientaciones; ratio explícito `(3,2)` en vertical.
- JPEG con EXIF orientation 6 generado en el test: dimensiones orientadas.
- JPEG corrupto (bytes inválidos con sufijo `.jpg`) → `review/unreadable`.
- `.txt`/`.png` junto a `.jpg` → `skipped`, no en `review/` ni log.
- Entradas inválidas: ratio `(0,2)`/bool/string, margin negativo/NaN/bool,
  `input_dir` archivo, detector sin `detect_people` → `ValueError` antes de
  escribir.
- Hash del original idéntico tras procesar; segunda corrida sobrescribe sin
  duplicar.

### Carpeta y log — F5; T4

- Lote mixto (2 saved + 1 no_person + 1 unreadable + 1 skipped):
  `review/` con 2 copias idénticas, `review.log` con exactamente 2 líneas
  `nombre: motivo`, resumen `{"processed":4,"saved":2,"review":2,
  "skipped":1}`.
- `output_dir` inexistente se crea con `review/` adentro.

### CLI — F3, F5; T1

- `main(["--input",...,"--output",...])` → `0`, salidas y resumen en consola.
- `--ratio 3:2` válido, `--ratio 3x2`/`0:2` → error argparse; `--margin -1`
 /`nan` → error; `--input` inexistente → distinto de cero sin crear output.
- Con stub inyectable: `cli` debe permitir sustituir la construcción del
  detector (p. ej. función `build_detector()` separada) para no requerir
  YOLO en tests.

## Procedimiento de implementación y validación

1. **Preparar:** leer contrato/historial y marcar `en implementación`.
   Comprobar baseline `.venv/bin/python -m pytest -q` (227 tests).
2. **Tests primero:** crear tests y stubs que lancen `NotImplementedError`.
   Ejecutar `.venv/bin/python -m pytest tests/test_processor.py
   tests/test_cli.py -v`; registrar fallos por comportamiento pendiente.
3. **Implementar:** mínima solución del contrato. Para defectos nuevos,
   regresión roja antes del fix.
4. **Verificar:** tests nuevos, `.venv/bin/python -m pytest` completo y
   `.venv/bin/python -m pip check` (sin dependencias nuevas). Registrar
   comandos/resultados y criterios.
5. **Pasada real separada:** `python -m app.cli --input fotos --output
   /tmp/opencode/out03` con `yolo11n.pt` existente (no descargarlo de
   nuevo; registrar su hash ya conocido). Usar las 3 fotos F6; registrar
   por archivo (detecciones, selección, crop, review.log, tiempos) y
   versiones. No agregar inferencia real a la suite.
6. **Entregar y revisar:** marcar `en revisión`; Astra inspecciona
   contrato, tests, código, evidencia real y diff. Cerrar solo verificado
   y sin hallazgos; si hay bloqueo, registrarlo y no cerrar.

No delegar ni implementar por el solo hecho de crear este plan. No iniciar
etapa 04 al terminar esta entrega.
