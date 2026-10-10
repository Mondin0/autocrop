# Etapa V2-02 — Avance por foto

Estado: pendiente

Dependencias: V2-01 completada y decisiones compartidas en [V2](../PLAN.md). El usuario debe aprobar este contrato antes de delegar implementación.

## Objetivo, alcance y exclusiones

Exponer el avance de `process_archive()` mientras procesa las fotos, para que una etapa posterior pueda guardarlo y mostrarlo. Esta etapa solo agrega eventos en memoria y tests. No incorpora API, Redis, RustFS, worker, navegador, cancelación ni estimaciones de tiempo; tampoco cambia la selección, detección, recorte, contenido del ZIP final o comportamiento de la CLI V1.

## Contrato y decisiones

- Añadir a `app.archive.process_archive()` un parámetro opcional final `on_progress: Callable[[dict[str, int | str | None]], None] | None = None`. Las llamadas existentes conservan resultado y comportamiento. El callback recibe un diccionario nuevo en cada evento con exactamente `current`, `processed`, `total`, `saved` y `review`. `current` es el nombre simple del JPEG en curso o `None`; los demás campos son enteros no negativos.
- `total` es la cantidad de JPEG aceptados de la raíz, sin contar otros archivos. Los JPEG se procesan en el orden determinista que usa `process_folder()`. `processed` cuenta fotos terminadas, y siempre cumple `processed == saved + review` y `processed <= total`.
- Tras validar y extraer completamente el ZIP, emitir un evento inicial con `current=None` y contadores en cero. Para cada JPEG, emitir uno inmediatamente antes de procesarlo con `current` igual a su nombre y contadores de fotos terminadas; emitir otro tras conocer su resultado, con el mismo `current` y contadores actualizados. Tras publicar el ZIP de salida, emitir un evento final con `current=None`, `processed=total` y los contadores finales. Para `n` JPEG, la ejecución exitosa emite `2n + 2` eventos.
- Un ZIP rechazado antes de completar validación y extracción no emite eventos. Si falla el detector, la escritura o el callback, la excepción se propaga; no se emite el evento final ni se publica un ZIP parcial. Los eventos ya entregados no se revierten. El callback final se invoca después de publicar la salida: si falla, la excepción se propaga y el ZIP completo permanece disponible.
- La incorporación del progreso no debe duplicar el motor de recorte ni procesar una foto más de una vez. Si se amplía `process_folder()` con un callback opcional, las llamadas existentes de V1 deben conservar firma compatible, resumen, archivos y mensajes.

## Criterios

- **F1:** un ZIP válido emite la secuencia inicial, antes/después de cada foto y final con nombres, orden y contadores correctos.
- **F2:** el resumen, contenido del ZIP y bytes de entrada son iguales con y sin callback; la CLI V1 conserva su comportamiento.
- **F3:** ZIP inválido o fallo durante extracción no emite progreso; fallo de detector o callback previo al evento final conserva los eventos ya emitidos y no publica salida parcial.
- **F4:** el evento final solo llega después de publicar el ZIP; un fallo del callback final deja disponible el resultado completo y propaga el error.
- **T1:** se reutiliza `process_folder()`; sin nuevos servicios ni dependencias de producción.
- **T2:** tests primero con fallo funcional observado; tests de etapa, suite completa y `pip check` desde `.venv`.

## Pruebas y validación

Tests públicos con JPEG sintéticos y detector controlado verifican F1–F4: dos fotos con resultados distintos y orden conocido, archivo no JPEG omitido, diccionarios independientes, paridad con llamada sin callback, ZIP inválido, entrada ilegible, fallo en detección, fallo del callback antes de procesar y fallo del callback final. Comprobar ausencia de salida parcial donde corresponda y presencia del ZIP completo en el fallo del callback final. Ejecutar los tests contra estructura mínima antes de implementar para observar fallos funcionales; después, tests de etapa, suite completa y `pip check`. Registrar comandos y resultados reales en [registro.md](registro.md); el director revisa el diff y los casos límite antes de cerrar.
