# Etapa V2-09 — Interfaz consistente y documentación de uso

Estado: completada

Aprobación: contrato aprobado por el usuario, con autorización para implementar únicamente esta etapa (V2-09).

Dependencias: V2-08 completada; decisiones compartidas en [V2](../PLAN.md).

## Objetivo, alcance y exclusiones

Evitar que consultas o envíos demorados mezclen trabajos y permitir operar la demo con mensajes claros. Afecta `frontend/index.html`, pruebas de navegador y README; revisar la redirección raíz de API únicamente para documentar los puertos. No requiere rediseño visual, framework, historial, persistencia al recargar, reanudación de sondeo ni funcionalidades de producto nuevas.

## Contratos y decisiones

- La página gestiona un único trabajo actual. Cada envío invalida las respuestas pendientes del trabajo anterior; cualquier respuesta tardía de carga, consulta o descarga anterior no cambia estado, contadores, errores ni enlace del actual. Usar un identificador de generación o mecanismo equivalente pequeño, sin biblioteca nueva.
- Impedir envíos duplicados mientras se recibe la aceptación de una carga; habilitar el envío al concluir o fallar. Tras aceptar, se puede enviar otro lote; eso cambia el trabajo visible, no cancela el anterior en servidor. Hacer visible este comportamiento.
- Consultar inmediatamente al aceptar y luego cada segundo, sin peticiones de estado superpuestas: programar la siguiente consulta al terminar la anterior. Terminal o error detiene el sondeo; respuestas HTTP y JSON inválido quedan como error legible. No inventar contadores ni cambiar los campos API.
- Una selección vacía produce un mensaje visible sin petición. Indicar en la página JPEG en raíz, máximo 500 MiB y descarga por tres horas. Mantener labels, alertas y estados accesibles existentes; nombres y errores externos se muestran con `textContent`.
- La descarga sigue asociada al UUID que la inició y conserva el nombre correcto aunque el usuario cambie de trabajo mientras espera. Un fallo de conexión o HTTP se muestra; 410 se explica como resultado vencido y 404 como resultado ausente o ya limpiado. No habilitar descarga de queued/processing/failed ni sustituir la descarga por una pestaña de error.
- Corregir README para que todos los comandos de CLI Docker V1 usen `--profile v1` cuando corresponda; el arranque V2 sigue sin carpetas del host. Describir reinicio (interrumpidos fallan), expiración/limpieza, retención de fallidos, diagnóstico por logs y límite de memoria del cliente al descargar. La raíz de API conserva su redirección histórica a 8080; si se personaliza el puerto frontend, indicar abrir directamente el puerto configurado. No añadir configuración extra para ese caso.

## Criterios funcionales

- **F1:** una respuesta demorada de un trabajo anterior nunca reemplaza la vista ni la descarga del actual.
- **F2:** no hay cargas duplicadas por doble clic ni sondeos concurrentes; se puede volver a enviar tras error o aceptación.
- **F3:** selección vacía, JSON inválido y errores HTTP/conexión de carga, estado o descarga quedan visibles y detienen lo que corresponda.
- **F4:** progreso y descarga conservan UUID, campos y semántica; límite y vencimiento son comprensibles.
- **F5:** README permite operar V1/V2 con sus perfiles y explica recuperación, limpieza y restricciones verificadas.

## Criterios técnicos

- **T1:** JavaScript nativo y estructura actual, sin dependencias ni rediseño ajeno al contrato; conservar accesibilidad y escapar texto externo.
- **T2:** regresiones de navegador primero, con respuestas controladas; suite de etapa y completa, `pip check` y `git diff --check` desde `.venv`.

## Casos y procedimiento de validación

F1/F2: demorar consulta A, aceptar B y resolver A con completed/failed/error; demorar aceptación y doble clic; demorar descarga A y cambiar a B; comprobar nombre y vista. Una consulta que tarda más de un segundo no genera otra concurrente. F3/F4: sin selección, aceptación/estado con JSON roto, red interrumpida y 413/404/409/410/500; todos los casos permiten un nuevo envío. Incluir nombres con caracteres HTML como texto inocuo. F5: leer comandos Docker de todo README y comprobar perfiles contra `docker compose config`, sin ejecutar la CLI sobre originales.

Usar el extra dev de Playwright existente en `.venv`; comprobar disponibilidad del navegador antes de pruebas. Registrar evidencia roja/verde y revisión en [registro.md](registro.md).
