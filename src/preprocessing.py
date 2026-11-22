"""Preprocesamiento: de los datos raw al dataset proveedor x fecha de corte.

El notebook ``notebooks/02_preprocesamiento.ipynb`` usa estas funciones paso a paso
y comenta los resultados. También se puede ejecutar todo de una vez desde la raíz
del repositorio:

    python src/preprocessing.py

Salidas (se reemplazan en cada ejecución):
- ``data/processed/dataset_proveedor_corte.csv``: el dataset final, sin nulos.
- ``results/plots/preprocessing/``: gráficos (limpieza, dataset y selección).
- ``results/summaries/preprocessing/``: ``resumen.md`` y la carpeta ``tables/`` con las
  tablas que muestra el resumen (registro de limpieza, resumen por corte, decisiones,
  diccionario de datos processed y validaciones).

La lectura de los archivos raw reutiliza las funciones de ``src/exploration.py``
para que cada fuente se lea de una sola forma en todo el proyecto.

Reglas generales:
- Cada variable de un corte usa solo información disponible hasta esa fecha.
- El target mira los 12 meses siguientes al corte.
- Todo lo que se aprende de los datos para elegir variables usa solo los cortes
  de entrenamiento. La estandarización queda para el pipeline de cada modelo.
"""

import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import average_precision_score, roc_auc_score

if __package__ in (None, ""):  # permite ejecutar "python src/preprocessing.py"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import exploration as ex  # noqa: E402

# ----------------------------------------------------------------------------
# Rutas, parámetros y nombres de salida
# ----------------------------------------------------------------------------
ROOT = ex.ROOT
RAW = ex.RAW
PROCESSED = ROOT / "data" / "processed"
PLOTS_DIR = ROOT / "results" / "plots" / "preprocessing"
SUMMARY_DIR = ROOT / "results" / "summaries" / "preprocessing"
ARCHIVO_DATASET = PROCESSED / "dataset_proveedor_corte.csv"

HORIZONTE_MESES = 12
VENTANA_MESES = 24                       # historial de actividad: últimos 24 meses (población = activos en esa ventana)
FIN_TRAIN = pd.Timestamp("2024-06-30")   # cortes de entrenamiento: hasta esta fecha
CORTE_VALIDACION = pd.Timestamp("2024-12-31")
CORTE_PRUEBA = pd.Timestamp("2025-06-30")
TOPE_DIAS = 1826                         # "más de 5 años o nunca" (las listas de sanciones cubren ~5 años)
MOTIVOS_PREVIOS = {                      # grupos de motivo para los antecedentes
    "información inexacta": "fraude_documental", "documentos falsos": "fraude_documental",
    "no perfeccionar / no suscribir el contrato": "no_perfeccionar",
    "contratar estando impedido": "impedido", "resolución del contrato": "resolucion_contrato",
}
UMBRAL_AUC = 0.52         # por debajo, la variable no separa sancionados de no sancionados
UMBRAL_DOMINANTE = 0.995  # un solo valor en más del 99.5% de las filas
UMBRAL_CORRELACION = 0.90  # |rho de Spearman| a partir del cual dos variables son redundantes

FIGURAS = {
    "limpieza": "limpieza/filas_antes_y_despues_de_la_limpieza.png",
    "cortes": "dataset/filas_y_prevalencia_por_corte.png",
    "poder": "seleccion/poder_predictivo_por_variable.png",
    "correlacion": "seleccion/correlacion_entre_variables_candidatas.png",
    "estabilidad": "seleccion/estabilidad_entre_cortes_de_entrenamiento.png",
    "deciles": "seleccion/tasa_de_sancion_por_decil_variables_principales.png",
}
TITULOS_FIGURAS = {
    "limpieza": "Filas antes y después de la limpieza",
    "cortes": "Filas y prevalencia por corte",
    "poder": "Poder predictivo de cada variable",
    "deciles": "Tasa de sanción por decil (variables principales)",
    "correlacion": "Correlación entre variables candidatas",
    "estabilidad": "Estabilidad entre cortes de entrenamiento",
}
TABLAS = {
    "limpieza": "tables/registro_de_limpieza.csv",
    "cortes": "tables/resumen_por_corte.csv",
    "decisiones": "tables/decisiones_de_variables.csv",
    "diccionario": "tables/diccionario_de_datos_processed.csv",
    "validaciones": "tables/validaciones.csv",
}
RESUMEN_MD = "resumen.md"

COLOR_PRIMARIO, COLOR_SECUNDARIO = ex.COLOR_PRIMARIO, ex.COLOR_SECUNDARIO
COLOR_ACENTO1, COLOR_ACENTO2 = ex.COLOR_ACENTO1, ex.COLOR_ACENTO2
COLORES_DECISION = {"se queda": COLOR_ACENTO1, "sale": "#c0c0c0"}


def _ruta(carpeta, nombre):
    ruta = carpeta / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return ruta


def guardar_figura(fig, clave):
    fig.savefig(_ruta(PLOTS_DIR, FIGURAS[clave]), dpi=150, bbox_inches="tight")


def guardar_tabla(df, clave, index=False):
    df.to_csv(_ruta(SUMMARY_DIR, TABLAS[clave]), index=index, encoding="utf-8-sig")


def _estilo(ax, titulo, eje="y"):
    ax.set_title(titulo, fontsize=12, fontweight="bold")
    ax.grid(axis=eje, alpha=0.3)


