# Trabajo en este repositorio

## Objetivo y fuentes de verdad

Construir por etapas Autocrop. El [índice de versiones](PLAN.md) distingue la CLI V1 de la web local V2.

- `PLAN.md`: índice de versiones. `.plans/v1/PLAN.md` conserva el contrato histórico; `.plans/v2/PLAN.md` contiene las decisiones compartidas de V2.
- `.plans/vN/NN-nombre/`: carpeta de una etapa. `plan.md`: contrato, criterios de aceptación y estado. `registro.md`: evidencia de ejecución y revisión. La numeración reinicia en cada versión.
- `AGENTS.md`: dinámica de trabajo e instrucciones comunes a todos los agentes.
- `README.md`: instalación y uso cuando exista una implementación ejecutable; no duplicar los planes.
- `.agents/skills/v2-stage/SKILL.md`: flujo portable para dirigir una etapa V2, invocado explícitamente por el usuario.

Antes de trabajar, leer este archivo, el plan de la versión y etapa asignadas y el código relacionado. Respetar las instrucciones explícitas del usuario. Resolver las contradicciones entre documentos antes de implementar el comportamiento afectado. No cambiar estados ni evidencia de V1 al desarrollar V2; la etapa V1-07 sigue en revisión hasta probar Mac Apple Silicon.

## Roles acordados

- El **director** define cada etapa y sus criterios técnicos y funcionales; por defecto, un modelo OpenAI Astra con razonamiento high.
- El **implementador** escribe primero la suite de tests y después implementa el contrato; por defecto, OpenCode Muse.
- El mismo **director** revisa tests e implementación y registra hallazgos. El implementador corrige y el director vuelve a revisar hasta cerrar la etapa.

Los roles son intercambiables por indicación del usuario: Claude puede dirigir y Codex Luna puede implementar. La skill V2 se invoca explícitamente para una etapa; el director usa la CLI o herramienta disponible para encargar trabajo a otro agente. No asumir que un subagente nativo de una plataforma puede ejecutar un proveedor distinto. El usuario aprueba el contrato de cada etapa V2 antes de delegar implementación; después, el director gestiona las revisiones y correcciones de esa etapa.

## Ciclo de una etapa

1. **Definir (director).** Crear `.plans/vN/NN-nombre/plan.md` con objetivo, alcance, exclusiones, contratos, decisiones, criterios funcionales y técnicos y validación, y `registro.md` vacío. Resolver las decisiones necesarias antes de delegar. En V2, esperar la aprobación explícita del usuario sobre el contrato. Definir las siguientes etapas cuando corresponda, sin desarrollar por adelantado todo el producto.
2. **Preparar (implementador).** Leer el contrato aprobado y marcar `en implementación` en `plan.md`. Si una ambigüedad cambia el comportamiento, devolverla al director antes de implementar esa parte.
3. **Tests primero (implementador).** Escribir la suite unitaria de la etapa antes de la lógica de producción. Se permite la estructura mínima y una función vacía que lance `NotImplementedError` para que los tests puedan importar y ejecutar. Confirmar fallos por funcionalidad pendiente: un fallo de instalación o importación no basta.
4. **Implementar (implementador).** Escribir la solución mínima que cumpla el contrato y haga pasar los tests. Ejecutar los tests de la etapa y la suite existente. No debilitar, eliminar, omitir ni marcar como esperados los fallos para acomodar una implementación incorrecta. Si un test interpreta mal el contrato, corregirlo y documentar el motivo para revisión.
5. **Entregar (implementador).** Registrar en la sección Implementación de `registro.md` los archivos modificados, comandos y resultados reales, criterios cubiertos y pendientes. Marcar `en revisión` en `plan.md`; no autodeclarar la etapa completada.
6. **Revisar (director).** Inspeccionar diff completo, correspondencia entre contrato y tests, calidad de aserciones, casos límite, funcionamiento y complejidad innecesaria. Ejecutar las comprobaciones necesarias; tests verdes por sí solos no aprueban la etapa. Cada hallazgo debe incluir ubicación, impacto, criterio afectado y corrección esperada, registrado en la sección Revisión de `registro.md`.
7. **Iterar y cerrar.** Con hallazgos, volver a `en implementación`. El implementador agrega el test de regresión pertinente antes de corregir un defecto y entrega nuevamente. El director revisa lo afectado y marca `completada` en `plan.md` cuando todos los criterios están verificados y no quedan hallazgos pendientes.

Si el entorno impide verificar algo, registrar comando, bloqueo y comprobación pendiente; no inventar resultados ni marcar la etapa completada. No implementar automáticamente la siguiente etapa.

## Formato de cada etapa

`.plans/vN/NN-nombre/plan.md`:

- Título, estado (`pendiente`, `en implementación`, `en revisión`, `completada`) y dependencias.
- Objetivo, alcance y exclusiones.
- Contratos y decisiones suficientes para implementar sin inventar reglas de producto.
- Criterios funcionales `F1`, `F2`, etc., y técnicos `T1`, `T2`, etc.
- Casos de prueba y procedimiento de validación vinculados a los criterios.

`.plans/vN/NN-nombre/registro.md`:

- Sección Implementación: comandos y resultados reales, criterios cubiertos y pendientes.
- Sección Revisión: hallazgos, correcciones y cierre.
- Ambas secciones empiezan sin resultados.

Los criterios funcionales describen resultados observables; los técnicos, propiedades de la solución. Cuando se necesiten fotos reales, agregar validación visual además de tests unitarios. Registrar hallazgos y resoluciones en `registro.md`, sin otro sistema de tickets.

## Reglas de implementación y documentación

- Funciones pequeñas, type hints y comportamiento determinista. Reutilizar código y biblioteca estándar antes de agregar dependencias.
- Separar detección, selección, matemática y lectura/escritura. Probar la matemática sin YOLO, red ni fotografías.
- Usar `pytest`. Probar contratos y resultados; evitar tests que repitan el algoritmo de producción o dependan de helpers privados.
- Crear y usar `.venv` para instalar dependencias y ejecutar tests; no instalar dependencias del proyecto globalmente.
- No implementar funciones fuera de la etapa, abstracciones hipotéticas ni fases futuras.
- Nunca modificar imágenes originales; documentar los casos que requieren revisión.
- Las decisiones compartidas van al `PLAN.md` de la versión; las específicas, al plan de etapa. La implementación no cambia por sí sola el contrato.
- Al entregar, informar brevemente qué cambió, qué se verificó y qué queda pendiente, con enlace al plan.
