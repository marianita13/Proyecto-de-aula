from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from api.analysis import (
    AnalysisError,
    estimate_capacity,
    fit_quadratic_model,
    load_k6_csv,
)


ROOT_DIR = Path(__file__).resolve().parent
K6_CSV_PATH = ROOT_DIR / "results" / "carga.csv"

st.set_page_config(
    page_title="Análisis de capacidad web",
    page_icon="📊",
    layout="wide",
)

st.title("Estimación de capacidad de una API")
st.caption(
    "Análisis de percentiles p95 observados con k6, ajuste cuadrático por mínimos "
    "cuadrados y búsqueda de raíz mediante el método de la secante."
)

with st.sidebar:
    st.header("Parámetros")
    max_response_time_s = st.number_input(
        "Tiempo máximo de respuesta (s)",
        min_value=0.001,
        value=2.0,
        step=0.1,
        format="%.3f",
    )
    tolerance_percent = st.number_input(
        "Tolerancia del error aproximado (%)",
        min_value=0.0001,
        value=0.05,
        step=0.01,
        format="%.4f",
    )
    max_iterations = st.number_input(
        "Máximo de iteraciones",
        min_value=1,
        max_value=1000,
        value=50,
        step=1,
    )
    if st.button("Recargar datos de carga.csv", use_container_width=True):
        st.rerun()

st.info(f"Archivo de mediciones: `{K6_CSV_PATH}`")

try:
    k6_data = load_k6_csv(K6_CSV_PATH)
except AnalysisError as exc:
    st.warning(str(exc))
    st.info(
        "Las mediciones están pendientes. Inicia la API, ejecuta el escenario local de k6 "
        "y vuelve a cargar este archivo."
    )
    st.stop()

measurements = k6_data.measurements
if k6_data.invalid_scenarios:
    st.warning("Se omitieron escenarios incompletos o inválidos:")
    for reason in k6_data.invalid_scenarios:
        st.write(f"- {reason}")

if measurements.empty:
    st.warning("El CSV no contiene niveles de carga válidos; las mediciones están pendientes.")
    st.stop()

min_vus = int(measurements["vus"].min())
max_vus = int(measurements["vus"].max())
st.success(
    f"Datos leídos del CSV: {len(measurements)} niveles válidos, entre "
    f"{min_vus} y {max_vus} usuarios virtuales."
)

st.subheader("Mediciones experimentales de k6")
st.dataframe(
    measurements.rename(
        columns={
            "scenario": "Escenario",
            "vus": "Usuarios virtuales",
            "requests": "Solicitudes",
            "average_s": "Promedio (s)",
            "min_s": "Mínimo (s)",
            "max_s": "Máximo (s)",
            "p95_s": "p95 (s)",
            "failure_rate_pct": "Fallidas (%)",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

model = None
try:
    model = fit_quadratic_model(measurements)
except AnalysisError as exc:
    st.error(f"No se pudo ajustar el modelo: {exc}")

fig, ax = plt.subplots(figsize=(10, 5.5))
ax.scatter(
    measurements["vus"],
    measurements["p95_s"],
    color="#176B87",
    s=70,
    label="p95 medido",
    zorder=3,
)
ax.axhline(
    max_response_time_s,
    color="#C0392B",
    linestyle="--",
    linewidth=1.8,
    label=f"Límite: {max_response_time_s:g} s",
)

if model is not None:
    users_grid = np.linspace(model.min_users, model.max_users, 300)
    fitted_times = [model.predict(float(users)) for users in users_grid]
    ax.plot(users_grid, fitted_times, color="#E67E22", linewidth=2, label="Ajuste cuadrático")
    st.subheader("Modelo ajustado")
    metric_a, metric_b = st.columns(2)
    metric_a.metric("Ecuación estimada", model.equation)
    metric_b.metric("R²", f"{model.r_squared:.5f}")
    st.caption(
        f"Ajuste calculado con {model.valid_levels} niveles distintos, en el rango "
        f"experimental de {model.min_users:g} a {model.max_users:g} VUs."
    )
    for warning in model.warnings:
        st.warning(warning)

ax.set_title("Usuarios concurrentes frente a latencia p95")
ax.set_xlabel("Usuarios virtuales concurrentes (VUs)")
ax.set_ylabel("Tiempo de respuesta p95 (segundos)")
if model is not None:
    ax.set_xlim(model.min_users, model.max_users)
ax.grid(True, alpha=0.25)
ax.legend()
st.pyplot(fig, use_container_width=True)
plt.close(fig)

if model is not None:
    st.subheader("Estimación con el método de la secante")
    try:
        estimate = estimate_capacity(
            model,
            measurements,
            max_response_time_s=max_response_time_s,
            tolerance_percent=tolerance_percent,
            max_iterations=int(max_iterations),
        )
    except AnalysisError as exc:
        st.warning(str(exc))
        st.caption(
            "No se presenta una capacidad máxima: el umbral debe estar cubierto por "
            "mediciones válidas y la raíz debe quedar dentro del rango probado."
        )
    else:
        st.caption(
            "Los valores iniciales se seleccionaron de niveles experimentales alrededor "
            "del cruce observado del umbral."
        )
        initial_a, initial_b = st.columns(2)
        initial_a.metric("x₀", f"{estimate.x0:g} VUs")
        initial_b.metric("x₁", f"{estimate.x1:g} VUs")

        result_a, result_b, result_c = st.columns(3)
        result_a.metric("Raíz aproximada", f"{estimate.root:.6f} VUs")
        result_b.metric("p95 estimado en la raíz", f"{estimate.estimated_response_s:.6f} s")
        result_c.metric("Iteraciones", estimate.iterations)
        st.metric(
            "Usuarios enteros bajo el límite",
            estimate.safe_users,
            help=(
                "Se toma floor(raíz) porque la raíz es el punto estimado donde p95 alcanza "
                "el umbral; el entero inferior se verifica con el modelo ajustado."
            ),
        )
        st.caption(
            f"Error aproximado final: {estimate.approximate_error_pct:.5g}%; "
            f"tolerancia: {estimate.tolerance_percent:g}%; "
            f"máximo: {estimate.max_iterations} iteraciones. "
            "La estimación depende de este equipo, API, prueba y rango medido."
        )

        if estimate.history:
            history = [
                {
                    "Iteración": row["iteration"],
                    "x previo": row["x_prev"],
                    "Nueva aproximación": row["x_curr"],
                    "f(x)": row["f_x"],
                    "Error aproximado (%)": row["approximate_error_pct"],
                }
                for row in estimate.history
            ]
            st.dataframe(history, use_container_width=True, hide_index=True)
