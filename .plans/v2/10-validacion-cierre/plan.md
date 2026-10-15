# Etapa V2-10 — Validación integral y cierre de V2

Estado: en revisión

Aprobación: contrato aprobado explícitamente por el usuario antes de delegar ejecución.

Dependencias: V2-07, V2-08 y V2-09 completadas; V2-01 a V2-06 conservan sus cierres históricos.

## Objetivo, alcance y exclusiones

Verificar la demo local Linux como producto integrado: arranque, fotos reales, progreso, descarga, límites, reinicio y caducidad. Esta es una etapa de aceptación y documentación, no una etapa para implementar mejoras libres. Cualquier defecto exige regresión previa y corrección dentro del contrato afectado, registrada aquí y revisada por el director. No incluye publicar imágenes, despliegue público, autenticación, Apple Silicon ni mejoras del detector.

## Contratos y decisiones

- Usar checkout, pesos locales y Compose existentes, sin descargar otro modelo ni modificar originales. Instalar herramientas de test solo en `.venv` desde el extra dev declarado y Chromium de Playwright si falta. No actualizar dependencias de producto durante el cierre.
- Preflight: estado Git, espacio libre, pesos, versión Compose, `.venv`, Playwright y puertos. Registrar SHA del checkout y hash de pesos, versiones y comandos reales. Un prerrequisito ausente queda como bloqueo concreto; no inventar resultados.
- Las fotos reales provienen de una carpeta o ZIP local indicado por el usuario; trabajar con copias temporales y comparar hashes de originales antes/después. No buscar fotos privadas fuera de las rutas autorizadas ni descargar un corpus para sustituir esa validación.
- Corpus pequeño pero representativo: persona con recorte, sin persona/revisión, múltiples personas, orientación EXIF/vertical y horizontal; añadir JPEG ilegible y nombres con espacios/caracteres españoles mediante fixtures controladas. Si el corpus real no cubre algún caso, completar con sintéticos y declarar cuál. Inspeccionar visualmente originales y recortes, revisar `review.log` y verificar bytes idénticos para fotos en review. Calidad de composición conserva los límites documentados de V1; no promete detectar siempre al deportista deseado.
- Recorrido con navegador real contra Compose: subir, observar queued/processing, nombres y contadores, completar, descargar ZIP íntegro con `review/` y `review.log`. Repetir con ZIP inválido/anidado y volver a enviar un lote válido sin reiniciar.
- Validar un ZIP válido grande, cercano al límite de 2 GiB, y rechazo por encima del límite a través del frontend y API; registrar tamaño, tiempo y pico de memoria de API/worker, sin imponer un objetivo de rendimiento inventado. Construir fixtures en temporales y eliminarlas al acabar. Demostrar que no aparecen copias completas del ZIP en memoria de servidor con evidencia combinada de tests de V2-07 y medición; diferenciar coste YOLO/decodificación. La memoria del navegador se registra como límite conocido.
- Reiniciar worker durante un trabajo; comprobar failed legible y avance de los pendientes. Reiniciar Compose sin borrar volúmenes y comprobar resultado completado vigente descargable. Los tests automáticos de fronteras cubren TTL con reloj; en servicios reales usar una copia de registros de prueba marcada con hora antigua para demostrar 410 previo a limpieza, eliminación posterior y reintento ante fallo de borrado. No esperar tres horas ni cambiar el TTL productivo.
- Usar recursos Docker de prueba identificados. No ejecutar `down -v` sobre datos preexistentes; preferir un nombre de proyecto aislado con nombres/puertos de contenedor ajustados en override temporal, sin alterar Compose productivo. Documentar el aislamiento antes de arrancar. Eliminar al terminar únicamente recursos creados por esta validación; conservar pesos, originales, entorno de trabajo y recursos ajenos.
- Actualizar README si la ejecución revela instrucciones incorrectas, y el índice V2 con estado final y enlace a la evidencia solo cuando todos los criterios estén verificados. No crear tag/release ni hacer commit/publicación automáticamente. V1-07 permanece en revisión.

## Criterios funcionales

- **F1:** una persona puede iniciar V2 y completar carga, avance y descarga desde localhost con las instrucciones del README.
- **F2:** fotos reales producen recortes y revisión inspeccionados visualmente; originales intactos y ZIP completo/integral.
- **F3:** entradas inválidas y límite excedido se rechazan de forma visible, sin impedir el siguiente trabajo válido.
- **F4:** reinicio, persistencia, caducidad y limpieza cumplen V2-08 con Redis y RustFS reales.
- **F5:** prueba de archivo grande completa el recorrido y aporta medición real de tiempo/memoria y límites observados.
- **F6:** quedan instrucciones correctas, evidencia reproducible y recursos de prueba limpiados sin afectar datos anteriores.

## Criterios técnicos

- **T1:** suite completa desde `.venv`, incluyendo navegador; `pip check`, `docker compose config` y `git diff --check` pasan. Todo skip se identifica y justifica; no omitir pruebas nuevas para cerrar.
- **T2:** pruebas integradas usan API/worker/frontend/Redis/RustFS reales, puertos solo loopback y pesos CPU locales; separar esta evidencia de los dobles unitarios.
- **T3:** el director verifica criterios y revisa diff/evidencia; no quedan hallazgos abiertos, verificaciones exigidas pendientes ni estados V1 modificados.

## Casos y procedimiento de validación

1. T1/T2: preflight, suite, configuración y stack aislado; registrar servicios, mounts, salud y puertos.
2. F1/F2: flujo navegador con corpus real, ZIP verificado (`testzip`, contenido, hashes) y revisión visual documentada con nombres de casos, conclusiones y limitaciones; no incluir las fotos privadas en Git.
3. F3/F5: inválidos, anidado, JPEG ilegible, límite exacto y exceso; archivo grande con métricas y nuevo lote válido después del error.
4. F4: interrupción y cola, reinicio conservando volúmenes, TTL/reintento de limpieza con datos de prueba; comparar HTTP y objetos/estado antes/después.
5. F6/T3: revisión independiente del director, README contrastado, limpieza identificada y cierre del índice V2.

Registrar comandos, resultados, fotos/casos examinados, hallazgos y correcciones en [registro.md](registro.md). Si faltan fotos reales, recursos o una comprobación requerida, dejar la etapa en revisión y V2 sin cierre; la demo puede seguir utilizable.