def limpiar_salidas():
    """Borra el dataset y los resultados anteriores para que no queden versiones viejas."""
    if PROCESSED.exists():
        for f in PROCESSED.iterdir():
            if f.is_file() and f.name != ".gitkeep":
                f.unlink()
    for carpeta in (PLOTS_DIR, SUMMARY_DIR):
        if carpeta.exists():
            shutil.rmtree(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------------
# 1. Lectura
# ----------------------------------------------------------------------------
def leer_fuentes(raw=RAW, verbose=True):
    """Lee todas las fuentes que usa el preprocesamiento (con las funciones del EDA)."""
    fuentes = {c: ex.leer_anuales(c, raw, verbose)[0]
               for c in ["convocatorias", "adjudicaciones", "ofertantes", "contratos", "ampliaciones"]}
    fuentes["penalidades"], _, fuentes["lineas_reparadas_penalidades"] = ex.leer_penalidades(raw)
    fuentes["sancionados"], _ = ex.leer_sanciones_conosce(raw)
    fuentes["rnp_inh"], fuentes["rnp_mul"], fuentes["archivo_rnp"] = ex.leer_rnp(raw)
    return fuentes


# ----------------------------------------------------------------------------
# 2. Limpieza de cada fuente
# ----------------------------------------------------------------------------
class Registro:
    """Anota cuántas filas quedan después de cada paso de limpieza."""

    def __init__(self):
        self.filas = []

    def anotar(self, fuente, paso, antes, despues, motivo):
        self.filas.append({"fuente": fuente, "paso": paso, "filas_antes": int(antes),
                           "filas_despues": int(despues), "filas_quitadas": int(antes - despues), "motivo": motivo})

    def tabla(self):
        return pd.DataFrame(self.filas)


def limpiar_adjudicaciones(adj_raw, conv_raw, postores, registro):
    """Ítems ganados por personas naturales y jurídicas, con sector, postores y ratio de precio."""
    adj = ex.preparar_adjudicaciones(adj_raw)
    n = len(adj)
    adj = adj.dropna(subset=["fecha_buenapro"])
    registro.anotar("adjudicaciones", "sin fecha de buena pro", n, len(adj),
                    "sin fecha no sabemos desde cuándo se conoce el ítem")
    n = len(adj)
    adj = adj[adj["tipo_proveedor"].isin(ex.TIPOS_CON_RUC) & (adj["patron_id"] == ex.ETIQUETA_RUC)]
    registro.anotar("adjudicaciones", "consorcios y no domiciliados", n, len(adj),
                    "solo tienen código, no RUC: sus sanciones no se pueden observar")
    n = len(adj)
    adj = adj.drop_duplicates(ex.CLAVE_ITEM + ["ruc_proveedor"])
    registro.anotar("adjudicaciones", "mismo ganador repetido en un ítem", n, len(adj), "filas duplicadas")

    conv = ex.preparar_convocatorias(conv_raw).drop_duplicates(ex.CLAVE_ITEM)
    adj = adj.merge(conv[ex.CLAVE_ITEM + ["sector_nivel_gobierno"]], on=ex.CLAVE_ITEM, how="left", validate="many_to_one")
    adj["n_postores"] = postores.reindex(pd.MultiIndex.from_frame(adj[ex.CLAVE_ITEM])).fillna(1).clip(lower=1).values
    ref = adj["monto_referencial_item_soles"]
    adj["ratio_adj_ref"] = (adj["monto_adjudicado_item_soles"] / ref).where(ref > 0).clip(0, 2)
    adj["departamento"] = adj["departamento_item"].fillna(adj["entidad_departamento"])
    adj["codigoentidad"] = adj["codigoentidad"].str.lstrip("0")
    return adj.rename(columns={"ruc_proveedor": "id_proveedor", "fecha_buenapro": "fecha"}).reset_index(drop=True)


def limpiar_ofertantes(of_raw, registro):
    """Ofertas de proveedores con RUC y número de postores por ítem (contando a todos)."""
    of, n_rep = ex.preparar_ofertantes(of_raw)
    registro.anotar("ofertantes", "postor repetido en el mismo ítem", len(of) + n_rep, len(of), "filas duplicadas")
    postores = of.groupby(ex.CLAVE_ITEM).size().rename("n_postores")
    fecha = of["fecha_presentacion_propuesta"]
    of["fecha"] = fecha.where(fecha >= "2000-01-01", of["fechaconvocatoria"])
    n = len(of)
    of = of[of["patron_id"] == ex.ETIQUETA_RUC]
    registro.anotar("ofertantes", "postores sin RUC (consorcios, extranjeros)", n, len(of),
                    "no pertenecen a la población")
    return of.rename(columns={"ruc_codigo_postor": "id_proveedor"})[["id_proveedor", "fecha"]].reset_index(drop=True), postores


def limpiar_penalidades(pen, fecha_maxima, registro):
    n = len(pen)
    pen = pen.drop_duplicates()
    registro.anotar("penalidades", "filas duplicadas", n, len(pen), "la misma penalidad registrada dos veces")
    n = len(pen)
    pen = pen[pen["fecha_penalidad"].notna() & (pen["fecha_penalidad"] <= fecha_maxima)]
    registro.anotar("penalidades", "fecha posterior a la descarga", n, len(pen), "fecha imposible")
    n = len(pen)
    pen = pen[pen["ruc_contratista"].str.fullmatch(r"\d{11}").fillna(False)]
    registro.anotar("penalidades", "sin RUC de 11 dígitos", n, len(pen), "no se pueden cruzar con los proveedores")
    return pen.rename(columns={"ruc_contratista": "id_proveedor", "fecha_penalidad": "fecha"})[
        ["id_proveedor", "fecha", "tipo_penalidad", "monto"]].reset_index(drop=True)


def limpiar_ampliaciones(amp_raw, contratos_raw, fecha_maxima, registro):
    """Ampliaciones con fecha de publicación, asignadas al proveedor del contrato."""
    amp = ex.preparar_ampliaciones(amp_raw)
    items = ex.items_contrato(ex.preparar_contratos(contratos_raw))
    proveedor = (items[items["patron_id"] == ex.ETIQUETA_RUC].drop_duplicates("n_cod_contrato")
                 .set_index("n_cod_contrato")["ruc_contratista"])
    n = len(amp)
    amp = amp.drop_duplicates(["codigocontrato", "numero_documento", "fecha_publicacion_ampliacion"])
    registro.anotar("ampliaciones", "filas duplicadas", n, len(amp), "la misma ampliación registrada dos veces")
    n = len(amp)
    amp = amp[amp["codigocontrato"].isin(proveedor.index)]
    registro.anotar("ampliaciones", "contrato no está en el archivo de contratos o es de un consorcio", n, len(amp),
                    "sin contrato no sabemos de qué proveedor es")
    n = len(amp)
    amp = amp[amp["fecha_publicacion_ampliacion"] <= fecha_maxima]
    registro.anotar("ampliaciones", "fecha posterior a la descarga", n, len(amp), "fecha imposible")
    return pd.DataFrame({"id_proveedor": amp["codigocontrato"].map(proveedor).values,
                         "fecha": amp["fecha_publicacion_ampliacion"].values})


def limpiar_sanciones(sanc_inh, rnp_inh, rnp_mul, registro):
    """Eventos de sanción (RNP + CONOSCE) con grupo de motivo y si la inhabilitación es indefinida."""
    eventos, n_filas = ex.construir_eventos(sanc_inh, rnp_inh, rnp_mul)
    registro.anotar("sanciones", "unir RNP y CONOSCE sin repetir (RUC, resolución, tipo)", n_filas, len(eventos),
                    "la misma resolución aparece en las dos fuentes")
    eventos["grupo_motivo"] = eventos["motivo_grupo"].map(MOTIVOS_PREVIOS).fillna("otro_motivo")
    eventos["indefinida"] = (eventos["tipo"] == "inhabilitación") & eventos["fin"].isna()
    return eventos.rename(columns={"ruc": "id_proveedor"})


def limpiar_fuentes(fuentes):
    """Aplica la limpieza a todas las fuentes y devuelve las tablas limpias y el registro."""
    registro = Registro()
    fechas = ex.fechas_de_las_fuentes(fuentes["sancionados"], fuentes["rnp_inh"], fuentes["archivo_rnp"])
    ofertas, postores = limpiar_ofertantes(fuentes["ofertantes"], registro)
    adj = limpiar_adjudicaciones(fuentes["adjudicaciones"], fuentes["convocatorias"], postores, registro)
    fecha_maxima = adj["fecha"].max()
    tablas = {
        "adjudicaciones": adj,
        "ofertas": ofertas,
        "penalidades": limpiar_penalidades(fuentes["penalidades"], fecha_maxima, registro),
        "ampliaciones": limpiar_ampliaciones(fuentes["ampliaciones"], fuentes["contratos"], fecha_maxima, registro),
        "sanciones": limpiar_sanciones(fuentes["sancionados"], fuentes["rnp_inh"], fuentes["rnp_mul"], registro),
    }
    return tablas, registro.tabla(), fechas


def graficar_limpieza(tabla_limpieza):
    t = tabla_limpieza.groupby("fuente").agg(antes=("filas_antes", "first"), despues=("filas_despues", "last"))
    t = t.sort_values("antes")
    fig, ax = plt.subplots(figsize=(10, 4))
    y = np.arange(len(t))
    ax.barh(y + 0.2, t["antes"], height=0.4, color="#c0c0c0", label="antes de limpiar")
    ax.barh(y - 0.2, t["despues"], height=0.4, color=COLOR_PRIMARIO, label="después de limpiar")
    ax.set_yticks(y)
    ax.set_yticklabels(t.index)
    ax.set_xscale("log")
    ax.set_xlabel("filas (escala log)")
    ax.legend()
    _estilo(ax, "Filas de cada fuente antes y después de la limpieza", "x")
    fig.tight_layout()
    guardar_figura(fig, "limpieza")
    return fig


# ----------------------------------------------------------------------------
# 3. Cortes y target
# ----------------------------------------------------------------------------
def definir_cortes(adjudicaciones, fechas_fuentes, horizonte_meses=HORIZONTE_MESES):
    """Cortes semestrales (30-jun y 31-dic) desde el primer semestre con datos hasta el
    último cuya ventana de ``horizonte_meses`` está completa en las listas de sanciones."""
    inicio = adjudicaciones["fecha"].min()
    ultimo = fechas_fuentes["fecha de extracción"].min() - pd.DateOffset(months=horizonte_meses)
    cortes = [pd.Timestamp(a, m, d) for a in range(inicio.year, ultimo.year + 1) for m, d in [(6, 30), (12, 31)]]
    return [c for c in cortes if inicio < c <= ultimo]


def etapa_de_corte(corte):
    if corte <= FIN_TRAIN:
        return "entrenamiento"
    return "validación" if corte == CORTE_VALIDACION else ("prueba" if corte == CORTE_PRUEBA else "otro")


# ----------------------------------------------------------------------------
# 4. Variables por corte
# ----------------------------------------------------------------------------
FAMILIAS = {"Adjudicación simplificada": "adj_simplificada", "Subasta inversa": "subasta_inversa",
            "Licitación pública": "licitacion", "Concurso público": "concurso", "Contratación directa": "directa",
            "Comparación de precios": "comparacion_precios", "Otros": "otros_procesos"}
OBJETOS = {"Bien": "bien", "Servicio": "servicio", "Obra": "obra", "Consultoría de Obra": "consultoria_obra"}
ENTIDADES = {"GOBIERNO LOCAL": "gob_local", "GOBIERNO REGIONAL": "gob_regional", "GOBIERNO NACIONAL": "gob_nacional",
             "FONAFE": "empresa_estatal", "PETROPERU": "empresa_estatal"}


def _proporciones(H, columna, mapa, prefijo, indice):
    t = pd.crosstab(H["id_proveedor"], H[columna].map(mapa).fillna("otro"), normalize="index")
    t = t.reindex(columns=sorted(set(mapa.values())), fill_value=0).add_prefix(prefijo)
    return t.reindex(indice, fill_value=0)


def _dias_desde(ultima, corte, indice):
    dias = (corte - ultima).dt.days.reindex(indice)
    return dias.fillna(TOPE_DIAS).clip(upper=TOPE_DIAS)


def construir_corte(tablas, corte, horizonte_meses=HORIZONTE_MESES, ventana_meses=VENTANA_MESES):
    """Una fila por proveedor activo: con al menos una buena pro en los ``ventana_meses``
    previos al corte.

    La actividad (ítems, montos, ofertas, diversificación, composición, precio y
    competencia) se mide en esa ventana móvil, para que las variables signifiquen lo
    mismo en todos los cortes. Los antecedentes (sanciones y penalidades) usan toda la
    historia disponible. Todo usa solo hechos con fecha <= corte; el target usa las
    sanciones con fecha en (corte, corte + horizonte]. Las variables salen sin nulos:
    los faltantes se resuelven con reglas fijas (ver diccionario).
    """
    corte = pd.Timestamp(corte)
    hace = lambda meses: corte - pd.DateOffset(months=meses)
    A = tablas["adjudicaciones"]
    H = A[(A["fecha"] <= corte) & (A["fecha"] > hace(ventana_meses))].assign(
        _lima=lambda d: d["departamento"].isin(["LIMA", "CALLAO"]).astype(float),
        _bajo_80=lambda d: (d["ratio_adj_ref"] < 0.8).astype(float).where(d["ratio_adj_ref"].notna()),
        _sin_competencia=lambda d: (d["n_postores"] == 1).astype(float))
    g = H.groupby("id_proveedor")
    idx = g.size().index
    F = pd.DataFrame(index=idx)

    # Perfil y antigüedad
    F["persona_juridica"] = (g["tipo_proveedor"].first() == "Persona Juridica").astype(int)
    F["meses_desde_ultima_buena_pro"] = (corte - g["fecha"].max()).dt.days / 30.4375

    # Actividad
    F["n_items_ganados_24m"] = g.size()
    F["monto_adjudicado_24m"] = g["monto_adjudicado_item_soles"].sum()
    for m in (6, 12):
        Hm = H[H["fecha"] > hace(m)].groupby("id_proveedor")
        F[f"n_items_ganados_{m}m"] = Hm.size().reindex(idx, fill_value=0)
        F[f"monto_adjudicado_{m}m"] = Hm["monto_adjudicado_item_soles"].sum().reindex(idx, fill_value=0)
    F["monto_adjudicado_medio"] = g["monto_adjudicado_item_soles"].mean()
    F["monto_adjudicado_max"] = g["monto_adjudicado_item_soles"].max()
    F["prop_items_ultimos_6m"] = (F["n_items_ganados_6m"] / F["n_items_ganados_12m"]).where(F["n_items_ganados_12m"] > 0, 0)
    F["meses_activos_12m"] = (H[H["fecha"] > hace(12)].assign(mes=lambda d: d["fecha"].dt.to_period("M"))
                              .groupby("id_proveedor")["mes"].nunique().reindex(idx, fill_value=0))

    # Diversificación y concentración
    F["n_entidades"] = g["codigoentidad"].nunique()
    F["n_departamentos"] = g["departamento"].nunique()
    F["n_sectores"] = g["sector_nivel_gobierno"].nunique()
    por_entidad = H.groupby(["id_proveedor", "codigoentidad"]).agg(n=("fecha", "size"), monto=("monto_adjudicado_item_soles", "sum"))
    pe = por_entidad.groupby(level=0)
    F["prop_items_entidad_principal"] = pe["n"].max() / F["n_items_ganados_24m"]
    monto_total = pe["monto"].sum()
    F["prop_monto_entidad_principal"] = (pe["monto"].max() / monto_total).where(monto_total > 0, 1.0)
    F["n_entidades_recurrentes"] = (por_entidad["n"] >= 2).groupby(level=0).sum()

    # Composición
    F = F.join(_proporciones(H, "objetocontractual", OBJETOS, "prop_obj_", idx))
    F = F.join(_proporciones(H, "familia_proceso", FAMILIAS, "prop_proc_", idx))
    F = F.join(_proporciones(H, "tipoentidad", ENTIDADES, "prop_ent_", idx))
    F["prop_items_lima_callao"] = g["_lima"].mean()

    # Precio y competencia
    F["ratio_adjudicado_referencial"] = g["ratio_adj_ref"].mean().fillna(1.0)
    F["prop_items_bajo_80pct_referencial"] = g["_bajo_80"].mean().fillna(0.0)
    F["postores_promedio_items_ganados"] = g["n_postores"].mean()
    F["prop_items_ganados_sin_competencia"] = g["_sin_competencia"].mean()

    # Participación (ofertas)
    O = tablas["ofertas"]
    Oc = O[(O["fecha"] <= corte) & (O["fecha"] > hace(ventana_meses))]
    F["n_ofertas_24m"] = Oc.groupby("id_proveedor").size().reindex(idx, fill_value=0)
    F["n_ofertas_12m"] = Oc[Oc["fecha"] > hace(12)].groupby("id_proveedor").size().reindex(idx, fill_value=0)
    F["tasa_exito"] = F["n_items_ganados_24m"] / np.maximum(F["n_ofertas_24m"], F["n_items_ganados_24m"])

    # Ejecución: penalidades y ampliaciones
    P = tablas["penalidades"]
    Pc = P[P["fecha"] <= corte]
    gp = Pc.groupby("id_proveedor")
    F["n_penalidades"] = gp.size().reindex(idx, fill_value=0)
    F["n_penalidades_12m"] = Pc[Pc["fecha"] > hace(12)].groupby("id_proveedor").size().reindex(idx, fill_value=0)
    F["n_penalidades_mora"] = Pc[Pc["tipo_penalidad"] == "Por Mora"].groupby("id_proveedor").size().reindex(idx, fill_value=0)
    F["monto_penalidades"] = gp["monto"].sum().reindex(idx, fill_value=0)
    F["tiene_penalidad_previa"] = (F["n_penalidades"] > 0).astype(int)
    F["dias_desde_ultima_penalidad"] = _dias_desde(gp["fecha"].max(), corte, idx)
    AM = tablas["ampliaciones"]
    F["n_ampliaciones"] = AM[AM["fecha"] <= corte].groupby("id_proveedor").size().reindex(idx, fill_value=0)

    # Antecedentes de sanciones
    E = tablas["sanciones"]
    Ec = E[E["fecha"] <= corte]
    ge = Ec.groupby("id_proveedor")
    F["n_inhabilitaciones_previas"] = Ec[Ec["tipo"] == "inhabilitación"].groupby("id_proveedor").size().reindex(idx, fill_value=0)
    F["n_multas_previas"] = Ec[Ec["tipo"] == "multa"].groupby("id_proveedor").size().reindex(idx, fill_value=0)
    F["n_sanciones_previas_12m"] = Ec[Ec["fecha"] > hace(12)].groupby("id_proveedor").size().reindex(idx, fill_value=0)
    for grupo in sorted(set(MOTIVOS_PREVIOS.values())) + ["otro_motivo"]:
        F[f"n_previas_{grupo}"] = Ec[Ec["grupo_motivo"] == grupo].groupby("id_proveedor").size().reindex(idx, fill_value=0)
    F["tiene_sancion_previa"] = ((F["n_inhabilitaciones_previas"] + F["n_multas_previas"]) > 0).astype(int)
    F["dias_desde_ultima_sancion"] = _dias_desde(ge["fecha"].max(), corte, idx)
    inh = Ec[Ec["tipo"] == "inhabilitación"]
    vigentes = inh.loc[inh["fin"].isna() | (inh["fin"] > corte), "id_proveedor"]
    F["inhabilitado_vigente_al_corte"] = F.index.isin(set(vigentes)).astype(int)
    F["inhabilitacion_indefinida_previa"] = F.index.isin(set(inh.loc[inh["indefinida"], "id_proveedor"])).astype(int)

    # Target: sanciones en (corte, corte + horizonte]
    fin = corte + pd.DateOffset(months=horizonte_meses)
    Ew = E[(E["fecha"] > corte) & (E["fecha"] <= fin)]
    F[f"y_inhabilitacion_{horizonte_meses}m"] = F.index.isin(set(Ew.loc[Ew["tipo"] == "inhabilitación", "id_proveedor"])).astype(int)
    F[f"y_multa_{horizonte_meses}m"] = F.index.isin(set(Ew.loc[Ew["tipo"] == "multa", "id_proveedor"])).astype(int)
    F["target"] = (F[f"y_inhabilitacion_{horizonte_meses}m"] | F[f"y_multa_{horizonte_meses}m"]).astype(int)

    F.insert(0, "fecha_corte", corte)
    return F.rename_axis("id_proveedor").reset_index()


def construir_dataset(tablas, cortes, verbose=True):
    partes = []
    for corte in cortes:
        partes.append(construir_corte(tablas, corte))
        if verbose:
            print(f"Corte {corte.date()}: {len(partes[-1]):,} proveedores")
    return pd.concat(partes, ignore_index=True)


COLUMNAS_ID = ["id_proveedor", "fecha_corte"]
COLUMNAS_TARGET = ["target", f"y_inhabilitacion_{HORIZONTE_MESES}m", f"y_multa_{HORIZONTE_MESES}m"]


def columnas_candidatas(dataset):
    return [c for c in dataset.columns if c not in COLUMNAS_ID + COLUMNAS_TARGET]


def resumen_por_corte(dataset):
    t = dataset.groupby("fecha_corte").agg(
        proveedores=("target", "size"), positivos=("target", "sum"),
        positivos_inhabilitacion=(COLUMNAS_TARGET[1], "sum"), positivos_multa=(COLUMNAS_TARGET[2], "sum"),
        con_sancion_previa=("tiene_sancion_previa", "mean"), con_penalidad_previa=("tiene_penalidad_previa", "mean"),
        items_ganados_24m_mediana=("n_items_ganados_24m", "median"))
    t.insert(2, "prevalencia_%", (t["positivos"] / t["proveedores"] * 100).round(2))
    t["con_sancion_previa"] = (t["con_sancion_previa"] * 100).round(1)
    t["con_penalidad_previa"] = (t["con_penalidad_previa"] * 100).round(1)

    t.insert(0, "etapa", [etapa_de_corte(c) for c in t.index])
    t.index = t.index.date
    return t.rename_axis("fecha_corte")


def graficar_cortes(resumen):
    fig, ax = plt.subplots(1, 2, figsize=(15, 4.2))
    etiquetas = [str(c) for c in resumen.index]
    colores = [{"entrenamiento": COLOR_PRIMARIO, "validación": COLOR_SECUNDARIO, "prueba": COLOR_ACENTO2}.get(e, "gray")
               for e in resumen["etapa"]]
    ax[0].bar(etiquetas, resumen["proveedores"], color=colores)
    ax[0].set_ylabel("proveedores")
    ax[0].tick_params(axis="x", rotation=30)
    for etapa, color in [("entrenamiento", COLOR_PRIMARIO), ("validación", COLOR_SECUNDARIO), ("prueba", COLOR_ACENTO2)]:
        ax[0].bar(0, 0, color=color, label=etapa)
    ax[0].legend()
    _estilo(ax[0], "Filas (proveedores) por fecha de corte")
    ax[1].plot(etiquetas, resumen["prevalencia_%"], marker="o", color="black", label="target (cualquier sanción)")
    ax[1].plot(etiquetas, resumen["positivos_inhabilitacion"] / resumen["proveedores"] * 100, marker="s",
               color=COLOR_PRIMARIO, label="inhabilitación")
    ax[1].plot(etiquetas, resumen["positivos_multa"] / resumen["proveedores"] * 100, marker="^",
               color=COLOR_SECUNDARIO, label="multa")
    ax[1].set_ylabel("% de proveedores sancionados en los 12 meses siguientes")
    ax[1].tick_params(axis="x", rotation=30)
    ax[1].legend()
    _estilo(ax[1], "Prevalencia del target por corte", "both")
    fig.tight_layout()
    guardar_figura(fig, "cortes")
    return fig


# ----------------------------------------------------------------------------
# 5. Catálogo de variables (diccionario)
# ----------------------------------------------------------------------------
# columna -> (grupo, descripción, regla para faltantes, transformación final)
SIN_FALTANTES = "no tiene faltantes"
CATALOGO = {
    "persona_juridica": ("Perfil", "1 si el RUC es de persona jurídica (20...), 0 si es persona natural (10...).", SIN_FALTANTES, "ninguna"),
    "meses_desde_ultima_buena_pro": ("Actividad", "Meses desde la última buena pro (como máximo 24).", SIN_FALTANTES, "ninguna"),
    "n_items_ganados_24m": ("Actividad", "Ítems ganados en los últimos 24 meses.", SIN_FALTANTES, "log1p"),
    "n_items_ganados_6m": ("Actividad", "Ítems ganados en los últimos 6 meses.", "0 si no ganó", "log1p"),
    "n_items_ganados_12m": ("Actividad", "Ítems ganados en los últimos 12 meses.", "0 si no ganó", "log1p"),
    "monto_adjudicado_24m": ("Montos", "Monto adjudicado en soles en los últimos 24 meses.", SIN_FALTANTES, "log1p"),
    "monto_adjudicado_6m": ("Montos", "Monto adjudicado en los últimos 6 meses.", "0 si no ganó", "log1p"),
    "monto_adjudicado_12m": ("Montos", "Monto adjudicado en los últimos 12 meses.", "0 si no ganó", "log1p"),
    "monto_adjudicado_medio": ("Montos", "Monto adjudicado promedio por ítem.", SIN_FALTANTES, "log1p"),
    "monto_adjudicado_max": ("Montos", "Monto del ítem más grande ganado.", SIN_FALTANTES, "log1p"),
    "prop_items_ultimos_6m": ("Actividad", "De lo ganado en 12 meses, proporción ganada en los últimos 6 (aceleración).", "0 si no ganó en 12 meses", "ninguna"),
    "meses_activos_12m": ("Actividad", "Meses distintos con al menos una buena pro en los últimos 12.", "0 si no ganó", "ninguna"),
    "n_entidades": ("Diversificación", "Entidades distintas con las que ganó.", SIN_FALTANTES, "log1p"),
    "n_departamentos": ("Diversificación", "Departamentos distintos de los ítems ganados.", SIN_FALTANTES, "log1p"),
    "n_sectores": ("Diversificación", "Sectores o niveles de gobierno distintos.", SIN_FALTANTES, "log1p"),
    "prop_items_entidad_principal": ("Concentración", "Proporción de ítems ganados con la entidad principal.", SIN_FALTANTES, "ninguna"),
    "prop_monto_entidad_principal": ("Concentración", "Proporción del monto ganado con la entidad principal.", "1 si el monto total es 0", "ninguna"),
    "n_entidades_recurrentes": ("Concentración", "Entidades con las que ganó 2 o más ítems.", SIN_FALTANTES, "log1p"),
    "prop_items_lima_callao": ("Composición", "Proporción de ítems en Lima o Callao.", SIN_FALTANTES, "ninguna"),
    "ratio_adjudicado_referencial": ("Precio", "Monto adjudicado / referencial, promedio por ítem (recortado en 0-2).", "1 (sin descuento) si ningún ítem tiene referencial", "ninguna"),
    "prop_items_bajo_80pct_referencial": ("Precio", "Proporción de ítems ganados por debajo del 80% del referencial.", "0 si ningún ítem tiene referencial", "ninguna"),
    "postores_promedio_items_ganados": ("Competencia", "Postores promedio en los ítems que ganó.", "ítem sin lista de postores = 1 postor", "log1p"),
    "prop_items_ganados_sin_competencia": ("Competencia", "Proporción de ítems ganados con un solo postor.", "ítem sin lista de postores = 1 postor", "ninguna"),
    "n_ofertas_24m": ("Participación", "Ofertas presentadas en los últimos 24 meses.", "0 si no presentó", "log1p"),
    "n_ofertas_12m": ("Participación", "Ofertas presentadas en los últimos 12 meses.", "0 si no presentó", "log1p"),
    "tasa_exito": ("Participación", "Ítems ganados / ofertas presentadas (últimos 24 meses).", "si ganó más de lo que ofertó (procesos sin postores), ofertas = ganados", "ninguna"),
    "n_penalidades": ("Ejecución", "Penalidades aplicadas por las entidades hasta el corte.", "0 si no tiene", "log1p"),
    "n_penalidades_12m": ("Ejecución", "Penalidades en los últimos 12 meses.", "0 si no tiene", "log1p"),
    "n_penalidades_mora": ("Ejecución", "Penalidades por mora (retraso).", "0 si no tiene", "log1p"),
    "monto_penalidades": ("Ejecución", "Monto total de penalidades.", "0 si no tiene", "log1p"),
    "tiene_penalidad_previa": ("Ejecución", "1 si tuvo al menos una penalidad antes del corte.", SIN_FALTANTES, "ninguna"),
    "dias_desde_ultima_penalidad": ("Ejecución", "Días desde la última penalidad.", f"{TOPE_DIAS} (tope: nunca o hace más de 5 años)", "log1p"),
    "n_ampliaciones": ("Ejecución", "Ampliaciones publicadas de sus contratos (solo contratos del archivo de contratos).", "0 si no tiene", "log1p"),
    "n_inhabilitaciones_previas": ("Antecedentes", "Inhabilitaciones con fecha anterior o igual al corte.", "0 si no tiene", "log1p"),
    "n_multas_previas": ("Antecedentes", "Multas con fecha anterior o igual al corte.", "0 si no tiene", "log1p"),
    "n_sanciones_previas_12m": ("Antecedentes", "Sanciones en los últimos 12 meses.", "0 si no tiene", "log1p"),
    "n_previas_fraude_documental": ("Antecedentes", "Sanciones previas por información inexacta o documentos falsos.", "0 si no tiene", "log1p"),
    "n_previas_impedido": ("Antecedentes", "Sanciones previas por contratar estando impedido.", "0 si no tiene", "log1p"),
    "n_previas_no_perfeccionar": ("Antecedentes", "Sanciones previas por no perfeccionar o no suscribir el contrato.", "0 si no tiene", "log1p"),
    "n_previas_resolucion_contrato": ("Antecedentes", "Sanciones previas por resolución del contrato.", "0 si no tiene", "log1p"),
    "n_previas_otro_motivo": ("Antecedentes", "Sanciones previas por otros motivos o sin motivo registrado.", "0 si no tiene", "log1p"),
    "tiene_sancion_previa": ("Antecedentes", "1 si tuvo alguna sanción antes del corte.", SIN_FALTANTES, "ninguna"),
    "dias_desde_ultima_sancion": ("Antecedentes", "Días desde la última sanción.", f"{TOPE_DIAS} (tope: nunca o hace más de 5 años)", "log1p"),
    "inhabilitado_vigente_al_corte": ("Antecedentes", "1 si tenía una inhabilitación vigente al corte.", SIN_FALTANTES, "ninguna"),
    "inhabilitacion_indefinida_previa": ("Antecedentes", "1 si tiene una inhabilitación sin fecha de fin (definitiva o indeterminada).", SIN_FALTANTES, "ninguna"),
}
for nombre, col in OBJETOS.items():
    CATALOGO[f"prop_obj_{col}"] = ("Composición", f"Proporción de ítems ganados de objeto {nombre.lower()}.", SIN_FALTANTES, "ninguna")
for nombre, col in FAMILIAS.items():
    CATALOGO[f"prop_proc_{col}"] = ("Composición", f"Proporción de ítems ganados por {nombre.lower()}.", SIN_FALTANTES, "ninguna")
CATALOGO["prop_ent_gob_local"] = ("Composición", "Proporción de ítems de gobiernos locales.", SIN_FALTANTES, "ninguna")
CATALOGO["prop_ent_gob_regional"] = ("Composición", "Proporción de ítems de gobiernos regionales.", SIN_FALTANTES, "ninguna")
CATALOGO["prop_ent_gob_nacional"] = ("Composición", "Proporción de ítems del gobierno nacional.", SIN_FALTANTES, "ninguna")
CATALOGO["prop_ent_empresa_estatal"] = ("Composición", "Proporción de ítems de empresas estatales (FONAFE, Petroperú).", SIN_FALTANTES, "ninguna")
ORDEN_GRUPOS = ["Perfil", "Actividad", "Montos", "Diversificación", "Concentración", "Composición", "Precio",
                "Competencia", "Participación", "Ejecución", "Antecedentes"]


# ----------------------------------------------------------------------------
# 6. Selección de variables (solo con los cortes de entrenamiento)
# ----------------------------------------------------------------------------
def _psi(referencia, actual, bins=10):
    """Population Stability Index entre dos distribuciones (cortes por deciles de la referencia)."""
    cortes = np.unique(np.quantile(referencia, np.linspace(0, 1, bins + 1)))
    if len(cortes) < 3:
        cortes = np.unique(np.concatenate([cortes, [np.min(actual), np.max(actual)]]))
    if len(cortes) < 2:
        return 0.0
    cortes[0], cortes[-1] = -np.inf, np.inf
    p = np.histogram(referencia, cortes)[0] / len(referencia) + 1e-4
    q = np.histogram(actual, cortes)[0] / len(actual) + 1e-4
    return float(np.sum((q - p) * np.log(q / p)))


def evaluar_variables(train, variables):
    """Calidad y poder predictivo individual de cada variable en entrenamiento."""
    y = train["target"].to_numpy()
    prevalencia = y.mean()
    filas = []
    for v in variables:
        x = train[v].to_numpy(dtype=float)
        auc = roc_auc_score(y, x) if np.nanstd(x) > 0 else 0.5
        sentido = 1 if auc >= 0.5 else -1
        filas.append({
            "variable": v, "grupo": CATALOGO.get(v, ("?",))[0],
            "%_nulos": round(np.isnan(x).mean() * 100, 2),
            "%_valor_dominante": round(pd.Series(x).value_counts(normalize=True).iloc[0] * 100, 2),
            "roc_auc": round(max(auc, 1 - auc), 4),
            "sentido": "más alto, más riesgo" if sentido > 0 else "más alto, menos riesgo",
            "pr_auc_sobre_azar": round(average_precision_score(y, sentido * x) / prevalencia, 2),
        })
    return pd.DataFrame(filas).set_index("variable")


def correlaciones(train, variables, n_max=60000, semilla=42):
    muestra = train[variables].sample(min(n_max, len(train)), random_state=semilla)
    return muestra.rank().corr()  # Spearman = Pearson sobre rangos


def estabilidad(train, variables, referencia=FIN_TRAIN):
    """PSI de cada variable en cada corte de entrenamiento frente al último corte de entrenamiento."""
    ref = train[train["fecha_corte"] == referencia]
    cortes = sorted(c for c in train["fecha_corte"].unique() if c != referencia)
    return pd.DataFrame({pd.Timestamp(c).date(): [_psi(ref[v].to_numpy(float), train.loc[train["fecha_corte"] == c, v].to_numpy(float))
                                                 for v in variables] for c in cortes}, index=variables)


def seleccionar_variables(evaluacion, corr):
    """Aplica las reglas de selección y devuelve la tabla de decisiones.

    1. Casi constante: un valor en más del 99.5% de las filas y sin poder predictivo.
    2. Sin poder predictivo: ROC-AUC individual menor a 0.52.
    3. Redundante: |rho de Spearman| >= 0.90 con otra variable de mayor ROC-AUC que ya se quedó.
    """
    tabla = evaluacion.copy()
    tabla["decision"], tabla["motivo"], tabla["correlacion_max_con"] = "se queda", "", ""
    for v in tabla.index:
        if tabla.loc[v, "%_valor_dominante"] > UMBRAL_DOMINANTE * 100 and tabla.loc[v, "roc_auc"] < 0.55:
            tabla.loc[v, ["decision", "motivo"]] = ["sale", "casi constante y sin poder predictivo"]
        elif tabla.loc[v, "roc_auc"] < UMBRAL_AUC:
            tabla.loc[v, ["decision", "motivo"]] = ["sale", f"sin poder predictivo (ROC-AUC < {UMBRAL_AUC})"]
    elegidas = []
    for v in tabla[tabla["decision"] == "se queda"].sort_values("roc_auc", ascending=False).index:
        rho = corr.loc[v, elegidas].abs() if elegidas else pd.Series(dtype=float)
        if len(rho) and rho.max() >= UMBRAL_CORRELACION:
            otra = rho.idxmax()
            tabla.loc[v, ["decision", "motivo"]] = ["sale", f"redundante con {otra} (rho = {corr.loc[v, otra]:.2f})"]
        else:
            elegidas.append(v)
    for v in tabla.index:
        otros = corr.loc[v].drop(v).abs().dropna()
        if len(otros):
            tabla.loc[v, "correlacion_max_con"] = f"{otros.idxmax()} ({corr.loc[v, otros.idxmax()]:.2f})"
    tabla.loc[tabla["decision"] == "se queda", "motivo"] = "tiene señal y no es redundante"
    return tabla


def graficar_poder_predictivo(decisiones):
    t = decisiones.sort_values("roc_auc")
    fig, ax = plt.subplots(figsize=(10, max(6, 0.22 * len(t))))
    ax.barh(t.index, t["roc_auc"], color=[COLORES_DECISION[d] for d in t["decision"]])
    ax.axvline(0.5, color="black", linewidth=0.8)
    ax.axvline(UMBRAL_AUC, color="gray", linestyle="--", label=f"umbral ({UMBRAL_AUC})")
    ax.set_xlim(0.45, max(0.8, t["roc_auc"].max() + 0.02))
    ax.set_xlabel("ROC-AUC de la variable sola (entrenamiento)")
    from matplotlib.patches import Patch
    manejadores = [Patch(color=c, label=d) for d, c in COLORES_DECISION.items()]
    ax.legend(handles=ax.get_legend_handles_labels()[0] + manejadores, loc="lower right")
    ax.tick_params(axis="y", labelsize=8)
    _estilo(ax, "Poder predictivo individual de cada variable", "x")
    fig.tight_layout()
    guardar_figura(fig, "poder")
    return fig


def graficar_correlaciones(corr, decisiones):
    orden = sorted(corr.index, key=lambda v: (ORDEN_GRUPOS.index(decisiones.loc[v, "grupo"]), v))
    c = corr.loc[orden, orden]
    fig, ax = plt.subplots(figsize=(15, 13))
    sns.heatmap(c, cmap="RdBu_r", center=0, vmin=-1, vmax=1, ax=ax, cbar_kws={"label": "rho de Spearman", "shrink": 0.6},
                xticklabels=True, yticklabels=True)
    ax.tick_params(labelsize=7)
    for etiqueta in ax.get_yticklabels() + ax.get_xticklabels():
        if decisiones.loc[etiqueta.get_text(), "decision"] == "sale":
            etiqueta.set_color("#999999")
    ax.set_title("Correlación entre variables candidatas (en gris: las que salen)", fontsize=12, fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "correlacion")
    return fig


def graficar_estabilidad(psi, decisiones, top=25):
    elegidas = decisiones[decisiones["decision"] == "se queda"].index
    t = psi.loc[psi.index.intersection(elegidas)]
    t = t.loc[t.max(axis=1).sort_values(ascending=False).index[:top]]
    fig, ax = plt.subplots(figsize=(9, max(5, 0.3 * len(t))))
    sns.heatmap(t, annot=True, fmt=".2f", cmap="Oranges", vmin=0, vmax=0.5, ax=ax, cbar_kws={"label": "PSI"},
                annot_kws={"size": 8})
    ax.set_xlabel(f"corte (comparado con {FIN_TRAIN.date()})")
    ax.tick_params(axis="y", labelsize=8)
    ax.set_title(f"Estabilidad de las variables elegidas (top {len(t)} por PSI)", fontsize=12, fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "estabilidad")
    return fig


def graficar_deciles(train, decisiones, n=8):
    top = decisiones[decisiones["decision"] == "se queda"].sort_values("roc_auc", ascending=False).index[:n]
    prevalencia = train["target"].mean() * 100
    fig, axes = plt.subplots(2, 4, figsize=(19, 7.5))
    for ax, v in zip(axes.ravel(), top):
        grupos = pd.qcut(train[v].rank(method="first"), 10, labels=False) + 1
        tasa = train.groupby(grupos)["target"].mean() * 100
        ax.bar(tasa.index.astype(str), tasa.values, color=COLOR_ACENTO1)
        ax.axhline(prevalencia, color="gray", linestyle="--", alpha=0.7)
        ax.set_xlabel("decil (1 = valores más bajos)")
        ax.set_ylabel("% sancionado en 12 meses")
        _estilo(ax, v, "y")
        ax.title.set_fontsize(10)
    fig.suptitle("Tasa de sanción por decil de las 8 variables con más señal (entrenamiento; línea = promedio)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "deciles")
    return fig


# ----------------------------------------------------------------------------
# 7. Tratamiento final, diccionario y validaciones
# ----------------------------------------------------------------------------
def tratamiento_final(dataset, elegidas):
    """Deja solo las variables elegidas y aplica log1p a las de cola larga (renombradas con log_)."""
    final = dataset[COLUMNAS_ID + COLUMNAS_TARGET + elegidas].copy()
    renombre = {}
    for v in elegidas:
        if CATALOGO[v][3] == "log1p":
            final[v] = np.log1p(final[v].clip(lower=0))
            renombre[v] = f"log_{v}"
    final = final.rename(columns=renombre)
    final["fecha_corte"] = pd.to_datetime(final["fecha_corte"]).dt.date
    return final.sort_values(["fecha_corte", "id_proveedor"]).reset_index(drop=True), renombre


def diccionario_de_datos_processed(final, renombre, decisiones):
    inverso = {nuevo: viejo for viejo, nuevo in renombre.items()}
    filas = [
        {"columna": "id_proveedor", "uso": "ID", "grupo": "Identificación", "descripcion": "RUC del proveedor (persona natural o jurídica).",
         "regla_para_faltantes": SIN_FALTANTES, "transformacion": "ninguna"},
        {"columna": "fecha_corte", "uso": "ID", "grupo": "Identificación", "descripcion": "Fecha de corte: las variables usan solo información hasta esta fecha.",
         "regla_para_faltantes": SIN_FALTANTES, "transformacion": "ninguna"},
        {"columna": "target", "uso": "Target", "grupo": "Target", "descripcion": f"1 si recibe una inhabilitación o multa en los {HORIZONTE_MESES} meses siguientes al corte.",
         "regla_para_faltantes": SIN_FALTANTES, "transformacion": "ninguna"},
        {"columna": COLUMNAS_TARGET[1], "uso": "Target (componente)", "grupo": "Target", "descripcion": "1 si recibe una inhabilitación en la ventana. No usar como predictora.",
         "regla_para_faltantes": SIN_FALTANTES, "transformacion": "ninguna"},
        {"columna": COLUMNAS_TARGET[2], "uso": "Target (componente)", "grupo": "Target", "descripcion": "1 si recibe una multa en la ventana. No usar como predictora.",
         "regla_para_faltantes": SIN_FALTANTES, "transformacion": "ninguna"},
    ]
    for col in final.columns:
        if col in COLUMNAS_ID + COLUMNAS_TARGET:
            continue
        origen = inverso.get(col, col)
        grupo, descripcion, regla, transf = CATALOGO[origen]
        filas.append({"columna": col, "uso": "Predictora", "grupo": grupo, "descripcion": descripcion,
                      "regla_para_faltantes": regla, "transformacion": transf,
                      "roc_auc_entrenamiento": decisiones.loc[origen, "roc_auc"],
                      "sentido": decisiones.loc[origen, "sentido"]})
    d = pd.DataFrame(filas)
    d["min"] = [final[c].min() if c not in ("id_proveedor", "fecha_corte") else "" for c in d["columna"]]
    d["max"] = [final[c].max() if c not in ("id_proveedor", "fecha_corte") else "" for c in d["columna"]]
    return d


def validar_dataset(final, tablas, dataset_crudo, n_muestra=400, semilla=42):
    """Comprobaciones que detienen el proceso si algo falla. Devuelve la tabla de resultados."""
    resultados = []

    def comprobar(nombre, condicion):
        resultados.append({"validación": nombre, "resultado": "OK" if condicion else "FALLA"})
        assert condicion, f"Validación fallida: {nombre}"

    predictoras = [c for c in final.columns if c not in COLUMNAS_ID + COLUMNAS_TARGET]
    comprobar("una fila por (id_proveedor, fecha_corte)", not final.duplicated(COLUMNAS_ID).any())
    comprobar("sin nulos en ninguna columna", not final.isna().any().any())
    comprobar("sin columnas constantes", bool(final[predictoras].nunique().gt(1).all()))
    comprobar("target y componentes solo 0/1", all(set(final[c].unique()) <= {0, 1} for c in COLUMNAS_TARGET))
    comprobar("target = inhabilitación o multa",
              bool((final["target"] == (final[COLUMNAS_TARGET[1]] | final[COLUMNAS_TARGET[2]])).all()))
    comprobar("solo RUC de 11 dígitos", bool(final["id_proveedor"].str.fullmatch(r"\d{11}").all()))
    comprobar("ventanas coherentes: 6m <= 12m <= 24m y al menos 1 ítem en 24m",
              bool(((dataset_crudo["n_items_ganados_6m"] <= dataset_crudo["n_items_ganados_12m"])
                    & (dataset_crudo["n_items_ganados_12m"] <= dataset_crudo["n_items_ganados_24m"])
                    & (dataset_crudo["n_items_ganados_24m"] >= 1)).all()))
    comprobar("las predictoras no incluyen el target ni sus componentes", not set(COLUMNAS_TARGET) & set(predictoras))

    # Recálculo independiente en una muestra: contamos directamente en las tablas limpias
    A, P, E = tablas["adjudicaciones"], tablas["penalidades"], tablas["sanciones"]
    muestra = dataset_crudo.sample(min(n_muestra, len(dataset_crudo)), random_state=semilla)
    ok_items = ok_target = ok_previas = ok_pen = True
    for fila in muestra.itertuples(index=False):
        corte, ruc = pd.Timestamp(fila.fecha_corte), fila.id_proveedor
        fin = corte + pd.DateOffset(months=HORIZONTE_MESES)
        inicio = corte - pd.DateOffset(months=VENTANA_MESES)
        ok_items &= int(((A["id_proveedor"] == ruc) & (A["fecha"] <= corte) & (A["fecha"] > inicio)).sum()) == fila.n_items_ganados_24m
        ev = E[E["id_proveedor"] == ruc]
        ok_target &= int(((ev["fecha"] > corte) & (ev["fecha"] <= fin)).any()) == fila.target
        ok_previas &= int((ev["fecha"] <= corte).sum()) == fila.n_inhabilitaciones_previas + fila.n_multas_previas
        ok_pen &= int(((P["id_proveedor"] == ruc) & (P["fecha"] <= corte)).sum()) == fila.n_penalidades
    comprobar(f"recálculo de ítems ganados (24 meses) en {len(muestra)} filas", ok_items)
    comprobar(f"recálculo del target en {len(muestra)} filas", ok_target)
    comprobar(f"recálculo de sanciones previas en {len(muestra)} filas", ok_previas)
    comprobar(f"recálculo de penalidades previas en {len(muestra)} filas", ok_pen)
    return pd.DataFrame(resultados)


# ----------------------------------------------------------------------------
# 8. Guardado
# ----------------------------------------------------------------------------
def _tabla_md(df):
    df = df.astype(str).apply(lambda col: col.str.replace("|", "\\|", regex=False))
    lineas = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    lineas += ["| " + " | ".join(fila) + " |" for fila in df.to_numpy()]
    return "\n".join(lineas)


def _enlace(clave):
    return f"Tabla: [`{TABLAS[clave]}`]({TABLAS[clave]})"


def _desplegable(titulo, contenido):
    return f"<details>\n<summary>{titulo}</summary>\n\n{contenido}\n\n</details>"


def escribir_resumen_md(final, resumen_cortes, decisiones, diccionario, tabla_limpieza, validaciones):
    elegidas = decisiones[decisiones["decision"] == "se queda"]
    salen = decisiones[decisiones["decision"] == "sale"]
    columnas_dec = ["variable", "grupo", "roc_auc", "pr_auc_sobre_azar", "sentido", "decision", "motivo"]
    top = elegidas.sort_values("roc_auc", ascending=False).head(10).reset_index()[columnas_dec[:5]]
    todas = decisiones.sort_values(["decision", "roc_auc"], ascending=[False, False]).reset_index()[columnas_dec]
    dic = diccionario[["columna", "uso", "grupo", "descripcion", "regla_para_faltantes", "transformacion"]]
    texto = f"""# Resumen del preprocesamiento

Generado automáticamente por `src/preprocessing.py` (o por `notebooks/02_preprocesamiento.ipynb`). Se reemplaza en cada ejecución.

## Dataset final

- Archivo: `data/processed/{ARCHIVO_DATASET.name}`
- Filas: {len(final):,} (una por proveedor y fecha de corte) | proveedores distintos: {final['id_proveedor'].nunique():,}
- Columnas: {final.shape[1]} (2 de identificación, 3 de target y {final.shape[1] - 5} predictoras)
- Población: personas naturales y jurídicas con al menos una buena pro en los {VENTANA_MESES} meses previos al corte (sin consorcios ni no domiciliados).
- Target: inhabilitación o multa en los {HORIZONTE_MESES} meses siguientes al corte.

## Filas y prevalencia por corte

{_tabla_md(resumen_cortes.reset_index())}

{_enlace("cortes")}

## Limpieza

{_tabla_md(tabla_limpieza)}

{_enlace("limpieza")}

## Selección de variables (solo cortes de entrenamiento)

De {len(decisiones)} variables candidatas se quedan {len(elegidas)} y salen {len(salen)}:
{chr(10).join(f'- {m}: {n}' for m, n in salen['motivo'].str.replace(r' con .*', ' con otra variable', regex=True).value_counts().items())}

Las 10 variables con más señal individual:

{_tabla_md(top)}

{_desplegable(f"Decisión para las {len(decisiones)} variables candidatas", _tabla_md(todas))}

{_enlace("decisiones")}

## Diccionario de datos processed

Las {len(dic)} columnas de `data/processed/{ARCHIVO_DATASET.name}`.

{_desplegable("Ver diccionario completo", _tabla_md(dic))}

{_enlace("diccionario")}

## Validaciones

{_tabla_md(validaciones)}

{_enlace("validaciones")}
"""
    texto += "\n## Gráficos\n\n" + "\n\n".join(
        f"### {titulo}\n\n![{titulo}](../../plots/preprocessing/{FIGURAS[clave]})" for clave, titulo in TITULOS_FIGURAS.items()) + "\n"
    _ruta(SUMMARY_DIR, RESUMEN_MD).write_text(texto, encoding="utf-8")


def guardar_salidas(final, resumen_cortes, decisiones, diccionario, tabla_limpieza, validaciones):
    final.to_csv(ARCHIVO_DATASET, index=False, float_format="%.6g")  # 6 cifras: suficiente y el archivo pesa menos
    guardar_tabla(tabla_limpieza, "limpieza")
    guardar_tabla(resumen_cortes, "cortes", index=True)
    guardar_tabla(decisiones.reset_index(), "decisiones")
    guardar_tabla(diccionario, "diccionario")
    guardar_tabla(validaciones, "validaciones")
    escribir_resumen_md(final, resumen_cortes, decisiones, diccionario, tabla_limpieza, validaciones)
    archivos = [ARCHIVO_DATASET, *PLOTS_DIR.rglob("*"), *SUMMARY_DIR.rglob("*")]
    return sorted(str(p.relative_to(ROOT)) for p in archivos if p.is_file())


# ----------------------------------------------------------------------------
# Ejecución completa
# ----------------------------------------------------------------------------
def main():
    """Ejecuta el preprocesamiento completo: raw -> data/processed/ y results/ (plots y summaries)."""
    plt.switch_backend("Agg")
    limpiar_salidas()
    print("1. Leyendo fuentes")
    fuentes = leer_fuentes()
    print("2. Limpiando")
    tablas, tabla_limpieza, fechas = limpiar_fuentes(fuentes)
    plt.close(graficar_limpieza(tabla_limpieza))
    print("3-4. Construyendo cortes y variables")
    cortes = definir_cortes(tablas["adjudicaciones"], fechas)
    dataset = construir_dataset(tablas, cortes)
    resumen = resumen_por_corte(dataset)
    print(resumen.to_string())
    plt.close(graficar_cortes(resumen))
    print("5-6. Seleccionando variables con los cortes de entrenamiento")
    candidatas = columnas_candidatas(dataset)
    train = dataset[dataset["fecha_corte"] <= FIN_TRAIN]
    evaluacion = evaluar_variables(train, candidatas)
    corr = correlaciones(train, candidatas)
    decisiones = seleccionar_variables(evaluacion, corr)
    psi = estabilidad(train, candidatas)
    decisiones["psi_max_entre_cortes"] = psi.max(axis=1).round(3)
    for fig in (graficar_poder_predictivo(decisiones), graficar_correlaciones(corr, decisiones),
                graficar_estabilidad(psi, decisiones), graficar_deciles(train, decisiones)):
        plt.close(fig)
    elegidas = decisiones[decisiones["decision"] == "se queda"].index.tolist()
    print(f"Variables: {len(candidatas)} candidatas -> {len(elegidas)} elegidas")
    print("7. Tratamiento final y validaciones")
    final, renombre = tratamiento_final(dataset, elegidas)
    diccionario = diccionario_de_datos_processed(final, renombre, decisiones)
    validaciones = validar_dataset(final, tablas, dataset)
    print(validaciones.to_string(index=False))
    print("8. Guardando")
    for archivo in guardar_salidas(final, resumen, decisiones, diccionario, tabla_limpieza, validaciones):
        print("  -", archivo)


if __name__ == "__main__":
    main()
