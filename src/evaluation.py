"""Métricas, evaluación y resultados de los 4 modelos.

El notebook ``notebooks/03_modelos.ipynb`` usa estas funciones paso a paso. También se
puede evaluar desde la raíz del repositorio, con los modelos ya entrenados en models/:

    python src/models.py        # entrena y guarda los modelos
    python src/evaluation.py    # evalúa y genera results/

Salidas (se reemplazan en cada ejecución):
- ``results/metrics.csv``: tabla comparativa de métricas (validación y prueba).
- ``results/model_comparison.txt``: resumen de resultados y análisis.
- ``results/plots/modeling/``: gráficos (seleccion/, evaluacion/, interpretacion/).
- ``results/summaries/modeling/``: ``resumen.md`` y ``tables/`` con las tablas que muestra.
"""

import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix, f1_score,
                             precision_recall_curve, precision_score, recall_score, roc_auc_score, roc_curve)
from sklearn.tree import export_text, plot_tree

if __package__ in (None, ""):  # permite ejecutar "python src/evaluation.py"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import models as m  # noqa: E402
from src import preprocessing as pp  # noqa: E402

# ----------------------------------------------------------------------------
# Rutas y parámetros
# ----------------------------------------------------------------------------
ROOT = m.ROOT
RESULTS = ROOT / "results"
PLOTS_DIR = RESULTS / "plots" / "modeling"
SUMMARY_DIR = RESULTS / "summaries" / "modeling"
METRICS_CSV = RESULTS / "metrics.csv"
COMPARISON_TXT = RESULTS / "model_comparison.txt"

FRACCION_REVISION = 0.10  # capacidad de revisión supuesta: el 10% de proveedores con más riesgo
N_BOOTSTRAP = 1000
SEMILLA = m.SEMILLA
NOMBRES, COLORES = m.NOMBRES, m.COLORES
BASELINE = "logistica"

FIGURAS = {
    "cortes": "seleccion/comparacion_de_cortes_de_entrenamiento.png",
    "ajuste": "seleccion/ajuste_de_hiperparametros.png",
    "mlp": "seleccion/curvas_de_entrenamiento_mlp.png",
    "curvas": "evaluacion/curvas_precision_recall_y_roc_prueba.png",
    "captura": "evaluacion/sancionados_encontrados_segun_revision_prueba.png",
    "confusion": "evaluacion/matrices_de_confusion_prueba.png",
    "intervalos": "evaluacion/intervalos_de_confianza_prueba.png",
    "importancia": "interpretacion/importancia_por_grupo_de_variables.png",
    "coeficientes": "interpretacion/coeficientes_logistica_e_importancia_arbol.png",
    "arbol": "interpretacion/primeros_niveles_del_arbol.png",
    "subgrupos": "interpretacion/deteccion_por_subgrupo_prueba.png",
}
TITULOS_FIGURAS = {
    "cortes": "Comparación de cortes de entrenamiento (validación)",
    "ajuste": "Ajuste de hiperparámetros (validación)",
    "mlp": "Curvas de entrenamiento del MLP",
    "curvas": "Curvas precision-recall y ROC (prueba)",
    "captura": "Sancionados encontrados según el % revisado (prueba)",
    "confusion": "Matrices de confusión (prueba)",
    "intervalos": "Intervalos de confianza al 95% (prueba)",
    "importancia": "Importancia por grupo de variables (validación)",
    "coeficientes": "Coeficientes de la regresión logística e importancia del árbol",
    "arbol": "Primeros niveles del árbol de decisión",
    "subgrupos": "Detección por subgrupo (prueba)",
}
TABLAS = {
    "division": "tables/division_temporal.csv",
    "cortes": "tables/comparacion_de_cortes.csv",
    "ajuste": "tables/ajuste_de_hiperparametros.csv",
    "intervalos": "tables/intervalos_de_confianza_prueba.csv",
    "baseline": "tables/comparacion_con_baseline_prueba.csv",
    "importancia": "tables/importancia_por_grupo.csv",
    "subgrupos": "tables/deteccion_por_subgrupo_prueba.csv",
}


def limpiar_salidas():
    """Borra los resultados anteriores de esta fase para que no queden versiones viejas."""
    for carpeta in (PLOTS_DIR, SUMMARY_DIR):
        if carpeta.exists():
            shutil.rmtree(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
    for archivo in (METRICS_CSV, COMPARISON_TXT):
        archivo.unlink(missing_ok=True)


def guardar_figura(fig, clave):
    ruta = PLOTS_DIR / FIGURAS[clave]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, dpi=150, bbox_inches="tight")


def guardar_tabla(df, clave, index=False):
    ruta = SUMMARY_DIR / TABLAS[clave]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=index, encoding="utf-8-sig")


def _estilo(ax, titulo, eje="both"):
    ax.set_title(titulo, fontsize=12, fontweight="bold")
    ax.grid(axis=eje, alpha=0.3)


# ----------------------------------------------------------------------------
# 1. Métricas
# ----------------------------------------------------------------------------
def top_k(p, fraccion=FRACCION_REVISION):
    """Índices del ``fraccion`` de filas con mayor probabilidad (los que se revisarían)."""
    k = max(1, int(round(fraccion * len(p))))
    return np.argsort(-p, kind="stable")[:k]


