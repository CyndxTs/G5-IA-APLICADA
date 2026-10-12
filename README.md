# Predicción del riesgo de sanción de proveedores en las contrataciones públicas peruanas

> **Pontificia Universidad Católica del Perú (PUCP)**
> Facultad de Ciencias e Ingeniería
> Curso: Inteligencia Artificial Aplicada (1INF62) - 2026-2

| Especificación | Detalle |
| :--- | :--- |
| **Tipo de proyecto** | Clasificación supervisada con datos abiertos del Estado peruano |
| **Fuente principal** | OECE/SEACE - Plataforma Nacional de Datos Abiertos |
| **Horizonte de predicción** | 12 meses posteriores a una fecha de corte |

---

## 1. Resumen Ejecutivo

Este proyecto consiste en construir un modelo de alerta temprana que, utilizando únicamente información pública disponible antes de una fecha de corte, estime la probabilidad de que un proveedor del Estado peruano registre una sanción o inhabilitación durante los siguientes 12 meses. 

El resultado no pretende demostrar corrupción ni fraude, sino servir como un mecanismo de priorización (score de riesgo) para la revisión de proveedores.

## 2. Problema y pregunta de investigación

El sistema peruano de contrataciones públicas genera grandes volúmenes de información transaccional. La revisión manual de todas las operaciones es limitada, por lo que resulta útil contar con mecanismos de priorización basados en evidencia histórica.

**Pregunta de investigación:**
*¿Es posible estimar, usando únicamente información disponible hasta una fecha de corte, qué proveedores del Estado peruano presentan mayor riesgo de recibir una sanción o inhabilitación durante los siguientes 12 meses?*

## 3. Dataset y fuentes de información

El proyecto se apoya exclusivamente en fuentes abiertas de la Plataforma Nacional de Datos Abiertos (OECE). La unidad de análisis es **proveedor-fecha de corte**.

| Fuente | Uso en el proyecto | Campos esperados | Rol |
| :--- | :--- | :--- | :--- |
| **Contratos de las entidades** | Historial contractual adjudicado | RUC, entidad, fechas, monto | Predictoras |
| **Órdenes de compra / servicios** | Actividad transaccional | Proveedor, fecha, monto | Predictoras |
| **Proveedores y consorcios** | Atributos del proveedor | RUC, razón social, ubigeo | Cruce / Predictoras |
| **Sancionados con inhabilitación** | Construcción del evento futuro | Proveedor, sanción, fechas | Etiqueta |

**Variable Objetivo:**
* `y(i,t) = 1`: Se registra una sanción/inhabilitación entre el día t+1 y 12 meses posteriores.
* `y(i,t) = 0`: No se observa sanción en dicho horizonte.

## 4. Diseño metodológico y Modelos

Para evitar la fuga de información (data leakage), se utilizará una partición temporal estricta de los datos. El RUC se utilizará únicamente para cruce de tablas, no como variable explicativa.

Debido al previsible desbalance de clases, la evaluación priorizará métricas como PR-AUC, Recall, Precision y F1-score.

**Modelos a comparar:**

| Modelo | Función en el proyecto | Ventaja |
| :--- | :--- | :--- |
| **Regresión Logística** | Baseline interpretable | Permite analizar signo y magnitud de asociaciones. |
| **Árbol de Decisión** | Reglas de clasificación | Altamente interpretable y fácil de explicar. |
| **K-Nearest Neighbors (KNN)** | Comparación por similitud | Intuitivo y no paramétrico. |
| **Perceptrón Multicapa (MLP)** | Modelo no lineal | Captura interacciones complejas. |

---

## 5. Estructura del Repositorio

El repositorio está organizado conforme a las directrices del curso:

```text
proyecto/
├── README.md                 
├── ENTREGABLE_PARCIAL.md     
├── ENTREGABLE_FINAL.md       
├── data/                     
│   ├── raw/                  
│   └── processed/            
├── notebooks/                
│   ├── 01_eda.ipynb          
│   └── 02_modelos.ipynb      
├── src/                      
│   ├── preprocessing.py      
│   ├── models.py             
│   └── evaluation.py         
├── results/                  
│   ├── metrics.csv           
│   ├── plots/                
│   └── model_comparison.txt  
├── papers/                   
│   └── paper_1_Quispe_Elvis.pdf
│   └── paper_2_.pdf
│   └── paper_3_.pdf
│   └── paper_4_.pdf
├── report.pdf                
├── presentation.pdf          
└── requirements.txt          
```

## 6. Instrucciones de ejecución

1. Clonar el repositorio:
   ```bash
   git clone https://github.com/CyndxTs/G5-IA-APLICADA.git
   cd G5-IA-APLICADA
   ```

2. **Instalar las dependencias requeridas:**
   Es recomendable contar con las bibliotecas listadas en el proyecto. Ejecuta:
   ```bash
   pip install -r requirements.txt
   ```

3. **Iniciar el entorno de Jupyter Notebook:**
   Desde la misma terminal, levanta el servidor local ejecutando:
   ```bash
   jupyter-notebook
   ```
   *Nota: Este comando abrirá automáticamente una pestaña en tu navegador web apuntando a la raíz del proyecto.*

4. **Ejecutar el código:**
   * En la interfaz web de Jupyter, navega hacia el directorio `notebooks/`.
   * Abre y ejecuta las celdas de forma secuencial, empezando por `01_eda.ipynb` y continuando con `02_modelos.ipynb`.

## 7. Integrantes del Grupo

* Giovanni Junior Rojas Turin - [20220348]
* Elvis Quispe Mamani - [20192663]
* Eduardo Valladares Coronado - [20211669]
* César Augusto Napurí de la Cruz - [20211692]
