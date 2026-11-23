# Predicción del riesgo de sanción de proveedores en las contrataciones públicas peruanas

Curso: Inteligencia Artificial Aplicada, PUCP  
Grupo: 5  

Última actualización: 23 de noviembre de 2026

## De qué trata

Buscamos anticipar qué proveedores del Estado peruano recibirán una inhabilitación o una multa del Tribunal de Contrataciones en los 12 meses siguientes a una fecha de corte, usando su historial público. El resultado es un puntaje para priorizar revisiones, no una acusación: un riesgo alto no prueba fraude ni incumplimiento.

## Resultados principales

Comparamos cuatro modelos del curso. Los evaluamos una sola vez en el corte de prueba (junio de 2025), donde el 2.4% de los proveedores fue sancionado en el año siguiente.

| Modelo | PR-AUC | Veces el azar | ROC-AUC | Sancionados encontrados revisando el 10% con más riesgo |
|---|---:|---:|---:|---:|
| Regresión logística (baseline) | 0.115 | 4.8 | 0.808 | 43% |
| Árbol de decisión | 0.086 | 3.5 | 0.761 | 37% |
| KNN | 0.104 | 4.3 | 0.796 | 42% |
| MLP (TensorFlow/Keras) | 0.117 | 4.8 | 0.806 | 43% |

En resumen:
- Los cuatro modelos superan claramente al azar: revisando el 10% con más riesgo, los tres mejores encuentran a más del 40% de los futuros sancionados.
- El MLP y la regresión logística empatan (la diferencia no es significativa con bootstrap). Elegimos la logística por ser más simple y explicable, como concluyen Gallego et al. (2021).
- El árbol es el más débil, a diferencia de Fonseca et al. (2024), que trabajaron con una muestra balanceada 50/50 y no con la prevalencia real (~2%).
- Lo que más pesa es el historial del proveedor (participación, penalidades y sanciones previas), más que los montos o el precio que destacan Sá et al. (2024) y Fonseca et al. (2024).
- El modelo encuentra a cerca de un tercio de los sancionados que no tenían antecedentes, que son el 83% del total.

El detalle está en `results/model_comparison.txt` y en `results/summaries/modeling/resumen.md`.

## Datos

Todo viene de fuentes públicas del OECE (ver la bibliografía). Los archivos originales están en `data/raw/`, una carpeta por fuente:

| Carpeta | Contenido | Fuente | Para qué la usamos |
|---|---|---|---|
| `adjudicaciones/` | Ítems con buena pro, 2022-2026 | Datos abiertos del OECE (CONOSCE) | Base del historial de cada proveedor |
| `convocatorias/` | Procesos convocados, 2022-2026 | Datos abiertos del OECE (CONOSCE) | Sector y tipo de proceso de cada ítem |
| `ofertantes/` | Postores por ítem, 2022-2026 | Datos abiertos del OECE (CONOSCE) | Competencia y participación |
| `contratos/` | Contratos firmados, 2022-2026 | Datos abiertos del OECE (CONOSCE) | Asignar ampliaciones a un proveedor |
| `ampliaciones/` | Ampliaciones de plazo, 2022-2026 | Datos abiertos del OECE (CONOSCE) | Señales de ejecución |
| `arbitraje/` | Arbitrajes, 2022-2026 | Datos abiertos del OECE (CONOSCE) | Solo en el EDA (muy pocos registros) |
| `penalidades/` | Penalidades aplicadas a proveedores | Datos abiertos del OECE (CONOSCE) | Señales de ejecución |
| `sancionados/` | Inhabilitaciones publicadas por el OECE | Datos abiertos del OECE (CONOSCE) | Target y antecedentes |
| `entidades_contratantes/` | Catálogo de entidades | Datos abiertos del OECE (CONOSCE) | Solo en el EDA |
| `rnp/` | Proveedores sancionados por el Tribunal en los últimos cinco años, descargado el 11-10-2026 | Registro Nacional de Proveedores (RNP) | Target y antecedentes (inhabilitaciones y multas) |

Casi todo se descargó por año desde el portal de datos abiertos del OECE. La única fuente aparte es el reporte del RNP, que trae las multas (el archivo de CONOSCE solo tiene inhabilitaciones). Lo unimos con `sancionados/` sin repetir resoluciones.

El preprocesamiento genera `data/processed/dataset_proveedor_corte.csv`:
- 181 708 filas, una por proveedor y fecha de corte, de 45 095 proveedores.
- Siete cortes semestrales, de junio de 2022 a junio de 2025. El último es el más reciente con 12 meses completos de sanciones observables.
- 44 columnas: 2 identificadores, 39 predictoras y 3 columnas de target.
- Población: personas naturales y jurídicas con al menos una buena pro en los 24 meses anteriores al corte.
- Target (`y_sancion_12m`): 1 si el proveedor recibe una inhabilitación o una multa en los 12 meses siguientes al corte. Entre el 1.7% y el 2.6% de las filas son positivas, según el corte.

