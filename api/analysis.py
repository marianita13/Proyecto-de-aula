from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from api.secant import SecantIteration, SecantResult, secant_method


SUMMARY_COLUMNS = [
    "scenario",
    "vus",
    "requests",
    "average_s",
    "min_s",
    "max_s",
    "p95_s",
    "failure_rate_pct",
]
REQUIRED_K6_COLUMNS = {"metric_name", "metric_value", "scenario"}


class AnalysisError(ValueError):
    """Error de datos o de cálculo que impide una estimación válida."""


@dataclass(frozen=True)
class K6Measurements:
    measurements: pd.DataFrame
    invalid_scenarios: tuple[str, ...]


@dataclass(frozen=True)
class QuadraticModel:
    a: float
    b: float
    c: float
    r_squared: float
    min_users: float
    max_users: float
    valid_levels: int
    warnings: tuple[str, ...]

    def predict(self, users: float) -> float:
        return self.a * users**2 + self.b * users + self.c

    @property
    def equation(self) -> str:
        return f"T(x) = {self.a:.8g}x² + {self.b:.8g}x + {self.c:.8g}"


@dataclass(frozen=True)
class CapacityEstimate:
    x0: float
    x1: float
    root: float
    estimated_response_s: float
    safe_users: int
    iterations: int
    approximate_error_pct: float
    tolerance_percent: float
    max_iterations: int
    history: list[SecantIteration]


def load_k6_csv(path: str | Path) -> K6Measurements:
    """Agrupa las métricas crudas de `k6 run --out csv=...` por escenario."""
    csv_path = Path(path)
    if not csv_path.is_file():
        raise AnalysisError(f"No se encontró el CSV de k6: {csv_path}")

    try:
        raw = pd.read_csv(csv_path)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise AnalysisError(f"No se pudo leer el CSV de k6: {exc}") from exc

    missing = REQUIRED_K6_COLUMNS.difference(raw.columns)
    if missing:
        raise AnalysisError(
            "El archivo no tiene el formato crudo de k6; faltan columnas: "
            + ", ".join(sorted(missing))
        )

    scenarios = raw["scenario"].astype("string")
    level_numbers = scenarios.str.extract(r"^level_(\d+)$", expand=False)
    selected = raw.loc[level_numbers.notna()].copy()
    selected["vus"] = pd.to_numeric(level_numbers.loc[level_numbers.notna()], errors="coerce")
    selected["metric_value"] = pd.to_numeric(selected["metric_value"], errors="coerce")

    valid_records: list[dict[str, str | int | float]] = []
    invalid_scenarios: list[str] = []

    for scenario, group in selected.groupby("scenario", sort=True, dropna=True):
        vus = int(group["vus"].iloc[0])
        request_values = group.loc[group["metric_name"].eq("http_reqs"), "metric_value"]
        duration_values = group.loc[
            group["metric_name"].eq("http_req_duration"), "metric_value"
        ]
        failure_values = group.loc[
            group["metric_name"].eq("http_req_failed"), "metric_value"
        ]

        requests = request_values.to_numpy(dtype=float)
        durations_ms = duration_values.to_numpy(dtype=float)
        failures = failure_values.to_numpy(dtype=float)

        valid_requests = (
            len(requests) > 0
            and np.isfinite(requests).all()
            and (requests > 0).all()
            and np.isclose(requests.sum(), round(float(requests.sum())))
        )
        valid_durations = (
            len(durations_ms) > 0
            and np.isfinite(durations_ms).all()
            and (durations_ms > 0).all()
        )
        valid_failures = (
            len(failures) > 0
            and np.isfinite(failures).all()
            and ((failures == 0) | (failures == 1)).all()
        )
        request_count = int(round(float(requests.sum()))) if valid_requests else 0

        if (
            vus <= 0
            or not valid_requests
            or not valid_durations
            or not valid_failures
            or request_count != len(durations_ms)
            or request_count != len(failures)
        ):
            invalid_scenarios.append(
                f"{scenario}: filas de solicitudes, duraciones o errores incompletas/inválidas"
            )
            continue

        valid_records.append(
            {
                "scenario": str(scenario),
                "vus": vus,
                "requests": request_count,
                "average_s": float(durations_ms.mean() / 1_000),
                "min_s": float(durations_ms.min() / 1_000),
                "max_s": float(durations_ms.max() / 1_000),
                "p95_s": float(np.quantile(durations_ms, 0.95) / 1_000),
                "failure_rate_pct": float(failures.mean() * 100),
            }
        )

    measurements = pd.DataFrame(valid_records, columns=SUMMARY_COLUMNS)
    if not measurements.empty:
        measurements = measurements.sort_values("vus").reset_index(drop=True)
    return K6Measurements(measurements, tuple(invalid_scenarios))


