import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from api.main import DEFAULT_MAX_RESPONSE_TIME, response_time_model, secant_method

st.set_page_config(page_title="Método de la secante", page_icon="📈", layout="wide")

st.title("Proyecto de aula: estimación de capacidad con el método de la secante")
st.caption("Aplicación para analizar la relación entre usuarios concurrentes y tiempo de respuesta.")

st.markdown(
    """
    La ecuación base del modelo es:

    T(x) = 0.00002x² + 0.003x + 0.2

    y la raíz se busca resolviendo:

    f(x) = T(x) - Tmáximo = 0
    """
)

with st.form("secant_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        max_response_time = st.number_input(
            "Tiempo máximo aceptado (s)",
            min_value=0.1,
            value=DEFAULT_MAX_RESPONSE_TIME,
            step=0.1,
        )
    with col2:
        x0 = st.number_input("Aproximación inicial x0", value=200.0, step=1.0)
    with col3:
        x1 = st.number_input("Aproximación inicial x1", value=250.0, step=1.0)

    col4, col5 = st.columns(2)
    with col4:
        tol = st.number_input("Tolerancia", value=1e-8, min_value=1e-12, format="%.1e")
    with col5:
        max_iter = st.number_input("Máximo de iteraciones", value=50, min_value=1, max_value=1000, step=1)

    submitted = st.form_submit_button("Calcular capacidad")

if submitted:
    try:
        result = secant_method(
            lambda value: response_time_model(value) - max_response_time,
            x0,
            x1,
            tol=tol,
            max_iter=int(max_iter),
        )
        root = float(result["root"])
        iterations = int(result["iterations"])
        max_users = math.floor(root)

        st.success(f"La estimación converge a una raíz de {root:.6f} usuarios.")

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Raíz estimada", f"{root:.6f}")
        col_b.metric("Iteraciones", iterations)
        col_c.metric("Usuarios máximos bajo el límite", max_users)

        history_df = pd.DataFrame(result["history"])
        history_df["x_prev"] = history_df["x_prev"].map(lambda value: round(float(value), 6))
        history_df["x_curr"] = history_df["x_curr"].map(lambda value: round(float(value), 6))
        history_df["f_x"] = history_df["f_x"].map(lambda value: round(float(value), 8))
        st.subheader("Tabla de iteraciones")
        st.dataframe(history_df, use_container_width=True, hide_index=True)

        x_values = np.linspace(max(0.0, min(x0, x1) - 50), max(x0, x1) + 120, 500)
        y_values = response_time_model(x_values)

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(x_values, y_values, label="T(x)", color="tab:blue", linewidth=2)
        ax.axhline(max_response_time, color="tab:red", linestyle="--", label=f"Límite = {max_response_time}s")
        ax.axvline(root, color="tab:green", linestyle=":", label=f"Raíz ≈ {root:.2f}")
        ax.scatter([x0, x1], [response_time_model(x0), response_time_model(x1)], color="orange", s=60, label="Puntos iniciales")
        ax.set_title("Tiempo de respuesta frente a usuarios concurrentes")
        ax.set_xlabel("Usuarios concurrentes (x)")
        ax.set_ylabel("Tiempo de respuesta (s)")
        ax.grid(True, alpha=0.3)
        ax.legend()
        st.pyplot(fig)

        st.subheader("Interpretación")
        st.write(
            f"Con un umbral de {max_response_time:.2f} s, la estimación del sistema alcanza el límite alrededor de "
            f"{root:.2f} usuarios concurrentes. Como la cantidad de usuarios debe ser entera, la capacidad segura "
            f"sería de {max_users} usuarios."
        )

    except ValueError as exc:
        st.error(str(exc))
