# Etapa V2-07 — Transferencias ZIP con memoria acotada

Estado: completada

Aprobación: contrato aprobado explícitamente por el usuario el 2026-10-14 para dirigir únicamente V2-07 con OpenCode Muse Free mediante un coordinador. No autoriza iniciar V2-08.

Dependencias: V2-01 a V2-06 completadas; decisiones compartidas en [V2](../PLAN.md).

## Objetivo, alcance y exclusiones

Hacer viable el límite anunciado de 500 MiB sin cargar ZIP completos en la memoria de API o worker. Afecta `app/jobs.py`, adaptadores de almacenamiento, endpoint de resultado y sus tests; revisar también el proxy. No cambia el motor, los límites ZIP, los campos HTTP ni las dependencias. No incluye control de cuotas del disco, escalado ni descarga progresiva a disco del navegador.

## Contratos y decisiones

- La recepción actual por bloques se conserva. El worker descarga la entrada a su temporal y publica la salida desde archivo mediante transferencias por bloques o las funciones de archivo de boto3; no usa `get()` completo, `Path.read_bytes()` ni `put(bytes)` para esos ZIP en producción.
- Agregar al adaptador existente la operación de descarga a archivo necesaria; reutilizar `put_file()`. Mantener las funciones públicas de bytes existentes para compatibilidad con sus callers y tests, sin usarlas en el recorrido de producción. Los dobles de memoria pueden almacenar bytes, pero las pruebas de esta etapa deben impedir materialización completa en el recorrido de producción.
- El endpoint de resultado comprueba estado y vencimiento antes de obtener el objeto. Descarga a un temporal por bloques y lo entrega con una respuesta de archivo; limpia el temporal al concluir, fallar o desconectarse el cliente. Esta decisión prioriza poder responder un error HTTP antes de iniciar el cuerpo; no promete tiempo al primer byte constante.
- Preservar bytes, `application/zip`, nombre de descarga y códigos 404/409/410. Si falla la lectura del resultado antes de enviar cabeceras, responder 409 conforme al comportamiento actual. Una descarga autorizada dentro del plazo puede terminar después de vencer. Una limpieza concurrente no borra el temporal local de una descarga ya preparada.
- Los errores de transferencia de entrada/salida conservan `failed`, mensaje legible y ausencia de resultado parcial descargable. Los temporales de cada operación se aíslan y se limpian en éxito y fallo; los cierres de cuerpos S3 se garantizan cuando se use lectura manual.
- Medir por separado la memoria de inferencia y la de transferencia: esta etapa elimina el crecimiento proporcional al ZIP en servidor, sin prometer una cantidad fija de RAM para YOLO ni para imágenes decodificadas. El frontend actual aún usa `Response.blob()`; documentar esa limitación de memoria del cliente.

## Criterios funcionales

- **F1:** cargar, procesar y descargar un ZIP conserva su resultado y progreso usando transferencias de archivo en servidor.
- **F2:** la descarga mantiene bytes, nombre, tipo y códigos de estado; no empieza si el resultado venció o no está completo.
- **F3:** fallos de lectura/escritura y desconexiones no dejan temporales ni resultados parciales descargables.
- **F4:** la API de bytes existente sigue disponible para sus callers; V1 conserva su comportamiento.

## Criterios técnicos

- **T1:** el recorrido de servidor no materializa un ZIP completo en bytes; usa adaptadores existentes y biblioteca estándar/dependencias instaladas.
- **T2:** regresiones primero demuestran fallos funcionales; tests de etapa y suite completa, `pip check` y `git diff --check` desde `.venv`.

## Casos y procedimiento de validación

- F1/T1: dobles de blob que rechazan `get()`/`put(bytes)` en el recorrido del worker y espían descargas/subidas a archivo; comparar el ZIP entregado byte a byte. Leer los callers de `result_bytes()`, `get()` y `put_file()` antes de cambiar interfaces.
- F2: estados queued/processing/failed, desconocido, resultado ausente y frontera exacta de tres horas con reloj inyectado.
- F3: error al descargar entrada, subir salida o preparar descarga; respuesta completada y cliente desconectado, comprobando limpieza de temporales de servidor.
- F4/T2: suite preexistente sin debilitar aserciones. La comprobación con RustFS y un archivo grande queda integrada en V2-10; no duplicar un benchmark aquí.

Registrar implementación y revisión en [registro.md](registro.md). No cerrar solo por tests verdes.