def recall_top(y, p, fraccion=FRACCION_REVISION):
    y = np.asarray(y)
    return y[top_k(p, fraccion)].sum() / y.sum()


def precision_top(y, p, fraccion=FRACCION_REVISION):
    return np.asarray(y)[top_k(p, fraccion)].mean()


def mejor_umbral(y, p):
    """Umbral que maximiza el F1 (se elige en validación y se aplica tal cual en prueba)."""
    prec, rec, umbrales = precision_recall_curve(y, p)
    f1 = 2 * prec[:-1] * rec[:-1] / np.clip(prec[:-1] + rec[:-1], 1e-12, None)
    return float(umbrales[np.argmax(f1)])


def metricas(y, p, umbral):
    y = np.asarray(y)
    pred = (p >= umbral).astype(int)
    prevalencia = y.mean()
    return {
        "PR-AUC": average_precision_score(y, p),
        "PR-AUC / azar": average_precision_score(y, p) / prevalencia,
        "ROC-AUC": roc_auc_score(y, p),
        "Recall top 10%": recall_top(y, p),
        "Precision top 10%": precision_top(y, p),
        "Lift top 10%": precision_top(y, p) / prevalencia,
        "Umbral": umbral,
        "Alertas": int(pred.sum()),
        "% alertas": pred.mean() * 100,
        "Precision": precision_score(y, pred, zero_division=0),
        "Recall": recall_score(y, pred, zero_division=0),
        "F1": f1_score(y, pred, zero_division=0),
        "Brier": brier_score_loss(y, p),
    }


def probabilidades(modelos, X):
    return {n: m.proba(modelo, X) for n, modelo in modelos.items()}


def tabla_metricas(modelos, p_val, partes, columnas):
    """Métricas en validación (modelos de selección) y en prueba (modelos finales).

    El umbral se elige en validación (máximo F1) y se traslada a prueba como porcentaje de
    alertas: el modelo final se entrena con otros cortes y sus puntajes cambian de escala, pero
    la proporción de proveedores a marcar sí se puede mantener."""
    val, test = partes["validación"], partes["prueba"]
    p_test = probabilidades(modelos, test[columnas])
    umbrales, filas = {}, []
    for n in modelos:
        u_val = mejor_umbral(val[m.TARGET], p_val[n])
        fraccion = (p_val[n] >= u_val).mean()
        umbrales[n] = float(np.quantile(p_test[n], 1 - fraccion))
        filas.append({"Modelo": NOMBRES[n], "Conjunto": "Validación", **metricas(val[m.TARGET], p_val[n], u_val)})
        filas.append({"Modelo": NOMBRES[n], "Conjunto": "Prueba", **metricas(test[m.TARGET], p_test[n], umbrales[n])})
    return pd.DataFrame(filas), p_test, umbrales


# ----------------------------------------------------------------------------
# 2. Incertidumbre: bootstrap en prueba
# ----------------------------------------------------------------------------
METRICAS_BOOTSTRAP = {"PR-AUC": average_precision_score, "ROC-AUC": roc_auc_score, "Recall top 10%": recall_top}


def bootstrap(y, probs, n=N_BOOTSTRAP, semilla=SEMILLA):
    """Remuestrea las filas de prueba con reemplazo ``n`` veces (las mismas filas para todos
    los modelos) y devuelve los valores de cada métrica por remuestreo."""
    y = np.asarray(y)
    rng = np.random.default_rng(semilla)
    muestras = {(modelo, metrica): [] for modelo in probs for metrica in METRICAS_BOOTSTRAP}
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].sum() == 0:
            continue
        for modelo, p in probs.items():
            for metrica, f in METRICAS_BOOTSTRAP.items():
                muestras[(modelo, metrica)].append(f(y[idx], p[idx]))
    return {k: np.array(v) for k, v in muestras.items()}


def intervalos(y, probs, muestras):
    filas = []
    for modelo, p in probs.items():
        for metrica, f in METRICAS_BOOTSTRAP.items():
            v = muestras[(modelo, metrica)]
            filas.append({"Modelo": NOMBRES[modelo], "Métrica": metrica, "Valor": f(np.asarray(y), p),
                          "IC 95% inferior": np.percentile(v, 2.5), "IC 95% superior": np.percentile(v, 97.5)})
    return pd.DataFrame(filas)


def comparacion_baseline(muestras, probs, y, baseline=BASELINE):
    """Diferencia de cada modelo frente al baseline con intervalo pareado (mismos remuestreos)."""
    filas = []
    for modelo in probs:
        if modelo == baseline:
            continue
        for metrica, f in METRICAS_BOOTSTRAP.items():
            dif = muestras[(modelo, metrica)] - muestras[(baseline, metrica)]
            real = f(np.asarray(y), probs[modelo]) - f(np.asarray(y), probs[baseline])
            bajo, alto = np.percentile(dif, [2.5, 97.5])
            filas.append({"Modelo": NOMBRES[modelo], "Métrica": metrica, "Diferencia vs baseline": real,
                          "IC 95% inferior": bajo, "IC 95% superior": alto,
                          "% remuestreos en que gana al baseline": (dif > 0).mean() * 100,
                          "Conclusión": ("mejor que el baseline" if bajo > 0 else
                                         "peor que el baseline" if alto < 0 else "sin diferencia clara")})
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------------
# 3. Interpretación
# ----------------------------------------------------------------------------
def grupos_de_variables(columnas):
    """Grupo de cada predictora según el catálogo del preprocesamiento."""
    return {c: pp.CATALOGO[c.removeprefix("log_")][0] for c in columnas}


