# Etapa V2-13 — Originales y reporte en el ZIP

Estado: completada

Dependencias: V2-01, V2-03 y V2-07 completadas; decisiones compartidas en [V2](../PLAN.md).

## Objetivo, alcance y exclusiones

Incluir en el ZIP descargable de cada trabajo los JPEG originales y un reporte HTML que relacione cada foto con el recorte producido o explique su estado de revisión. Afecta el empaquetado de salida y sus pruebas; el contrato HTTP y el formato de entrada no cambian. No incluye cambios al motor de recorte, interfaz web, V1, miniaturas, galerías ni recursos externos.

## Contrato y decisiones

- El resultado de `process_archive()` mantiene su resumen y archivos existentes (recortes, `review/` y `review.log`) y agrega todos los JPEG aceptados de la entrada, byte por byte, bajo `originals/<nombre-original>`. Los originales permanecen inalterados.
- Agrega `reporte.html` en la raíz del ZIP. El documento está en español, es legible sin conexión y no carga CSS, scripts, imágenes ni otros recursos externos. Presenta una fila por cada JPEG del lote, ordenada por nombre, con el nombre original y un enlace al original. Si el procesamiento lo guardó, muestra un enlace al recorte generado. Si quedó en revisión, muestra el motivo registrado por `process_folder()`/`review.log` y un enlace al archivo correspondiente en `review/`.
- El estado y motivo se derivan de las salidas existentes del procesador; no se vuelve a ejecutar detección ni se infiere un motivo distinto. Todo nombre mostrado se escapa como texto HTML y los enlaces apuntan a rutas relativas dentro del ZIP.
- Si el lote falla antes de producir un resultado válido, se conserva el comportamiento actual: no se publica ZIP parcial. No cambia la validación de entrada, límites, estados de trabajo, API de descarga ni limpieza temporal.

## Criterios

- **F1:** todo original JPEG incluido en la entrada aparece una vez bajo `originals/` en el ZIP final y conserva exactamente sus bytes; las salidas existentes permanecen.
- **F2:** `reporte.html` contiene una fila y enlace al original por foto procesada; cada éxito enlaza al recorte y cada revisión muestra su motivo y enlace a `review/<nombre>`.
- **F3:** el reporte funciona como HTML local sin recursos externos, escapa nombres y motivos y sus enlaces relativos resuelven a entradas existentes del ZIP.
- **F4:** ZIP de entrada inválido o fallo de lote no deja un ZIP final parcial; el resumen de procesamiento y contrato HTTP existentes no cambian.
- **T1:** empaquetado determinista, sin dependencias nuevas ni cambios a V1; evitar recalcular recortes o modificar originales.
- **T2:** tests primero con fallo funcional observado; tests focales, suite completa, `pip check` y `git diff --check` desde `.venv`.

## Pruebas y validación

Con detector controlado, probar lote mixto (guardado y revisión), lote sin revisiones, lote con todas las fotos en revisión, nombres con caracteres HTML y nombres existentes en ambas áreas. Inspeccionar el ZIP para igualdad byte a byte de originales, presencia de todas las rutas enlazadas y ausencia de referencias externas; probar además fallo de procesamiento sin salida parcial. Ejecutar tests de etapa y suite completa, `pip check` y `git diff --check` desde `.venv`. Registrar comandos y resultados reales en [registro.md](registro.md); revisar el HTML generado como documento local y el diff completo antes de cerrar.
