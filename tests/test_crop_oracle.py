"""Oraculo independiente de posicion y tamanos (etapa 01, F1-F5, decision 5).

Independencia respecto de ``app/crop.py``:

- Tamanos por barrido ``k=1..max_k`` (sin ``ceil``): el menor ``k`` que
  contiene la envolvente y alcanza los objetivos de margen exactos
  (``Fraction``) es el deseado; si ninguno lo logra se satura a ``max_k``
  y se devuelve ``None`` si ese tamano no contiene la envolvente
  (decision 4). ``max_k`` tambien se obtiene por enumeracion.
- Posicion SIN floor ni clamp: se enumeran TODOS los origenes enteros
  factibles de cada eje (recorte dentro de la imagen E inclusion exacta
  de la caja original via ``Fraction``) y se elige el MAYOR origen no
  superior al ideal; si ninguno existe, el minimo factible (decision 5).
  Sin cercania absoluta, sin ``floor``, sin ``//`` y sin mediana/clamp
  sobre el ideal para posicion.
- Los unicos ``//`` del archivo reducen la proporcion por ``gcd``
  (division exacta, no posicion) y ``math.floor/ceil`` solo define la
  envolvente entera (decision 2, no posicion).

Los casos bigint (2**1100) se verifican directos, sin barrer
dimensiones gigantes.
"""
from __future__ import annotations

import fractions
import math
import random

from app.crop import calculate_crop

F = fractions.Fraction


def _oracle(W, H, bbox, ar, margin):
    l, t, r, b = bbox
    # Reduccion exacta p:q (gcd divide exacto; unico uso de //, no posicion).
    g = math.gcd(ar[0], ar[1])
    p, q = ar[0] // g, ar[1] // g
    # Envolvente entera (decision 2).
    ex0 = l if isinstance(l, int) else math.floor(l)
    ey0 = t if isinstance(t, int) else math.floor(t)
    ex1 = r if isinstance(r, int) else math.ceil(r)
    ey1 = b if isinstance(b, int) else math.ceil(b)
    sw, sh = ex1 - ex0, ey1 - ey0
    # max_k por enumeracion: mayor k con (k*p, k*q) dentro de la imagen.
    max_k = 0
    for cand in range(1, min(W, H) + 1):
        if cand * p <= W and cand * q <= H:
            max_k = cand
    if max_k < 1:
        return None
    # Objetivos de margen exactos sobre la caja original (decision 3).
    tw = (F(r) - F(l)) * (1 + 2 * F(margin))
    th = (F(b) - F(t)) * (1 + 2 * F(margin))
    # Menor k factible que contiene envolvente y alcanza margen.
    chosen = None
    for cand in range(1, max_k + 1):
        if cand * p >= sw and cand * q >= sh and F(cand * p) >= tw and F(cand * q) >= th:
            chosen = cand
            break
    if chosen is None:  # saturacion: reducir margen (decision 4).
        chosen = max_k
        if chosen * p < sw or chosen * q < sh:
            return None
    cw, ch = chosen * p, chosen * q
    # Origenes factibles por enumeracion exhaustiva (sin formula de intervalo).
    ideal_x = (F(l) + F(r)) / 2 - F(cw, 2)
    feas_x = [o for o in range(0, W - cw + 1) if F(o) <= F(l) and F(o + cw) >= F(r)]
    if not feas_x:
        return None
    le_x = [o for o in feas_x if F(o) <= ideal_x]
    ox = le_x[-1] if le_x else feas_x[0]
    ideal_y = (F(t) + F(b)) / 2 - F(ch, 2)
    feas_y = [o for o in range(0, H - ch + 1) if F(o) <= F(t) and F(o + ch) >= F(b)]
    if not feas_y:
        return None
    le_y = [o for o in feas_y if F(o) <= ideal_y]
    oy = le_y[-1] if le_y else feas_y[0]
    return (ox, oy, ox + cw, oy + ch)


