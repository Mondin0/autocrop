# Trabajo en este repositorio

## Objetivo y fuentes de verdad

Construir por etapas el MVP local de recorte de fotografías deportivas descrito en `PLAN.md`.

- `PLAN.md`: alcance del producto, decisiones compartidas e índice de etapas.
- `plans/NN-nombre/`: carpeta de una etapa. `plan.md`: contrato, criterios de aceptación y estado. `registro.md`: evidencia de ejecución y revisión.
- `AGENTS.md`: dinámica de trabajo e instrucciones comunes a todos los agentes.
- `README.md`: instalación y uso cuando exista una implementación ejecutable; no duplicar los planes.

Antes de trabajar, leer este archivo, `PLAN.md`, el plan asignado y el código relacionado. Respetar las instrucciones explícitas del usuario. Resolver las contradicciones entre documentos antes de implementar el comportamiento afectado.

## Roles acordados

- **Astra con razonamiento high** define cada etapa y sus criterios de aceptación técnicos y funcionales.
- **Muse** escribe primero la suite de tests unitarios y después implementa el contrato.
- **Astra** revisa tests e implementación y registra hallazgos. Muse corrige y Astra vuelve a revisar hasta cerrar la etapa.

Estos roles describen el intercambio acordado con el usuario; no ordenan lanzar agentes ni cambiar modelos automáticamente. Cada sesión trabaja en el rol y etapa asignados.

## Ciclo de una etapa

1. **Definir (Astra).** Crear `plans/NN-nombre/plan.md` con objetivo, alcance, exclusiones, contratos, decisiones, criterios funcionales y técnicos y validación, y `registro.md` vacío. Resolver las decisiones necesarias antes de delegar. Definir las siguientes etapas cuando corresponda, sin desarrollar por adelantado todo el producto.
2. **Preparar (Muse).** Leer el contrato y marcar `en implementación` en `plan.md`. Si una ambigüedad cambia el comportamiento, devolverla a Astra antes de implementar esa parte.
3. **Tests primero (Muse).** Escribir la suite unitaria de la etapa antes de la lógica de producción. Se permite la estructura mínima y una función vacía que lance `NotImplementedError` para que los tests puedan importar y ejecutar. Confirmar fallos por funcionalidad pendiente: un fallo de instalación o importación no basta.
4. **Implementar (Muse).** Escribir la solución mínima que cumpla el contrato y haga pasar los tests. Ejecutar los tests de la etapa y la suite existente. No debilitar, eliminar, omitir ni marcar como esperados los fallos para acomodar una implementación incorrecta. Si un test interpreta mal el contrato, corregirlo y documentar el motivo para revisión.
5. **Entregar (Muse).** Registrar en la sección Implementación de `registro.md` los archivos modificados, comandos y resultados reales, criterios cubiertos y pendientes. Marcar `en revisión` en `plan.md`; no autodeclarar la etapa completada.
6. **Revisar (Astra).** Inspeccionar diff completo, correspondencia entre contrato y tests, calidad de aserciones, casos límite, funcionamiento y complejidad innecesaria. Ejecutar las comprobaciones necesarias; tests verdes por sí solos no aprueban la etapa. Cada hallazgo debe incluir ubicación, impacto, criterio afectado y corrección esperada, registrado en la sección Revisión de `registro.md`.
7. **Iterar y cerrar.** Con hallazgos, volver a `en implementación`. Muse agrega el test de regresión pertinente antes de corregir un defecto y entrega nuevamente. Astra revisa lo afectado y marca `completada` en `plan.md` cuando todos los criterios están verificados y no quedan hallazgos pendientes.

Si el entorno impide verificar algo, registrar comando, bloqueo y comprobación pendiente; no inventar resultados ni marcar la etapa completada. No implementar automáticamente la siguiente etapa.

## Formato de cada etapa

`plans/NN-nombre/plan.md`:

- Título, estado (`pendiente`, `en implementación`, `en revisión`, `completada`) y dependencias.
- Objetivo, alcance y exclusiones.
- Contratos y decisiones suficientes para implementar sin inventar reglas de producto.
- Criterios funcionales `F1`, `F2`, etc., y técnicos `T1`, `T2`, etc.
- Casos de prueba y procedimiento de validación vinculados a los criterios.

`plans/NN-nombre/registro.md`:

- Sección Implementación (Big Pickle): comandos y resultados reales, criterios cubiertos y pendientes.
- Sección Revisión (Astra): hallazgos, correcciones y cierre.
- Ambas secciones empiezan sin resultados.

Los criterios funcionales describen resultados observables; los técnicos, propiedades de la solución. Cuando se necesiten fotos reales, agregar validación visual además de tests unitarios. Registrar hallazgos y resoluciones en `registro.md`, sin otro sistema de tickets.

## Reglas de implementación y documentación

- Funciones pequeñas, type hints y comportamiento determinista. Reutilizar código y biblioteca estándar antes de agregar dependencias.
- Separar detección, selección, matemática y lectura/escritura. Probar la matemática sin YOLO, red ni fotografías.
- Usar `pytest`. Probar contratos y resultados; evitar tests que repitan el algoritmo de producción o dependan de helpers privados.
- Crear y usar `.venv` para instalar dependencias y ejecutar tests; no instalar dependencias del proyecto globalmente.
- No implementar funciones fuera de la etapa, abstracciones hipotéticas ni fases futuras.
- Nunca modificar imágenes originales; documentar los casos que requieren revisión.
- Las decisiones compartidas van a `PLAN.md`; las específicas, al plan de etapa. La implementación no cambia por sí sola el contrato.
- Al entregar, informar brevemente qué cambió, qué se verificó y qué queda pendiente, con enlace al plan.
