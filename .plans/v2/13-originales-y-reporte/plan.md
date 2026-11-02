# Etapa V2-13 — Originales y reporte en el ZIP

Estado: completada

Dependencias: V2-01, V2-03 y V2-07 completadas; decisiones compartidas en [V2](../PLAN.md).

## Objetivo, alcance y exclusiones

Incluir en el ZIP descargable de cada trabajo los JPEG originales y un reporte HTML que relacione cada foto con el recorte producido o explique su estado de revisión. Afecta el empaquetado de salida y sus pruebas; el contrato HTTP y el formato de entrada no cambian. No incluye cambios al motor de recorte, interfaz web, V1, miniaturas, galerías ni recursos externos.

## Contrato y decisiones

- El ZIP de salida contiene todos los JPEG originales byte por byte en la raíz. Cada recorte exitoso también queda en la raíz con nombre `<base>-crop<ext>`; las fotos en revisión quedan solo como original, sin carpetas ni copias adicionales. Se rechaza el lote si un nombre de recorte colisiona (sin distinguir mayúsculas) con otro original.
- Agrega `reporte.html` en la raíz del ZIP. El documento está en español, es legible sin conexión y no carga recursos externos. Incluye únicamente filas para fotos en revisión, ordenadas por nombre, con motivo registrado por `process_folder()`/`review.log` y enlace al original.
- El estado y motivo se derivan de las salidas existentes del procesador; no se vuelve a ejecutar detección ni se infiere un motivo distinto. Todo nombre mostrado se escapa como texto HTML y los enlaces apuntan a rutas relativas dentro del ZIP.
- Si el lote falla antes de producir un resultado válido, se conserva el comportamiento actual: no se publica ZIP parcial. No cambia la validación de entrada, límites, estados de trabajo, API de descarga ni limpieza temporal.

## Criterios

- **F1:** todo original JPEG aparece una vez en la raíz con bytes idénticos; cada éxito tiene un recorte raíz `<base>-crop<ext>`; una revisión queda solo como original.
- **F2:** `reporte.html` contiene solo las fotos en revisión, con el motivo registrado y enlace al original; si no hay fallas, no hay filas de fotos.
- **F3:** el reporte funciona como HTML local sin recursos externos, escapa nombres y motivos y sus enlaces relativos resuelven a entradas existentes del ZIP.
- **F4:** ZIP inválido, fallo de lote o colisión de nombre no deja un ZIP final parcial; colisiones se rechazan antes de procesar. El resumen y contrato HTTP existentes no cambian.
- **T1:** empaquetado determinista, sin dependencias nuevas ni cambios a V1; evitar recalcular recortes o modificar originales.
- **T2:** tests primero con fallo funcional observado; tests focales, suite completa, `pip check` y `git diff --check` desde `.venv`.

## Pruebas y validación

Con detector controlado, probar lote mixto (guardado y revisión), lote sin revisiones, lote con todas las fotos en revisión, nombres con caracteres HTML y nombres existentes en ambas áreas. Inspeccionar el ZIP para igualdad byte a byte de originales, presencia de todas las rutas enlazadas y ausencia de referencias externas; probar además fallo de procesamiento sin salida parcial. Ejecutar tests de etapa y suite completa, `pip check` y `git diff --check` desde `.venv`. Registrar comandos y resultados reales en [registro.md](registro.md); revisar el HTML generado como documento local y el diff completo antes de cerrar.
