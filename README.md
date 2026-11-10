# Proyecto de Métodos Numéricos: método de la secante

El proyecto estima la concurrencia asociada a un límite de tiempo de respuesta. Esta primera etapa crea una API local y un ensayo k6 reproducible. La tarea de `/work` es sintética: sirve para practicar la medición, no para afirmar la capacidad de una aplicación real.

## 1. Preparar el entorno

Desde esta carpeta, en PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 2. Iniciar la API local

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

La API escucha solo en el equipo local. En otra terminal, comprueba:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/work
```

## 3. Ejecutar el ensayo de carga

Instala k6 siguiendo su documentación oficial. Con la API todavía activa, crea el directorio de resultados y ejecuta el ensayo:

```powershell
New-Item -ItemType Directory -Force results
```

El ensayo calienta la API y luego mide niveles secuenciales de 1, 2, 4, 8, 12, 24, 48 y 96 usuarios virtuales durante 15 segundos cada uno. La pausa entre niveles ayuda a distinguir sus mediciones. La duración total es de aproximadamente 144 segundos.

Guarda este ensayo ampliado en un archivo distinto para conservar la primera medición:

```powershell
k6 run --out csv=results/carga_ampliada.csv loadtest/scenarios.js
```

La primera ejecución registró p95 de 13,23 ms con 1 usuario y 111,23 ms con 12, sin solicitudes fallidas; por tanto, no alcanzó el umbral ilustrativo de 2 segundos. En el resumen de k6 y en `results/carga_ampliada.csv`, conserva para cada nivel la duración de respuesta (`http_req_duration`), especialmente `p(95)`, y la tasa de solicitudes fallidas. No declares una capacidad si hay errores o si el nivel no se mantuvo estable.

La prueba genera carga solo en la API local. Si el equipo se vuelve lento o notas un comportamiento anormal, detén k6 con `Ctrl+C`; los resultados ya escritos en el CSV se conservan.

## 4. Validar la API

```powershell
python -m unittest discover -s tests -v
```

## Criterios para el experimento

- Ejecuta la prueba solo contra esta API local o contra un sistema propio/autorizado. No cambies el destino del guion para apuntar a servicios de terceros.
- Mantén iguales la máquina, la configuración, la versión del código y las condiciones de red durante las mediciones; registra esos datos en el informe.
- Repite el ensayo y reporta la variabilidad. Un resultado de k6 refleja usuarios virtuales y esta operación sintética, no usuarios reales ni una capacidad universal.
- Antes de ajustar los niveles de concurrencia, revisa que la máquina siga respondiendo normalmente y que el proceso de la API no presente errores.

La siguiente etapa será usar las mediciones para seleccionar y justificar una función \(T(x)\), definir \(f(x)=T(x)-T_{\mathrm{máximo}}\), e implementar y validar el método de la secante.

## Etapa 2: método de la secante para estimar capacidad

El prototipo ya incluye un modelo didáctico de tiempo de respuesta y la implementación del método de la secante.

```python
from api.main import estimate_users_for_limit

result = estimate_users_for_limit(max_response_time=2.0, x0=200.0, x1=250.0)
print(result)
# {'root': 234.2329219201431, 'iterations': 4, 'max_users_under_limit': 234}
```

La ecuación base es:

\[
T(x)=0.00002x^2 + 0.003x + 0.2
\]

con

\[
f(x)=T(x)-2
\]

y la raíz aproximada se obtiene con el método de la secante. En una medición real, se reemplaza este modelo con una función ajustada a los datos obtenidos en k6 y se repite el procedimiento con la tolerancia y los puntos iniciales adecuados.

## Interfaz gráfica con Streamlit

Puedes abrir la aplicación visual con:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

La interfaz permite:

- ingresar el tiempo máximo tolerado
- definir dos aproximaciones iniciales
- ajustar la tolerancia y el número máximo de iteraciones
- ver la tabla de iteraciones del método de la secante
- visualizar la gráfica de la función y la raíz estimada
- obtener la capacidad de usuarios máxima segura bajo el umbral seleccionado
