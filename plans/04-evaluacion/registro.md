# Etapa 04 — Registro de ejecución y revisión

Contrato: [plan.md](plan.md). Estado vigente: ver `plan.md`.

## Implementación (Muse)

### Estado

**Pendiente de ejecución local.**

La evaluación completa requiere las 3 fotografías de `fotos/` y las 10 de
`fotos/reales/`. La carpeta `fotos/` está excluida por `.gitignore`, por
lo que las imágenes no están disponibles mediante el conector de GitHub y no
pueden inspeccionarse visualmente desde esta sesión.

No se ejecutaron nuevas corridas de etapa 04 y no se modificaron `app/` ni
`tests/`.

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

### Diez fotografías nuevas

**Pendientes.** Los archivos de `fotos/reales/` no están versionados y sus
nombres/resultados no son visibles desde GitHub. Muse debe completar diez
filas adicionales tras la corrida local, sin inventar resultados.

### Comandos pendientes para la ejecución local

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
sha256sum yolo11n.pt

rm -rf /tmp/opencode/out04-f6 /tmp/opencode/out04-reales

.venv/bin/python -m app.cli \
  --input fotos \
  --output /tmp/opencode/out04-f6

.venv/bin/python -m app.cli \
  --input fotos/reales \
  --output /tmp/opencode/out04-reales
```

Después de la corrida se deben abrir original y salida por cada foto y
completar independientemente: detección, selección y composición.

### Riesgos detectados para backlog

| Problema | Categoría | Impacto | Prioridad | Evidencia / motivo |
| --- | --- | --- | --- | --- |
| Entrada y salida iguales pueden sobrescribir el original | **Seguridad de datos** | **Crítico** | **P0** | `process_folder()` permite `input_dir == output_dir`; en éxito, `_execute()` guarda `output_dir / name`, que coincide con el archivo fuente. Contradice la garantía de no modificar originales. No corregir en etapa 04. |
| Una excepción del detector interrumpe el lote | **Robustez operativa** | **Alto** | **P1** | `process_folder()` no captura excepciones alrededor de `detector.detect_people()`. En un lote de miles, una inferencia fallida puede abortar el proceso completo. Fue aceptado explícitamente en etapa 03; debe reconsiderarse después de la evaluación. |
| Falso positivo puede generar crop extremadamente pequeño | **Calidad fotográfica** | **Alto** | **P1** | `Empty_road_mongolia.jpg`: 5 falsos positivos, selección de una caja pequeña y salida 123×82. El pipeline cumple técnicamente pero genera una fotografía inútil. |
| Solapamientos de rutas distintos de igualdad exacta no tienen política explícita | **Seguridad de datos** | Medio | P1 | No existe validación de relaciones padre/hijo o resolución canónica de rutas. La igualdad exacta ya demuestra un defecto real; los demás solapamientos deben definirse y probarse en la iteración de seguridad de datos. |

### Veredicto provisional

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

La ejecución y el cierre quedan **pendientes** hasta que Muse corra las dos
muestras locales y complete las 13 evaluaciones visuales.
