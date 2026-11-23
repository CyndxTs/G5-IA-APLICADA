"""Implementación y entrenamiento de los 4 modelos.

Modelos (uno por integrante del grupo):
1. Regresión logística (baseline)
2. Árbol de decisión
3. KNN
4. MLP (red neuronal densa con TensorFlow/Keras, como en el curso)

El notebook ``notebooks/03_modelos.ipynb`` usa estas funciones paso a paso. También se
puede entrenar todo desde la raíz del repositorio:

    python src/models.py        # entrena y guarda los modelos en models/
    python src/evaluation.py    # evalúa los modelos guardados y genera results/

La carpeta ``models/`` no se sube a git: se regenera cada vez que se entrena.

Reglas:
- División temporal: entrenamiento hasta jun-2024, validación dic-2024, prueba jun-2025.
- Selección (cortes, hiperparámetros, umbral, época del MLP): se entrena solo con cortes cuyo
  target ya se conocía en la fecha de validación (ventana de 12 meses cerrada antes del
  31-dic-2024, es decir, cortes hasta dic-2023) y se mide en validación. Si usáramos el corte de
  jun-2024 para elegir, el modelo conocería sanciones de 2025 que en dic-2024 aún no ocurrían.
- Modelo final: se reentrena con lo elegido usando los cortes hasta jun-2024 (sus etiquetas ya
  se conocen el 30-jun-2025) y se evalúa una sola vez en prueba.
- La estandarización va dentro de cada modelo y se ajusta solo con entrenamiento.
"""

import json
import os
import shutil
import sys
from itertools import product
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")  # menos mensajes de TensorFlow

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

if __package__ in (None, ""):  # permite ejecutar "python src/models.py"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import preprocessing as pp  # noqa: E402

# ----------------------------------------------------------------------------
# Rutas y parámetros
# ----------------------------------------------------------------------------
ROOT = pp.ROOT
ARCHIVO_DATASET = pp.ARCHIVO_DATASET
MODELS_DIR = ROOT / "models"
SEMILLA = 42

COLUMNAS_ID = pp.COLUMNAS_ID
TARGET = "target"
COMPONENTES_TARGET = pp.COLUMNAS_TARGET[1:]
FIN_TRAIN, CORTE_VALIDACION, CORTE_PRUEBA = pp.FIN_TRAIN, pp.CORTE_VALIDACION, pp.CORTE_PRUEBA

NOMBRES = {"logistica": "Regresión logística", "arbol": "Árbol de decisión", "knn": "KNN", "mlp": "MLP"}
COLORES = {"logistica": "#2E86AB", "arbol": "#A23B72", "knn": "#ff7f0e", "mlp": "#2a9d8f"}

HORIZONTE_MESES = pp.HORIZONTE_MESES
# Último corte cuya ventana del target termina antes (o en) la fecha de validación
FIN_SELECCION = CORTE_VALIDACION - pd.DateOffset(months=HORIZONTE_MESES)

# Opciones de cortes para entrenar. Se aplican igual al conjunto de selección (hasta dic-2023)
# y al entrenamiento final (hasta jun-2024).
TOLERANCIA_CORTES = 0.002  # diferencia de PR-AUC promedio que tratamos como empate
OPCIONES_CORTES = {
    "todos los cortes": "todos",
    "sin los cortes de 2022": pd.Timestamp("2023-01-01"),
    "solo el último corte": "ultimo",
}

# Configuración base (para comparar opciones de cortes) y grillas de hiperparámetros
CONFIG_BASE = {
    "logistica": {"C": 0.01},
    "arbol": {"max_depth": 6, "min_samples_leaf": 100},
    "knn": {"n_neighbors": 101, "weights": "uniform"},
    "mlp": {"capas": (64, 32), "dropout": 0.2},
}
GRILLAS = {
    "logistica": {"C": [0.00001, 0.0001, 0.001, 0.01, 0.1, 1]},
    "arbol": {"max_depth": [3, 4, 6, 8, 10, 12], "min_samples_leaf": [50, 100, 200, 400, 800]},
    "knn": {"n_neighbors": [51, 101, 201, 401, 801, 1201, 1601, 2401], "weights": ["uniform", "distance"]},
    "mlp": {"capas": [(16,), (64, 32), (128, 64, 32), (256, 128, 64), (512, 256, 128)], "dropout": [0.0, 0.3, 0.5]},
}


# ----------------------------------------------------------------------------
# 1. Datos
# ----------------------------------------------------------------------------
def cargar_dataset(ruta=ARCHIVO_DATASET):
    df = pd.read_csv(ruta, dtype={"id_proveedor": "string"}, parse_dates=["fecha_corte"])
    return df


