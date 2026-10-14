# Etapa V2-08 — Recuperación y limpieza de trabajos

Estado: completada

Aprobación: contrato aprobado explícitamente por el usuario en esta sesión; cierre revisado por el director el 2026-10-14.

Dependencias: V2-07 completada; decisiones compartidas en [V2](../PLAN.md).

## Objetivo, alcance y exclusiones

Evitar trabajos atascados tras reiniciar el único worker y fugas de ZIP por fallos o limpieza incompleta. Afecta `app/jobs.py`, `app/worker.py`, adaptadores Redis/memoria y tests. No incorpora múltiples workers, reintentos automáticos de inferencia, nuevos estados públicos, cancelación ni garantías de alta disponibilidad.

## Contratos y decisiones

- Conservar estados HTTP queued/processing/completed/failed y FIFO. Se admite exactamente un worker, como en Compose actual. Antes de tomar nuevos trabajos al arrancar, reconciliar los reclamados por una ejecución anterior: pasar a `failed`, con `current=None`, mensaje legible de interrupción y hora de finalización. No reanudar ni repetir inferencia silenciosamente; el usuario puede reenviar su ZIP.
- La reclamación desde Redis debe conservar duraderamente el identificador antes de sacarlo de la cola pendiente, mediante una operación atómica de Redis que lo mueva a una lista de trabajo activo. Retirarlo de esa lista solo después de persistir un estado terminal. Reconciliar también un id reclamado aún marcado queued y un id con estado terminal: el primero falla por interrupción y el segundo conserva el resultado. Los trabajos todavía en cola mantienen orden y no se pierden al reiniciar. El doble en memoria implementa el mismo contrato observable.
- Tras errores transitorios de Redis en el ciclo del worker, reconciliar lo reclamado antes de seguir consumiendo; si Redis sigue inaccesible, registrar el error y esperar, sin descartar identificadores. No tratar un fallo al guardar estado como procesamiento exitoso.
- `finished_at` se registra también para failed. Completados y fallidos se limpian después de tres horas de su estado terminal. Los nuevos fallidos nunca permiten descarga. Para registros failed antiguos sin `finished_at`, asignar al primer encuentro una hora de inicio de retención; no borrarlos inmediatamente. No cambiar los estados/evidencia de etapas anteriores.
- La descarga mantiene 200 hasta el límite inclusivo de tres horas y 410 después mientras exista el registro; una vez eliminados objetos y estado, 404. Resolver explícitamente la contradicción textual de V2-03 (limpieza diferida frente a tarea periódica): la limpieza queda implementada y reforzada aquí, sin editar el contrato histórico.
- Intentar limpieza antes de cada nuevo trabajo y en cada vuelta ociosa, nunca durante una inferencia. Por tanto una inferencia larga puede retrasar la eliminación física; el vencimiento de descarga sigue siendo exacto. No añadir un scheduler ni otro contenedor.
- Eliminar el estado/indexado solo después de borrar ambos objetos; si una eliminación falla, conservar el registro vencido para reintentar y registrar el error. Las eliminaciones son idempotentes: un objeto ya ausente no impide completar la limpieza. Aislar el fallo de un trabajo para poder limpiar otros.
- Si fallan guardado o encolado durante la presentación de un nuevo trabajo, no devolver 202. Intentar revertir objeto y estado propios, sin tocar otros trabajos; registrar un fallo de reversión. Tras volver los servicios, limpiar los huérfanos del prefijo de trabajos que no tengan estado ni reclamación, con antigüedad mayor de tres horas para no interferir con una presentación en curso. Reutilizar listado/paginación S3; no escanear objetos ajenos al prefijo ni cargar sus cuerpos. Una respuesta 202 solo se emite una vez persistidos objeto, estado y cola.

## Criterios funcionales

- **F1:** reiniciar el worker vuelve fallido el trabajo interrumpido, conserva el completado y continúa la cola pendiente en FIFO.
- **F2:** no hay ventana entre sacar un id de cola y conservarlo para recuperación; un fallo de estado no pierde la reclamación.
- **F3:** completados y fallidos caducan según reloj; activos y resultados vigentes no se borran.
- **F4:** fallos de borrado conservan evidencia para reintentar, sin impedir limpiar otros trabajos.
- **F5:** una cola continuamente ocupada no evita los intentos de limpieza entre trabajos.
- **F6:** una presentación fallida no devuelve aceptación; sus huérfanos se revierten o se eliminan posteriormente sin afectar trabajos válidos.

## Criterios técnicos

- **T1:** reutilizar servicios, Redis y RustFS; sin nuevas dependencias ni infraestructura, con mensajes útiles de fallo.
- **T2:** tests primero con reloj y almacenes controlados; pruebas de etapa, suite completa, `pip check` y `git diff --check` desde `.venv`.

## Casos y procedimiento de validación

- F1/F2: corte tras reclamación, tras guardar processing y tras publicar resultado pero antes de liberar reclamación; nuevo worker falla solo trabajos sin terminal persistido. Corte de Redis al guardar progreso/terminal y recuperación posterior. Probar con Redis real en V2-10, no solo con el doble.
- F3/F4: frontera exacta del TTL, completed/failed/queued/processing, failed histórico; fallo en cada borrado, reintento idempotente y segundo trabajo que sí se limpia.
- F5: varios trabajos sin hueco ocioso, comprobando limpieza entre ellos; no exigir interrupción de inferencia.
- F6: fallos al subir, guardar y encolar; reversión fallida, objeto huérfano antiguo, objeto reciente de una presentación en curso y paginación de listado. Verificar aislamiento por prefijo y UUID.

Registrar comandos y resultados en [registro.md](registro.md). El director revisa particularmente ventanas de fallo, límites del único worker y ausencia de pérdida de datos.
