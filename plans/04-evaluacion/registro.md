# Etapa 04 — Registro de ejecución y revisión

Contrato: [plan.md](plan.md). Estado vigente: ver `plan.md`.

## Implementación (Muse)

### Estado

**Ejecutado el 2026-10-08 como Muse. Sin cambios en `app/` ni `tests/`;
solo cambiaron el plan y este registro.**

Baseline intacto: `.venv/bin/python -m pytest` → `301 passed in 1.06s`;
`.venv/bin/python -m pip check` → `No broken requirements found`.

Pesos y versiones: `sha256sum yolo11n.pt` →
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`;
Python 3.12.3, Pillow 12.3.0, ultralytics 8.4.174, torch 2.14.1+cu130.
Detector vigente verificado en `app/detector.py:113-124`: `classes=[0]`,
`conf=0.25`, `device="cpu"`, `imgsz=640`.

Dos corridas base sin flags extra (ratio auto, `margin` default 0.15).
Rutas de salida inexistentes antes de correr (verificado con `ls`); no hizo
falta borrar. Ambas terminan en exit `0`:

- A: `--input fotos --output /tmp/opencode/out04-f6` → wall 5.463s →
  `3 processed, 3 saved, 0 review, 0 skipped`.
- B: `--input fotos/reales --output /tmp/opencode/out04-reales` → wall
  4.806s → `10 processed, 10 saved, 0 review, 0 skipped`.

`review.log` vacío (0 bytes) y `review/` vacío en ambas salidas: ningún caso
`no_person` / `no_valid_crop` / `unreadable` en estas 13 fotos.
Falsos positivos confirmados: 0 (ver nota correctiva en la tabla).
`skipped = 0`: los 10 `.jpeg` de `reales/` sí se procesan (sufijo soportado).

Originales intactos: `sha256sum` idénticos antes y después (ver lista en
Comandos ejecutados). Sin solapamiento entrada/salida: entradas en `fotos/`,
salidas en `/tmp/opencode/` (árboles disjuntos; salidas con mismo nombre de
archivo pero en directorio distinto, originales nunca abiertos en escritura).

F2 verificado por script: las 13 salidas son JPEG RGB válidos, proporción
exacta del ratio aplicado (`Fraction(w,h) == ratio`), bbox seleccionada
contenida en el crop y crop dentro de la imagen.

Determinismo (T2): segunda corrida repite ambos resúmenes idénticos y el
mismo snapshot de tamaños (`stat %n %s` → sha256
`e1808c43…55ae2693` en ambas). Hash de contenido post-segunda-corrida:
`1bd3b157…0c384`.

Inspección visual: real, con capacidad visual directa sobre los 13 originales
y sus 13 crops (26 imágenes abiertas y vistas). Ningún criterio visual quedó
pendiente; ninguna dimensión se infirió desde logs o geometría.

### Evidencia heredada de etapas 02–03

Esta evidencia sirve como baseline, pero **no sustituye** las dos corridas ni
la revisión visual exigidas por etapa 04.

| Foto | Tamaño | Detecciones | Selección vigente | Crop etapa 03 | Salida | Detección correcta | Selección correcta | Composición aceptable |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| `Empty_road_mongolia.jpg` | 960×540 | 5 | `(10.78, 306.82, 34.17, 368.83)` | `(0, 296, 123, 378)` | 123×82 | **No** — falsos positivos; no hay personas | **No** — no existe sujeto real que seleccionar | **No** — caso conocido visualmente inútil |
| `Group_of_runners_at_the_Vienna_City_Marathon_2026-05.jpg` | 960×640 | 11 | `(681.06, 236.80, 907.17, 633.23)` | `(186, 124, 960, 640)` | 774×516 | Sí según validación visual previa de cajas | **Pendiente** — falta confirmar que el corredor de mayor área sea el sujeto fotográfico deseado | **Pendiente** — no inferirlo desde geometría |
| `Lone_runner.jpg` | 500×667 | 1 | `(59.39, 242.84, 288.28, 607.99)` | `(14, 186, 332, 663)` | 318×477 | Sí según validación visual previa | Sí por existir un único corredor detectado | **Pendiente** — requiere inspección del crop de etapa 04 |

Resultados heredados de la corrida real de etapa 03:
`3 processed, 3 saved, 0 review, 0 skipped`. Esto demuestra ejecución
técnica, no usabilidad fotográfica.

### Tabla de 13 archivos — corrida actual 2026-10-08 (inspección visual directa)

Detección/selección/composición se evalúan de forma independiente por foto
(F3/F4/F5). `det` = detecciones corresponden a personas reales; `sel` = la
caja de mayor área es el sujeto del fotógrafo; `comp` = sujeto entero,
margen/centrado razonables, encuadre utilizable.

| Foto | Tamaño orientado | N det | Bbox sujeto | Ratio | Crop | Salida | Estado | det | sel | comp | Nota |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Empty_road_mongolia.jpg` | 960×540 | 5 | `(10.78, 306.82, 34.17, 368.83)` | 3:2 | `(0, 296, 123, 378)` | 123×82 | saved | Sí* | No | No | *Sin sujeto principal. Las 5 cajas tienen candidatos reales visibles (peatón cortado en borde izq. = caja elegida, mujer de rosa, grupo lejano); sin FP demostrables — corrige la lectura heredada. Crop inútil guardado como éxito. |
| `Group_of_runners_at_the_Vienna_City_Marathon_2026-05.jpg` | 960×640 | 11 | `(681.06, 236.80, 907.17, 633.23)` | 3:2 | `(186, 124, 960, 640)` | 774×516 | saved | Sí | No | No | 11 detecciones plausibles, sin FP evidentes. Mayor área = corredor de espaldas, desenfocado, cortado por borde derecho; el pelotón y el arco pierden contexto. |
| `Lone_runner.jpg` | 500×667 | 1 | `(59.39, 242.84, 288.28, 607.99)` | 2:3 | `(14, 186, 332, 663)` | 318×477 | saved | Sí | Sí | Sí | Corredor único entero, encuadre ajustado utilizable. |
| `DSC00004.jpg.jpeg` | 1280×1920 | 7 | `(367.02, 523.39, 685.10, 1488.13)` | 2:3 | `(107, 377, 945, 1634)` | 838×1257 | saved | Sí | Sí | Sí | Lorena 3395 central y nítida; Ariel cortado en borde izq. pero secundario; Obelisco conservado. |
| `DSC00030.jpg.jpeg` | 1280×1920 | 7 | `(493.53, 515.92, 914.72, 1803.85)` | 2:3 | `(145, 243, 1263, 1920)` | 1118×1677 | saved | Sí | Sí | Sí | Florencia 16150 frontal, gesto a cámara; buen crop con contexto. |
| `DSC00084.jpg.jpeg` | 1280×1920 | 3 | `(352.02, 482.44, 861.54, 1723.54)` | 2:3 | `(68, 295, 1144, 1909)` | 1076×1614 | saved | Sí | Sí | Sí | Gabriel 18013 con bandera; pies al límite inferior pero enteros; posibles FN menores en fondo. |
| `DSC00128.jpg.jpeg` | 1280×1920 | 8 | `(168.90, 283.84, 797.98, 1914.34)` | 2:3 | `(0, 0, 1280, 1920)` | 1280×1920 | saved | Sí | Sí | Sí | Gastón 15279; sujeto tan grande que el crop = marco completo; pies ya cortados en origen. |
| `DSC00130.jpg.jpeg` | 1280×1920 | 8 | `(321.65, 390.00, 937.26, 1783.27)` | 2:3 | `(25, 108, 1233, 1920)` | 1208×1812 | saved | Sí | Sí | Sí | Marcos 7599 central; segunda corredora 16047 cortada en borde derecho. |
| `DSC05769.jpg.jpeg` | 1301×1920 | 6 | `(486.77, 434.28, 789.83, 1431.25)` | 2:3 | `(205, 283, 1071, 1582)` | 866×1299 | saved | Sí | Sí | Sí | 14329 sonriente central; brazos laterales (fotógrafo/ciclista/Humberto) bien excluidos. |
| `DSC05784.jpg.jpeg` | 1280×1920 | 6 | `(189.65, 784.78, 622.84, 1903.16)` | 2:3 | `(0, 465, 970, 1920)` | 970×1455 | saved | Sí | Sí | Sí | Gabriela 15565 frontal; pies cortados ya en origen; Pablo 7410 excluido a la derecha; posibles FN menores en fondo. |
| `DSC09438.jpg.jpeg` | 1280×1920 | 11 | `(878.62, 845.58, 1132.83, 1520.06)` | 2:3 | `(694, 743, 1280, 1622)` | 586×879 | saved | Sí | No | No | 11 detecciones sin FP evidentes. Mayor área = 16619 lateral; Matías 12704 (central, frontal) queda fuera del crop y parcialmente cortado en el borde izquierdo. |
| `DSC09465.jpg.jpeg` | 1280×1920 | 10 | `(420.90, 662.72, 769.34, 1514.23)` | 2:3 | `(226, 534, 964, 1641)` | 738×1107 | saved | Sí | Sí | Sí | Natacha 13117 frontal haciendo corazón; buen crop. |
| `DSC09470.jpg.jpeg` | 1280×1920 | 10 | `(351.46, 483.91, 991.90, 1920.00)` | 2:3 | `(34, 51, 1280, 1920)` | 1246×1869 | saved | Sí | Sí | Sí | Natacha 13117 (otra toma); crop casi marco completo; pie cortado ya en origen. |