def _check_f1(W, H, bbox, ar, res):
    assert res is not None
    assert isinstance(res, tuple) and len(res) == 4
    assert all(type(v) is int for v in res)
    gl, gt, gr, gb = res
    assert 0 <= gl < gr <= W and 0 <= gt < gb <= H
    assert gl <= math.floor(bbox[0]) and gt <= math.floor(bbox[1])
    assert gr >= math.ceil(bbox[2]) and gb >= math.ceil(bbox[3])
    g = math.gcd(ar[0], ar[1])
    assert (gr - gl) * (ar[1] // g) == (gb - gt) * (ar[0] // g)


def test_oraculo_tabla_plan():
    casos = [
        (1000, 800, (400, 300, 600, 500), (1, 1), 0.15, (370, 270, 630, 530)),
        (1000, 800, (0, 300, 200, 500), (1, 1), 0.15, (0, 270, 260, 530)),
        (1000, 800, (800, 300, 1000, 500), (1, 1), 0.15, (740, 270, 1000, 530)),
        (1000, 800, (400, 0, 600, 200), (1, 1), 0.15, (370, 0, 630, 260)),
        (1000, 800, (400, 600, 600, 800), (1, 1), 0.15, (370, 540, 630, 800)),
        (1000, 800, (100, 100, 900, 700), (3, 2), 0.5, (0, 67, 999, 733)),
        (600, 1000, (100, 50, 500, 950), (3, 2), 0.0, None),
        (10, 10, (4.2, 4.2, 5.8, 5.8), (1, 1), 0.0, (4, 4, 6, 6)),
    ]
    for W, H, bb, ar, m, exp in casos:
        assert calculate_crop(W, H, bb, ar, m) == exp
        assert _oracle(W, H, bb, ar, m) == exp


def test_oraculo_exhaustivo_enteros():
    ars = [(1, 1), (3, 2), (2, 3)]
    for W, H in [(5, 5), (6, 4), (4, 6), (7, 5)]:
        for l in range(0, W - 1):
            for r in range(l + 1, W + 1):
                for tt in range(0, H - 1):
                    for bb in range(tt + 1, H + 1):
                        for ar in ars:
                            for m in [0, 0.15]:
                                got = calculate_crop(W, H, (l, tt, r, bb), ar, m)
                                assert got == _oracle(W, H, (l, tt, r, bb), ar, m)
                                if got is not None:
                                    _check_f1(W, H, (l, tt, r, bb), ar, got)


def test_oraculo_fraccionarios_semilla():
    rng = random.Random(7)
    for _ in range(500):
        W = rng.randint(5, 30)
        H = rng.randint(5, 30)
        l = rng.uniform(0, W - 1)
        r = rng.uniform(l + 0.05, W)
        tt = rng.uniform(0, H - 1)
        b = rng.uniform(tt + 0.05, H)
        ar = rng.choice([(1, 1), (4, 5), (3, 2), (2, 3), (16, 9)])
        m = rng.choice([0, 0.1, 0.15, 0.5, 2.0])
        got = calculate_crop(W, H, (l, tt, r, b), ar, m)
        assert got == _oracle(W, H, (l, tt, r, b), ar, m)
        if got is not None:
            _check_f1(W, H, (l, tt, r, b), ar, got)


def test_oraculo_empate_medio_pixel():
    # Centro (5,5), crop 3x3 -> ideal 3.5; empate -> mayor origen <= ideal = 3.
    assert calculate_crop(10, 10, (4, 4, 6, 6), (1, 1), 0.25) == (3, 3, 6, 6)
    assert _oracle(10, 10, (4, 4, 6, 6), (1, 1), 0.25) == (3, 3, 6, 6)


def test_oraculo_bigint_directo_sin_barrido():
    # Sin enumeracion: dimensiones gigantes no se barren; solo el contrato.
    n = 2**1100
    assert calculate_crop(n + 2, 2, (n, 0, n + 1, 1), (1, 1), 0) == (n, 0, n + 1, 1)
    assert calculate_crop(10, 10, (4, 4, 6, 6), (1, 1), n) == (0, 0, 10, 10)
