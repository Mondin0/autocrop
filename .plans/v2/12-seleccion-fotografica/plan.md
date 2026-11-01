# V2-12 — Selección automática de sujetos y formaciones

Estado: completada

Dependencias: motor compartido V1 y ZIP/progreso V2 existentes. V2-10 continúa en revisión y no se modifica. Contrato aprobado mediante la instrucción de implementar el plan el 2026-11-01.

## Objetivo, alcance y exclusiones

Conservar equipos en formación y evitar que una persona grande desenfocada desplace al protagonista enfocado. Afecta selección, procesador compartido web/CLI, tests y README. No incluye controles UI, modelos, entrenamiento, seguimiento, publicación ni infraestructura.

## Contratos y decisiones

- Incorporar `select_target(image, boxes) -> tuple[bbox | None, str]`. Imagen Pillow RGB ya orientada; cajas finitas `(left, top, right, bottom)`, ordenadas, no vacías y dentro de la imagen. Entradas inválidas producen `ValueError`. Motivos: `individual`, `group` (requieren caja), `no_person`, `ambiguous_subject` (devuelven None). No convertir errores de detección o cálculo en ambigüedad.
- Mantener `select_subject(boxes)` y su contrato histórico por área para consumidores directos. El procesador usa la nueva selección.
- Identificar formación principal y proteger íntegramente su envolvente. Varias personas no bastan; una persona aislada del fondo no amplía automáticamente el grupo.
- Considerar evidencia visual y relevancia de escena además del tamaño. No elegir automáticamente el más nítido. Evidencia incierta permite ambigüedad.
- Grupos usan 3:2 automático; individuales conservan proporción automática actual; proporción explícita prevalece siempre. Conservar margen, geometría, JPEG, originales y `no_valid_crop` cuando no cabe la caja completa.
- Ambigüedad copia original sin alteraciones a review/, registra `ambiguous_subject` y usa contadores existentes. No cambiar formatos API, progreso ni ZIP.
- Implementador elige algoritmo/parámetros y documenta reglas y calibración; prohibidas excepciones por nombre o fotos de prueba. Separar detección, evaluación visual, selección y geometría. Reutilizar pesos/dependencias locales; no cambiar YOLO ni descargar modelos.

## Criterios funcionales

- **F1:** DSC06443.jpg conserva equipo completo, cabezas/extremidades presentes, sin envolvente determinada por espectador lateral; salida automática 3:2.
- **F2:** DSC06460.jpg y DSC06461.jpg eligen jugador azul/amarillo derecho, conservan detección completa y no el rojo/amarillo grande del primer plano. Revisión no satisface F2.
- **F3:** selección incierta admite revisión específica. DSC06854.jpg es exploratorio ambiguo, sin protagonista exigido.
- **F4:** conservar persona única, ausencia de personas, ilegible, EXIF, margen, proporción explícita e imposibilidad geométrica.
- **F5:** web y CLI usan nueva selección; resultados llegan a ZIP y contadores sin cambios de interfaces.
- **F6:** comparar DSC06444.jpg y 12 fotos adicionales reproducibles distribuidas por el ZIP. Registrar selección, composición y revisiones nuevas; resolver regresiones antes del cierre.

## Criterios técnicos y validación

- **T1:** separación indicada, pesos y dependencias existentes, sin red/modelos nuevos.
- **T2:** tests primero con rojo funcional (stub importable permitido), implementación mínima y verde; no debilitar tests para acomodar errores.
- **T3:** tests públicos sintéticos sin pesos/red/fotos privadas: validaciones, vacío, persona única, grupo con aislado, jugada múltiple, desenfoque, superpuestos, empate, ambigüedad.
- **T4:** integración: ratio explícita, revisión idéntica, motivo en log, contadores, ZIP y protecciones de sobrescritura.
- **T5:** tests focales y suite completa desde .venv, pip check, git diff --check; README con comportamiento y límites.
- **T6:** medir anterior/nuevo en misma muestra y entorno, separar detección/selección, sin garantía inventada de rendimiento.

Inspección visual obligatoria F1/F2/F6, considerando composición además de cajas: detección incompleta no justifica cortar integrantes. Guardar originales, anotaciones y comparativas fuera de Git; registrar nombres, hashes, parámetros y conclusiones. Tests verdes no cierran sin aprobación visual.

## Delegación y revisión

Verificar disponibilidad y gratuidad exactas de DeepSeek Free en OpenCode antes de delegar; consultar si no se confirma, sin sustitución. Un subagente coordinador invoca OpenCode para toda la etapa; correcciones en misma sesión, sin editores simultáneos. Director revisa independientemente diff, criterios y evidencia, registra hallazgos con ubicación/impacto/criterio/corrección y exige regresión antes de corregir. Implementador entrega en revisión; solo director cierra con todos los criterios verificados. Informar entregas, hallazgos, verificaciones y confianza primera/final; ante bloqueo no inventar cierre.
