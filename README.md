# Propuesta de proyecto

## Predicción del riesgo de sanción de proveedores en las contrataciones públicas peruanas

**Curso:** Inteligencia Artificial Aplicada — PUCP  
**Entrega:** Parcial, semana 8  
**Actualización:** 11 de octubre de 2026

## Avance de la entrega parcial

Completamos el EDA, la construcción del dataset y el entrenamiento y evaluación en validación de dos modelos:

| Modelo | Configuración seleccionada | PR-AUC en validación |
|---|---|---:|
| Regresión logística — baseline | `C = 0.001` | 0,084 |
| Árbol de decisión | `max_depth = 5`, `min_samples_leaf = 20` | 0,064 |

Calculamos la métrica con `average_precision_score`, como en el notebook. Consideramos los resultados preliminares; debemos aplicar el umbral y reportar métricas de prueba. Implementaremos KNN y MLP para la entrega final.

Para cerrar el parcial, registraremos los resúmenes por integrante y actualizaremos `ENTREGABLE_PARCIAL.md`.

## Organización

```text
G5-IA-APLICADA/
├── README.md
├── Propuesta_Proyecto_IA_Riesgo_Proveedores_Publicos.md
├── setup_entorno_virtual.bat
├── requirements.txt
├── data/
│   ├── raw/
│   └── processed/
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_preprocesamiento.ipynb
│   └── 03_modelos.ipynb
└── papers/
│   ├── paper1.pdf
│   ├── paper2.pdf
│   ├── paper3.pdf
│   └── paper4.pdf
```

## Ejecución

En Windows, ejecutamos `setup_entorno_virtual.bat` desde la raíz. Verificamos Python 3.12, ofrecemos su instalación si falta, creamos o reutilizamos `.venv` e instalamos `requirements.txt`.

Conservamos los originales en `data/raw/contratos/`, `convocatorias/`, `entidades_contratantes/`, `rnp/` y `sancionados/`. Seleccionamos el intérprete de `.venv` en Jupyter o VS Code y ejecutamos los notebooks en orden: **01 → 02 → 03**.

## Problema y objetivo

Consideramos que el volumen de contrataciones públicas dificulta revisar a todos los proveedores. Proponemos usar su historial contractual para priorizar revisiones según el riesgo de sanción futura.

Nos planteamos la siguiente pregunta: **¿podemos estimar qué proveedores del Estado peruano recibirán una inhabilitación o multa durante los 12 meses posteriores a una fecha de corte, usando su información histórica?**

Buscamos comparar regresión logística, árbol de decisión, KNN y MLP con datos públicos del OECE/SEACE y del RNP. Interpretamos el puntaje como una señal para revisión, sin atribuir fraude o corrupción.

## Datos y alcance implementado

Integramos contratos y convocatorias de 2023–2026, entidades contratantes, sanciones de CONOSCE y la exportación del Tribunal de Contrataciones del RNP. Conservamos los originales en `data/raw/`.

Definimos una fila por **proveedor y fecha de corte**. Usamos el RUC del contratista; para consorcios probables con códigos cortos, usamos el RUC de pago como identificación inferida.

Construimos `dataset_proveedor_corte.csv` con **30.049 filas, 10.033 proveedores y 49 columnas**: 44 predictoras, dos identificadores y tres etiquetas. Incluimos cinco cortes semestrales entre junio de 2023 y junio de 2025.

Definimos `target = 1` si observamos una inhabilitación o multa en `(corte, corte + 12 meses]`. Interpretamos el cero como ausencia de evento registrado. Observamos entre **1,82 % y 3,50 %** de positivos por corte.

Dejamos fuera de esta versión las órdenes de compra y servicio y las penalidades propuestas inicialmente.

## Metodología y avance

Organizamos el trabajo en tres notebooks:

| Notebook | Trabajo realizado |
|---|---|
| `01_eda.ipynb` | Exploramos principalmente 2024; revisamos distribuciones, nulos, duplicados, identificadores, fechas y cruces. |
| `02_preprocesamiento.ipynb` | Homologamos formatos, depuramos contratos e integramos sanciones por RUC–resolución–tipo. Construimos variables, etiquetas y diccionario. |
| `03_modelos.ipynb` | Dividimos por tiempo y comparamos regresión logística y árbol en validación. |

Calculamos actividad en ventanas de 3, 6, 12 y 24 meses, montos en soles con `log1p`, crecimiento, concentración, diversificación, frecuencia, antigüedad, composición y antecedentes. Filtramos contratos por la mayor fecha entre publicación y suscripción y excluimos adicionales, reducciones y prórrogas.

Verificamos unicidad, ventanas y etiquetas; recalculamos contratos, antecedentes y etiquetas en **400 filas**, con validaciones superadas en la ejecución guardada.

Entrenamos con junio y diciembre de 2023 y junio de 2024 (**11.610 filas**); validamos con diciembre de 2024 (**8.406**) y reservamos junio de 2025 para prueba (**10.033**). Ajustamos recorte de extremos e imputación solo con entrenamiento, estandarizamos para regresión logística y usamos pesos de clase.

Usamos `setup_entorno_virtual.bat` para preparar Python 3.12, `.venv` y las dependencias de `requirements.txt`; ejecutamos los notebooks en orden.

## Modelos

Mantenemos cuatro modelos del curso:

| Modelo | Uso y estado |
|---|---|
| Regresión logística | Implementamos el baseline interpretable y ajustamos `C`. |
| Árbol de decisión | Implementamos reglas y controlamos profundidad y tamaño de hoja. |
| KNN | Compararemos proveedores por similitud en la entrega final. |
| MLP | Evaluaremos relaciones no lineales en la entrega final. |


## 6. Bibliografía

- Sá, T. A., Pessanha, J. F. M., y Alves, F. J. dos S. (2024). Métodos de classificação supervisionada aplicados à identificação de fraudes de fornecedores. *Contabilometria, 11*(2), 125–146. [Artículo](https://revistas.fucamp.edu.br/index.php/contabilometria/article/view/3045).
- Fonseca, J. B. R., Garcia, L. F. P., y Caetano, M. F. (2024). Estimating the Risk of Failure in Government Auctions in Brazil. En *Anais do XXI Encontro Nacional de Inteligência Artificial e Computacional (ENIAC)* (pp. 637–646). Sociedade Brasileira de Computação. [DOI](https://doi.org/10.5753/eniac.2024.245280).
- Gallego, J., Rivero, G., y Martínez, J. (2021). Preventing rather than punishing: An early warning model of malfeasance in public procurement. *International Journal of Forecasting, 37*(1), 360–377. [DOI](https://doi.org/10.1016/j.ijforecast.2020.06.006).
- Medina-Hernández, M., Kertész, J., y Fazekas, M. (2026). Learning from sanctioned government suppliers: A machine learning and network science approach to detecting fraud and corruption in Mexico. *Scientific Reports, 16*, 22382. [Versión publicada](https://doi.org/10.1038/s41598-026-48873-w). Versión consultada inicialmente: [preprint de 2025, arXiv:2512.19491v2](https://arxiv.org/abs/2512.19491v2).
- Organismo Especializado para las Contrataciones Públicas Eficientes (OECE). [Portal de Datos Abiertos](https://www.gob.pe/14272-acceder-al-portal-de-datos-abiertos-del-oece) y [Registro Nacional de Proveedores](https://www.rnp.gob.pe/).
