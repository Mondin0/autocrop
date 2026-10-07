# Etapa 04 — Evaluación del pipeline con fotos reales

Estado: pendiente

Dependencias: [etapa 01 completada](../01-crop/plan.md),
[etapa 02 completada](../02-deteccion/plan.md),
[etapa 03 completada](../03-procesamiento/plan.md).
Implementación: Muse. Revisión: Astra.

## Objetivo

Decidir si el MVP es usable: correr la CLI de la etapa 03 tal cual sobre
fotos reales y registrar por foto si el recorte sirve. No genera código
nuevo; genera la evidencia y el veredicto de cierre del MVP.

## Alcance y entregables

- Dos corridas reales con la CLI existente, sin flags extra (ratio auto,
  `margin` default `0.15`):
  - A: `fotos/` (3 F6) → `/tmp/opencode/out04-f6`.
  - B: `fotos/reales/` (10) → `/tmp/opencode/out04-reales`.
- Tabla de 13 filas en `registro.md`: archivo, tamaño orientado, N
  detecciones, bbox sujeto, ratio aplicado, crop, tamaño salida, estado
  (`saved`/`review`), OK visual (sí/no + nota de 1 línea).
- Métricas por corrida y total: `processed/saved/review/skipped`,
  contenido de `review.log`, falsos positivos registrados sin ocultar.
- Veredicto: MVP usable sí/no + backlog de fases futuras. Sin `models.py`,
  sin estrategias nuevas, sin reentrenamiento.

## Exclusiones

Foco/nitidez (Fase 2), XMP/Lightroom (Fase 3), RAW (Fase 4), GUI/desktop
(Fase 5), optimización de miles de fotos (Fase 6), cambio de heurística de
selección (mayor área), cambio de umbral/modelo, conversión de formatos y
control de calidad configurable. Un falso positivo aislado no cambia la
regla de área; se registra como límite conocido.

No cambiar `app/` ni `tests/` en esta etapa. Si un bug tumba el lote, se
registra como hallazgo bloqueante y se corrige en la etapa que corresponda;
la 04 no es vía para nuevas features.

## Decisiones de evaluación

- Mismo detector documentado: `yolo11n.pt` del directorio actual,
  `confidence=0.25`, CPU. No descargar pesos de nuevo; registrar
  `sha256sum` y versiones (Python, Pillow, ultralytics, torch).
- Ratio auto por imagen (3:2 horizontal, 2:3 vertical, 1:1 cuadrada),
  margen `0.15`. Sin `--ratio` ni `--margin` en las corridas base.
- Nunca modificar originales; comparar hash/mtime antes/después o apoyarse
  en la cobertura de la suite (hash intacto). Anotaciones visuales, si se
  generan, como archivos nuevos fuera de `fotos/`.
- `review/` solo recibe copias `copy2` sin recorte parcial, con motivo en
  `review.log` (`no_person` / `no_valid_crop` / `unreadable`).

## Criterios funcionales

- **F1:** ambas corridas terminan en exit `0`; resumen consistente
  (`saved + review = processed`, `skipped = 0` esperado, todo `.jpg`).
- **F2:** cada `saved` es JPEG válido con proporción exacta del ratio
  aplicado y bbox sujeto contenida en el crop; originales intactos.
- **F3:** revisión visual por foto: sujeto principal entero y centrado
  razonable; `review/` solo con casos sin persona/sin crop/ilegible y
  motivo correcto; falsos positivos (ref. `Empty_road`, 5 detecciones en
  03) registrados, no ocultos ni forzados a revisión.

## Criterios técnicos

- **T1:** baseline intacto: `.venv/bin/python -m pytest` → `301 passed`,
  `.venv/bin/python -m pip check` limpio, sin dependencias nuevas ni
  cambios en `app/`/`tests/`.
- **T2:** determinismo: segunda corrida sobrescribe idéntica (mismo
  resumen y tamaños), orden por nombre, sin reloj/azar.
- **T3:** evidencia reproducible en `registro.md`: comandos y resultados
  reales, versiones, hash de pesos, tiempos por corrida.

## Casos y procedimiento de validación

1. **Preparar:** leer contrato/historial y marcar `en implementación`.
   Baseline `.venv/bin/python -m pytest -q` (301 tests) y `pip check`.
2. **Corridas reales (fuera de la suite):** limpiar outputs y ejecutar
   `python -m app.cli --input fotos --output /tmp/opencode/out04-f6` y
   `python -m app.cli --input fotos/reales --output
   /tmp/opencode/out04-reales`. Registrar por archivo lo pedido en
   Alcance + tiempos y versiones. No agregar inferencia real a la suite.
3. **Revisión visual:** abrir salida vs original (o anotación nueva) y
   marcar OK visual por fila. Verificar proporción exacta y sujeto entero.
4. **Entregar y revisar:** llenar `## Implementación` con tablas y
   métricas; marcar `en revisión`. Astra verifica contrato, evidencia y
   diff (debería ser solo `registro.md` + este plan). Cierra a
   `completada` solo verificado y sin hallazgos; con eso el MVP queda
   cerrado y usable. Fases futuras van a backlog, no a esta etapa.

No delegar ni implementar por el solo hecho de crear este plan. No hay
etapa 05 en el MVP.