def importancia_por_grupo(modelos, val, columnas, n_muestra=12000, repeticiones=3, semilla=SEMILLA):
    """Importancia por permutación por grupo de variables: cuánto cae el PR-AUC en validación
    si se desordenan juntas todas las variables de un grupo. Misma medida para los 4 modelos.
    Se usa una muestra de validación para que KNN no tarde demasiado."""
    rng = np.random.default_rng(semilla)
    muestra = val.sample(min(n_muestra, len(val)), random_state=semilla).reset_index(drop=True)
    X, y = muestra[columnas], muestra[m.TARGET]
    grupos = pd.Series(grupos_de_variables(columnas))
    filas = []
    for nombre, modelo in modelos.items():
        base = average_precision_score(y, m.proba(modelo, X))
        for grupo, cols in grupos.groupby(grupos).groups.items():
            caidas = []
            for _ in range(repeticiones):
                Xp = X.copy()
                orden = rng.permutation(len(Xp))
                Xp[list(cols)] = Xp[list(cols)].to_numpy()[orden]
                caidas.append(base - average_precision_score(y, m.proba(modelo, Xp)))
            filas.append({"Modelo": NOMBRES[nombre], "Grupo": grupo, "Variables": len(cols),
                          "Caída de PR-AUC": np.mean(caidas), "Caída relativa %": np.mean(caidas) / base * 100})
    return pd.DataFrame(filas)


def coeficientes_logistica(modelo, columnas):
    return pd.Series(modelo.named_steps["modelo"].coef_[0], index=columnas).sort_values()


def importancia_arbol(modelo, columnas):
    return pd.Series(modelo.named_steps["modelo"].feature_importances_, index=columnas).sort_values()


def reglas_arbol(modelo, columnas, profundidad=3):
    return export_text(modelo.named_steps["modelo"], feature_names=list(columnas), max_depth=profundidad, decimals=2)


def deteccion_por_subgrupo(test, p_test, fraccion=FRACCION_REVISION):
    """Si se revisa el top 10% de cada modelo: qué % de los sancionados de cada subgrupo se encuentra."""
    tope = np.log1p(pp.TOPE_DIAS)  # el CSV guarda 6 cifras: comparamos con tolerancia
    subgrupos = {
        "Con sanción previa": test["log_dias_desde_ultima_sancion"] < tope - 1e-4,
        "Sin sanción previa": test["log_dias_desde_ultima_sancion"] >= tope - 1e-4,
        "Persona jurídica": test["persona_juridica"] == 1,
        "Persona natural": test["persona_juridica"] == 0,
        "Sancionado con inhabilitación": test[m.COMPONENTES_TARGET[0]] == 1,
        "Sancionado con multa": test[m.COMPONENTES_TARGET[1]] == 1,
    }
    y = test[m.TARGET].to_numpy()
    filas = []
    for nombre, p in p_test.items():
        revisados = np.zeros(len(p), dtype=bool)
        revisados[top_k(p, fraccion)] = True
        for sub, mascara in subgrupos.items():
            mascara = mascara.to_numpy()
            positivos = (y == 1) & mascara
            filas.append({"Modelo": NOMBRES[nombre], "Subgrupo": sub, "Sancionados": int(positivos.sum()),
                          "% de todos los sancionados": positivos.sum() / y.sum() * 100,
                          "Encontrados en el top 10%": int((positivos & revisados).sum()),
                          "% encontrado": (positivos & revisados).sum() / max(positivos.sum(), 1) * 100})
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------------
# 4. Gráficos
# ----------------------------------------------------------------------------
def graficar_cortes(tabla_cortes, elegida):
    t = tabla_cortes[[NOMBRES[n] for n in NOMBRES] + ["promedio"]]
    fig, ax = plt.subplots(figsize=(11, 4.2))
    x = np.arange(len(t.columns))
    ancho = 0.8 / len(t)
    for i, (opcion, fila) in enumerate(t.iterrows()):
        ax.bar(x + i * ancho, fila.values, width=ancho, label=opcion + (" (elegida)" if opcion == elegida else ""),
               color=["#c0c0c0", m.COLORES["logistica"], m.COLORES["mlp"]][i % 3], edgecolor="black" if opcion == elegida else None)
    ax.set_xticks(x + ancho * (len(t) - 1) / 2)
    ax.set_xticklabels(t.columns)
    ax.set_ylabel("PR-AUC en validación")
    ax.legend(fontsize=9, ncol=len(t), loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False)
    _estilo(ax, "¿Con qué cortes entrenar? (configuración base de cada modelo)", "y")
    fig.tight_layout()
    guardar_figura(fig, "cortes")
    return fig


