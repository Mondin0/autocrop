# Etapa V2-04 — Arquitectura local con Docker Compose

Estado: completada

Dependencias: V2-01, V2-02 y V2-03 completadas; decisiones compartidas en [V2](../PLAN.md).

## Objetivo, alcance y exclusiones

Permitir levantar en Linux la arquitectura de procesamiento V2 con Docker Compose para una demo privada local. La etapa integra la API y el worker V2-03 con Redis y RustFS. No incluye la interfaz web, autenticación, acceso público, despliegue remoto ni cambios al contrato HTTP o al motor de recorte.

## Contrato y decisiones

- Compose inicia servicios separados para API, worker, Redis y RustFS. API y worker usan la misma versión de la aplicación; Redis provee cola/estado y RustFS almacena ZIPs de entrada/salida conforme a V2-03.
- La API queda disponible únicamente en la interfaz loopback del host (`localhost`). Los servicios internos se comunican por la red de Compose; Redis y RustFS no publican puertos al host.
- El despliegue se configura mediante `compose.yaml` y variables de entorno documentadas en `.env.example`. Los valores por defecto permiten levantar la demo local sin exponer servicios internos. No se incluyen credenciales reales en el repositorio.
- Los servicios dependientes tienen healthchecks y la API/worker esperan a que Redis y RustFS estén listos. Un servicio no saludable debe producir un estado de Compose observable y un mensaje útil en sus logs.
- Los datos de Redis y RustFS sobreviven a `docker compose down` y `up` mediante volúmenes nombrados; `docker compose down -v` los elimina explícitamente. Los trabajos y sus ZIP mantienen la expiración funcional definida en V2-03.
- La imagen de aplicación instala solo dependencias necesarias para V2 y conserva la ejecución CPU. El proceso de API sirve `app.jobs.create_app`; el worker ejecuta la cola existente. La imagen no descarga pesos ni procesa archivos al iniciarse.
- `docker compose up --build` construye y levanta el conjunto; `docker compose down` lo detiene. El README documenta los comandos de inicio, URL local y detención.
- Se conserva la CLI V1 y su configuración Docker actual, salvo cambios estrictamente necesarios para que la configuración V2 coexista sin alterar su comportamiento.

## Hotfix posterior: rutas de acceso local

- En la API, `GET /health` devuelve HTTP 200 con `{"status":"ok"}`, `GET /` redirige a `http://localhost:8080` y `GET /favicon.ico` devuelve HTTP 204.
- Las rutas desconocidas siguen devolviendo HTTP 404; las rutas de trabajos conservan el contrato V2-03.
- La redirección usa el puerto frontend predeterminado de Compose.

## Criterios

- **F1:** `docker compose config` valida la configuración y `docker compose up --build` levanta API, worker, Redis y RustFS en Linux.
- **F2:** la API responde en `http://localhost` según el puerto publicado; Redis y RustFS solo son accesibles desde la red de Compose.
- **F3:** API y worker comparten configuración y conectan con los servicios correctos; una solicitud de trabajo puede recorrer cola, procesamiento y publicación del resultado con el contrato V2-03.
- **F4:** reiniciar el conjunto conserva el estado/objetos en volúmenes y se respetan las reglas de expiración de V2-03; la eliminación explícita de volúmenes borra esos datos.
- **F5:** variables y valores de configuración están documentados, no contienen secretos reales y permiten personalizar los parámetros locales necesarios.
- **F6:** las instrucciones permiten iniciar, consultar logs y detener la demo; la configuración Docker V1 sigue disponible.
- **T1:** Compose define healthchecks y dependencias listas para Redis y RustFS; los contenedores usan una red privada y solo la API publica un puerto ligado a loopback.
- **T2:** las comprobaciones se pueden ejecutar sin YOLO real ni fotos reales, usando servicios o dobles controlados para verificar el ciclo de API/worker.

## Pruebas y validación

Validar `docker compose config`, levantar el conjunto en Linux, comprobar el enlace loopback y la ausencia de puertos publicados para Redis/RustFS, y verificar el ciclo V2-03 con servicios reales. Comprobar persistencia entre reinicios y eliminación con `down -v`. Ejecutar los tests de etapa y la suite completa desde `.venv`, además de `pip check` y `git diff --check`. No se requiere inferencia YOLO ni fotografía real. Registrar resultados y limitaciones del entorno en [registro.md](registro.md); el director revisa el diff y los criterios antes de cerrar.
