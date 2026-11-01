---
name: v2-stage
description: Direct an explicitly invoked Autocrop V2 stage through contract, delegation, review, closure, and next-stage handoff only when requested.
---

# Dirigir una etapa V2

Usar esta skill solo para una etapa concreta de `.plans/v2/` y el rol pedido por el usuario. Leer `AGENTS.md`, `.plans/v2/PLAN.md`, el contrato y el código pertinente. Mantener `plan.md` como contrato y estado, y `registro.md` como evidencia e historial de revisión.

## Definir

Redactar el contrato de la etapa con los criterios y la validación necesarios para implementarla sin inventar decisiones de producto. Crear el registro con secciones Implementación y Revisión vacías. Presentar el contrato al usuario y esperar su aprobación explícita antes de encargar código. No delegar la implementación de la etapa siguiente en la sesión que cerró la anterior.

Redactar un contrato declarativo: definir el resultado observable y sus restricciones, no una secuencia de pasos de implementación. Precisar interfaz y tipos, entradas válidas e inválidas, salidas y errores observables, límites y casos frontera, invariantes, componentes afectados, exclusiones, criterios de aceptación y comprobación concreta para cada criterio. Resolver antes del traspaso toda ambigüedad que pueda cambiar el comportamiento, para evitar idas y vueltas por decisiones de producto. Dejar al implementador la elección de algoritmo, estructura interna y detalles técnicos que satisfagan el contrato; imponerlos solo cuando sean una restricción necesaria y justificar por qué. Mantener el plan tan breve como permita esa precisión. Si una decisión indispensable sigue abierta, preguntarla en vez de delegar una suposición al implementador.

## Delegar y revisar

Respetar el modelo director elegido por el usuario; no exigir un modelo frontera por defecto ni afirmar un cambio de modelo que la plataforma no permite realizar. Tras la aprobación, elegir un implementador gratuito y apto de OpenCode Zen, salvo indicación expresa del usuario. Verificar disponibilidad y coste y registrar el modelo y un motivo breve. Si no se pueden confirmar, consultar al usuario sin sustituir proveedor ni elegir un modelo de pago. Ver [invocación de implementadores](references/implementers.md) para el traspaso.

El director invoca OpenCode directamente por CLI; no implementa la etapa en su sesión principal. No crear un subagente que solo coordine o espere el proceso. Usar un coordinador únicamente si el usuario lo solicita o aporta trabajo independiente necesario. Encargar la etapa completa con contrato aprobado, tests primero, evidencia roja funcional, implementación mínima, validaciones y evidencias de entrega concretas. Incluir las restricciones de acceso a datos. Evitar implementadores simultáneos sobre los mismos archivos.

Esperar la terminación del implementador antes de revisar su entrega o devolver correcciones. Se pueden preparar comprobaciones independientes, pero no evaluar versiones intermedias ni enviar hallazgos sobre trabajo sin entregar. Consultar logs solo ante un error, una solicitud del implementador o indicios concretos de bloqueo; no sondearlos repetidamente para producir mensajes de progreso.

Tras cada entrega, revisar el diff completo, correspondencia con contrato y tests, casos límite y validación visual cuando corresponda. Usar los criterios como lista de verificación, con evidencia observada o hueco concreto. Registrar cada hallazgo con ubicación, impacto, criterio y corrección esperada. Agrupar todos los hallazgos en una única devolución a la misma sesión; exigir la regresión antes de cada corrección. No comunicar hallazgos de uno en uno.

Ejecutar pruebas focales tras cada corrección y la suite completa una vez sobre la entrega candidata final. El director comprueba independientemente los resultados esenciales; no repetir comprobaciones propias sobre el mismo código salvo cambios posteriores o una duda concreta. Respetar las validaciones adicionales del contrato. Leer solo los archivos y fragmentos de logs necesarios.

Después de dos rondas de correcciones, si siguen incumplidos criterios obligatorios, detener nuevas delegaciones, registrar los defectos y la decisión necesaria y pedir autorización para continuar. No cambiar de modelo ni prolongar el ciclo por cuenta propia. Cerrar solo cuando todos los criterios estén verificados; de lo contrario mantener `en revisión` con los pendientes explícitos.

## Límites

Respetar autorizaciones y permisos del entorno; no usar flags que desactiven controles de aprobación o sandbox. No atribuir al implementador resultados que el director no pueda corroborar. Conservar la evidencia previa al iterar. Informar al usuario del cierre o bloqueo con enlace al plan.

Al entregar, informar brevemente criterios cumplidos y pendientes, número de entregas y rondas de corrección, hallazgos corregidos, comprobaciones independientes y riesgos concretos, con enlace al plan. Los porcentajes de confianza son opcionales si el usuario los pide: son estimaciones de juicio, no probabilidades medidas, y no habilitan trabajo adicional. No prolongar la revisión sin un riesgo o criterio identificable.

## Siguiente etapa y nueva sesión

Preparar la siguiente etapa solo cuando el usuario lo pida. Reutilizar un contrato pendiente cuando corresponda; si hace falta uno nuevo, crear únicamente su `plan.md`, `registro.md` vacío y entrada en el índice V2. Presentar el contrato y esperar su aprobación explícita antes de delegar. Prepararlo no autoriza implementarlo.

Tras la aprobación, entregar un mensaje breve para una nueva sesión principal de Codex con la etapa, enlace al contrato e indicación de invocar `$v2-stage`. Terminar la sesión actual sin lanzar la siguiente etapa; la nueva sesión vuelve a leer las fuentes de verdad.
