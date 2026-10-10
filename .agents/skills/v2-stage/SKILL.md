---
name: v2-stage
description: Direct an explicitly invoked Autocrop V2 stage through contract, delegation, review, closure, and next-stage handoff when appropriate.
---

# Dirigir una etapa V2

Usar esta skill solo para una etapa concreta de `.plans/v2/` y el rol pedido por el usuario. Leer `AGENTS.md`, `.plans/v2/PLAN.md`, el contrato y el código pertinente. Mantener `plan.md` como contrato y estado, y `registro.md` como evidencia e historial de revisión.

## Definir

Redactar el contrato de la etapa con los criterios y la validación necesarios para implementarla sin inventar decisiones de producto. Crear el registro con secciones Implementación y Revisión vacías. Presentar el contrato al usuario y esperar su aprobación explícita antes de encargar código. No delegar la implementación de la etapa siguiente en la sesión que cerró la anterior.

Redactar un contrato declarativo: definir el resultado observable y sus restricciones, no una secuencia de pasos de implementación. Precisar interfaz y tipos, entradas válidas e inválidas, salidas y errores observables, límites y casos frontera, invariantes, componentes afectados, exclusiones, criterios de aceptación y comprobación concreta para cada criterio. Resolver antes del traspaso toda ambigüedad que pueda cambiar el comportamiento, para evitar idas y vueltas por decisiones de producto. Dejar al implementador la elección de algoritmo, estructura interna y detalles técnicos que satisfagan el contrato; imponerlos solo cuando sean una restricción necesaria y justificar por qué. Mantener el plan tan breve como permita esa precisión. Si una decisión indispensable sigue abierta, preguntarla en vez de delegar una suposición al implementador.

## Delegar y revisar

Tras la aprobación, el director (modelo frontera indicado por el usuario o predeterminado del repositorio) elige un modelo gratuito y apto entre los disponibles en OpenCode Zen, salvo que el usuario indique expresamente otro implementador. Verifica disponibilidad y coste antes de delegar; registra el modelo y un motivo breve. Si no puede confirmar que un modelo de Zen es gratuito y apto, se detiene y consulta al usuario mediante AskUserTool o la herramienta equivalente de preguntas de la plataforma; no elige por su cuenta un modelo de otro proveedor o de pago. Lanzar obligatoriamente un subagente para coordinar la implementación; el director no implementa la etapa en su sesión principal. Ese subagente invoca OpenCode por CLI con el modelo elegido, espera su resultado y devuelve al director el código de salida y la evidencia. El subagente nativo solo coordina la CLI: no cambia de proveedor por sí mismo y puede consumir algunos tokens del proveedor del director. Si no hay subagentes disponibles, explicar el bloqueo y no sustituir este paso con una invocación directa desde la sesión principal. Ver [invocación de implementadores](references/implementers.md) para el traspaso. Dar al implementador una etapa completa y pedir tests primero, evidencia roja funcional, implementación mínima, suite verde y registro de resultados. Evitar encargos simultáneos que editen los mismos archivos.

El mismo director revisa el diff completo, el contrato frente a los tests, la evidencia y los casos límite. Usar los criterios y comprobaciones del contrato como lista de verificación: para cada uno, anotar evidencia observada o hueco concreto. Registrar cada hallazgo con ubicación, impacto, criterio y corrección esperada. Pedir la regresión antes de cada corrección. Cerrar la etapa solo cuando todos los criterios estén verificados; si falta una comprobación, registrar el bloqueo y mantener `en revisión`.

## Límites

Respetar autorizaciones y permisos del entorno; no usar flags que desactiven controles de aprobación o sandbox. No atribuir al implementador resultados que el director no pueda corroborar. Conservar la evidencia previa al iterar. Informar al usuario del cierre o bloqueo con enlace al plan.

Al terminar el análisis y cierre de una etapa, informar dos porcentajes de confianza del director: uno sobre la primera entrega del implementador, antes de las correcciones de revisión, y otro sobre la etapa final. Basar ambas cifras en la cobertura real de criterios, calidad de las aserciones, ejecución independiente, integración pertinente y riesgos residuales concretos; explicar en una frase qué impide subir la cifra. Informar también el número de entregas, los hallazgos corregidos y las comprobaciones independientes del director para evaluar si el contrato inicial redujo las vueltas. Son estimaciones de juicio, no probabilidades medidas. No añadir dudas genéricas ni prolongar la revisión sin un riesgo o criterio identificable. Si la etapa no puede cerrarse, informar la confianza actual y el bloqueo sin inventar una cifra final.

## Siguiente etapa y nueva sesión

Solo después de cerrar la etapa y verificar todos sus criterios, usar la confianza final como puerta para preparar el siguiente contrato: debe ser mayor al 85 %, o mayor al 90 % si la etapa afecta seguridad, integridad de datos o riesgo de pérdida de archivos. Explicar brevemente si se la considera crítica. El umbral no reemplaza los criterios de cierre. Si no se alcanza, informar el riesgo concreto que limita la confianza y no preparar automáticamente la etapa siguiente; evitar pruebas adicionales sin una hipótesis verificable.

Si se supera el umbral, identificar la siguiente etapa necesaria a partir de `.plans/v2/PLAN.md` y el código existente. Reutilizar un contrato `pendiente` ya redactado cuando corresponda; de lo contrario, crear solo su `plan.md` declarativo y `registro.md` vacío y añadirla al índice V2. Presentar el contrato y pedir su aprobación explícita mediante AskUserTool o la herramienta equivalente de preguntas. Prepararlo no autoriza implementarlo.

Tras la aprobación, entregar al usuario un mensaje breve para pegar en una nueva sesión principal de Codex, con la etapa, enlace al contrato y la indicación de invocar `$v2-stage`. Terminar la sesión actual sin lanzar la siguiente etapa. La nueva sesión vuelve a leer las fuentes de verdad y empieza el ciclo desde cero; un subagente no sustituye esa nueva sesión principal.