def predictoras(df):
    return [c for c in df.columns if c not in COLUMNAS_ID + [TARGET] + COMPONENTES_TARGET]


def dividir(df):
    """División temporal en entrenamiento, validación y prueba (más el subconjunto de selección)."""
    partes = {
        "entrenamiento": df[df["fecha_corte"] <= FIN_TRAIN],
        "validación": df[df["fecha_corte"] == CORTE_VALIDACION],
        "prueba": df[df["fecha_corte"] == CORTE_PRUEBA],
    }
    assert sum(len(p) for p in partes.values()) == len(df), "Hay cortes fuera de la división"
    partes["selección"] = partes["entrenamiento"][partes["entrenamiento"]["fecha_corte"] <= FIN_SELECCION]
    return {k: v.reset_index(drop=True) for k, v in partes.items()}


USO_CONJUNTOS = {
    "selección": "entrenar para elegir cortes, hiperparámetros, umbral y época",
    "validación": "medir y elegir (target conocido recién en dic-2025)",
    "entrenamiento": "entrenar los modelos finales",
    "prueba": "evaluación final, una sola vez",
}


def tabla_division(partes):
    orden = ["selección", "validación", "entrenamiento", "prueba"]
    return pd.DataFrame([{
        "conjunto": k, "cortes": ", ".join(str(c.date()) for c in sorted(partes[k]["fecha_corte"].unique())),
        "filas": len(partes[k]), "positivos": int(partes[k][TARGET].sum()),
        "prevalencia_%": round(partes[k][TARGET].mean() * 100, 2), "uso": USO_CONJUNTOS[k],
    } for k in orden]).set_index("conjunto")


def cortes_de(df, opcion):
    """Filtra los cortes de ``df`` según la opción (todos, desde una fecha o solo el último)."""
    regla = OPCIONES_CORTES[opcion]
    if regla == "todos":
        sub = df
    elif regla == "ultimo":
        sub = df[df["fecha_corte"] == df["fecha_corte"].max()]
    else:
        sub = df[df["fecha_corte"] >= regla]
    return sub.reset_index(drop=True)


# ----------------------------------------------------------------------------
# 2. Los 4 modelos
# ----------------------------------------------------------------------------
def construir_logistica(C=0.01):
    """Regresión logística con regularización L2. Necesita variables estandarizadas."""
    return Pipeline([("escalador", StandardScaler()),
                     ("modelo", LogisticRegression(C=C, class_weight="balanced", max_iter=3000, random_state=SEMILLA))])


def construir_arbol(max_depth=6, min_samples_leaf=100):
    """Árbol de decisión. No necesita estandarizar: cada división usa un umbral sobre una variable."""
    return Pipeline([("modelo", DecisionTreeClassifier(max_depth=max_depth, min_samples_leaf=min_samples_leaf,
                                                       class_weight="balanced", random_state=SEMILLA))])


def construir_knn(n_neighbors=101, weights="uniform"):
    """KNN: la distancia depende de la escala, así que estandarizamos. No admite pesos de clase."""
    return Pipeline([("escalador", StandardScaler()),
                     ("modelo", KNeighborsClassifier(n_neighbors=n_neighbors, weights=weights, n_jobs=-1))])


def _keras():
    """Importa Keras (solo cuando se usa el MLP) y silencia los avisos informativos de TensorFlow."""
    import tensorflow as tf

    tf.get_logger().setLevel("ERROR")
    return tf.keras


