"""Regresiones R9b: math.isfinite(int) desborda con n=2**1100 (F1/F2/F6).

Fase roja previa a la correccion: ambas fallan con OverflowError porque
la validacion convierte enteros arbitrarios a float via math.isfinite.
"""
from __future__ import annotations

from app.crop import calculate_crop

N = 2**1100


def test_r9b_bbox_bigint_mas_alla_de_float():
    assert calculate_crop(N + 2, 2, (N, 0, N + 1, 1), (1, 1), 0) == (N, 0, N + 1, 1)


def test_r9b_margin_bigint_satura():
    assert calculate_crop(10, 10, (4, 4, 6, 6), (1, 1), N) == (0, 0, 10, 10)
