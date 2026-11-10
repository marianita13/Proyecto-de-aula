import time

from fastapi import FastAPI


WORK_ITERATIONS = 100_000
CHECKSUM_MODULUS = 1_000_003

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