class MLPKeras(BaseEstimator, ClassifierMixin):
    """Perceptrón multicapa con TensorFlow/Keras (Sequential + Dense, como en el curso).

    - Entrada estandarizada (el escalador se ajusta solo con entrenamiento).
    - Capas ocultas Dense con ReLU y Dropout; salida Dense(1, sigmoid) porque el problema es binario.
    - Pérdida binary_crossentropy, optimizador Adam y pesos de clase para el desbalance.
    - Early stopping con el PR-AUC del corte de validación (no con validation_split, que mezclaría cortes).
    """

    def __init__(self, capas=(64, 32), dropout=0.2, learning_rate=1e-3, batch_size=512,
                 epocas_max=80, paciencia=8, semilla=SEMILLA):
        self.capas = capas
        self.dropout = dropout
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.epocas_max = epocas_max
        self.paciencia = paciencia
        self.semilla = semilla

    def _construir_red(self, n_entradas):
        keras = _keras()
        from tensorflow.keras.layers import Dense, Dropout, Input

        keras.utils.set_random_seed(self.semilla)
        capas = [Input(shape=(n_entradas,))]
        for i, unidades in enumerate(self.capas, start=1):
            capas.append(Dense(unidades, activation="relu", name=f"oculta_{i}"))
            if self.dropout > 0:
                capas.append(Dropout(self.dropout, name=f"dropout_{i}"))
        capas.append(Dense(1, activation="sigmoid", name="salida"))
        red = keras.Sequential(capas)
        red.compile(optimizer=keras.optimizers.Adam(learning_rate=self.learning_rate),
                    loss="binary_crossentropy", metrics=[keras.metrics.AUC(curve="PR", name="pr_auc")])
        return red

    def fit(self, X, y, X_val=None, y_val=None, verbose=0):
        keras = _keras()

        X, y = np.asarray(X, dtype="float32"), np.asarray(y, dtype="float32")
        self.escalador_ = StandardScaler().fit(X)
        self.red_ = self._construir_red(X.shape[1])
        n_pos, n_neg = y.sum(), len(y) - y.sum()
        pesos = {0: len(y) / (2 * n_neg), 1: len(y) / (2 * n_pos)}  # igual que class_weight="balanced"
        callbacks, validacion = [], None
        if X_val is not None:
            validacion = (self.escalador_.transform(np.asarray(X_val, dtype="float32")), np.asarray(y_val, dtype="float32"))
            callbacks.append(keras.callbacks.EarlyStopping(monitor="val_pr_auc", mode="max", patience=self.paciencia,
                                                           restore_best_weights=True))
        historia = self.red_.fit(self.escalador_.transform(X), y, epochs=self.epocas_max, batch_size=self.batch_size,
                                 validation_data=validacion, class_weight=pesos, callbacks=callbacks,
                                 verbose=verbose, shuffle=True)
        self.historia_ = {k: [float(v) for v in vals] for k, vals in historia.history.items()}
        self.mejor_epoca_ = int(np.argmax(self.historia_["val_pr_auc"]) + 1) if X_val is not None else len(historia.epoch)
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X):
        p = self.red_.predict(self.escalador_.transform(np.asarray(X, dtype="float32")), verbose=0,
                              batch_size=4096).ravel()
        return np.column_stack([1 - p, p])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)

    def n_parametros(self):
        return int(self.red_.count_params())


def construir_mlp(capas=(64, 32), dropout=0.2):
    return MLPKeras(capas=tuple(capas), dropout=dropout)


CONSTRUCTORES = {"logistica": construir_logistica, "arbol": construir_arbol, "knn": construir_knn, "mlp": construir_mlp}


def entrenar(nombre, params, X, y, X_val=None, y_val=None):
    modelo = CONSTRUCTORES[nombre](**params)
    if nombre == "mlp":
        return modelo.fit(X, y, X_val, y_val)
    return modelo.fit(X, y)


def proba(modelo, X):
    return modelo.predict_proba(X)[:, 1]


# ----------------------------------------------------------------------------
# 3. ¿Con qué cortes entrenar?
# ----------------------------------------------------------------------------
def comparar_cortes(partes, columnas, opciones=OPCIONES_CORTES, verbose=True):
    """Entrena los 4 modelos (configuración base) con cada opción de cortes del conjunto de
    selección y mide el PR-AUC en validación."""
    val = partes["validación"]
    filas = []
    for opcion in opciones:
        train = cortes_de(partes["selección"], opcion)
        fila = {"opcion": opcion, "cortes": ", ".join(str(c.date()) for c in sorted(train["fecha_corte"].unique())),
                "filas": len(train), "positivos": int(train[TARGET].sum())}
        for nombre in NOMBRES:
            modelo = entrenar(nombre, CONFIG_BASE[nombre], train[columnas], train[TARGET], val[columnas], val[TARGET])
            fila[NOMBRES[nombre]] = average_precision_score(val[TARGET], proba(modelo, val[columnas]))
        fila["promedio"] = np.mean([fila[NOMBRES[n]] for n in NOMBRES])
        filas.append(fila)
        if verbose:
            print(f"{opcion}: PR-AUC promedio en validación = {fila['promedio']:.4f}")
    tabla = pd.DataFrame(filas).set_index("opcion")
    # Si varias opciones quedan a menos de TOLERANCIA_CORTES del mejor promedio, la diferencia es
    # ruido: elegimos la que tiene más filas (más positivos, estimaciones más estables).
    empatadas = tabla[tabla["promedio"] >= tabla["promedio"].max() - TOLERANCIA_CORTES]
    return tabla, empatadas["filas"].idxmax()


