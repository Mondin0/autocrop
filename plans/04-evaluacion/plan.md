# Etapa 04 — Evaluación del pipeline con fotos reales

Estado: completada

Dependencias: [etapa 01 completada](../01-crop/plan.md),
[etapa 02 completada](../02-deteccion/plan.md),
[etapa 03 completada](../03-procesamiento/plan.md).
Implementación: Muse. Revisión: Astra.

## Objetivo

Decidir si el MVP es funcionalmente útil para un fotógrafo deportivo, no
solamente si el pipeline ejecuta correctamente. Correr la CLI de la etapa 03
tal cual sobre fotos reales y evaluar por separado:

1. **Detección:** si YOLO detecta correctamente las personas reales.
2. **Selección:** si la heurística vigente (mayor área) elige al sujeto que
   realmente interesa en la fotografía.
3. **Composición:** si el crop conserva al sujeto completo y produce un
   encuadre fotográficamente aceptable.

La composición requiere inspección visual. Un resultado técnicamente válido
puede ser visualmente inútil. La etapa no corrige los problemas encontrados:
genera evidencia, backlog y el veredicto de cierre del MVP.

## Alcance y entregables

- Dos corridas reales con la CLI existente, sin flags extra (ratio auto,
  `margin` default `0.15`):
  - A: `fotos/` (3 F6) → `/tmp/opencode/out04-f6`.
  - B: `fotos/reales/` (10) → `/tmp/opencode/out04-reales`.
- Tabla de 13 filas en `registro.md`: archivo, tamaño orientado, N
  detecciones, bbox sujeto, ratio aplicado, crop, tamaño salida, estado
  (`saved`/`review`), detección correcta (sí/no), selección correcta
  (sí/no), composición aceptable (sí/no) y nota breve.
- Si una dimensión no puede verificarse visualmente, marcarla explícitamente
  como **pendiente**; no inferir calidad visual a partir de que el programa
  haya terminado o de que la geometría sea válida.
- Métricas por corrida y total: `processed/saved/review/skipped`,
  contenido de `review.log`, falsos positivos registrados sin ocultar.
- Veredicto: MVP usable sí/no + backlog priorizado. Sin `models.py`, sin
  estrategias nuevas, sin reentrenamiento.

## Exclusiones

Foco/nitidez (Fase 2), XMP/Lightroom (Fase 3), RAW (Fase 4), GUI/desktop
(Fase 5), optimización de miles de fotos (Fase 6), cambio de heurística de
selección (mayor área), cambio de umbral/modelo, conversión de formatos y
control de calidad configurable. Un falso positivo aislado no cambia la
regla de área; se registra como límite conocido.

No cambiar `app/` ni `tests/` en esta etapa. Si un bug tumba el lote, se
registra como hallazgo bloqueante y se corrige en la iteración que
corresponda; la 04 no es vía para nuevas features ni un ciclo indefinido de
mejoras.

## Decisiones de evaluación

- Mismo detector documentado: `yolo11n.pt` del directorio actual,
  `confidence=0.25`, CPU. No descargar pesos de nuevo; registrar
  `sha256sum` y versiones (Python, Pillow, ultralytics, torch).
- Ratio auto por imagen (3:2 horizontal, 2:3 vertical, 1:1 cuadrada),
  margen `0.15`. Sin `--ratio` ni `--margin` en las corridas base.
- Nunca modificar originales; comparar hash/mtime antes/después o apoyarse
  en la cobertura existente, pero además revisar explícitamente que entrada
  y salida no coincidan ni se solapen de forma peligrosa.
- `review/` solo recibe copias `copy2` sin recorte parcial, con motivo en
  `review.log` (`no_person` / `no_valid_crop` / `unreadable`).
- `Empty_road_mongolia.jpg` es una limitación conocida: en etapa 03 produjo
  cinco falsos positivos y un JPEG 123×82. No corregir modelo, umbral,
  selección ni crop durante esta evaluación; clasificar el problema como
  evidencia de calidad funcional insuficiente.

