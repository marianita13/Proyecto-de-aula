from __future__ import annotations

import math
from collections.abc import Callable
from typing import TypedDict


class SecantIteration(TypedDict):
    iteration: int
    x_prev: float
    x_curr: float
    f_x: float
    approximate_error_pct: float


class SecantResult(TypedDict):
    root: float
    iterations: int
    approximate_error_pct: float
    history: list[SecantIteration]


def secant_method(
    function: Callable[[float], float],
    x0: float,
    x1: float,
    *,
    tolerance_percent: float = 0.05,
    max_iterations: int = 50,
) -> SecantResult:
    """Approximate a root until relative approximate error is within tolerance_percent."""
    if not math.isfinite(tolerance_percent) or tolerance_percent <= 0:
        raise ValueError("La tolerancia porcentual debe ser positiva y finita.")
    if max_iterations <= 0:
        raise ValueError("El máximo de iteraciones debe ser mayor que cero.")
    if not math.isfinite(x0) or not math.isfinite(x1):
        raise ValueError("Las aproximaciones iniciales deben ser finitas.")
    if x0 == x1:
        raise ValueError("Las aproximaciones iniciales x0 y x1 deben ser distintas.")

    x_prev = float(x0)
    x_curr = float(x1)
    f_prev = float(function(x_prev))
    f_curr = float(function(x_curr))
    if not math.isfinite(f_prev) or not math.isfinite(f_curr):
        raise ValueError("La función produjo un valor no finito en las aproximaciones iniciales.")

    if f_prev == 0.0:
        return {
            "root": x_prev,
            "iterations": 0,
            "approximate_error_pct": 0.0,
            "history": [],
        }
    if f_curr == 0.0:
        return {
            "root": x_curr,
            "iterations": 0,
            "approximate_error_pct": 0.0,
            "history": [],
        }

    history: list[SecantIteration] = []
    approximate_error_pct = math.inf

    for iteration in range(1, max_iterations + 1):
        denominator = f_curr - f_prev
        if not math.isfinite(denominator) or denominator == 0.0:
            raise ValueError("La secante no puede continuar: el denominador es cero o no finito.")

        x_next = x_curr - f_curr * (x_curr - x_prev) / denominator
        if not math.isfinite(x_next):
            raise ValueError("La secante produjo una aproximación no finita.")
        f_next = float(function(x_next))
        if not math.isfinite(f_next):
            raise ValueError("La función produjo un valor no finito durante la iteración.")

        approximate_error_pct = (
            0.0
            if f_next == 0.0
            else math.inf
            if x_next == 0.0
            else abs((x_next - x_curr) / x_next) * 100
        )
        history.append(
            {
                "iteration": iteration,
                "x_prev": x_curr,
                "x_curr": x_next,
                "f_x": f_next,
                "approximate_error_pct": approximate_error_pct,
            }
        )

        if approximate_error_pct <= tolerance_percent:
            return {
                "root": x_next,
                "iterations": iteration,
                "approximate_error_pct": approximate_error_pct,
                "history": history,
            }

        x_prev, x_curr = x_curr, x_next
        f_prev, f_curr = f_curr, f_next

    raise ValueError(
        f"No se alcanzó el error aproximado de {tolerance_percent:g}% "
        f"después de {max_iterations} iteraciones."
    )