Totales visuales: detección 13/13 (1 con matiz correctivo), selección 10/13,
composición 10/13. Detecciones totales del lote: 93. Sin `review`
en ninguna foto: todo corrió por la rama `saved`.

Métricas por corrida: A `3 processed, 3 saved, 0 review, 0 skipped`,
`review.log` vacío; B `10 processed, 10 saved, 0 review, 0 skipped`,
`review.log` vacío. Total: `13 processed, 13 saved, 0 review, 0 skipped`.

### Riesgos detectados para backlog

| Problema | Categoría | Impacto | Prioridad | Evidencia / motivo |
| --- | --- | --- | --- | --- |
| Entrada y salida iguales pueden sobrescribir el original | **Seguridad de datos** | **Crítico** | **P0** | `process_folder()` permite `input_dir == output_dir`; en éxito, `_execute()` guarda `output_dir / name`, que coincide con el archivo fuente. Contradice la garantía de no modificar originales. No corregir en etapa 04. En las corridas actuales se usaron árboles disjuntos y los hashes de originales no cambiaron; el defecto sigue vigente en código (`app/processor.py:72-105`). |
| Una excepción del detector interrumpe el lote | **Robustez operativa** | **Alto** | **P1** | `process_folder()` no captura excepciones alrededor de `detector.detect_people()`. En un lote de miles, una inferencia fallida puede abortar el proceso completo. Fue aceptado explícitamente en etapa 03; debe reconsiderarse después de la evaluación. No ejercitado en estas corridas (ninguna excepción). |
| Ausencia de sujeto principal produce un crop extremadamente pequeño | **Calidad fotográfica** | **Alto** | **P1** | `Empty_road_mongolia.jpg` produce salida 123×82 guardada como `saved` (no va a `review/`). La inspección visual muestra personas reales diminutas, no FP demostrables: el problema es compositivo (sin sujeto principal → micro-crop inútil como éxito), no de detección. Falta una salvaguarda de tamaño mínimo → `review`. |
| Solapamientos de rutas distintos de igualdad exacta no tienen política explícita | **Seguridad de datos** | Medio | P1 | No existe validación de relaciones padre/hijo o resolución canónica de rutas. La igualdad exacta ya demuestra un defecto real; los demás solapamientos deben definirse y probarse en la iteración de seguridad de datos. |
| Heurística de mayor área elige sujeto lateral o de espaldas (NUEVO, corrida actual) | **Calidad fotográfica** | Alto | P1 | `Group_…Vienna…`: elige corredor de espaldas desenfocado cortado por el borde (sel No, comp No). `DSC09438`: elige 16619 lateral y deja fuera a Matías 12704, central y frontal (sel No, comp No). 2/13 fotos afectadas. No corregir en etapa 04; es backlog de estrategia de selección. |

