# V2 — Procesamiento local de lotes ZIP

## Objetivo

Un fotógrafo levanta Docker Compose en su computadora Linux, abre una página local, sube un ZIP de fotos JPEG, ve el avance por foto y descarga un ZIP con el contenido completo de la carpeta de salida actual: recortes, `review/` y `review.log`. La CLI V1 sigue disponible.

## Decisiones compartidas

- Un ZIP de entrada de hasta 500 MiB contiene JPEG `.jpg`/`.jpeg` en su raíz. Se rechazan ZIP inválidos, sin JPEG o con JPEG dentro de subcarpetas. La extracción debe limitar el contenido real descomprimido a 2 GiB y evitar nombres peligrosos y colisiones.
- El procesador existente en `app.processor.process_folder` es el motor de recorte. Los originales no se modifican; cada trabajo usa directorios temporales aislados.
- La pantalla muestra trabajo en cola, foto actual, procesadas/total, guardadas y enviadas a revisión. Consulta el estado cada segundo; al finalizar habilita la descarga.
- FastAPI sirve API y pantalla sencilla. Redis mantiene cola y estado; un worker procesa un trabajo a la vez. RustFS guarda temporalmente los ZIP de entrada y salida.
- El ZIP final puede descargarse hasta tres horas después de terminar el trabajo. La API rechaza descargas vencidas y una tarea limpia objetos y temporales; la caducidad exacta no depende de las reglas por días de RustFS.
- Compose publica la web en `localhost` por defecto. La primera validación es en Linux y se trata de una demo privada local. No se añade autenticación ni acceso público en esta versión.
- El director redacta cada contrato; el usuario lo aprueba antes de delegar código. El implementador escribe tests primero; el director revisa el diff y la evidencia hasta cerrar hallazgos. Ver [AGENTS.md](../../AGENTS.md).

## Etapas

1. [ZIP seguro alrededor del motor](01-zip-seguro/plan.md): entrada, límites, extracción y empaquetado de salida sin servicios web.
2. [Avance por foto](02-avance-por-foto/plan.md): eventos de progreso observables durante el procesamiento de un ZIP, sin servicios web.
3. [API y worker de trabajos](03-api-worker/plan.md): crear trabajos de procesamiento, consultar su estado/progreso y descargar el resultado usando Redis y RustFS, sin interfaz web ni configuración Compose.
4. [Arquitectura local con Docker Compose](04-compose/plan.md): ejecutar la API, el worker, Redis y RustFS como demo local integrada, accesible solo desde localhost.
5. [Interfaz web local](05-interfaz-local/plan.md): subir un ZIP desde el navegador, consultar el avance por foto y descargar el resultado desde la API local.
6. [Arranque Compose sin carpetas de datos del host](06-compose-sin-datos-host/plan.md): iniciar la demo V2 sin directorios de entrada/salida del host, conservando el build local de pesos y dependencias.

7. [Transferencias ZIP con memoria acotada](07-transferencias-acotadas/plan.md): eliminar ZIP completos en memoria del servidor, conservar HTTP y limpiar temporales.
8. [Recuperación y limpieza de trabajos](08-ciclo-de-vida/plan.md): reclamación durable, interrupciones visibles, retención de fallidos y limpieza reintentable incluso con cola ocupada.
9. [Interfaz consistente y documentación](09-interfaz-consistente/plan.md): aislar respuestas tardías, evitar envíos/sondeos duplicados y corregir instrucciones de V1/V2.
10. [Validación integral y cierre](10-validacion-cierre/plan.md): navegador y servicios reales, corpus fotográfico, lote grande, reinicio y expiración.

## Ruta de cierre propuesta el 2026-10-14

Las etapas 01–06 están completadas según sus registros. A pedido del usuario se definen ahora todos los contratos restantes para el alcance de demo privada local, sin implementar etapas futuras por adelantado. V2-07 está completada desde el 2026-10-14, con evidencia en su [registro](07-transferencias-acotadas/registro.md). V2 todavía no se declara cerrada: faltan las etapas propuestas 08–10 y su aceptación integral. No se agregan autenticación, publicación, historial, cancelación, nuevos parámetros de recorte ni soporte Mac V2.

La lectura del código identifica transferencias completas en `JobService.run_next()`/`result_bytes()`, limpieza solo ociosa y borrados fallidos silenciados en `cleanup()`, reclamación no durable con `lpop()` y sondeo concurrente sin descarte de respuestas antiguas en `frontend/index.html`. Estos son motivos de los nuevos contratos, no resultados de implementación. Las evidencias históricas no se modifican.

### Decisiones de los contratos pendientes

- Un único worker; los trabajos interrumpidos fallan de forma visible, sin reanudación automática.
- Completed y failed conservan estado hasta limpieza después de tres horas desde el terminal. Antes de limpieza, resultado completed vencido devuelve 410; después de borrar estado devuelve 404.
- Limpieza entre trabajos y en espera: una inferencia larga puede retrasar el borrado físico, nunca ampliar la disponibilidad de descarga.
- Transferencias de servidor a archivos, con temporales aislados y limpieza; el navegador actual conserva la limitación de memoria de `Response.blob()`.
- La implementación de la recepción multipart ya usa archivo temporal; no se promete cuota global de disco ni protección para exposición pública. La prueba grande verificará el límite efectivo por frontend/API y registrará consumo temporal.
- Cierre obligatorio con fotos reales autorizadas y revisión visual, además de sintéticos y tests; V1-07 permanece sin cambios.

### Ejecución y avances

Orden: **07 → 08 → 09 → 10**. Cada etapa requiere aprobación explícita de su contrato antes de delegar; puede aprobarse el conjunto identificando estos cuatro contratos. La petición de preparar planes no se registra como aprobación de implementación. Después de cada entrega, el director revisa y gestiona correcciones de esa misma etapa; para iniciar la siguiente debe haber una instrucción explícita de continuar, además de su contrato aprobado.

Implementador solicitado: **OpenCode Muse Free**, invocado por CLI mediante un subagente coordinador; nunca sustituirlo por un subagente nativo que use otro proveedor. Los encargos remiten a AGENTS y al contrato, exigen tests primero y evidencia roja/verde. El director mantiene revisión y cierre. Cada registro empieza vacío y recibirá solamente resultados reales.

Avances revisables: 07 entrega el recorrido sin ZIP completo en RAM del servidor; 08 entrega recuperación/retención; 09 entrega navegador consistente; 10 aporta evidencia de aceptación y cierre. Mostrar al usuario los resultados al terminar cada entrega/revisión, con pendientes explícitos. La medianoche es una prioridad de ejecución, no una garantía ni motivo para reducir validaciones. El camino crítico incluye disponibilidad de Muse, builds Docker, Chromium y corpus real; no se fijan estimaciones de tiempo sin medir.

### Revisión de planificación

El 2026-10-14, un subagente coordinador ejecutó una auditoría de solo lectura con `opencode run --model opencode/muse-spark-1.3-contributor-free --title "V2 auditoria de cierre"`; modelo listado por `opencode models`, salida 0. Muse confirmó fuga de entradas/estados failed, ausencia de evidencia fotográfica real con saved y ausencia de validación integrada de caducidad. También señaló la redirección fija a 8080 y los riesgos de RAM/limpieza ociosa. El director contrastó esas observaciones con el código y conserva el redirect histórico, documentando el puerto personalizado en V2-09; separa las correcciones en 07–09 y aceptación en 10 para hacer cada entrega revisable. La auditoría no ejecutó tests ni Docker ni cambió código; no cuenta como validación funcional.
