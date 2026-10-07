# Etapa 01 — Matemática del recorte

Estado: completada

Dependencias: ninguna. Implementación: Muse. Revisión: Astra.

## Objetivo y alcance

Crear la base mínima de Python 3.12+ y una función pura que calcule un recorte con proporción fija, incluya al sujeto completo y permanezca dentro de la imagen. Escribir los tests unitarios antes de implementar la lógica, según [AGENTS.md](../../AGENTS.md).

Entregables: `app/__init__.py`, `app/crop.py`, `tests/test_crop.py`, `pyproject.toml` y un `README.md` con instalación y ejecución de tests. En esta etapa, la producción de `app/crop.py` usa solamente biblioteca estándar (la restricción no aplica a etapas posteriores); `pytest` es dependencia de desarrollo. No crear otros módulos vacíos.

Fuera de alcance: YOLO, selección del sujeto, lectura/escritura de imágenes, orientación EXIF, proporción automática, CLI, carpetas de revisión y optimización de lotes. La función recibe dimensiones ya orientadas y una proporción explícita; etapas posteriores resolverán orientación y salida.

## Contrato público

```python
def calculate_crop(
    image_width: int,
    image_height: int,
    subject_bbox: tuple[float, float, float, float],
    aspect_ratio: tuple[int, int],
    margin: float,
) -> tuple[int, int, int, int] | None:
    ...
```

- Dimensiones: enteros positivos. Caja: tupla de cuatro números finitos `(left, top, right, bottom)` con `0 <= left < right <= image_width` y `0 <= top < bottom <= image_height`. Aceptar coordenadas enteras y fraccionarias.
- Proporción: tupla de dos enteros positivos `(ancho, alto)`. Reducir por máximo común divisor; pares equivalentes producen el mismo resultado.
- Margen: número finito no negativo. `0.15` agrega un 15 % del ancho de la caja a cada lado y un 15 % del alto arriba y abajo; se calcula sobre la caja original.
- Entradas fuera de estos tipos, longitudes o límites producen `ValueError`. Los booleanos no son entradas numéricas válidas. No corregir cajas inválidas silenciosamente.
- Resultado: coordenadas enteras con extremos derecho e inferior exclusivos; ancho `right-left`, alto `bottom-top`.
- Devolver `None` cuando las entradas son válidas pero no existe un recorte entero que respete la proporción e incluya toda la caja. No cortar parcialmente al sujeto.

## Decisiones de geometría

1. **Proporción exacta:** para el par reducido `p:q`, los tamaños válidos son `(k*p, k*q)` con `k` entero positivo. Puede agregarse espacio por cuantización; no se usan tolerancias de proporción.
2. **Tamaño mínimo:** obtener la caja envolvente entera redondeando izquierda/arriba hacia abajo y derecha/abajo hacia arriba. Elegir el menor tamaño válido que pueda contenerla.
3. **Margen:** el tamaño deseado es el menor tamaño válido que también alcance ancho y alto de la caja original multiplicados por `1 + 2*margin`.
4. **Si no cabe:** limitar el tamaño deseado al mayor tamaño válido que entra en la imagen. Si ese tamaño no contiene la envolvente del sujeto, devolver `None`. Esto reduce el margen antes de considerar imposible el recorte.
5. **Posición:** usar el centro de la caja original. En cada eje, redondear hacia abajo el origen ideal y limitarlo al intervalo de orígenes enteros que mantiene el recorte dentro de la imagen y la caja completa dentro del recorte. En empates de medio píxel, elegir el origen menor.

El desplazamiento cerca de bordes puede dejar márgenes asimétricos. El margen es una petición; incluir al sujeto y respetar límites y proporción es obligatorio. Esta función solo calcula coordenadas.

## Criterios de aceptación funcionales

