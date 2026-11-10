import math
import time
from typing import Callable, TypedDict

from fastapi import FastAPI


WORK_ITERATIONS = 100_000
CHECKSUM_MODULUS = 1_000_003
DEFAULT_MAX_RESPONSE_TIME = 2.0

app = FastAPI(
    title="API de prueba de carga",
    description="API local para medir el efecto de la concurrencia sobre una tarea acotada.",
    version="0.1.0",
)


def _bounded_cpu_work() -> int:
    checksum = 0
    for value in range(WORK_ITERATIONS):
        checksum = (checksum + (value * 31) % CHECKSUM_MODULUS) % CHECKSUM_MODULUS
    return checksum


def response_time_model(users: float, a: float = 0.00002, b: float = 0.003, c: float = 0.2) -> float:
    """Modelo didáctico de tiempo de respuesta en segundos para x usuarios concurrentes."""
    return a * (users ** 2) + b * users + c


def secant_function(users: float, max_response_time: float = DEFAULT_MAX_RESPONSE_TIME) -> float:
    """Ecuación para encontrar el valor de usuarios cuya respuesta iguala el umbral."""
    return response_time_model(users) - max_response_time


class SecantHistoryEntry(TypedDict):
    x_prev: float
    x_curr: float
    f_x: float


class SecantResult(TypedDict):
    root: float
    iterations: int
    history: list[SecantHistoryEntry]


class CapacityEstimate(TypedDict):
    root: float
    iterations: int
    max_users_under_limit: int


def secant_method(
    f: Callable[[float], float],
    x0: float,
    x1: float,
    *,
    tol: float = 1e-8,
    max_iter: int = 50,
) -> SecantResult:
    """Calcula una raíz de f(x)=0 usando el método de la secante."""
    if tol <= 0:
        raise ValueError("tol debe ser un valor positivo")
    if max_iter <= 0:
        raise ValueError("max_iter debe ser mayor que cero")

    x_prev = float(x0)
    x_curr = float(x1)
    f_prev = float(f(x_prev))
    f_curr = float(f(x_curr))

    history: list[SecantHistoryEntry] = [
        {"x_prev": x_prev, "x_curr": x_curr, "f_x": f_curr},
    ]

    if math.isclose(f_prev, 0.0, abs_tol=tol):
        return {"root": x_prev, "iterations": 0, "history": history}
    if math.isclose(f_curr, 0.0, abs_tol=tol):
        return {"root": x_curr, "iterations": 0, "history": history}
    if math.isclose(f_curr - f_prev, 0.0, abs_tol=tol):
        raise ValueError("La secante no puede evaluarse con un denominador cercano a cero.")

    for iteration in range(1, max_iter + 1):
        x_next = x_curr - (f_curr * (x_curr - x_prev)) / (f_curr - f_prev)
        f_next = float(f(x_next))
        history.append({"x_prev": x_curr, "x_curr": x_next, "f_x": f_next})

        if abs(f_next) < tol or abs(x_next - x_curr) < tol:
            return {"root": x_next, "iterations": iteration, "history": history}

        x_prev, x_curr = x_curr, x_next
        f_prev, f_curr = f_curr, f_next

        if math.isclose(f_curr - f_prev, 0.0, abs_tol=tol):
            raise ValueError("La secante no pudo continuar porque el denominador se volvió cero.")

    raise ValueError(f"No se alcanzó convergencia después de {max_iter} iteraciones.")


def estimate_users_for_limit(
    max_response_time: float = DEFAULT_MAX_RESPONSE_TIME,
    x0: float = 200.0,
    x1: float = 250.0,
    *,
    tol: float = 1e-8,
    max_iter: int = 50,
) -> CapacityEstimate:
    """Estima la cantidad de usuarios concurrentes que alcanza el tiempo máximo permitido."""
    result = secant_method(
        lambda value: secant_function(value, max_response_time=max_response_time),
        x0,
        x1,
        tol=tol,
        max_iter=max_iter,
    )
    root = float(result["root"])
    max_users_under_limit = math.floor(root)
    return {
        "root": root,
        "iterations": int(result["iterations"]),
        "max_users_under_limit": max_users_under_limit,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/work")
def work() -> dict[str, int | float]:
    started_at = time.perf_counter()
    checksum = _bounded_cpu_work()
    elapsed_ms = (time.perf_counter() - started_at) * 1_000
    return {
        "work_iterations": WORK_ITERATIONS,
        "server_time_ms": round(elapsed_ms, 3),
        "checksum": checksum,
    }


@app.get("/secant-demo")
def secant_demo() -> dict[str, float | int | dict[str, float | str]]:
    estimate = estimate_users_for_limit()
    return {
        "max_response_time_s": DEFAULT_MAX_RESPONSE_TIME,
        "model": {
            "expression": "T(x) = 0.00002x^2 + 0.003x + 0.2",
            "root": estimate["root"],
        },
        "estimated_users": estimate["max_users_under_limit"],
    }