## Estructura del repositorio

```text
G5-IA-APLICADA/
├── README.md
├── G5_ENTREGABLE_PARCIAL.md # checklist de lo entregado en la semana 8
├── G5_ENTREGABLE_FINAL.md   # checklist de lo entregado en la semana 15
├── G5_REPORTE.pdf           # reporte final (formato paper)
├── G5_PRESENTACION.pdf      # diapositivas de la presentación
├── requirements.txt
├── setup_entorno_virtual.bat
├── data/
│   ├── raw/                 # fuentes originales (ver tabla de datos)
│   └── processed/
│       └── dataset_proveedor_corte.csv
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_preprocesamiento.ipynb
│   └── 03_modelos.ipynb
├── src/
│   ├── exploration.py       # lectura de fuentes y análisis exploratorio
│   ├── preprocessing.py     # limpieza, cruces, variables, target y selección
│   ├── models.py            # los 4 modelos, ajuste en validación y guardado
│   └── evaluation.py        # métricas, bootstrap, interpretación y gráficos
├── models/                  # modelos entrenados (no se sube a git)
├── results/
│   ├── metrics.csv
│   ├── model_comparison.txt
│   ├── plots/
│   │   ├── exploration/
│   │   ├── preprocessing/
│   │   └── modeling/
│   └── summaries/
│       ├── exploration/     # resumen.md + tables/
│       ├── preprocessing/   # resumen.md + tables/
│       └── modeling/        # resumen.md + tables/
└── papers/                  # un paper revisado por integrante
    ├── PAPER_1_QUISPE_ELVIS.pdf        # Sá et al. (2024)
    ├── PAPER_2_NAPURI_CESAR.pdf        # Fonseca et al. (2024)
    ├── PAPER_3_VALLADARES_EDUARDO.pdf  # Gallego et al. (2021)
    └── PAPER_4_ROJAS_GIOVANNI.pdf      # Medina-Hernández et al. (2026)
```

La plantilla del curso pide `01_eda` y `02_modelos`; separamos el preprocesamiento en su propio notebook por su extensión, así que los modelos quedaron en `03_modelos.ipynb`. Por lo mismo agregamos `src/exploration.py`.

El código está en `src/` y los notebooks lo llaman paso a paso. Cada ejecución reemplaza sus propias salidas. Los `resumen.md` de `results/summaries/` reúnen las tablas y los gráficos de cada etapa.

## Cómo ejecutarlo

En Windows:

1. Ejecutar `setup_entorno_virtual.bat` desde el Explorador de archivos. Instala lo que falte (VS Code con sus extensiones y Python 3.12), crea el entorno `.venv` con las librerías de `requirements.txt`, lo deja como intérprete de VS Code y abre el proyecto.
2. Correr los notebooks en orden: `01_eda` → `02_preprocesamiento` → `03_modelos`.

## Metodología

### 1. Exploración (`01_eda.ipynb`)

Revisamos cada fuente (volumen, faltantes, duplicados, identificadores y fechas) y cómo se cruzan. Decisiones principales:
- El historial se arma con las adjudicaciones, porque los contratos solo cubren ~9% de lo adjudicado.
- Consorcios y no domiciliados quedan fuera: no tienen un RUC con el cual encontrar sus sanciones.
- Las listas de sanciones solo cubren ~5 años, lo que limita los antecedentes de los primeros cortes.

### 2. Preprocesamiento (`02_preprocesamiento.ipynb`)

- Limpiamos cada fuente y unimos las sanciones del RNP y de CONOSCE sin repetir resoluciones.
- Calculamos variables con información anterior a cada corte, en una ventana de 24 meses, agrupadas en perfil, actividad, montos, diversificación, concentración, composición, precio, competencia, participación, ejecución y antecedentes. Varios grupos vienen de los papers (montos de Sá et al., competencia y precio de Fonseca et al. y Gallego et al., concentración y tipo de proceso de Medina-Hernández et al.); ejecución y participación son aportes nuestros.
- Llenamos faltantes con reglas fijas (no con promedios) y aplicamos `log1p` a las colas largas.
- Seleccionamos variables solo con los cortes de entrenamiento (señal mínima, sin casi constantes ni redundantes) y validamos el dataset recalculando 400 filas desde cero.

### 3. Modelos (`03_modelos.ipynb`)

La división respeta el tiempo:

| Conjunto | Cortes | Uso |
|---|---|---|
| Selección | jun-2022 a dic-2023 | Entrenar para elegir cortes, hiperparámetros, umbral y épocas |
| Validación | dic-2024 | Medir y elegir |
| Entrenamiento final | jun-2022 a jun-2024 | Reentrenar los modelos elegidos |
| Prueba | jun-2025 | Evaluación final, una sola vez |