## Criterios funcionales

- **F1 — Ejecución:** ambas corridas terminan en exit `0`; resumen
  consistente (`saved + review = processed`, `skipped = 0` esperado,
  todo `.jpg`).
- **F2 — Integridad técnica:** cada `saved` es JPEG válido con proporción
  exacta del ratio aplicado y bbox seleccionada contenida en el crop;
  originales intactos.
- **F3 — Detección:** por foto se registra si las detecciones de persona
  corresponden a personas reales. Falsos positivos y falsos negativos se
  registran sin ocultarlos.
- **F4 — Selección:** por foto se registra si la caja elegida por mayor área
  corresponde al sujeto que el fotógrafo consideraría principal. Que sea la
  mayor caja no basta para aprobar funcionalmente este criterio.
- **F5 — Composición:** inspección visual por foto: sujeto principal entero,
  margen/centrado razonables y encuadre fotográficamente utilizable. Una
  proporción matemáticamente correcta no implica aprobación visual.
- **F6 — Cierre:** emitir veredicto de usabilidad del MVP y backlog
  priorizado. La evaluación termina después de reunir la evidencia acordada;
  los fixes se realizan después, no dentro de esta etapa.

## Criterios técnicos

- **T1:** baseline intacto: `.venv/bin/python -m pytest` → `301 passed`,
  `.venv/bin/python -m pip check` limpio, sin dependencias nuevas ni
  cambios en `app/`/`tests/`.
- **T2:** determinismo: segunda corrida sobrescribe idéntica (mismo resumen
  y tamaños), orden por nombre, sin reloj/azar.
- **T3:** evidencia reproducible en `registro.md`: comandos y resultados
  reales, versiones, hash de pesos, tiempos por corrida.
- **T4:** riesgos encontrados se clasifican sin implementar correcciones:
  **seguridad de datos**, **robustez operativa** o **calidad fotográfica**,
  con impacto y prioridad.

## Riesgos a revisar para backlog

Como mínimo analizar:

1. Posible sobrescritura de originales si entrada y salida coinciden o se
   solapan.
2. Interrupción completa del lote ante excepciones del detector.
3. Generación de crops excesivamente pequeños por falsos positivos.

No corregirlos en etapa 04. Registrar evidencia, impacto, categoría y
prioridad.

## Casos y procedimiento de validación

1. **Preparar (Muse):** leer contrato/historial y marcar `en implementación`.
   Baseline `.venv/bin/python -m pytest -q` (301 tests) y `pip check`.
2. **Corridas reales:** limpiar outputs y ejecutar
   `python -m app.cli --input fotos --output /tmp/opencode/out04-f6` y
   `python -m app.cli --input fotos/reales --output /tmp/opencode/out04-reales`.
   Registrar por archivo lo pedido en Alcance + tiempos y versiones. No
   agregar inferencia real a la suite.
3. **Revisión funcional:** para cada foto revisar original, detecciones,
   selección y salida. Registrar F3, F4 y F5 de forma independiente. Si la
   imagen no puede abrirse/inspeccionarse, marcar la dimensión pendiente.
4. **Riesgos:** inspeccionar el comportamiento vigente y clasificar los tres
   riesgos mínimos del backlog; no implementar fixes.
5. **Entregar (Muse):** completar `## Implementación`, marcar
   `en revisión`. No autodeclarar usable/completada.
6. **Revisar (Astra):** verificar evidencia, tabla de 13 fotos, clasificación
   de riesgos y veredicto. Cerrar a `completada` solo con las 13 evaluadas
   y sin evidencia pendiente necesaria para el veredicto. No iniciar fixes
   dentro de esta etapa.

No delegar ni implementar por el solo hecho de crear este plan. No hay
etapa 05 en el MVP.