def graficar_ajuste(ajustes, prevalencia_val):
    fig, axes = plt.subplots(1, 4, figsize=(21, 4.5))
    # Regresión logística: C
    t = ajustes["logistica"][0]
    ax = axes[0]
    ax.plot(t["C"].astype(str), t["pr_auc_entrenamiento"], marker="o", label="Entrenamiento", color="#1f77b4")
    ax.plot(t["C"].astype(str), t["pr_auc_validacion"], marker="s", label="Validación", color="#ff7f0e")
    ax.set_xlabel("C (más alto = menos regularización)")
    # Árbol: profundidad x hoja (validación)
    t = ajustes["arbol"][0]
    for hoja, g in t.groupby("min_samples_leaf"):
        axes[1].plot(g["max_depth"].astype(str), g["pr_auc_validacion"], marker="o", label=f"min_samples_leaf={hoja}")
    axes[1].set_xlabel("max_depth (profundidad máxima)")
    # KNN: k x pesos (validación)
    t = ajustes["knn"][0]
    for pesos, g in t.groupby("weights"):
        axes[2].plot(g["n_neighbors"].astype(str), g["pr_auc_validacion"], marker="o", label=f"weights={pesos}")
    axes[2].set_xlabel("k (número de vecinos)")
    # MLP: arquitectura x dropout
    t = ajustes["mlp"][0]
    for drop, g in t.groupby("dropout"):
        axes[3].plot(g["capas"].astype(str), g["pr_auc_validacion"], marker="o", label=f"dropout={drop}")
    axes[3].set_xlabel("capas ocultas (neuronas por capa)")
    for ax, nombre in zip(axes, NOMBRES):
        ax.axhline(prevalencia_val, color="gray", linestyle="--", alpha=0.6, label="azar (prevalencia)")
        ax.set_ylabel("PR-AUC")
        ax.legend(fontsize=8)
        ax.tick_params(axis="x", rotation=30)
        _estilo(ax, NOMBRES[nombre])
    fig.tight_layout()
    guardar_figura(fig, "ajuste")
    return fig


