# Etapa V2-05 — Interfaz web local

Estado: completada

Dependencias: V2-01, V2-02, V2-03 y V2-04 completadas; decisiones compartidas en [V2](../PLAN.md).

## Objetivo, alcance y exclusiones

Permitir que una persona use la demo local desde un contenedor frontend separado: enviar un ZIP, seguir el procesamiento por foto y descargar el ZIP de salida a través de la API existente. No incluye autenticación, acceso público, cancelación, historial de trabajos, cambios al contrato de API ni cambios a V1.

## Contrato y decisiones

- Compose incorpora un servicio `frontend` separado de la API. Sirve la página estática en `http://localhost:8080` (ligado a loopback) y reenvía las rutas `/api/` al servicio `api:8000` por la red interna de Compose. El servicio `api` conserva la publicación local de V2-04 en su puerto actual. El navegador usa el origen del frontend para todas las llamadas; no requiere CORS, CDN, cuenta ni servicio externo.
- `GET /` en el servicio frontend sirve la página; los recursos de la página pertenecen a ese servicio, no a la aplicación FastAPI. El proxy conserva método, ruta, query, cuerpo, códigos y respuestas de la API.
- La página permite seleccionar y enviar un ZIP mediante `POST /api/jobs` como multipart con el campo `file` ya definido en V2-03. Una aceptación muestra el identificador y estado inicial del trabajo. La interfaz puede dejar la selección libre; la validación autoritativa de formato y contenido sigue en el procesador.
- Para un trabajo aceptado, consulta `GET /api/jobs/{job_id}` cada segundo mientras su estado sea `queued` o `processing`. Muestra el estado, la foto actual cuando exista y los contadores `processed/total`, `saved` y `review` tal como los devuelve la API. No calcula ni inventa progreso.
- Al llegar a `completed`, detiene la consulta y ofrece descargar el resultado mediante `GET /api/jobs/{job_id}/result`. En `failed`, detiene la consulta y muestra el mensaje `error` devuelto por la API. No ofrece descarga antes de completar.
- Los errores observables de envío, consulta o descarga (incluidos límite excedido, respuesta HTTP no exitosa y fallo de conexión) se presentan como mensaje visible en la página; un error de consulta detiene el sondeo hasta que la persona vuelva a enviar un trabajo. No se pierde la posibilidad de enviar otro trabajo.
- No se agregan rutas de API ni se altera su semántica. La raíz `/` del frontend sirve la página; rutas no contratadas como `/health` continúan sin estar disponibles en la API. La interfaz solo gestiona el trabajo actual de la página; no promete persistencia del identificador tras recargar.

## Criterios

- **F1:** `GET /` por el puerto del frontend sirve la página de carga; las llamadas `/api/*` pasan por el proxy al servicio API y conservan las respuestas V2-03.
- **F2:** seleccionar y enviar un ZIP genera una petición multipart `file` a `/api/jobs`; ante HTTP 202 la página muestra el trabajo aceptado y consulta su estado cada segundo.
- **F3:** durante `queued`/`processing` se muestran estado, `current` cuando no sea nulo y los contadores recibidos (`processed/total`, `saved`, `review`); no se muestra progreso inventado.
- **F4:** ante `completed` cesa el sondeo y aparece una descarga al endpoint `/result`; en `failed` cesa el sondeo, aparece el error y no se ofrece descarga.
- **F5:** fallos HTTP o de conexión durante envío/consulta/descarga quedan visibles y no dejan el sondeo en ejecución indefinida; después de un error de consulta se puede iniciar otro trabajo.
- **T1:** Compose ejecuta frontend y API en contenedores separados; publica ambos solo en loopback (frontend en 8080 y API según V2-04), y el frontend llega a la API por la red interna. No requiere dependencias de servicios web externos.
- **T2:** pruebas con cliente HTTP y/o navegador controlado cubren carga, estado en progreso, finalización, fallo y errores de transporte sin YOLO real, RustFS/Redis reales ni fotos reales.

## Pruebas y validación

Con dobles controlados, comprobar la ruta frontend `/`, el proxy de rutas `/api/*`, el envío multipart, la consulta y el sondeo de estados, la visibilidad de contadores y foto actual, el cese de sondeo en estados terminales, la descarga solo tras completar y la presentación/recuperación ante errores. Ejecutar tests de etapa, suite completa, `pip check` y `git diff --check` desde `.venv`. En Linux con Compose, verificar manualmente el recorrido en navegador desde `http://localhost:8080`: subir un ZIP sintético, observar avance, completar y descargar el ZIP. No se requiere inferencia YOLO ni fotografía real. Registrar comandos y resultados reales en [registro.md](registro.md); el director revisa el diff y cada criterio antes de cerrar.
