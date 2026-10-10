# Etapa V2-03 — API y worker de trabajos

Estado: pendiente

Contrato aprobado explícitamente por el usuario el 2026-10-10. La aprobación autoriza iniciar la implementación de esta etapa en una sesión nueva.

Dependencias: V2-01 y V2-02 completadas; decisiones compartidas en [V2](../PLAN.md).

## Objetivo, alcance y exclusiones

Permitir que un cliente local cree un trabajo de procesamiento de ZIP, consulte su estado y progreso, y descargue el ZIP completo al terminar. La API y el worker conectan `process_archive()` con Redis para cola/estado y RustFS para los ZIP temporales. No incluye pantalla, Compose, autenticación, despliegue público ni cambios al motor de recorte.

## Contrato y decisiones

- FastAPI expone `POST /api/jobs` con un archivo multipart llamado `file`. Acepta un ZIP de hasta 500 MiB medidos mientras se recibe; si supera el límite, devuelve HTTP 413 y descarta el temporal de entrada. La carga se escribe en temporal/almacenamiento por bloques, sin mantener el archivo completo en memoria. La llamada válida devuelve HTTP 202 con `{ "job_id": "<uuid>", "status": "queued" }` y encola el trabajo. La validación de contenido ZIP ocurre en el worker mediante `process_archive()`; los ZIP inválidos terminan como trabajos `failed` con un mensaje legible.
- `GET /api/jobs/{job_id}` devuelve HTTP 200 y `{job_id, status, current, processed, total, saved, review, error}`. `status` es `queued`, `processing`, `completed` o `failed`; `current` es el JPEG en curso o `null`; los contadores son enteros no negativos y cumplen `processed == saved + review` y `processed <= total`. `error` es `null` salvo en estado `failed`. Un id desconocido devuelve HTTP 404.
- Un worker procesa un trabajo a la vez en orden de encolado. Al iniciarlo cambia el estado a `processing`; actualiza el estado consultable con cada callback de progreso de V2-02; al terminar publica el ZIP y marca `completed`. Errores de validación o procesamiento marcan `failed`, con mensaje legible y sin ZIP parcial descargable.
- `GET /api/jobs/{job_id}/result` devuelve el ZIP final con HTTP 200 solo cuando el trabajo está `completed` y no venció. En estados `queued` o `processing` devuelve HTTP 409; en `failed` devuelve HTTP 409; vencido devuelve HTTP 410; id desconocido devuelve HTTP 404.
- Cada trabajo tiene un UUID independiente y sus objetos de RustFS no se comparten con otros trabajos. El ZIP final puede descargarse hasta tres horas después de terminar; vencido ese plazo la API responde HTTP 410. Se registra la hora de finalización en Redis. La limpieza de objetos vencidos queda para una etapa posterior, pero la API no entrega resultados vencidos.
- Una tarea periódica elimina los objetos de entrada y salida y el estado Redis cuando un trabajo completado lleva más de tres horas. La expiración de la descarga se calcula desde la hora de finalización registrada, no desde la ejecución de esta limpieza.
- La API y el worker usan los mismos nombres y tipos de campos de progreso definidos en V2-02. No se agregan estimaciones de tiempo ni cancelación.

## Criterios

- **F1:** crear trabajo válido devuelve 202 con UUID, estado `queued` y encola el archivo; archivo mayor a 500 MiB devuelve 413.
- **F2:** el estado refleja cola, procesamiento, eventos V2-02 y resultado final; respeta invariantes de contadores y devuelve 404 para ids desconocidos.
- **F3:** el worker procesa un trabajo a la vez, mantiene cada ZIP aislado y marca `completed` solo después de que el resultado completo esté disponible en RustFS.
- **F4:** ZIP rechazado o fallo de procesamiento marca `failed` con error legible y no ofrece un resultado parcial.
- **F5:** la descarga entrega los bytes exactos del ZIP final únicamente durante las tres horas posteriores a completar; los estados no descargables devuelven los códigos acordados.
- **F6:** el trabajo de limpieza elimina estado y objetos de trabajos vencidos sin borrar resultados antes del límite de tres horas.
- **T1:** API y worker reutilizan `process_archive()` y su callback; Redis almacena cola/estado y RustFS los ZIP de entrada/salida.
- **T2:** pruebas sin inferencia real verifican rutas HTTP, ciclo de estados, serialización de progreso, fallos, aislamiento, límites de descarga y expiración usando Redis/RustFS de prueba o dobles controlados.

## Pruebas y validación

Probar endpoints HTTP con cliente FastAPI, ZIP sintéticos y worker invocable de forma controlada. Verificar F1–F6 y errores de Redis/RustFS sin depender de YOLO ni fotos reales. Ejecutar tests de etapa, suite completa y `pip check` desde `.venv`. La validación con servicios reales y Compose queda para una etapa posterior. Registrar comandos y resultados en [registro.md](registro.md); el director revisa el diff y los casos límite antes de cerrar.