def graficar_mlp(historias, mejor):
    """Curvas de la configuración elegida (pérdida y PR-AUC, como en los notebooks de clase) y el
    PR-AUC de validación de todas las configuraciones."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 4.6))
    h = historias[mejor]
    epocas = range(1, len(h["loss"]) + 1)
    mejor_epoca = int(np.argmax(h["val_pr_auc"]) + 1)
    for ax, clave, ylabel in [(axes[0], "loss", "Pérdida (binary crossentropy)"), (axes[1], "pr_auc", "PR-AUC")]:
        ax.plot(epocas, h[clave], label="Entrenamiento", color="#1f77b4")
        ax.plot(epocas, h["val_" + clave], label="Validación", color="#ff7f0e", linestyle="--")
        ax.axvline(mejor_epoca, color="black", linestyle=":", alpha=0.6, label=f"mejor época ({mejor_epoca})")
        ax.set_xlabel("Época")
        ax.set_ylabel(ylabel)
        ax.legend(fontsize=9)
        _estilo(ax, f"{ylabel.split(' ')[0]} - configuración elegida")
    for config, hh in historias.items():
        elegida = config == mejor
        axes[2].plot(range(1, len(hh["val_pr_auc"]) + 1), hh["val_pr_auc"], linewidth=2.5 if elegida else 1,
                     alpha=1 if elegida else 0.45, color=m.COLORES["mlp"] if elegida else None,
                     label=config + (" (elegida)" if elegida else ""))
    axes[2].set_xlabel("Época")
    axes[2].set_ylabel("PR-AUC en validación")
    axes[2].legend(fontsize=6.5, ncol=2)
    _estilo(axes[2], "Todas las configuraciones (validación)")
    fig.suptitle(f"MLP: curvas de entrenamiento ({mejor})", fontsize=13, fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "mlp")
    return fig


def graficar_curvas(y, probs, tabla_prueba):
    azar = np.mean(y)
    fig, ax = plt.subplots(1, 2, figsize=(14, 5.5))
    for n, p in probs.items():
        prec, rec, _ = precision_recall_curve(y, p)
        ax[0].plot(rec, prec, color=COLORES[n], lw=2, label=f"{NOMBRES[n]} (PR-AUC={tabla_prueba.loc[NOMBRES[n], 'PR-AUC']:.3f})")
        fpr, tpr, _ = roc_curve(y, p)
        ax[1].plot(fpr, tpr, color=COLORES[n], lw=2, label=f"{NOMBRES[n]} (AUC={tabla_prueba.loc[NOMBRES[n], 'ROC-AUC']:.3f})")
    ax[0].axhline(azar, color="black", linestyle="--", alpha=0.4, label=f"Azar ({azar:.3f})")
    ax[0].set_xlabel("Recall")
    ax[0].set_ylabel("Precision")
    ax[0].legend(fontsize=9)
    _estilo(ax[0], "Curvas precision-recall (prueba)")
    ax[1].plot([0, 1], [0, 1], "k--", alpha=0.3, label="Clasificador aleatorio")
    ax[1].set_xlabel("Tasa de falsos positivos")
    ax[1].set_ylabel("Tasa de verdaderos positivos")
    ax[1].legend(loc="lower right", fontsize=9)
    _estilo(ax[1], "Curvas ROC (prueba)")
    fig.tight_layout()
    guardar_figura(fig, "curvas")
    return fig


def curva_captura(y, p, puntos=101):
    y = np.asarray(y)
    orden = np.argsort(-p, kind="stable")
    acumulado = np.concatenate([[0], np.cumsum(y[orden])]) / y.sum()
    fracciones = np.linspace(0, 1, puntos)
    return fracciones, acumulado[(fracciones * len(y)).round().astype(int)]


def graficar_captura(y, probs):
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    for n, p in probs.items():
        f, c = curva_captura(y, p)
        ax.plot(f * 100, c * 100, color=COLORES[n], lw=2, label=NOMBRES[n])
    ax.plot([0, 100], [0, 100], "k--", alpha=0.4, label="Azar")
    ax.axvline(FRACCION_REVISION * 100, color="gray", linestyle=":", label=f"revisar el {FRACCION_REVISION:.0%}")
    ax.set_xlabel("% de proveedores revisados (de mayor a menor riesgo)")
    ax.set_ylabel("% de los sancionados encontrados")
    ax.legend()
    _estilo(ax, "¿Cuántos sancionados encontramos según cuánto revisamos? (prueba)")
    fig.tight_layout()
    guardar_figura(fig, "captura")
    return fig


def graficar_confusion(y, probs, umbrales):
    fig, axes = plt.subplots(1, len(probs), figsize=(4.3 * len(probs), 3.9))
    for ax, (n, p) in zip(axes, probs.items()):
        cm = confusion_matrix(y, (p >= umbrales[n]).astype(int), labels=[0, 1])
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False, ax=ax,
                    xticklabels=["No sanc.", "Sancionado"], yticklabels=["No sanc.", "Sancionado"])
        ax.set_title(NOMBRES[n], fontsize=11, fontweight="bold")
        ax.set_xlabel("Predicción")
        ax.set_ylabel("Real")
    fig.tight_layout()
    guardar_figura(fig, "confusion")
    return fig


def graficar_intervalos(tabla_ic, prevalencia):
    metricas_ = list(METRICAS_BOOTSTRAP)
    fig, axes = plt.subplots(1, len(metricas_), figsize=(17, 3.8))
    for ax, metrica in zip(axes, metricas_):
        t = tabla_ic[tabla_ic["Métrica"] == metrica].iloc[::-1]
        for i, (_, fila) in enumerate(t.iterrows()):
            color = COLORES[[k for k, v in NOMBRES.items() if v == fila["Modelo"]][0]]
            valor, bajo, alto = fila["Valor"], fila["IC 95% inferior"], fila["IC 95% superior"]
            ax.errorbar(valor, i, xerr=[[valor - bajo], [alto - valor]], fmt="o", color=color, capsize=5, markersize=7)
        ax.set_yticks(range(len(t)))
        ax.set_yticklabels(t["Modelo"])
        if metrica == "PR-AUC":
            ax.axvline(prevalencia, color="gray", linestyle="--", alpha=0.6, label="azar")
            ax.legend(fontsize=8)
        if metrica == "Recall top 10%":
            ax.axvline(FRACCION_REVISION, color="gray", linestyle="--", alpha=0.6, label="azar")
            ax.legend(fontsize=8)
        ax.set_xlabel(metrica)
        _estilo(ax, metrica, "x")
    fig.suptitle("Valor en prueba e intervalo de confianza al 95% (bootstrap)", fontsize=13, fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "intervalos")
    return fig


def graficar_importancia(tabla_imp):
    t = tabla_imp.pivot(index="Grupo", columns="Modelo", values="Caída relativa %")[[NOMBRES[n] for n in NOMBRES]]
    t = t.loc[t.mean(axis=1).sort_values(ascending=False).index]
    fig, ax = plt.subplots(figsize=(9, 6))
    sns.heatmap(t, annot=True, fmt=".1f", cmap="Oranges", ax=ax, cbar_kws={"label": "caída del PR-AUC (%)"})
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_title("¿Cuánto empeora cada modelo si desordenamos un grupo de variables?", fontsize=12, fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "importancia")
    return fig


def graficar_coeficientes(coef, imp_arbol, n=12):
    fig, ax = plt.subplots(1, 2, figsize=(16, 6))
    top = coef.reindex(coef.abs().sort_values(ascending=False).index[:n]).sort_values()
    ax[0].barh(top.index, top.values, color=[COLORES["arbol"] if v < 0 else COLORES["logistica"] for v in top.values])
    ax[0].axvline(0, color="black", lw=0.8)
    ax[0].set_xlabel("Coeficiente (variables estandarizadas)")
    _estilo(ax[0], f"Regresión logística: {n} coeficientes más grandes", "x")
    top = imp_arbol.sort_values(ascending=False)[:n].sort_values()
    ax[1].barh(top.index, top.values, color=COLORES["arbol"])
    ax[1].set_xlabel("Importancia (reducción de impureza)")
    _estilo(ax[1], f"Árbol de decisión: {n} variables más importantes", "x")
    for a in ax:
        a.tick_params(axis="y", labelsize=9)
    fig.tight_layout()
    guardar_figura(fig, "coeficientes")
    return fig


def graficar_arbol(modelo, columnas, profundidad=2):
    fig, ax = plt.subplots(figsize=(20, 8))
    plot_tree(modelo.named_steps["modelo"], feature_names=list(columnas), class_names=["no sanc.", "sancionado"],
              max_depth=profundidad, filled=True, impurity=False, proportion=True, rounded=True, fontsize=9, ax=ax)
    ax.set_title(f"Árbol de decisión: primeros {profundidad} niveles (proporciones con pesos de clase)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "arbol")
    return fig


def graficar_subgrupos(tabla_sub):
    t = tabla_sub.pivot(index="Subgrupo", columns="Modelo", values="% encontrado")[[NOMBRES[n] for n in NOMBRES]]
    t = t.loc[tabla_sub["Subgrupo"].unique()]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    t.plot.barh(ax=ax, color=[COLORES[n] for n in NOMBRES], width=0.8)
    ax.invert_yaxis()
    ax.axvline(FRACCION_REVISION * 100, color="gray", linestyle="--", label="azar (10%)")
    ax.set_xlabel("% de los sancionados del subgrupo que entra al top 10% de riesgo")
    ax.set_ylabel("")
    ax.legend(fontsize=9, loc="lower right")
    _estilo(ax, "¿A quiénes encuentra cada modelo? (prueba)", "x")
    fig.tight_layout()
    guardar_figura(fig, "subgrupos")
    return fig


# ----------------------------------------------------------------------------
# 5. Resultados escritos
# ----------------------------------------------------------------------------
def _md(df, index=False, decimales=4):
    df = df.reset_index() if index else df.copy()
    df = df.apply(lambda col: col.round(decimales) if col.dtype.kind == "f" else col)
    df = df.map(lambda v: "" if (not isinstance(v, (tuple, list)) and pd.isna(v)) else str(v).replace("|", "\\|"))
    lineas = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * df.shape[1]]
    return "\n".join(lineas + ["| " + " | ".join(fila) + " |" for fila in df.to_numpy()])


def textos_de_analisis(r):
    """Frases de análisis calculadas a partir de los resultados (las usan el .txt y el resumen)."""
    prueba = r["metricas"][r["metricas"]["Conjunto"] == "Prueba"].set_index("Modelo")
    val = r["metricas"][r["metricas"]["Conjunto"] == "Validación"].set_index("Modelo")
    mejor = prueba["PR-AUC"].idxmax()
    base = NOMBRES[BASELINE]
    azar = r["prevalencia_prueba"]
    comp = r["baseline"]
    comp_pr = comp[comp["Métrica"] == "PR-AUC"].set_index("Modelo")
    imp = r["importancia"].groupby("Grupo")["Caída relativa %"].mean().sort_values(ascending=False)
    sub = r["subgrupos"][r["subgrupos"]["Modelo"] == mejor].set_index("Subgrupo")
    return {
        "mejor": mejor, "base": base, "azar": azar, "prueba": prueba, "val": val, "comp_pr": comp_pr,
        "grupos_top": imp.index[:3].tolist(), "sub": sub,
        "orden": " > ".join(f"{n} ({v:.3f})" for n, v in prueba["PR-AUC"].sort_values(ascending=False).items()),
    }


def escribir_comparacion_txt(r):
    a = textos_de_analisis(r)
    p, cp, sub = a["prueba"], a["comp_pr"], a["sub"]
    mejor, base = a["mejor"], a["base"]
    ic = r["intervalos"].set_index(["Modelo", "Métrica"])
    lineas = [
        "COMPARACIÓN DE MODELOS - Riesgo de sanción de proveedores del Estado (horizonte de 12 meses)",
        "=" * 92, "",
        "Datos",
        f"- Selección: modelos entrenados con cortes hasta {m.FIN_SELECCION.date()} ({r['opcion_cortes']}) y medidos en "
        f"validación ({m.CORTE_VALIDACION.date()}).",
        f"- Modelos finales: reentrenados con {r['opcion_cortes']} hasta {m.FIN_TRAIN.date()} ({r['n_train']:,} filas, "
        f"{r['pos_train']:,} positivos).",
        f"- Validación: {m.CORTE_VALIDACION.date()} | Prueba: {m.CORTE_PRUEBA.date()} ({r['n_test']:,} proveedores, "
        f"{r['pos_test']:,} sancionados; azar = prevalencia = {a['azar']:.3f}).",
        f"- {len(r['columnas'])} predictoras. Cortes, hiperparámetros, umbral (como % de alertas) y épocas del MLP "
        "elegidos en validación; prueba usada una sola vez.",
        "", "Resultados en PRUEBA",
        p[["PR-AUC", "PR-AUC / azar", "ROC-AUC", "Recall top 10%", "Precision top 10%", "Lift top 10%",
           "Precision", "Recall", "F1", "Brier"]].round(3).to_string(),
        "", "Intervalos de confianza al 95% (bootstrap, 1000 remuestreos)",
        *[f"- {n}: PR-AUC {ic.loc[(n, 'PR-AUC'), 'Valor']:.3f} [{ic.loc[(n, 'PR-AUC'), 'IC 95% inferior']:.3f}, "
          f"{ic.loc[(n, 'PR-AUC'), 'IC 95% superior']:.3f}] | Recall top 10% {ic.loc[(n, 'Recall top 10%'), 'Valor']:.3f} "
          f"[{ic.loc[(n, 'Recall top 10%'), 'IC 95% inferior']:.3f}, {ic.loc[(n, 'Recall top 10%'), 'IC 95% superior']:.3f}]"
          for n in p.index],
        "", f"Comparación con el baseline ({base}), diferencia de PR-AUC con intervalo pareado",
        *[f"- {n}: {cp.loc[n, 'Diferencia vs baseline']:+.3f} [{cp.loc[n, 'IC 95% inferior']:+.3f}, "
          f"{cp.loc[n, 'IC 95% superior']:+.3f}] -> {cp.loc[n, 'Conclusión']}" for n in cp.index],
        "", "Análisis",
        f"- Mejor modelo por PR-AUC en prueba: {mejor} ({p.loc[mejor, 'PR-AUC']:.3f}, {p.loc[mejor, 'PR-AUC / azar']:.1f} veces el azar).",
        f"- Orden: {a['orden']}.",
        f"- Revisando el 10% de proveedores con más riesgo, {mejor} encuentra el {p.loc[mejor, 'Recall top 10%']*100:.0f}% "
        f"de los futuros sancionados, con una precision de {p.loc[mejor, 'Precision top 10%']*100:.1f}% "
        f"({p.loc[mejor, 'Lift top 10%']:.1f} veces la tasa promedio).",
        f"- Grupos de variables más importantes (promedio de los 4 modelos): {', '.join(a['grupos_top'])}.",
        f"- Por subgrupo ({mejor}, top 10%): encuentra el {sub.loc['Con sanción previa', '% encontrado']:.0f}% de los "
        f"sancionados con sanción previa y el {sub.loc['Sin sanción previa', '% encontrado']:.0f}% de los que no tenían; "
        f"el {sub.loc['Sancionado con inhabilitación', '% encontrado']:.0f}% de las inhabilitaciones y el "
        f"{sub.loc['Sancionado con multa', '% encontrado']:.0f}% de las multas.",
        "", "Limitaciones",
        "- Los archivos de contratos cubren ~9% de lo adjudicado; el historial se construyó con adjudicaciones.",
        "- Consorcios y no domiciliados quedan fuera: no tienen RUC y sus sanciones no se pueden observar.",
        "- Las listas de sanciones solo cubren ~5 años: antecedentes subestimados en los primeros cortes.",
        "- 'No sancionado' significa que no se observó una sanción en 12 meses, no que el proveedor cumplió.",
        "- Las probabilidades no están calibradas (pesos de clase): sirven para ordenar, no como % real de riesgo.",
        "- Un solo corte de validación y uno de prueba; la prevalencia cambia entre cortes.",
        "", "Uso: el puntaje sirve para priorizar revisiones. Un riesgo alto no prueba fraude ni responsabilidad.",
    ]
    COMPARISON_TXT.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return COMPARISON_TXT


def escribir_resumen(r):
    a = textos_de_analisis(r)
    enlace = lambda clave: f"Tabla: [`{TABLAS[clave]}`]({TABLAS[clave]})"
    prueba_cols = ["PR-AUC", "PR-AUC / azar", "ROC-AUC", "Recall top 10%", "Precision top 10%", "Lift top 10%",
                   "Umbral", "% alertas", "Precision", "Recall", "F1", "Brier"]
    params = pd.DataFrame([{"Modelo": NOMBRES[n], "Hiperparámetros elegidos": m._texto_params(v)}
                           for n, v in r["mejores_parametros"].items()])
    texto = f"""# Resumen del modelado

