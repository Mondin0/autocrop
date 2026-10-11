# Etapa V2-06 — Arranque Compose sin carpetas de datos en el host

Estado: completada

Dependencias: V2-01 a V2-05 completadas y decisiones compartidas en [V2](../PLAN.md). Contrato aprobado explícitamente por el usuario el 2026-10-10.

## Objetivo, alcance y exclusiones

Permitir levantar la demo web V2 mediante Compose sin crear carpetas `fotos/` o `output/` en el host. El código del checkout y `yolo11n.pt` siguen siendo entradas locales del build. Los ZIP, resultados y estado de trabajos permanecen en servicios y volúmenes Docker. No cambiar el Dockerfile, descargar el modelo automáticamente, actualizar dependencias o imágenes, ni cambiar el código o contrato de V1.

## Contrato y decisiones

- El arranque predeterminado de `docker compose up` incluye frontend, API, worker, Redis y RustFS, y no requiere ni monta carpetas de datos del host.
- El servicio de CLI `autocrop` de V1 permanece disponible bajo el perfil explícito `v1`; al activarlo conserva sus montajes y comportamiento existentes.
- El build de la aplicación usa el `yolo11n.pt` local existente, sin descargarlo. Se conservan el Dockerfile y las dependencias actuales. Dependencias o imágenes base pueden requerir red si no están en caché.
- El estado y los ZIP de V2 siguen persistidos en los volúmenes nombrados `redis-data` y `rustfs-data`. `docker compose down` los conserva; `docker compose down -v` los elimina.
- El README documenta la prueba web con los requisitos reales: Docker Compose, checkout, `yolo11n.pt` y ZIP de entrada; no requiere `.env`, `fotos/` ni `output/` para V2.

## Criterios

- **F1:** Compose predeterminado activa los servicios V2 sin bind mounts de datos del host ni requisitos de carpetas `fotos/` y `output/`.
- **F2:** el servicio V1 no se inicia por defecto y sigue disponible con perfil `v1`, preservando sus mounts.
- **F3:** `yolo11n.pt` se incorpora desde el checkout al build existente; no se agrega descarga del modelo ni cambio de dependencias.
- **F4:** Redis y RustFS persisten los datos en sus volúmenes nombrados y el README explica la diferencia entre `down` y `down -v`.
- **F5:** el README permite desplegar la web con `docker compose up -d --build` y probar carga, progreso y descarga desde `http://localhost:8080` sin preparar carpetas o `.env`.
- **T1:** pruebas de configuración cubren servicios por defecto, perfil V1, ausencia de bind mounts en V2, puertos loopback y volúmenes.
- **T2:** una comprobación de extremo a extremo con Playwright y un ZIP/JPEG sintético verifica carga, finalización y descarga contra el stack Compose real.

## Pruebas y validación

Escribir primero tests para F1–F4/T1 y registrar fallos funcionales. Ejecutar tests de etapa y suite completa desde `.venv`, `pip check`, `git diff --check` y `docker compose config`. Levantar el stack, completar con Chromium/Playwright el flujo sintético de carga a descarga y comprobar que V2 inicia sin directorios `fotos/` y `output/`. Registrar comandos y resultados reales en [registro.md](registro.md); el director revisa el diff y cada criterio antes del cierre. Tras la revisión, detener Compose y borrar únicamente los recursos Docker y artefactos Playwright usados en la prueba; conservar el código, documentación y modelo del proyecto.