### Veredicto

**MVP parcialmente usable (veredicto de Muse, pendiente revisión de Astra).**

- Caso central (fotos de maratón con sujeto frontal claro): **usable en 9/10**
  fotos de `fotos/reales/` con detección, selección y composición correctas;
  `DSC09438` es la excepción por selección lateral y crop que corta al corredor
  central.
- Lote desatendido: **no usable todavía**. `Empty_road` guarda un JPEG
  123×82 inútil como éxito en lugar de derivarlo a `review/`; la heurística
  de mayor área falla en 2/13 (espaldas/lateral); y la protección de
  originales ante `input == output` sigue ausente en código (P0).
- Criterios: F1 ✓ (exits 0, `saved + review = processed`, `skipped = 0`),
  F2 ✓ (13 JPEG válidos, proporción exacta, bbox contenida, originales
  intactos), F3/F4/F5 ✓ (13/13 evaluadas visualmente de forma independiente:
  det 13/13, sel 10/13, comp 10/13), F6 ✓ (este veredicto + backlog).
  T1 ✓ (301 passed, `pip check` limpio, sin cambios en `app/`/`tests/` ni
  dependencias nuevas), T2 ✓ (segunda corrida idéntica), T3 ✓ (comandos,
  versiones, hash de pesos y tiempos registrados abajo), T4 ✓ (riesgos
  clasificados sin implementar correcciones).

La etapa 04 debe cerrarse con **una única pasada de evaluación y un
veredicto**, no con correcciones iterativas. Los defectos encontrados pasan
al backlog posterior.

