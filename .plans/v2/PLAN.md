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

Las etapas posteriores se definirán una por vez para conectar API, cola, almacenamiento, interfaz y operación. No implementarlas durante la etapa 01.