Generado automáticamente por `src/evaluation.py` (o por `notebooks/03_modelos.ipynb`). Se reemplaza en cada ejecución.

## División temporal

{_md(r['division'], index=True)}

{enlace("division")}

## Cortes de entrenamiento (elegidos en validación)

PR-AUC en validación de cada modelo con su configuración base. Opción elegida: **{r['opcion_cortes']}**.

{_md(r['tabla_cortes'], index=True)}

{enlace("cortes")}

## Hiperparámetros (elegidos en validación)

{_md(params)}

<details>
<summary>Ver todas las configuraciones probadas</summary>

{_md(r['tabla_ajuste'])}

</details>

{enlace("ajuste")}

## Métricas en validación y prueba

Validación: modelos de selección. Prueba: modelos finales. El umbral se elige en validación (máximo F1) y pasa a prueba como el mismo % de alertas. Azar en prueba (prevalencia): {a['azar']:.3f}.

{_md(r['metricas'][['Modelo', 'Conjunto'] + prueba_cols])}

Tabla: [`results/metrics.csv`](../../metrics.csv)

## Intervalos de confianza en prueba (bootstrap)

{_md(r['intervalos'])}

{enlace("intervalos")}

## Comparación con el baseline ({a['base']})

{_md(r['baseline'])}