def fit_quadratic_model(
    measurements: pd.DataFrame,
    *,
    poor_fit_threshold: float = 0.9,
) -> QuadraticModel:
    """Ajusta T(x)=ax²+bx+c a niveles medidos válidos usando mínimos cuadrados."""
    required = {"vus", "p95_s"}
    if not required.issubset(measurements.columns):
        raise AnalysisError("Las mediciones deben incluir las columnas 'vus' y 'p95_s'.")
    if not math.isfinite(poor_fit_threshold) or not 0 <= poor_fit_threshold <= 1:
        raise AnalysisError("El umbral de R² debe estar entre 0 y 1.")

    frame = measurements.loc[:, ["vus", "p95_s"]].copy()
    frame["vus"] = pd.to_numeric(frame["vus"], errors="coerce")
    frame["p95_s"] = pd.to_numeric(frame["p95_s"], errors="coerce")
    valid_mask = (
        np.isfinite(frame["vus"].to_numpy(dtype=float))
        & np.isfinite(frame["p95_s"].to_numpy(dtype=float))
        & (frame["vus"].to_numpy(dtype=float) > 0)
        & (frame["p95_s"].to_numpy(dtype=float) > 0)
    )
    valid = frame.loc[valid_mask]
    users = valid["vus"].to_numpy(dtype=float)
    response_times = valid["p95_s"].to_numpy(dtype=float)

    if len(np.unique(users)) < 3:
        raise AnalysisError(
            "Se necesitan al menos tres niveles de concurrencia válidos y distintos "
            "para ajustar una función cuadrática."
        )

    coefficients, _, rank, _, _ = np.polyfit(users, response_times, deg=2, full=True)
    if rank < 3 or not np.isfinite(coefficients).all():
        raise AnalysisError("No fue posible obtener un ajuste cuadrático de rango completo.")

    predicted = np.polyval(coefficients, users)
    residual_sum_squares = float(np.sum((response_times - predicted) ** 2))
    total_sum_squares = float(np.sum((response_times - response_times.mean()) ** 2))
    if total_sum_squares <= np.finfo(float).eps:
        raise AnalysisError("R² no está definido porque los valores p95 no presentan variación.")
    r_squared = 1.0 - residual_sum_squares / total_sum_squares

    warnings: list[str] = []
    if r_squared < poor_fit_threshold:
        warnings.append(
            f"El ajuste es poco representativo (R²={r_squared:.4f}, menor que "
            f"{poor_fit_threshold:.2f}); interpreta la raíz con cautela."
        )
    if len(np.unique(users)) < 5:
        warnings.append(
            "El ajuste usa menos de cinco niveles; agrega niveles y repeticiones para "
            "evaluar mejor la representatividad."
        )
    if len(frame) > len(valid):
        warnings.append(
            f"Se excluyeron {len(frame) - len(valid)} filas no numéricas, no finitas "
            "o no positivas del ajuste."
        )

    return QuadraticModel(
        a=float(coefficients[0]),
        b=float(coefficients[1]),
        c=float(coefficients[2]),
        r_squared=float(r_squared),
        min_users=float(users.min()),
        max_users=float(users.max()),
        valid_levels=len(np.unique(users)),
        warnings=tuple(warnings),
    )


