# Etapa V2-13 — Fotos finales y reporte en el ZIP

Estado: completada

Dependencias: V2-01, V2-03 y V2-07 completadas; decisiones compartidas en [V2](../PLAN.md).

## Objetivo, alcance y exclusiones

Incluir en el ZIP descargable una sola versión de cada JPEG y un reporte HTML que explique las fotos en revisión. Afecta el empaquetado de salida, sus pruebas y los límites documentados de entrada; el formato de entrada no cambia. No incluye cambios al motor de recorte, interfaz web aparte del aviso de límite, V1, miniaturas, galerías ni recursos externos.

## Contrato y decisiones

- El ZIP de salida contiene cada foto una sola vez en la raíz, con el nombre original: si se recortó con éxito, contiene la imagen recortada; si quedó en revisión, contiene el original byte por byte. No agrega sufijos `-crop`, carpetas ni copias adicionales.
- Agrega `reporte.html` en la raíz del ZIP. El documento está en español, es legible sin conexión y no carga recursos externos. Incluye únicamente filas para fotos en revisión, ordenadas por nombre, con motivo registrado por `process_folder()`/`review.log` y enlace al original.
- El estado y motivo se derivan de las salidas existentes del procesador; no se vuelve a ejecutar detección ni se infiere un motivo distinto. Todo nombre mostrado se escapa como texto HTML y los enlaces apuntan a rutas relativas dentro del ZIP.
- La subida admite ZIP comprimidos de hasta 5 GiB y hasta 5 GiB descomprimidos (incluyendo archivos no JPEG dentro del total declarado y real). El resultado no tiene un nuevo límite específico.
- Si el lote falla antes de producir un resultado válido, no se publica ZIP parcial. No cambian estados de trabajo, API de descarga ni limpieza temporal.

## Criterios

- **F1:** cada JPEG aparece una sola vez en la raíz con su nombre original; éxitos contienen el recorte y revisiones el original sin modificar.
- **F2:** `reporte.html` contiene solo las fotos en revisión, con el motivo registrado y enlace al original; si no hay fallas, no hay filas de fotos.
- **F3:** el reporte funciona como HTML local sin recursos externos, escapa nombres y motivos y sus enlaces relativos resuelven a entradas existentes del ZIP.
- **F4:** ZIP inválido, fallo de lote o exceso de cualquiera de los límites no deja un ZIP final parcial; no hay colisión artificial de nombre de recorte. El resumen y contrato HTTP existentes no cambian.
- **F5:** se aceptan archivos comprimidos y contenido descomprimido de hasta 5 GiB inclusive, y se rechaza el byte siguiente.
- **T1:** empaquetado determinista, sin dependencias nuevas ni cambios a V1; evitar recalcular recortes o modificar originales.
- **T2:** tests primero con fallo funcional observado; tests focales, suite completa, `pip check` y `git diff --check` desde `.venv`.

## Pruebas y validación

Con detector controlado, probar lote mixto (guardadas y revisiones), lote sin revisiones, lote con todas las fotos en revisión y nombres con caracteres HTML. Verificar que cada archivo se incluye una vez con nombre original, los recortes sustituyen a sus originales, los originales de revisión son byte por byte idénticos y las rutas del reporte existen; probar fallo sin ZIP parcial. Probar límites comprimido y descomprimido en el byte exacto y un byte por encima mediante constantes reducidas en tests, además de comprobar los valores de 5 GiB y el aviso UI. Ejecutar tests focales y suite completa, `pip check` y `git diff --check` desde `.venv`; no generar fixtures de 5 GiB. Registrar resultados reales en [registro.md](registro.md) y revisar el diff completo.