Separamos selección y entrenamiento final porque la etiqueta de jun-2024 recién se conoce en jun-2025; usarla para elegir en dic-2024 sería usar información del futuro.

Preprocesamiento propio y configuración elegida de cada modelo:

| Modelo | Escalado | Desbalance de clases | Hiperparámetros elegidos |
|---|---|---|---|
| Regresión logística | `StandardScaler` | `class_weight="balanced"` | `C = 0.0001` |
| Árbol de decisión | ninguno | `class_weight="balanced"` | `max_depth = 8`, `min_samples_leaf = 100` |
| KNN | `StandardScaler` | umbral y k grande | `n_neighbors = 1601`, `weights = "uniform"` |
| MLP (Keras `Sequential`) | `StandardScaler` | pesos de clase en `fit` | capas (256, 128, 64), `dropout = 0.5`, `adam`, early stopping por PR-AUC de validación |

Usamos pesos de clase para conservar la distribución real: el submuestreo de Sá et al. (2024) descartaría a casi todos los proveedores no sancionados. Gallego et al. (2021) obtuvieron un ranking algo mejor con sobremuestreo, así que probarlo queda como trabajo futuro.

Métricas, pensadas para ordenar proveedores a revisar:
- PR-AUC (principal): más exigente que la ROC-AUC con 2% de positivos; el azar vale la prevalencia.
- Recall, precision y lift en el top 10%: cuántos sancionados se encuentran revisando a 1 de cada 10, como el ranking de Gallego et al. (2021) y el lift de Medina-Hernández et al. (2026).
- ROC-AUC, F1 con umbral elegido en validación y Brier, como referencia. No usamos accuracy: no alertar nunca daría 98%.

Las diferencias se prueban con bootstrap (1000 remuestreos) contra el baseline, y la interpretación usa importancia por grupo de variables, coeficientes, reglas del árbol y detección por subgrupo.

## Limitaciones

- Las variables de ampliaciones son parciales, porque los contratos cubren ~9% de lo adjudicado.
- Consorcios y no domiciliados quedan fuera.
- Los antecedentes de los primeros cortes están subestimados (las listas cubren ~5 años).
- Un 0 en el target es "sanción no observada", no "cumplió"; Medina-Hernández et al. (2026) lo abordan con aprendizaje PU.
- Las probabilidades no están calibradas: sirven para ordenar.
- Solo hay un corte de validación y uno de prueba.

## Bibliografía

### Papers revisados

Cada integrante revisó uno de los cuatro papers (carpeta `papers/`). El notebook `03_modelos.ipynb` tiene una sección que compara nuestros resultados con los de cada uno.

- Sá, T. A., Pessanha, J. F. M., y Alves, F. J. dos S. (2024). Métodos de classificação supervisionada aplicados à identificação de fraudes de fornecedores. *Contabilometria, 11*(2), 125–146. [Artículo](https://revistas.fucamp.edu.br/index.php/contabilometria/article/view/3045).
- Fonseca, J. B. R., Garcia, L. F. P., y Caetano, M. F. (2024). Estimating the Risk of Failure in Government Auctions in Brazil. En *Anais do XXI Encontro Nacional de Inteligência Artificial e Computacional (ENIAC)* (pp. 637–646). Sociedade Brasileira de Computação. [DOI](https://doi.org/10.5753/eniac.2024.245280).
- Gallego, J., Rivero, G., y Martínez, J. (2021). Preventing rather than punishing: An early warning model of malfeasance in public procurement. *International Journal of Forecasting, 37*(1), 360–377. [DOI](https://doi.org/10.1016/j.ijforecast.2020.06.006).
- Medina-Hernández, M., Kertész, J., y Fazekas, M. (2026). Learning from sanctioned government suppliers: A machine learning and network science approach to detecting fraud and corruption in Mexico. *Scientific Reports, 16*, 22382. [Versión publicada](https://doi.org/10.1038/s41598-026-48873-w). Versión consultada inicialmente: [preprint de 2025, arXiv:2512.19491v2](https://arxiv.org/abs/2512.19491v2).

### Fuentes de datos

- Organismo Especializado para las Contrataciones Públicas Eficientes (OECE). (2026). *Portal de Datos Abiertos del OECE (CONOSCE)*: convocatorias, adjudicaciones, ofertantes, contratos, ampliaciones, arbitraje, penalidades, sancionados y entidades contratantes, 2022-2026 [Conjuntos de datos]. Recuperado en octubre-noviembre de 2026 de https://www.gob.pe/14272-acceder-al-portal-de-datos-abiertos-del-oece
- Organismo Especializado para las Contrataciones Públicas Eficientes (OECE), Registro Nacional de Proveedores. (2026). *Relación de proveedores sancionados por el Tribunal de Contrataciones Públicas de los últimos cinco años* [Reporte]. Descargado el 11 de octubre de 2026 de https://www.gob.pe/689-relacion-de-proveedores-sancionados-para-contratar-con-elestado