def estimate_capacity(
    model: QuadraticModel,
    measurements: pd.DataFrame,
    *,
    max_response_time_s: float = 2.0,
    tolerance_percent: float = 0.05,
    max_iterations: int = 50,
) -> CapacityEstimate:
    """Busca con secante el cruce observado y rechaza raíces extrapoladas."""
    if not math.isfinite(max_response_time_s) or max_response_time_s <= 0:
        raise AnalysisError("El tiempo máximo debe ser un número positivo y finito.")
    if measurements.empty or not {"vus", "p95_s"}.issubset(measurements.columns):
        raise AnalysisError("No hay mediciones válidas para estimar la capacidad.")

    valid = measurements.loc[:, ["vus", "p95_s"]].copy()
    valid["vus"] = pd.to_numeric(valid["vus"], errors="coerce")
    valid["p95_s"] = pd.to_numeric(valid["p95_s"], errors="coerce")
    valid = valid.loc[
        np.isfinite(valid["vus"].to_numpy(dtype=float))
        & np.isfinite(valid["p95_s"].to_numpy(dtype=float))
        & (valid["vus"] > 0)
        & (valid["p95_s"] > 0)
    ].sort_values("vus")
    if valid.empty:
        raise AnalysisError("No hay filas válidas para estimar la capacidad.")

    measured_times = valid["p95_s"].to_numpy(dtype=float)
    if float(measured_times.max()) < max_response_time_s:
        raise AnalysisError(
            f"Las mediciones p95 no alcanzan el límite de {max_response_time_s:g} s. "
            "No se puede afirmar una capacidad máxima; ejecuta pruebas con más usuarios."
        )
    if float(measured_times.min()) > max_response_time_s:
        raise AnalysisError(
            "Todas las mediciones p95 superan el límite; falta un nivel medido por debajo "
            "para acotar el cruce y determinar una capacidad segura."
        )

    observed_crossing = False
    p95_values = valid["p95_s"].to_numpy(dtype=float)
    for left, right in zip(p95_values[:-1], p95_values[1:]):
        if (left - max_response_time_s) * (right - max_response_time_s) <= 0:
            observed_crossing = True
            break
    if not observed_crossing:
        raise AnalysisError(
            "Los niveles experimentales no acotan el cruce del tiempo máximo; "
            "añade pruebas alrededor del umbral."
        )

    users = valid["vus"].to_numpy(dtype=float)
    model_values = np.array([model.predict(float(user)) for user in users])
    model_residuals = model_values - max_response_time_s
    candidate_pairs: list[tuple[float, float, float]] = []
    for index in range(len(users) - 1):
        left_residual = float(model_residuals[index])
        right_residual = float(model_residuals[index + 1])
        if left_residual * right_residual <= 0 and users[index] != users[index + 1]:
            distance_to_observed_limit = abs(float(p95_values[index]) - max_response_time_s)
            distance_to_observed_limit += abs(float(p95_values[index + 1]) - max_response_time_s)
            candidate_pairs.append(
                (distance_to_observed_limit, float(users[index]), float(users[index + 1]))
            )
    if not candidate_pairs:
        raise AnalysisError(
            "El modelo ajustado no cruza el límite dentro del rango experimental; "
            "no se calculará una raíz extrapolada."
        )

    _, x0, x1 = min(candidate_pairs)
    try:
        result: SecantResult = secant_method(
            lambda value: model.predict(value) - max_response_time_s,
            x0,
            x1,
            tolerance_percent=tolerance_percent,
            max_iterations=max_iterations,
        )
    except ValueError as exc:
        raise AnalysisError(str(exc)) from exc

    root = result["root"]
    range_tolerance = max(1e-10, abs(model.max_users - model.min_users) * 1e-10)
    if not model.min_users - range_tolerance <= root <= model.max_users + range_tolerance:
        raise AnalysisError(
            f"La raíz aproximada ({root:.6g}) queda fuera del rango experimental "
            f"[{model.min_users:g}, {model.max_users:g}] usuarios; se rechaza la extrapolación."
        )

    safe_users = math.floor(root)
    estimated_response = model.predict(root)
    if safe_users < model.min_users or model.predict(float(safe_users)) > max_response_time_s:
        raise AnalysisError(
            "La raíz no permite identificar un número entero de usuarios dentro del rango "
            "medido cuyo tiempo estimado quede bajo el límite."
        )

    return CapacityEstimate(
        x0=x0,
        x1=x1,
        root=root,
        estimated_response_s=estimated_response,
        safe_users=safe_users,
        iterations=result["iterations"],
        approximate_error_pct=result["approximate_error_pct"],
        tolerance_percent=tolerance_percent,
        max_iterations=max_iterations,
        history=result["history"],
    )


def write_measurements_csv(measurements: pd.DataFrame, path: str | Path) -> None:
    """Escribe la tabla resumen por nivel en formato CSV para análisis posterior."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    measurements.loc[:, SUMMARY_COLUMNS].to_csv(output_path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resume las métricas crudas CSV de k6 por nivel de concurrencia."
    )
    parser.add_argument("--input", type=Path, default=Path("results/carga.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/mediciones.csv"))
    args = parser.parse_args()

    data = load_k6_csv(args.input)
    if data.measurements.empty:
        raise SystemExit("El CSV no contiene escenarios de carga válidos.")
    write_measurements_csv(data.measurements, args.output)
    print(f"Se guardaron {len(data.measurements)} niveles en {args.output}.")
    for warning in data.invalid_scenarios:
        print(f"ADVERTENCIA: {warning}")


if __name__ == "__main__":
    main()