{enlace("baseline")}

## Importancia por grupo de variables (validación)

{_md(r['importancia'].pivot(index='Grupo', columns='Modelo', values='Caída relativa %').round(1), index=True)}

{enlace("importancia")}

## Detección por subgrupo (prueba, top 10%)

{_md(r['subgrupos'])}

{enlace("subgrupos")}

## Conclusión

- Mejor modelo por PR-AUC en prueba: {a['mejor']} ({a['prueba'].loc[a['mejor'], 'PR-AUC']:.3f}, {a['prueba'].loc[a['mejor'], 'PR-AUC / azar']:.1f} veces el azar). Orden: {a['orden']}.
- Revisando el 10% de proveedores con más riesgo se encuentra el {a['prueba'].loc[a['mejor'], 'Recall top 10%']*100:.0f}% de los futuros sancionados.
- El análisis completo está en [`results/model_comparison.txt`](../../model_comparison.txt).

## Gráficos

""" + "\n\n".join(f"### {t}\n\n![{t}](../../plots/modeling/{FIGURAS[c]})" for c, t in TITULOS_FIGURAS.items()) + "\n"
    ruta = SUMMARY_DIR / "resumen.md"
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def guardar_resultados(r):
    """Escribe metrics.csv, model_comparison.txt, las tablas y el resumen."""
    r["metricas"].to_csv(METRICS_CSV, index=False, encoding="utf-8-sig")
    guardar_tabla(r["division"], "division", index=True)
    guardar_tabla(r["tabla_cortes"], "cortes", index=True)
    guardar_tabla(r["tabla_ajuste"], "ajuste")
    guardar_tabla(r["intervalos"], "intervalos")
    guardar_tabla(r["baseline"], "baseline")
    guardar_tabla(r["importancia"], "importancia")
    guardar_tabla(r["subgrupos"], "subgrupos")
    escribir_comparacion_txt(r)
    escribir_resumen(r)
    archivos = [METRICS_CSV, COMPARISON_TXT, *PLOTS_DIR.rglob("*"), *SUMMARY_DIR.rglob("*")]
    return sorted(str(p.relative_to(ROOT)) for p in archivos if p.is_file())


def tabla_ajuste_completa(ajustes):
    partes = []
    for n, (tabla, *_rest) in ajustes.items():
        t = tabla[["configuracion", "pr_auc_entrenamiento", "pr_auc_validacion", "elegida"]].copy()
        t.insert(0, "Modelo", NOMBRES[n])
        partes.append(t)
    return pd.concat(partes, ignore_index=True)


# ----------------------------------------------------------------------------
# Ejecución completa
# ----------------------------------------------------------------------------
def main():
    """Evalúa los modelos guardados en models/ y genera todos los resultados."""
    plt.switch_backend("Agg")
    limpiar_salidas()
    df = m.cargar_dataset()
    partes = m.dividir(df)
    modelos, p_val, info = m.cargar_modelos()
    columnas = info["predictoras"]
    train = m.cortes_de(partes["entrenamiento"], info["opcion_cortes"])
    ajustes = {n: (pd.DataFrame(info["ajuste"][n]), None, info["mejores_parametros"][n], info["historias_mlp"] if n == "mlp" else {})
               for n in NOMBRES}
    for n in ajustes:
        if n == "mlp":
            ajustes[n][0]["capas"] = ajustes[n][0]["capas"].apply(tuple)
    tabla_cortes = pd.DataFrame(info["tabla_cortes"]).set_index("opcion")
    print("Calculando métricas...")
    tabla, p_test, umbrales = tabla_metricas(modelos, p_val, partes, columnas)
    y_test = partes["prueba"][m.TARGET].to_numpy()
    print("Bootstrap...")
    muestras = bootstrap(y_test, p_test)
    print("Importancia por grupo...")
    r = {
        "division": m.tabla_division(partes), "tabla_cortes": tabla_cortes, "opcion_cortes": info["opcion_cortes"],
        "tabla_ajuste": tabla_ajuste_completa(ajustes), "mejores_parametros": info["mejores_parametros"],
        "metricas": tabla, "intervalos": intervalos(y_test, p_test, muestras),
        "baseline": comparacion_baseline(muestras, p_test, y_test),
        "importancia": importancia_por_grupo(modelos, partes["validación"], columnas),
        "subgrupos": deteccion_por_subgrupo(partes["prueba"], p_test),
        "columnas": columnas, "n_train": len(train), "pos_train": int(train[m.TARGET].sum()),
        "n_test": len(y_test), "pos_test": int(y_test.sum()), "prevalencia_prueba": y_test.mean(),
    }
    prueba = tabla[tabla["Conjunto"] == "Prueba"].set_index("Modelo")
    figuras = [
        graficar_cortes(tabla_cortes, info["opcion_cortes"]),
        graficar_ajuste(ajustes, partes["validación"][m.TARGET].mean()),
        graficar_mlp(info["historias_mlp"], m._texto_params(info["mejores_parametros"]["mlp"]).replace("[", "(").replace("]", ")")),
        graficar_curvas(y_test, p_test, prueba), graficar_captura(y_test, p_test),
        graficar_confusion(y_test, p_test, umbrales), graficar_intervalos(r["intervalos"], y_test.mean()),
        graficar_importancia(r["importancia"]),
        graficar_coeficientes(coeficientes_logistica(modelos["logistica"], columnas), importancia_arbol(modelos["arbol"], columnas)),
        graficar_arbol(modelos["arbol"], columnas), graficar_subgrupos(r["subgrupos"]),
    ]
    for fig in figuras:
        plt.close(fig)
    for archivo in guardar_resultados(r):
        print("  -", archivo)
    print(open(COMPARISON_TXT, encoding="utf-8").read())


if __name__ == "__main__":
    main()