### Comandos ejecutados y resultados reales

```bash
.venv/bin/python -m pytest -q        # 301 passed (1.06s, re-confirmado con resumen)
.venv/bin/python -m pip check        # No broken requirements found.
sha256sum yolo11n.pt                 # 0ebbc80d…7644ee1 (ver Estado)
.venv/bin/python -c "import ..."     # python 3.12.3, pillow 12.3.0, ultralytics 8.4.174, torch 2.14.1+cu130

ls /tmp/opencode/out04-f6 /tmp/opencode/out04-reales  # inexistentes antes de correr; no hubo que borrar

.venv/bin/python -m app.cli --input fotos --output /tmp/opencode/out04-f6
# 3 processed, 3 saved, 0 review, 0 skipped — exit 0 — wall 5.463s

.venv/bin/python -m app.cli --input fotos/reales --output /tmp/opencode/out04-reales
# 10 processed, 10 saved, 0 review, 0 skipped — exit 0 — wall 4.806s

sha256sum fotos/*.jpg fotos/reales/*.jpeg  # idénticos antes y después:
# dab5c98c… Empty_road_mongolia.jpg | 726867dc… Group_…Vienna….jpg | 4680c857… Lone_runner.jpg
# d7ddad6f… DSC00004 | 96b3fb9e… DSC00030 | 8c5082e7… DSC00084 | 465fe6ad… DSC00128
# 600a78ac… DSC00130 | ae9d462a… DSC05769 | f8ca4360… DSC05784 | 19e8f191… DSC09438
# b77f042a… DSC09465 | 7a7a3309… DSC09470

# Segunda corrida (determinismo): mismos resúmenes; snapshot de tamaños idéntico (sha256 e1808c43…55ae2693).
git status --short  # solo " M plans/04-evaluacion/plan.md" (más este registro); app/ y tests/ intactos.
```

### Veredicto provisional anterior (reemplazado por el veredicto de arriba)

**No se puede declarar el MVP usable todavía.**

La etapa 03 demuestra que el pipeline ejecuta y conserva sus contratos
técnicos en el caso normal, pero la evidencia de `Empty_road_mongolia.jpg`
prueba que eso no alcanza para validar utilidad fotográfica. Faltan las 10
fotografías nuevas y la inspección visual de composición sobre las 13.

La etapa 04 debe cerrarse con **una única pasada de evaluación y un
veredicto**, no con correcciones iterativas. Los defectos encontrados pasan
al backlog posterior.

## Revisión (Astra)

### Revisión previa del contrato

Se revisaron `PLAN.md`, `AGENTS.md`, los planes/registros de etapas 01–03,
`plans/04-evaluacion/plan.md`, `app/processor.py`, `app/cli.py` y
`.gitignore`.

Ajuste mínimo aplicado al contrato de etapa 04:

- separación explícita de **detección**, **selección** y **composición**;
- composición obligatoriamente visual;
- prohibición de inferir calidad funcional desde un exit 0 o geometría válida;
- clasificación de riesgos en seguridad de datos, robustez operativa y
  calidad fotográfica;
- cierre acotado: reunir evidencia, decidir y derivar fixes al backlog.

No se alteró la arquitectura ni el alcance funcional del MVP. No se
modificaron `app/` ni `tests/`.

### Estado de revisión

**Revisión completada por Astra el 2026-10-08.** Se contrastaron el plan, el
diff, los resultados de tests y `pip check`, la tabla de 13 archivos, el
resumen de ejecución, la integridad de originales y la inspección visual de
los tres casos de composición/selección fallida. No se modificaron `app/` ni
`tests/`.

Hallazgos de revisión y resolución:

- El veredicto decía que las 10 fotos de `fotos/reales/` eran correctas,
  aunque `DSC09438` figuraba con selección incorrecta. Corregido a 9/10;
  también se cuenta su crop como composición no aceptable porque corta al
  corredor central.
- El backlog describía el crop de `Empty_road_mongolia.jpg` como efecto de
  falsos positivos, mientras la inspección actual no confirma falsos
  positivos. Renombrado como ausencia de sujeto principal y micro-crop.
- Corregidos los conteos de composición y la afirmación de 2–3 fallos de
  selección: la evidencia documenta dos fallos.
- La evidencia heredada de etapa 03 permanece identificada como heredada y
  separada de la corrida actual.

Los criterios F1–F6 y T1–T4 quedan verificados con la evidencia registrada.
Los defectos P0/P1 se mantienen como backlog; la etapa 04 no incluye
correcciones de producción. **Etapa completada.**
