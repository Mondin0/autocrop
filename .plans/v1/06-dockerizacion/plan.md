# Etapa 06 — Dockerización del MVP

Estado: completada

Dependencias: etapa 05 completada. Implementación: Muse por OpenCode Zen; revisión: agente coordinador.

## Objetivo y alcance

Empaquetar la CLI existente para ejecutar lotes desde un contenedor persistente llamado `autocrop`. Crear Dockerfile, compose.yaml, .dockerignore, entrada ejecutable del paquete, pruebas y documentación. Conservar el procesamiento vigente. Excluir GPU, servicios web, interfaz interactiva, cambios de selección/crop y etapas futuras.

## Contrato y decisiones

- Uso: `docker compose up -d --build`, luego `docker exec -it autocrop autocrop --input /input --output /output`. Mantener `--ratio` y `--margin`, valores por defecto y códigos de salida existentes. `docker exec` requiere un comando después del nombre del contenedor; documentarlo explícitamente.
- Registrar `autocrop = app.cli:main` como console script en pyproject.toml. Mantener `python -m app.cli`. No duplicar parser ni lógica de procesamiento.
- Imagen basada en Python 3.12 slim con dependencias de sistema estrictamente necesarias. Instalar paquete y dependencias; preferir PyTorch CPU para evitar bibliotecas CUDA innecesarias. No instalar dependencias del proyecto globalmente en el host.
- Directorio de trabajo fijo dentro de la imagen con `yolo11n.pt`, copiado desde el archivo local al construir. Construir sin ese archivo debe fallar. No descargar pesos durante build ni ejecución. Conservar la ruta del detector existente mediante WORKDIR.
- Compose usa servicio y container_name `autocrop`, sin puertos ni restart automático, y un proceso inactivo persistente (sleep infinity). Las ejecuciones son secuenciales, iniciadas por docker exec. Detener con docker compose down.
- Bind mounts configurables por AUTOCROP: usar variables `AUTOCROP_INPUT_DIR` (default ./fotos) y `AUTOCROP_OUTPUT_DIR` (default ./output). Destinos /input solo lectura y /output escritura. Preparar directorios explícitamente según README; no crear una entrada inexistente silenciosamente (bind create_host_path: false). Salida debe existir antes de up.
- Ejecutar con UID/GID del usuario host configurados mediante `AUTOCROP_UID` y `AUTOCROP_GID` (README exporta id -u e id -g antes de up) para producir archivos editables por el usuario. Preparar HOME/config temporal escribible si Ultralytics lo necesita. Pesos y aplicación legibles para ese usuario.
- .dockerignore excluye .git, .venv, fotos, output, caches, secretos/config local y artefactos no necesarios; incluye código, metadatos y los pesos requeridos. No enviar fotos al contexto de construcción.
- Rutas distintas de contenedor pueden montar la misma carpeta del host: comprobar que las protecciones existentes por identidad de archivo siguen evitando sobrescrituras. No prometer igualdad canónica de dos bind mounts distintos; originales quedan protegidos por montaje readonly y controles existentes.
- README documenta requisitos Docker/Compose/pesos, export de variables con rutas absolutas y UID/GID, mkdir de salida, build/up, help, procesamiento, resultados, cambio de mounts mediante recreación y down. Documentar CPU y que empaquetar no mejora la selección del sujeto.
- PLAN.md incorpora índice y decisión Docker solicitada por usuario. No reabrir etapas 01–05 ni revertir cambios previos sin commit.

## Criterios de aceptación

- F1: build y up crean contenedor autocrop activo; exec autocrop --help devuelve 0; opciones existentes funcionan.
- F2: JPEG de prueba procesado con YOLO real produce crop o review y resumen en host; hash original permanece idéntico. Imagen vacía sintética válida permite probar review sin depender de selección deportiva.
- F3: /input es readonly incluso ante intento de escritura; /output escribible; archivos generados pertenecen al UID/GID configurado.
- F4: pesos presentes dentro de imagen, ejecución funcional sin red (exec en contenedor con red deshabilitada o prueba equivalente), sin descarga de modelo.
- F5: entradas inexistentes o argumentos inválidos devuelven error; conflicto --input /input --output /input preserva originales y falla. Dos mounts a misma carpeta no alteran originales.
- F6: instrucciones de inicio, uso y parada reproducibles; cambiar rutas exige recrear.
- T1: pruebas primero con evidencia roja por comportamiento pendiente, luego verde; comprobar console script instalado y configuración Docker sin tests que solo repitan líneas de implementación.
- T2: suite completa `.venv/bin/python -m pytest` y `.venv/bin/python -m pip check` verdes; en imagen pip check verde.
- T3: contexto excluye fotos/entorno/secretos; runtime CPU; reutilizar CLI y protecciones. Sin cambios en crop, subject ni processor salvo defecto de integración demostrado y aprobado por revisión.

## Validación y entrega

Muse escribe primero pruebas pertinentes del empaquetado y registra fallos funcionales reales (no importar módulo inexistente). Ejecuta build, compose config/up, help, procesamiento sintético real, checks de permisos/hash/readonly, errores, pesos sin red, suite y pip check. Usar temporales para fotos/output de pruebas, nunca sobrescribir fotos locales. Registrar comandos, resultados, tamaños/limitaciones relevantes y bloqueos reales en registro.md. Si una comprobación queda bloqueada, mantener en revisión; no inventar resultados ni cerrar etapa. No publicar imagen ni hacer commits.

Revisor inspecciona diff completo de etapa, valida contrato/pruebas/documentación y ejecuta comprobaciones apropiadas. Hallazgos incluyen ubicación, impacto, criterio y corrección esperada. Correcciones por Muse con regresión antes de lógica cuando corresponda. Solo cerrar completada sin pendientes.
