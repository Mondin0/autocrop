"""Regresiones R9: precision exacta con enteros arbitrarios (F1/F2/F6).

No limita el contrato por tamano de entero; la aritmetica debe ser exacta
sin colapsar enteros distintos via float(). Fase roja previa a la correccion.
"""
from __future__ import annotations

from app.crop import calculate_crop

N = 2**53


def test_r9_grande_ejemplo_coordinador():
    # (n,0,n+1,1) con 1:1 y margen 0 debe dar (n,0,n+1,1), no ValueError.
    assert calculate_crop(N + 2, 2, (N, 0, N + 1, 1), (1, 1), 0) == (N, 0, N + 1, 1)


def test_r9_enteros_mas_alla_de_float_range():
    w = 2**310
    assert calculate_crop(w, 2, (w - 2, 0, w - 1, 1), (1, 1), 0) == (w - 2, 0, w - 1, 1)


def test_r9_margen_int_grande_centrado():
    # caja 10x10 con margen int 3 -> objetivo 70x70, k=70, centrado exacto.
    assert calculate_crop(100, 100, (40, 40, 50, 50), (1, 1), 3) == (10, 10, 80, 80)


def test_r9_proporcion_grande_int():
    # p,q enteros grandes equivalentes a 3:2; mismo resultado que (3,2).
    r1 = calculate_crop(100, 100, (40, 40, 60, 60), (3, 2), 0.0)
    r2 = calculate_crop(100, 100, (40, 40, 60, 60), (3 * 10**30, 2 * 10**30), 0.0)
    assert r1 == (35, 40, 65, 60)
    assert r2 == r1


def test_r9_centro_enteros_grandes_asimetrico():
    # n impar: centro en n+0.5, crop 2x2 -> ideal n-0.5, empate -> origen menor.
    n = 2**53 + 1
    res = calculate_crop(n + 2, 4, (n, 0, n + 1, 2), (1, 1), 0)
    assert res == (n - 1, 0, n + 1, 2)


def test_r9_mixto_int_grande_float_pequeno():
    # n+0.25/n+1.5 ya llegan como float(n)/float(n+2) (precision del llamante);
    # sobre esos valores recibidos el calculo es exacto; empate -> origen menor.
    n = 2**53
    res = calculate_crop(n + 4, 4, (n + 0.25, 0.25, n + 1.5, 2.75), (1, 1), 0)
    assert res == (n - 1, 0, n + 2, 3)
