# Estimación experimental de capacidad con el método de la secante

## Objetivo

El proyecto estima el nivel de usuarios virtuales concurrentes asociado a un límite de
tiempo de respuesta. k6 genera solicitudes a la API local; Python resume las muestras,
ajusta una función cuadrática a sus percentiles p95 y aplica el método de la secante.
No se declara una capacidad si los datos no cubren el umbral o la raíz queda fuera del
rango probado.

La ruta `/work` realiza una tarea sintética y acotada para el experimento. Los resultados
describen únicamente esta API, máquina, configuración y ejecución; no equivalen a la
capacidad de un servicio en producción.

## Fundamento matemático

La variable independiente es \(x\), cantidad de VUs. La variable dependiente \(T(x)\)
es el p95 de duración medido por k6, convertido de milisegundos a segundos. Con los
niveles válidos del CSV, NumPy ajusta por mínimos cuadrados:

\[
T(x)=ax^2+bx+c
\]

Los coeficientes se estiman de las mediciones; no hay una función de respuesta fija en
el código. Se reporta \(R^2\) para describir qué tan bien representa el ajuste los datos.
Un \(R^2 < 0.90\) se advierte como ajuste poco representativo. El gráfico y la secante
se limitan al rango de concurrencia medido.

Para un umbral configurable \(T_{\max}\), el método de la secante busca la raíz de:

\[
f(x)=ax^2+bx+c-T_{\max}=0
\]

\[
x_{n+1}=x_n-\frac{f(x_n)(x_n-x_{n-1})}{f(x_n)-f(x_{n-1})}
\]

Los valores iniciales se toman de niveles experimentales adyacentes alrededor del
cruce. La capacidad entera se obtiene como \(\lfloor x_{\text{raíz}}\rfloor\) y se
verifica que la respuesta del modelo en ese entero no exceda el límite. Si el CSV no
alcanza el umbral, no se presenta una capacidad: hay que probar más concurrencia.
La parada usa el error relativo aproximado entre iteraciones,
\(E_a=|(x_n-x_{n-1})/x_n|\times100\%\), con tolerancia inicial de **0.05 %**.

## Arquitectura

- `api/main.py`: API FastAPI con `/health` y `/work`.
- `loadtest/scenarios.js`: ensayo local k6 con niveles de 1, 2, 4, 8, 12, 24, 48 y 96 VUs.
- `results/carga.csv`: salida cruda de k6 (muestras por métrica).
- `api/analysis.py`: lectura del CSV con Pandas, validación, resumen por nivel,
  ajuste cuadrático, cálculo de R² y cálculo de capacidad.
- `api/secant.py`: implementación independiente del método de la secante.
- `results/mediciones.csv`: resumen normalizado generado por el analizador.
- `streamlit_app.py`: visualización de los datos, el ajuste y la estimación.

## Tecnologías

Python, FastAPI, Uvicorn, k6, Pandas, NumPy, Matplotlib y Streamlit. SciPy no es
necesario para este ajuste: `numpy.polyfit` resuelve los mínimos cuadrados y se mantiene
la secante implementada explícitamente para que el procedimiento sea visible y evaluable.

## Instalación en Windows

Desde PowerShell, en la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Ejecutar la API

En una terminal:

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Comprueba en otra terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/work
```

La API escucha en loopback. Ejecuta las pruebas únicamente en esta API propia o en un
sistema para el que tengas autorización.

## Generar mediciones con k6

Instala k6 y confirma que `k6 version` funciona. Mantén la API activa. Desde la raíz
del proyecto:

```powershell
New-Item -ItemType Directory -Force results
k6 run --out csv=results/carga.csv loadtest/scenarios.js
```

El ensayo calienta el servicio y luego mide ocho niveles, secuencialmente, durante 15
segundos cada uno, con pausas entre niveles. La salida cruda conserva métricas por
solicitud; el resumen de k6 muestra promedio, mínimo, máximo y p95.

Convierte el CSV crudo en una tabla resumida por nivel:

```powershell
python -m api.analysis --input results/carga.csv --output results/mediciones.csv
```

El resumen incluye VUs, solicitudes, promedio, mínimo, máximo y p95 en segundos, además
del porcentaje de solicitudes fallidas. El analizador omite escenarios incompletos o
con valores inválidos. En el ensayo existente, el archivo contiene niveles hasta 12 VUs;
el p95 máximo observado es aproximadamente 0.1112 s, por debajo de 2 s. Por tanto,
esos datos no demuestran una capacidad máxima para el umbral de 2 s; el nuevo ensayo
debe completar niveles mayores.

Si k6 o la API causan un uso excesivo de recursos, detén el ensayo con `Ctrl+C`. No
ejecutes cargas contra servicios de terceros.

## Ejecutar Streamlit

Desde la raíz del proyecto:

```powershell
python -m streamlit run streamlit_app.py --server.address 127.0.0.1
```

La aplicación lee `results/carga.csv` directamente al cargar y al pulsar **Recargar
datos de carga.csv**. Muestra los datos válidos por nivel, la gráfica p95, la curva
ajustada y R². Solo muestra raíz y capacidad entera si las mediciones cubren el umbral
y el resultado queda dentro del rango experimental. Para actualizar tras una prueba,
vuelve a generar `results/carga.csv` con k6 y pulsa el botón de recarga.

## Pruebas unitarias

```powershell
python -m unittest discover -s tests -v
```

## Interpretación y limitaciones

- Cada punto corresponde a VUs de k6, no necesariamente a personas o sesiones reales.
- El p95 se calcula a partir de las muestras crudas de cada escenario; errores y filas
  incompletas no se ocultan y los escenarios inválidos se reportan.
- Se requieren al menos tres niveles válidos distintos para ajustar la cuadrática;
  se recomienda medir más niveles y repetir la prueba.
- Un ajuste cuadrático puede no representar la respuesta real del servidor. R² bajo,
  errores de carga o alta variabilidad reducen la confianza de la estimación.
- La secante no garantiza convergencia para cualquier par inicial. Se verifican
  denominadores, valores finitos, tolerancia y máximo de iteraciones.
- No se extrapola: la raíz debe estar dentro de los niveles experimentales y los datos
  deben mostrar un cruce del umbral. Si no se alcanza el límite, se necesitan más
  mediciones de concurrencia.
- La carpeta `results/` está excluida por `.gitignore`; los CSV generados se conservan
  localmente y no se incorporan al control de versiones automáticamente.