# ----------------------------------------------------------------------------
# 4. Ajuste de hiperparámetros (en validación)
# ----------------------------------------------------------------------------
def _combinaciones(grilla):
    claves = list(grilla)
    return [dict(zip(claves, valores)) for valores in product(*grilla.values())]


def _texto_params(params):
    return ", ".join(f"{k}={v}" for k, v in params.items())


def ajustar_modelo(nombre, Xtr, ytr, Xva, yva, grilla=None, verbose=True):
    """Prueba cada combinación de la grilla y elige la de mayor PR-AUC en validación.

    Devuelve (tabla de resultados, mejor modelo entrenado, mejores parámetros, extras).
    Para KNN calculamos los vecinos de validación una sola vez (con el k más grande)
    y derivamos el resto de configuraciones; da el mismo resultado y es mucho más rápido.
    """
    grilla = grilla or GRILLAS[nombre]
    filas, modelos, extras = [], {}, {}
    if nombre == "knn":
        k_max = max(grilla["n_neighbors"])
        base = construir_knn(k_max).fit(Xtr, ytr)
        distancias, indices = base.named_steps["modelo"].kneighbors(base.named_steps["escalador"].transform(Xva))
        y_vecinos = np.asarray(ytr)[indices]
        for params in _combinaciones(grilla):
            k = params["n_neighbors"]
            if params["weights"] == "uniform":
                p = y_vecinos[:, :k].mean(axis=1)
            else:
                w = 1 / np.maximum(distancias[:, :k], 1e-12)
                p = (w * y_vecinos[:, :k]).sum(axis=1) / w.sum(axis=1)
            filas.append({**params, "configuracion": _texto_params(params), "pr_auc_entrenamiento": np.nan,
                          "pr_auc_validacion": average_precision_score(yva, p)})
    else:
        for params in _combinaciones(grilla):
            modelo = entrenar(nombre, params, Xtr, ytr, Xva, yva)
            clave = _texto_params(params)
            modelos[clave] = modelo
            fila = {**params, "configuracion": clave,
                    "pr_auc_entrenamiento": average_precision_score(ytr, proba(modelo, Xtr)),
                    "pr_auc_validacion": average_precision_score(yva, proba(modelo, Xva))}
            if nombre == "mlp":
                fila.update({"mejor_epoca": modelo.mejor_epoca_, "parametros_red": modelo.n_parametros()})
                extras[clave] = modelo.historia_
            filas.append(fila)
            if verbose:
                print(f"  {NOMBRES[nombre]} [{clave}]: PR-AUC val = {fila['pr_auc_validacion']:.4f}")
    tabla = pd.DataFrame(filas)
    mejor = tabla.loc[tabla["pr_auc_validacion"].idxmax()]
    mejores_params = {k: (mejor[k].item() if hasattr(mejor[k], "item") else mejor[k]) for k in grilla}
    if nombre == "knn":
        mejores_params["n_neighbors"] = int(mejores_params["n_neighbors"])
        modelo_final = construir_knn(**mejores_params).fit(Xtr, ytr)
    else:
        if nombre == "arbol" and pd.isna(mejores_params.get("max_depth")):
            mejores_params["max_depth"] = None
        modelo_final = modelos[mejor["configuracion"]]
    tabla["elegida"] = tabla["configuracion"] == mejor["configuracion"]
    return tabla, modelo_final, mejores_params, extras


def ajustar_todos(train, val, columnas, verbose=True):
    resultados = {}
    for nombre in NOMBRES:
        if verbose:
            print(f"Ajustando {NOMBRES[nombre]}...")
        resultados[nombre] = ajustar_modelo(nombre, train[columnas], train[TARGET], val[columnas], val[TARGET],
                                            verbose=verbose)
    return resultados


# ----------------------------------------------------------------------------
# 5. Modelos finales
# ----------------------------------------------------------------------------
def entrenar_finales(partes, opcion, ajustes, columnas, verbose=True):
    """Reentrena cada modelo con sus hiperparámetros elegidos usando los cortes de entrenamiento
    (hasta jun-2024) de la opción elegida. El MLP usa el número de épocas elegido en validación."""
    train = cortes_de(partes["entrenamiento"], opcion)
    finales = {}
    for nombre, (_, _, params, _) in ajustes.items():
        if nombre == "mlp":
            modelo = MLPKeras(capas=tuple(params["capas"]), dropout=params["dropout"],
                              epocas_max=ajustes["mlp"][1].mejor_epoca_)
            finales[nombre] = modelo.fit(train[columnas], train[TARGET])
        else:
            finales[nombre] = entrenar(nombre, params, train[columnas], train[TARGET])
        if verbose:
            print(f"  {NOMBRES[nombre]} final entrenado con {len(train):,} filas")
    return finales, train