- **F1:** todo resultado distinto de `None` tiene área positiva, coordenadas enteras dentro de la imagen, contiene toda la caja y cumple `(right-left)*q == (bottom-top)*p`.
- **F2:** usar el menor tamaño que satisface caja, margen y proporción cuando cabe, centrado según la regla anterior. Con margen cero, agregar espacio solo por proporción y cuantización.
- **F3:** desplazar correctamente en los cuatro bordes y esquinas, sin excluir al sujeto.
- **F4:** reducir el margen si es necesario; devolver `None` cuando no cabe el sujeto completo con la proporción pedida.
- **F5:** soportar imágenes horizontales, verticales y cuadradas; proporciones `1:1`, `4:5`, `3:2`, `2:3`, `16:9` y pares equivalentes.
- **F6:** entradas inválidas producen `ValueError`, distinguiéndolas de una imposibilidad geométrica (`None`).

## Criterios de aceptación técnicos

- **T1:** función pura, sin I/O, red, estado mutable global ni dependencias de imágenes o detección.
- **T2:** type hints y docstring del contrato; cálculo directo con biblioteca estándar, sin recorrer píxeles ni todos los tamaños posibles.
- **T3:** suite escrita antes de la lógica; registrar una ejecución fallida por funcionalidad pendiente y otra satisfactoria después. Los tests verifican contratos, sin replicar el algoritmo ni depender de helpers privados.
- **T4:** documentar Python 3.12+, entorno virtual, instalación de dependencias de desarrollo y `python -m pytest`. Resultados deterministas.

## Tests y validación

Big Pickle escribe la suite completa de esta etapa antes de implementar la lógica. Relacionar grupos de tests con IDs de criterios mediante nombres o comentarios breves; parametrizar cuando mejore la claridad.

Ejemplos con resultados calculados de antemano:

| Imagen | Caja | Proporción | Margen | Resultado | Criterios |
|---|---|---|---|---|---|
| 1000 × 800 | (400, 300, 600, 500) | 1:1 | 0.15 | (370, 270, 630, 530) | F1, F2 |
| 1000 × 800 | (0, 300, 200, 500) | 1:1 | 0.15 | (0, 270, 260, 530) | F3 |
| 1000 × 800 | (800, 300, 1000, 500) | 1:1 | 0.15 | (740, 270, 1000, 530) | F3 |
| 1000 × 800 | (400, 0, 600, 200) | 1:1 | 0.15 | (370, 0, 630, 260) | F3 |
| 1000 × 800 | (400, 600, 600, 800) | 1:1 | 0.15 | (370, 540, 630, 800) | F3 |
| 1000 × 800 | (100, 100, 900, 700) | 3:2 | 0.5 | (0, 67, 999, 733) | F4 |
| 600 × 1000 | (100, 50, 500, 950) | 3:2 | 0 | None | F4, F5 |
| 10 × 10 | (4.2, 4.2, 5.8, 5.8) | 1:1 | 0 | (4, 4, 6, 6) | F1, F2 |

Cubrir además:

- Sujeto pequeño, grande, pegado a una esquina y ocupando toda la imagen; casos viables e incompatibles con la proporción (F1–F4).
- Matriz pequeña de orientaciones y proporciones, comprobando límites, inclusión y proporción exacta de cada resultado válido (F1, F5).
- Proporciones equivalentes `(3, 2)` y `(6, 4)`, imagen demasiado pequeña para un tamaño permitido, centrado con empate de medio píxel y llamadas repetidas (F2, F4, F5, T4).
- Dimensiones cero/negativas/no enteras, cajas vacías/invertidas/fuera de límites, tuplas de longitud incorrecta, proporción inválida, margen negativo, booleanos y números no finitos (F6).

Ejecutar `python -m pytest` desde la raíz. No se necesitan fotos reales en esta etapa. Astra revisa tests, implementación y evidencia de ejecución antes de cerrarla.

## Validación

La evidencia de ejecución y revisión se registra en [registro.md](registro.md), inicialmente sin resultados.