# ----------------------------------------------------------------------------
# 6. Guardar y cargar
# ----------------------------------------------------------------------------
def _json(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, tuple):
        return list(obj)
    return str(obj)


def _guardar_modelo(modelo, nombre, carpeta):
    if nombre == "mlp":
        modelo.red_.save(carpeta / "mlp.keras")
        joblib.dump({"escalador": modelo.escalador_, "params": modelo.get_params(), "historia": modelo.historia_,
                     "mejor_epoca": modelo.mejor_epoca_}, carpeta / "mlp_escalador.joblib")
    else:
        joblib.dump(modelo, carpeta / f"{nombre}.joblib")


def guardar_modelos(finales, ajustes, columnas, tabla_cortes, opcion_cortes, p_validacion, train_final):
    """Guarda los 4 modelos finales, las probabilidades de validación de los modelos de selección
    y la información del entrenamiento en models/ (reemplaza lo anterior)."""
    if MODELS_DIR.exists():
        shutil.rmtree(MODELS_DIR)
    MODELS_DIR.mkdir(parents=True)
    for nombre, modelo in finales.items():
        _guardar_modelo(modelo, nombre, MODELS_DIR)
    pd.DataFrame(p_validacion).to_csv(MODELS_DIR / "probabilidades_validacion.csv", index=False)
    info = {
        "predictoras": columnas, "opcion_cortes": opcion_cortes,
        "cortes_entrenamiento_final": sorted(str(c.date()) for c in train_final["fecha_corte"].unique()),
        "mejores_parametros": {n: a[2] for n, a in ajustes.items()},
        "epocas_mlp": ajustes["mlp"][1].mejor_epoca_,
        "tabla_cortes": tabla_cortes.reset_index().to_dict(orient="records"),
        "ajuste": {n: a[0].to_dict(orient="records") for n, a in ajustes.items()},
        "historias_mlp": ajustes["mlp"][3],
    }
    (MODELS_DIR / "entrenamiento.json").write_text(json.dumps(info, default=_json, ensure_ascii=False, indent=1),
                                                    encoding="utf-8")
    return sorted(p.name for p in MODELS_DIR.iterdir())


def cargar_modelos():
    """Carga los modelos finales, las probabilidades de validación y la información del entrenamiento."""
    keras = _keras()

    info = json.loads((MODELS_DIR / "entrenamiento.json").read_text(encoding="utf-8"))
    modelos = {n: joblib.load(MODELS_DIR / f"{n}.joblib") for n in ["logistica", "arbol", "knn"]}
    extra = joblib.load(MODELS_DIR / "mlp_escalador.joblib")
    mlp = MLPKeras(**extra["params"])
    mlp.red_, mlp.escalador_ = keras.models.load_model(MODELS_DIR / "mlp.keras"), extra["escalador"]
    mlp.historia_, mlp.mejor_epoca_, mlp.classes_ = extra["historia"], extra["mejor_epoca"], np.array([0, 1])
    modelos["mlp"] = mlp
    modelos = {n: modelos[n] for n in NOMBRES}
    p_val = pd.read_csv(MODELS_DIR / "probabilidades_validacion.csv")
    return modelos, {n: p_val[n].to_numpy() for n in NOMBRES}, info


# ----------------------------------------------------------------------------
# Ejecución completa
# ----------------------------------------------------------------------------
def main():
    """Elige cortes e hiperparámetros en validación, entrena los modelos finales y los guarda en models/."""
    df = cargar_dataset()
    columnas = predictoras(df)
    partes = dividir(df)
    print(tabla_division(partes).to_string())
    print("\n1. Comparando opciones de cortes de entrenamiento (en validación)")
    tabla_cortes, opcion = comparar_cortes(partes, columnas)
    print(f"Opción elegida: {opcion}")
    print("\n2. Ajustando hiperparámetros (en validación)")
    ajustes = ajustar_todos(cortes_de(partes["selección"], opcion), partes["validación"], columnas)
    for nombre, (tabla, _, params, _) in ajustes.items():
        print(f"{NOMBRES[nombre]}: {params} | PR-AUC val = {tabla['pr_auc_validacion'].max():.4f}")
    p_val = {n: proba(a[1], partes["validación"][columnas]) for n, a in ajustes.items()}
    print("\n3. Entrenando los modelos finales")
    finales, train_final = entrenar_finales(partes, opcion, ajustes, columnas)
    print("\n4. Guardando en models/:", guardar_modelos(finales, ajustes, columnas, tabla_cortes, opcion, p_val, train_final))


if __name__ == "__main__":
    main()
