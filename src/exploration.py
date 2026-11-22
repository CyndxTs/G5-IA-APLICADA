"""Funciones del análisis exploratorio (EDA) de los datos raw.

El notebook ``notebooks/01_eda.ipynb`` usa estas funciones paso a paso y comenta
los resultados. También se puede ejecutar todo de una vez desde la raíz del
repositorio:

    python src/exploration.py

En ambos casos se reemplazan las salidas anteriores:
- ``results/plots/exploration/``: gráficos, en una carpeta por fuente.
- ``results/summaries/exploration/``: ``resumen.md`` con los hallazgos y decisiones, y la
  carpeta ``tables/`` con las tablas que muestra el resumen (fuentes, diccionario de
  datos raw, cruces entre fuentes y tasa de sanción por grupo).

Los archivos se leen por carpeta, sin depender de su nombre exacto: se toman
todos los ``.xlsx`` (o ``.csv`` / ``.xls``) de cada carpeta de ``data/raw/`` y el
año se obtiene del nombre del archivo cuando está presente.
"""

import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from lxml import html as lxml_html

# ----------------------------------------------------------------------------
# Rutas, colores y nombres de los gráficos
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PLOTS_DIR = ROOT / "results" / "plots" / "exploration"
SUMMARY_DIR = ROOT / "results" / "summaries" / "exploration"

COLOR_PRIMARIO = "#1f77b4"
COLOR_SECUNDARIO = "#ff7f0e"
COLOR_ACENTO1 = "#2E86AB"
COLOR_ACENTO2 = "#A23B72"

FIGURAS = {
    "conv_categoricas": "convocatorias/variables_categoricas_principales.png",
    "conv_montos_fechas": "convocatorias/montos_referenciales_e_items_por_mes.png",
    "adj_tipo_montos": "adjudicaciones/tipo_de_proveedor_y_montos_adjudicados.png",
    "adj_fechas": "adjudicaciones/buenas_pro_por_trimestre_y_anio_de_archivo.png",
    "ofertantes": "ofertantes/postores_por_item_y_participacion_de_proveedores.png",
    "contratos_cobertura": "contratos/cobertura_de_contratos_por_tipo_de_proceso.png",
    "contratos_fechas": "contratos/firmas_por_trimestre_y_dias_desde_la_buena_pro.png",
    "penalidades": "ejecucion/penalidades_por_anio_tipo_y_monto.png",
    "ampliaciones_arbitraje": "ejecucion/ampliaciones_y_arbitrajes_por_anio.png",
    "rnp": "sanciones/rnp_tipo_estado_y_monto_de_multas.png",
    "sanciones_anio_motivo": "sanciones/sanciones_por_anio_y_motivo.png",
    "tasas_grupo": "objetivo/tasa_de_sancion_a_12_meses_por_grupo.png",
    "tiempo_sancion": "objetivo/tiempo_hasta_la_siguiente_sancion.png",
}

CLAVE_ITEM = ["codigoconvocatoria", "n_item"]           # convocatoria-ítem (convocatorias y adjudicaciones)
CLAVE_CONTRATO_ITEM = ["n_cod_contrato", "num_item"]
TIPOS_CON_RUC = ["Persona Juridica", "Persona Natural"]  # proveedores que pueden cruzarse con sanciones
ETIQUETA_RUC = "RUC de 11 dígitos"
ETIQUETA_CONSORCIO = "código de 5-8 dígitos (consorcio)"
ETIQUETA_EXTRANJERO = "código L... (no domiciliado)"


def limpiar_salidas():
    """Borra los gráficos y el resumen anteriores para que no queden versiones viejas."""
    for carpeta in (PLOTS_DIR, SUMMARY_DIR):
        if carpeta.exists():
            shutil.rmtree(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)


def guardar_figura(fig, clave):
    """Guarda la figura en results/plots/exploration/ con el nombre definido en FIGURAS."""
    ruta = PLOTS_DIR / FIGURAS[clave]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, dpi=150, bbox_inches="tight")
    return ruta


def _estilo(ax, titulo, eje="y"):
    ax.set_title(titulo, fontsize=12, fontweight="bold")
    ax.grid(axis=eje, alpha=0.3)


def anio_en_nombre(nombre):
    encontrado = re.search(r"(20\d{2})", str(nombre))
    return int(encontrado.group(1)) if encontrado else np.nan


def _fecha(serie, formato=None):
    return pd.to_datetime(serie, format=formato, errors="coerce")


# ----------------------------------------------------------------------------
# 1. Inventario y lectura de archivos
# ----------------------------------------------------------------------------
def inventario_archivos(raw=RAW):
    """Lista los archivos de data/raw con su carpeta y tamaño."""
    return pd.DataFrame([
        {"carpeta": f.parent.name, "archivo": f.name, "tamaño_MB": round(f.stat().st_size / 1e6, 1)}
        for f in sorted(raw.rglob("*")) if f.is_file()
    ])


def leer_anuales(carpeta, raw=RAW, verbose=True):
    """Lee todos los Excel de una carpeta como texto, sin depender del nombre del archivo.

    Devuelve el DataFrame apilado (encabezados en minúscula para poder juntar los
    años, más las columnas ``archivo`` y ``anio_archivo``) y un diccionario con los
    encabezados originales por archivo.
    """
    partes, encabezados = [], {}
    for f in sorted((raw / carpeta).glob("*.xlsx")):
        if verbose:
            print("Leyendo:", f"{carpeta}/{f.name}")
        df = pd.read_excel(f, dtype=str, engine="openpyxl")
        encabezados[f.name] = list(df.columns)
        df.columns = [c.strip().lower() for c in df.columns]
        df["archivo"] = f.name
        df["anio_archivo"] = anio_en_nombre(f.name)
        partes.append(df)
    if not partes:
        raise FileNotFoundError(f"No hay archivos .xlsx en {raw / carpeta}")
    partes = [p for p in partes if len(p)] or partes[:1]
    return pd.concat(partes, ignore_index=True), encabezados


def tabla_archivos(fuentes):
    """Compara filas y encabezados por archivo. ``fuentes``: {carpeta: (df, encabezados)}."""
    filas = []
    for carpeta, (df, encabezados) in fuentes.items():
        base = [c.lower() for c in list(encabezados.values())[0]]
        for archivo, cols in encabezados.items():
            cols_min = [c.lower() for c in cols]
            filas.append({
                "carpeta": carpeta, "archivo": archivo,
                "filas": int((df["archivo"] == archivo).sum()), "columnas": len(cols),
                "encabezados_en_mayúscula": all(c == c.upper() for c in cols),
                "diferencias_con_el_primer_año": ", ".join(sorted(set(cols_min) ^ set(base))) or "-",
            })
    return pd.DataFrame(filas)


def perfil_columnas(df, excluir=("archivo", "anio_archivo")):
    """Tipo, % de nulos, valores distintos y un ejemplo por columna."""
    filas = []
    for c in df.columns:
        if c in excluir:
            continue
        s = df[c]
        filas.append({"columna": c, "tipo": str(s.dtype), "%_nulos": round(s.isna().mean() * 100, 1),
                      "valores_distintos": s.nunique(),
                      "ejemplo": str(s.dropna().iloc[0])[:45] if s.notna().any() else ""})
    perfil = pd.DataFrame(filas).set_index("columna")
    perfil["constante"] = perfil["valores_distintos"] <= 1
    return perfil


def clasificar_identificador(serie):
    """Clasifica un identificador de proveedor: RUC, código de consorcio, no domiciliado u otro."""
    r = serie.astype("string")
    return pd.Series(np.select(
        [r.str.fullmatch(r"\d{11}").fillna(False), r.str.fullmatch(r"\d{5,8}").fillna(False),
         r.str.match(r"^L\d+$").fillna(False)],
        [ETIQUETA_RUC, ETIQUETA_CONSORCIO, ETIQUETA_EXTRANJERO], default="otro"), index=r.index)


def familia_proceso(tipo_proceso):
    """Agrupa los ~40 tipos de proceso de selección en familias."""
    tp = tipo_proceso.fillna("").str.upper()
    return pd.Series(np.select(
        [tp.str.contains("SIMPLIFICADA"), tp.str.contains("SUBASTA"), tp.str.contains("LICITACI"),
         tp.str.contains("CONCURSO"), tp.str.contains("DIRECTA"), tp.str.contains("COMPARACI")],
        ["Adjudicación simplificada", "Subasta inversa", "Licitación pública", "Concurso público",
         "Contratación directa", "Comparación de precios"], default="Otros"), index=tipo_proceso.index)


# ----------------------------------------------------------------------------
# 2. Convocatorias
# ----------------------------------------------------------------------------
def preparar_convocatorias(convocatorias_raw):
    """Convierte montos y fechas de las convocatorias a su tipo real."""
    conv = convocatorias_raw.rename(columns={"sector / nivel de gobierno": "sector_nivel_gobierno"}).copy()
    for c in ["montoreferencial", "monto_referencial_item"]:
        conv[c] = pd.to_numeric(conv[c], errors="coerce")
    for c in ["fecha_convocatoria", "fechaintegracionbases", "fechapresentacionpropuesta"]:
        conv[c] = _fecha(conv[c])
    return conv


def graficar_categoricas_convocatorias(convocatorias,
                                       columnas=("tipoentidad", "objetocontractual",
                                                 "tipoprocesoseleccion", "sector_nivel_gobierno")):
    fig, ax = plt.subplots(2, 2, figsize=(14, 7.5))
    for a, c in zip(ax.ravel(), columnas):
        convocatorias[c].value_counts().head(8).sort_values().plot.barh(ax=a, color=COLOR_PRIMARIO)
        a.set_ylabel("")
        a.set_xlabel("ítems")
        _estilo(a, c, "x")
    fig.tight_layout()
    guardar_figura(fig, "conv_categoricas")
    return fig


def graficar_montos_fechas_convocatorias(convocatorias):
    fig, ax = plt.subplots(1, 2, figsize=(14, 4))
    np.log10(convocatorias["monto_referencial_item"].clip(lower=1)).plot.hist(bins=40, ax=ax[0], color=COLOR_PRIMARIO)
    ax[0].set_ylabel("ítems")
    ax[0].set_xlabel("log10(monto referencial)")
    _estilo(ax[0], "Monto referencial por ítem (log10)", "both")
    por_mes = convocatorias["fecha_convocatoria"].dt.to_period("M").value_counts().sort_index()
    ax[1].plot(por_mes.index.astype(str), por_mes.values, marker="o", color=COLOR_PRIMARIO, markersize=3)
    ax[1].set_xticks(range(0, len(por_mes), 3))
    ax[1].set_xticklabels(por_mes.index.astype(str)[::3], rotation=45)
    ax[1].set_ylabel("ítems")
    _estilo(ax[1], "Ítems convocados por mes", "both")
    fig.tight_layout()
    guardar_figura(fig, "conv_montos_fechas")
    return fig


# ----------------------------------------------------------------------------
# 3. Adjudicaciones
# ----------------------------------------------------------------------------
def preparar_adjudicaciones(adjudicaciones_raw):
    """Convierte fechas y montos, renombra el RUC del proveedor y agrega la familia de proceso."""
    adj = adjudicaciones_raw.rename(columns={"ruc proveedor": "ruc_proveedor"}).copy()
    for c in ["fecha_convocatoria", "fecha_buenapro", "fecha_consentimiento_bp"]:
        adj[c] = _fecha(adj[c], "%d/%m/%Y")
    for c in ["monto_referencial_item_soles", "monto_adjudicado_item_soles", "cantidad_adjudicado_item"]:
        adj[c] = pd.to_numeric(adj[c], errors="coerce")
    adj["patron_id"] = clasificar_identificador(adj["ruc_proveedor"])
    adj["familia_proceso"] = familia_proceso(adj["tipoprocesoseleccion"])
    return adj


def estructura_adjudicaciones(adj, convocatorias):
    """Qué representa cada fila y cómo calza con las convocatorias."""
    por_item = adj.groupby(CLAVE_ITEM).agg(filas=("ruc_proveedor", "size"), ganadores=("ruc_proveedor", "nunique"))
    k_adj = set(por_item.index)
    k_conv = set(zip(convocatorias["codigoconvocatoria"], convocatorias["n_item"]))
    dias_bp = (adj["fecha_buenapro"] - adj["fecha_convocatoria"]).dt.days
    return {
        "filas": len(adj), "items": len(por_item), "duplicadas": int(adj.duplicated().sum()),
        "items_varios_ganadores": int((por_item["ganadores"] > 1).sum()),
        "items_en_convocatorias": len(k_adj & k_conv), "items_convocatorias": len(k_conv),
        "sin_fecha_buenapro": int(adj["fecha_buenapro"].isna().sum()),
        "dias_conv_bp": dias_bp.describe(),
        "tipo_proveedor": adj["tipo_proveedor"].value_counts(),
        "patron_por_tipo": pd.crosstab(adj["tipo_proveedor"], adj["patron_id"]),
        "monedas": adj["moneda"].value_counts(),
    }


def graficar_adjudicaciones_tipo_montos(adj):
    fig, ax = plt.subplots(1, 3, figsize=(17, 4.2))
    adj["tipo_proveedor"].value_counts().sort_values().plot.barh(ax=ax[0], color=COLOR_PRIMARIO)
    ax[0].set_ylabel("")
    ax[0].set_xlabel("ítems adjudicados (miles)")
    ax[0].xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x / 1000:.0f}"))
    _estilo(ax[0], "Tipo de proveedor ganador", "x")
    np.log10(adj["monto_adjudicado_item_soles"].clip(lower=1)).plot.hist(bins=40, ax=ax[1], color=COLOR_PRIMARIO)
    ax[1].set_xlabel("log10(monto adjudicado en soles)")
    ax[1].set_ylabel("ítems")
    _estilo(ax[1], "Monto adjudicado por ítem (log10)", "both")
    ratio = (adj["monto_adjudicado_item_soles"] / adj["monto_referencial_item_soles"]).where(
        adj["monto_referencial_item_soles"] > 0)
    ratio.clip(0, 1.5).plot.hist(bins=60, ax=ax[2], color=COLOR_SECUNDARIO)
    ax[2].set_xlabel("monto adjudicado / monto referencial (recortado en 1.5)")
    ax[2].set_ylabel("ítems")
    _estilo(ax[2], "Adjudicado frente a referencial", "both")
    fig.tight_layout()
    guardar_figura(fig, "adj_tipo_montos")
    return fig


def graficar_fechas_adjudicaciones(adj):
    trimestre = adj["fecha_buenapro"].dt.to_period("Q").value_counts().sort_index()
    fig, ax = plt.subplots(1, 2, figsize=(15, 4.2), gridspec_kw={"width_ratios": [1.6, 1]})
    ax[0].bar(trimestre.index.astype(str), trimestre.values, color=COLOR_PRIMARIO)
    ax[0].tick_params(axis="x", rotation=45)
    ax[0].set_ylabel("ítems adjudicados")
    _estilo(ax[0], "Buenas pro por trimestre")
    con_fecha = adj.dropna(subset=["fecha_buenapro"])
    cruce = pd.crosstab(con_fecha["anio_archivo"].astype(int).rename("archivo (año)"),
                        con_fecha["fecha_buenapro"].dt.year.astype(int).rename("año de la buena pro"))
    sns.heatmap(cruce, annot=True, fmt="d", cmap="Blues", cbar=False, ax=ax[1], annot_kws={"size": 8})
    ax[1].set_title("Año del archivo vs año de la buena pro", fontsize=12, fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "adj_fechas")
    return fig


# ----------------------------------------------------------------------------
# 4. Ofertantes
# ----------------------------------------------------------------------------
def preparar_ofertantes(ofertantes_raw):
    """Renombra la llave, convierte fechas y quita postores repetidos en el mismo ítem."""
    of = ofertantes_raw.rename(columns={"codigo_convocatoria": "codigoconvocatoria"}).copy()
    of["fechaconvocatoria"] = _fecha(of["fechaconvocatoria"])
    of["fecha_presentacion_propuesta"] = _fecha(of["fecha_presentacion_propuesta"])
    n_rep = int(of.duplicated(CLAVE_ITEM + ["ruc_codigo_postor"]).sum())
    of = of.drop_duplicates(CLAVE_ITEM + ["ruc_codigo_postor"]).reset_index(drop=True)
    of["patron_id"] = clasificar_identificador(of["ruc_codigo_postor"])
    return of, n_rep


def resumen_ofertantes(of, adj):
    """Postores por ítem, cobertura frente a adjudicaciones y si el ganador figura entre los postores."""
    postores = of.groupby(CLAVE_ITEM).size().rename("n_postores")
    k_adj = set(zip(adj["codigoconvocatoria"], adj["n_item"]))
    claves_postor = set(zip(of["codigoconvocatoria"], of["n_item"], of["ruc_codigo_postor"]))
    ganadores = adj.drop_duplicates(CLAVE_ITEM + ["ruc_proveedor"])
    en_postores = pd.Series([(a, b, c) in claves_postor for a, b, c in
                             zip(ganadores["codigoconvocatoria"], ganadores["n_item"], ganadores["ruc_proveedor"])],
                            index=ganadores.index)
    items_con_postores = set(postores.index)
    sin_postores = adj[[k not in items_con_postores for k in zip(adj["codigoconvocatoria"], adj["n_item"])]]
    return {
        "postores": postores,
        "pct_items_adj_con_postores": len(k_adj & set(postores.index)) / len(k_adj) * 100,
        "pct_ganador_entre_postores": en_postores.mean() * 100,
        "ganador_entre_postores_por_tipo": en_postores.groupby(ganadores["tipo_proveedor"]).mean() * 100,
        "procesos_sin_postores": sin_postores["tipoprocesoseleccion"].value_counts().head(6),
        "fechas_propuesta_antes_2000": int((of["fecha_presentacion_propuesta"] < "2000-01-01").sum()),
    }


def participacion_proveedores(of, adj):
    """Por proveedor con RUC: ofertas presentadas, ítems ganados y tasa de éxito."""
    ofertas = of[of["patron_id"] == ETIQUETA_RUC].groupby("ruc_codigo_postor").size().rename("ofertas")
    ganados = adj[adj["patron_id"] == ETIQUETA_RUC].drop_duplicates(CLAVE_ITEM + ["ruc_proveedor"]) \
        .groupby("ruc_proveedor").size().rename("ganados")
    part = pd.concat([ofertas, ganados], axis=1).fillna(0)
    part["tasa_exito"] = (part["ganados"] / part["ofertas"]).where(part["ofertas"] > 0).clip(upper=1)
    return part


def graficar_ofertantes(postores, participacion):
    fig, ax = plt.subplots(1, 3, figsize=(17, 4.2))
    dist = postores.clip(upper=10).value_counts().sort_index()
    ax[0].bar([str(int(i)) if i < 10 else "10+" for i in dist.index], dist.values, color=COLOR_PRIMARIO)
    ax[0].set_xlabel("postores por ítem")
    ax[0].set_ylabel("ítems")
    _estilo(ax[0], "Competencia: postores por ítem")
    np.log10(participacion.loc[participacion["ofertas"] > 0, "ofertas"]).plot.hist(bins=40, ax=ax[1], color=COLOR_PRIMARIO)
    ax[1].set_xlabel("log10(ofertas presentadas 2022-2026)")
    ax[1].set_ylabel("proveedores")
    _estilo(ax[1], "Ofertas por proveedor (log10)", "both")
    participacion.loc[participacion["ofertas"] >= 5, "tasa_exito"].plot.hist(bins=40, ax=ax[2], color=COLOR_SECUNDARIO)
    ax[2].set_xlabel("ítems ganados / ofertas (proveedores con 5+ ofertas)")
    ax[2].set_ylabel("proveedores")
    _estilo(ax[2], "Tasa de éxito por proveedor", "both")
    fig.tight_layout()
    guardar_figura(fig, "ofertantes")
    return fig


# ----------------------------------------------------------------------------
# 5. Contratos
# ----------------------------------------------------------------------------
def preparar_contratos(contratos_raw):
    """Convierte montos y fechas de contratos a su tipo real (sin limpiar nada más)."""
    contratos = contratos_raw.copy()
    for c in [x for x in contratos.columns if x.startswith("monto")]:
        contratos[c] = pd.to_numeric(contratos[c], errors="coerce")
    for c in [x for x in contratos.columns if x.startswith("fecha")]:
        contratos[c] = _fecha(contratos[c])
    return contratos


def items_contrato(contratos):
    """Una fila por contrato-ítem, con el patrón del identificador y el id del proveedor."""
    items = contratos.drop_duplicates(CLAVE_CONTRATO_ITEM).copy()
    items["patron_id"] = clasificar_identificador(items["ruc_contratista"])
    es_consorcio = items["patron_id"] == ETIQUETA_CONSORCIO
    items["id_proveedor"] = items["ruc_destinatario_pago"].where(es_consorcio, items["ruc_contratista"])
    return items


def estructura_contratos(contratos, items):
    """Resume qué representa cada fila del archivo de contratos."""
    tam_grupo = contratos.groupby(CLAVE_CONTRATO_ITEM).size()
    repetidos = contratos[contratos.duplicated(CLAVE_CONTRATO_ITEM, keep=False)]
    cambian = pd.Series({c: int((repetidos.groupby(CLAVE_CONTRATO_ITEM)[c].nunique(dropna=False) > 1).sum())
                         for c in contratos.columns if c not in CLAVE_CONTRATO_ITEM + ["archivo", "anio_archivo"]})
    return {
        "filas": len(contratos), "contrato_items": len(tam_grupo),
        "contratos": contratos["n_cod_contrato"].nunique(),
        "codigo_igual": bool((contratos["n_cod_contrato"] == contratos["codigo_contrato"]).all()),
        "en_dos_archivos": int((contratos.groupby(CLAVE_CONTRATO_ITEM)["archivo"].nunique() > 1).sum()),
        "duplicadas": int(contratos.duplicated().sum()),
        "filas_por_item": tam_grupo.value_counts().sort_index(),
        "columnas_que_cambian": cambian[cambian > 0].rename("contrato-ítem donde cambia"),
        "pct_modificaciones": ((contratos.groupby("n_cod_contrato")[["monto_adicional", "monto_reduccion", "monto_prorroga"]]
                                .max() > 0).mean() * 100).round(1),
    }


def cobertura_contratos(adj, items, top=10):
    """% de ítems adjudicados que tienen contrato en nuestros archivos, por año de archivo y por tipo de proceso."""
    claves = set(zip(items["codigoconvocatoria"], items["num_item"]))
    items_adj = adj.drop_duplicates(CLAVE_ITEM)
    tiene = pd.Series([k in claves for k in zip(items_adj["codigoconvocatoria"], items_adj["n_item"])],
                      index=items_adj.index, name="tiene_contrato")
    por_archivo = tiene.groupby(items_adj["anio_archivo"]).agg(items="size", con_contrato="sum")
    por_archivo["%_con_contrato"] = (por_archivo["con_contrato"] / por_archivo["items"] * 100).round(1)
    por_proceso = (tiene.groupby(items_adj["tipoprocesoseleccion"]).agg(items="size", pct="mean")
                   .sort_values("items", ascending=False).head(top))
    return tiene, por_archivo, por_proceso


def graficar_cobertura_contratos(por_proceso):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    (por_proceso["pct"] * 100).sort_values().plot.barh(ax=ax, color=COLOR_SECUNDARIO)
    ax.set_xlabel("% de ítems adjudicados con contrato en nuestros datos")
    ax.set_ylabel("")
    _estilo(ax, "Cobertura de contratos por tipo de proceso (top 10 por volumen)", "x")
    fig.tight_layout()
    guardar_figura(fig, "contratos_cobertura")
    return fig


def contratos_vs_adjudicacion(items, adj):
    """Compara el proveedor y las fechas del contrato con los de su adjudicación."""
    a = adj.drop_duplicates(CLAVE_ITEM + ["ruc_proveedor"])[CLAVE_ITEM + ["ruc_proveedor", "tipo_proveedor", "fecha_buenapro"]]
    m = items.merge(a, left_on=["codigoconvocatoria", "num_item"], right_on=CLAVE_ITEM, how="inner")
    m["dias_bp_a_firma"] = (m["fecha_suscripcion_contrato"] - m["fecha_buenapro"]).dt.days
    coincide = (m["ruc_contratista"] == m["ruc_proveedor"]).groupby(m["tipo_proveedor"]).mean() * 100
    return m, coincide


def anomalias_fechas_contratos(items):
    cu = items.drop_duplicates("n_cod_contrato")
    dias_pub = (cu["fecha_publicacion_contrato"] - cu["fecha_suscripcion_contrato"]).dt.days
    duracion = (cu["fecha_vigencia_final"] - cu["fecha_vigencia_inicial"]).dt.days
    tabla = pd.DataFrame([
        {"revisión": "firma antes de 2022", "contratos": int((cu["fecha_suscripcion_contrato"] < "2022-01-01").sum())},
        {"revisión": "publicación antes de la firma", "contratos": int((dias_pub < 0).sum())},
        {"revisión": "publicación más de 1 año después de la firma", "contratos": int((dias_pub > 365).sum())},
        {"revisión": "vigencia final antes de la inicial", "contratos": int((duracion < 0).sum())},
        {"revisión": "duración mayor a 10 años", "contratos": int((duracion > 3650).sum())},
    ])
    return tabla, dias_pub


def graficar_fechas_contratos(items, cruce_adj):
    cu = items.drop_duplicates("n_cod_contrato")
    trimestre = cu["fecha_suscripcion_contrato"].dt.to_period("Q")
    trimestre = trimestre[trimestre >= pd.Period("2022Q1")].value_counts().sort_index()
    fig, ax = plt.subplots(1, 2, figsize=(15, 4.2), gridspec_kw={"width_ratios": [1.6, 1]})
    ax[0].bar(trimestre.index.astype(str), trimestre.values, color=COLOR_PRIMARIO)
    ax[0].tick_params(axis="x", rotation=45)
    ax[0].set_ylabel("contratos")
    _estilo(ax[0], "Contratos por trimestre de suscripción")
    cruce_adj["dias_bp_a_firma"].clip(-10, 120).plot.hist(bins=65, ax=ax[1], color=COLOR_PRIMARIO)
    ax[1].set_xlabel("días entre la buena pro y la firma (recortado en 120)")
    ax[1].set_ylabel("contrato-ítem")
    _estilo(ax[1], "De la buena pro a la firma", "both")
    fig.tight_layout()
    guardar_figura(fig, "contratos_fechas")
    return fig


# ----------------------------------------------------------------------------
# 6. Ejecución de contratos: ampliaciones, arbitraje y penalidades
# ----------------------------------------------------------------------------
def preparar_ampliaciones(ampliaciones_raw):
    amp = ampliaciones_raw.copy()
    for c in ["fecha_modificacion_contrato", "fecha_creacion_ampliacion", "fecha_publicacion_ampliacion",
              "fecha_vigencia_inicio", "fecha_vigencia_fin", "fecha_vigencia_fin_actual"]:
        amp[c] = _fecha(amp[c], "%d/%m/%Y")
    amp["plazo"] = pd.to_numeric(amp["plazo"], errors="coerce")
    return amp


def resumen_ampliaciones(amp, contratos):
    codigos = set(contratos["n_cod_contrato"])
    return {
        "filas": len(amp), "contratos_distintos": amp["codigocontrato"].nunique(),
        "pct_en_contratos": amp["codigocontrato"].isin(codigos).mean() * 100,
        "pct_contratos_con_ampliacion": len(set(amp["codigocontrato"]) & codigos) / len(codigos) * 100,
        "publicacion_igual_creacion": (amp["fecha_publicacion_ampliacion"] == amp["fecha_creacion_ampliacion"]).mean() * 100,
        "fecha_modificacion_imposible": int((amp["fecha_modificacion_contrato"] < "2000-01-01").sum()),
        "plazo": amp["plazo"].describe(),
        "dias_modificacion_a_publicacion": (amp["fecha_publicacion_ampliacion"] - amp["fecha_modificacion_contrato"]).dt.days.describe(),
        "sistema_origen": amp["sistema_origen"].value_counts(),
    }


def preparar_arbitraje(arbitraje_raw):
    arb = arbitraje_raw.copy()
    for c in [x for x in arb.columns if x.startswith("fecha")]:
        arb[c] = _fecha(arb[c], "%d/%m/%Y")
    return arb


def leer_penalidades(raw=RAW):
    """Lee el CSV de penalidades (separado por '|', en cp1252).

    Algunas filas tienen '|' dentro de la descripción o saltos de línea dentro de un
    campo, así que se lee línea por línea: los 6 primeros campos y el último (monto)
    son fijos y lo que queda en medio es la descripción.
    """
    archivo = sorted((raw / "penalidades").glob("*.csv"))[-1]
    lineas = archivo.read_text(encoding="cp1252").splitlines()
    cabecera = [c.strip() for c in lineas[0].split("|")]
    n, filas, buffer, reparadas = len(cabecera), [], "", 0
    for linea in lineas[1:]:
        if buffer:
            reparadas += 1
        buffer = linea if not buffer else buffer + " " + linea
        if buffer.count("|") >= n - 1:
            partes = buffer.split("|")
            reparadas += int(len(partes) > n)
            filas.append(partes[:6] + ["|".join(partes[6:-1]), partes[-1]])
            buffer = ""
    pen = pd.DataFrame(filas, columns=["id_contrato", "ruc_contratista", "tipo_penalidad", "objeto_contrato",
                                       "entidad", "fecha_penalidad", "motivo", "monto"])
    pen["fecha_penalidad"] = _fecha(pen["fecha_penalidad"], "%d/%m/%y")
    pen["monto"] = pd.to_numeric(pen["monto"].str.strip().str.replace(",", ".", regex=False), errors="coerce")
    return pen, archivo, reparadas


def resumen_penalidades(pen, contratos, adj):
    return {
        "filas": len(pen), "duplicadas": int(pen.duplicated().sum()),
        "contratos": pen["id_contrato"].nunique(), "proveedores": pen["ruc_contratista"].nunique(),
        "pct_ruc_11": pen["ruc_contratista"].str.fullmatch(r"\d{11}").mean() * 100,
        "pct_contrato_en_contratos": pen["id_contrato"].isin(set(contratos["n_cod_contrato"])).mean() * 100,
        "pct_ruc_en_adjudicaciones": pen["ruc_contratista"].isin(set(adj["ruc_proveedor"])).mean() * 100,
        "fecha_min": pen["fecha_penalidad"].min(), "fecha_max": pen["fecha_penalidad"].max(),
        "fechas_futuras": int((pen["fecha_penalidad"] > adj["fecha_buenapro"].max()).sum()),
        "tipo": pen["tipo_penalidad"].value_counts(), "monto": pen["monto"].describe(),
    }


def graficar_penalidades(pen):
    fig, ax = plt.subplots(1, 2, figsize=(14, 4.2))
    anual = pd.crosstab(pen["fecha_penalidad"].dt.year, pen["tipo_penalidad"])
    anual.plot.bar(ax=ax[0], color=[COLOR_PRIMARIO, COLOR_SECUNDARIO], rot=0)
    ax[0].set_xlabel("")
    ax[0].set_ylabel("penalidades")
    _estilo(ax[0], "Penalidades por año y tipo")
    np.log10(pen["monto"].clip(lower=1)).plot.hist(bins=40, ax=ax[1], color=COLOR_PRIMARIO)
    ax[1].set_xlabel("log10(monto de la penalidad)")
    ax[1].set_ylabel("penalidades")
    _estilo(ax[1], "Monto de la penalidad (log10)", "both")
    fig.tight_layout()
    guardar_figura(fig, "penalidades")
    return fig


def graficar_ampliaciones_arbitraje(amp, arb):
    fig, ax = plt.subplots(1, 2, figsize=(14, 4.2))
    amp["fecha_publicacion_ampliacion"].dt.year.value_counts().sort_index().plot.bar(ax=ax[0], color=COLOR_PRIMARIO, rot=0)
    ax[0].set_xlabel("año de publicación")
    ax[0].set_ylabel("ampliaciones")
    _estilo(ax[0], "Ampliaciones de contrato por año")
    arb["fecha_instalacion"].dt.year.value_counts().sort_index().plot.bar(ax=ax[1], color=COLOR_ACENTO2, rot=0)
    ax[1].set_xlabel("año de instalación del arbitraje")
    ax[1].set_ylabel("arbitrajes")
    _estilo(ax[1], "Arbitrajes por año")
    fig.tight_layout()
    guardar_figura(fig, "ampliaciones_arbitraje")
    return fig


# ----------------------------------------------------------------------------
# 7. Entidades
# ----------------------------------------------------------------------------
def leer_entidades(raw=RAW):
    archivo = sorted((raw / "entidades_contratantes").glob("*.csv"))[-1]
    return pd.read_csv(archivo, sep="|", encoding="cp1252", dtype=str)


def cobertura_entidades(codigos_entidad, entidades):
    """% de códigos de entidad que existen en la tabla (sin ceros a la izquierda)."""
    validos = set(entidades["CODCONSUCODE"].str.lstrip("0"))
    return codigos_entidad.str.lstrip("0").isin(validos).mean() * 100


# ----------------------------------------------------------------------------
# 8. Sanciones
# ----------------------------------------------------------------------------
def leer_sanciones_conosce(raw=RAW):
    """Inhabilitaciones publicadas en CONOSCE, con fechas convertidas."""
    archivo = sorted((raw / "sancionados").glob("*.csv"))[-1]
    inh = pd.read_csv(archivo, sep="|", encoding="cp1252", dtype=str)
    inh["inicio"] = _fecha(inh["FECHA_INICIO"], "%Y%m%d")
    inh["fin"] = _fecha(inh["FECHA_FIN"], "%Y%m%d")
    return inh, archivo


def resumen_sanciones_conosce(inh):
    originales = [c for c in inh.columns if c not in ("inicio", "fin")]
    return pd.Series({
        "filas": len(inh), "RUC distintos": inh["RUC"].nunique(),
        "RUC de 11 dígitos %": round(inh["RUC"].str.fullmatch(r"\d{11}").mean() * 100, 1),
        "filas duplicadas": int(inh.duplicated(subset=originales).sum()),
        "RUC+resolución repetidos": int(inh.duplicated(["RUC", "NUMERO_RESOLUCION"]).sum()),
        "sin fecha fin": int(inh["fin"].isna().sum()),
        "fin antes de inicio": int((inh["fin"] < inh["inicio"]).sum()),
        "fecha de corte": inh["FECHA_CORTE"].unique()[0],
    }, name="CONOSCE inhabilitaciones")


COLUMNAS_RNP_INH = ["numero", "razon_social", "ruc", "resolucion", "periodo", "desde", "hasta",
                    "infraccion", "otra_infraccion", "norma", "estado"]
COLUMNAS_RNP_MUL = ["numero", "razon_social", "ruc", "resolucion", "fecha_resolucion", "monto_multa",
                    "infraccion", "periodo_suspension", "desde", "hasta", "otra_infraccion",
                    "norma", "verificacion_pago", "estado"]


def leer_rnp(raw=RAW):
    """Lee la exportación del RNP (.xls que en realidad es HTML) con sus dos tablas.

    Las filas de 11 celdas son inhabilitaciones y las de 14, multas.
    """
    archivo = sorted((raw / "rnp").glob("*.xls"))[-1]
    documento = lxml_html.fromstring(archivo.read_bytes().decode("cp1252"))
    filas_inh, filas_mul = [], []
    for fila in documento.xpath("//tr"):
        celdas = fila.xpath("./td|./th")
        if len(celdas) in (11, 14) and celdas[0].text_content().strip().isdigit():
            valores = [" ".join(c.text_content().split()) for c in celdas]
            (filas_inh if len(celdas) == 11 else filas_mul).append(valores)
    inh = pd.DataFrame(filas_inh, columns=COLUMNAS_RNP_INH)
    mul = pd.DataFrame(filas_mul, columns=COLUMNAS_RNP_MUL)
    for df in (inh, mul):
        df["desde_dt"] = _fecha(df["desde"], "%d/%m/%Y")
        df["hasta_dt"] = _fecha(df["hasta"], "%d/%m/%Y")
    mul["fecha_resolucion_dt"] = _fecha(mul["fecha_resolucion"], "%d/%m/%Y")
    mul["monto_multa"] = pd.to_numeric(mul["monto_multa"], errors="coerce")
    return inh, mul, archivo


def graficar_rnp(rnp_inh, rnp_mul):
    fig, ax = plt.subplots(1, 3, figsize=(15, 3.8))
    (rnp_inh["periodo"].eq("DEFINITIVO").map({True: "Definitiva", False: "Temporal"})
     .value_counts().plot.bar(ax=ax[0], color=COLOR_PRIMARIO, rot=0))
    _estilo(ax[0], "RNP inhabilitaciones: tipo")
    rnp_inh["estado"].value_counts().plot.bar(ax=ax[1], color=COLOR_PRIMARIO, rot=0)
    _estilo(ax[1], "RNP inhabilitaciones: estado")
    np.log10(rnp_mul["monto_multa"].clip(lower=1)).plot.hist(bins=40, ax=ax[2], color=COLOR_PRIMARIO)
    _estilo(ax[2], "RNP multas: monto (log10)")
    for a in ax:
        a.set_xlabel("")
        a.set_ylabel("sanciones")
    fig.tight_layout()
    guardar_figura(fig, "rnp")
    return fig


def normalizar_resolucion(serie):
    return serie.str.upper().str.replace(r"\s+", "", regex=True)


def solapamiento_inhabilitaciones(sanc_inh, rnp_inh):
    """Cuántas inhabilitaciones (RUC, resolución) están en ambas fuentes o solo en una."""
    a = set(zip(sanc_inh["RUC"], normalizar_resolucion(sanc_inh["NUMERO_RESOLUCION"])))
    b = set(zip(rnp_inh["ruc"], normalizar_resolucion(rnp_inh["resolucion"])))
    return pd.Series({"en ambas": len(a & b), "solo en RNP": len(b - a), "solo en CONOSCE": len(a - b)},
                     name="inhabilitaciones")


def agrupar_motivo(motivo):
    """Agrupa el texto libre del motivo de infracción en pocas categorías."""
    m = motivo.fillna("").str.upper()
    return pd.Series(np.select(
        [m.str.strip().eq(""), m.str.contains("INEXACTA"), m.str.contains("FALSO|ADULTERAD"), m.str.contains("IMPEDID"),
         m.str.contains("PERFECCIONAR|SUSCRIBIR|FORMALIZAR|MANTENER"), m.str.contains("RESUEL|RESCISI|RESOLUCI")],
        ["sin motivo registrado", "información inexacta", "documentos falsos", "contratar estando impedido",
         "no perfeccionar / no suscribir el contrato", "resolución del contrato"], default="otros"), index=motivo.index)


def construir_eventos(sanc_inh, rnp_inh, rnp_mul):
    """Une las sanciones en eventos (RUC, resolución, tipo), dando prioridad al RNP.

    Fecha del evento: inicio de la inhabilitación o fecha de resolución de la multa.
    Las multas vienen solo del RNP.
    """
    eventos = pd.concat([
        pd.DataFrame({"ruc": rnp_inh["ruc"], "res": normalizar_resolucion(rnp_inh["resolucion"]), "tipo": "inhabilitación",
                      "fecha": rnp_inh["desde_dt"], "fin": rnp_inh["hasta_dt"], "motivo": rnp_inh["infraccion"], "fuente": "RNP"}),
        pd.DataFrame({"ruc": rnp_mul["ruc"], "res": normalizar_resolucion(rnp_mul["resolucion"]), "tipo": "multa",
                      "fecha": rnp_mul["fecha_resolucion_dt"], "fin": rnp_mul["hasta_dt"], "motivo": rnp_mul["infraccion"],
                      "fuente": "RNP"}),
        pd.DataFrame({"ruc": sanc_inh["RUC"], "res": normalizar_resolucion(sanc_inh["NUMERO_RESOLUCION"]),
                      "tipo": "inhabilitación", "fecha": sanc_inh["inicio"], "fin": sanc_inh["fin"],
                      "motivo": sanc_inh["DE_MOTIVO_INFRACCION"], "fuente": "CONOSCE"}),
    ], ignore_index=True)
    n_filas = len(eventos)
    eventos = eventos.drop_duplicates(["ruc", "res", "tipo"]).dropna(subset=["fecha"]).reset_index(drop=True)
    eventos["motivo_grupo"] = agrupar_motivo(eventos["motivo"])
    return eventos, n_filas


def fechas_de_las_fuentes(sanc_inh, rnp_inh, archivo_rnp):
    """Fecha de extracción de cada fuente y fecha de fin más antigua que incluyen."""
    fecha_rnp = re.search(r"(\d{4}-\d{2}-\d{2})", archivo_rnp.name)
    return pd.DataFrame({
        "fecha de extracción": [pd.Timestamp(fecha_rnp.group(1)) if fecha_rnp else pd.NaT,
                                _fecha(sanc_inh["FECHA_CORTE"], "%Y%m%d").max()],
        "fecha de fin más antigua": [rnp_inh["hasta_dt"].min(), sanc_inh["fin"].min()],
    }, index=["RNP", "CONOSCE"])


def graficar_sanciones_anio_motivo(eventos, desde=2015):
    fig, ax = plt.subplots(1, 2, figsize=(15, 4.5))
    anual = pd.crosstab(eventos["fecha"].dt.year, eventos["tipo"]).loc[desde:]
    anual.plot.bar(ax=ax[0], color=[COLOR_PRIMARIO, COLOR_SECUNDARIO], rot=0)
    ax[0].set_xlabel("")
    ax[0].set_ylabel("sanciones")
    _estilo(ax[0], "Sanciones por año del evento")
    motivos = pd.crosstab(eventos["motivo_grupo"], eventos["tipo"])
    motivos.loc[motivos.sum(axis=1).sort_values().index].plot.barh(
        ax=ax[1], stacked=True, color=[COLOR_PRIMARIO, COLOR_SECUNDARIO])
    ax[1].set_ylabel("")
    ax[1].set_xlabel("sanciones")
    _estilo(ax[1], "Motivo de la sanción (agrupado)", "x")
    fig.tight_layout()
    guardar_figura(fig, "sanciones_anio_motivo")
    return fig


# ----------------------------------------------------------------------------
# 9. Relación entre fuentes
# ----------------------------------------------------------------------------
def _pct_en(a, b):
    a = list(a)
    return round(pd.Series(a).isin(set(b)).mean() * 100, 2) if a else np.nan


def tabla_cruces(convocatorias, adj, of, items, amp, arb, pen, entidades, eventos):
    """Para cada par de fuentes: llave usada y % de filas de la primera que encuentran pareja."""
    k_conv = set(zip(convocatorias["codigoconvocatoria"], convocatorias["n_item"]))
    k_adj = set(zip(adj["codigoconvocatoria"], adj["n_item"]))
    k_of = set(zip(of["codigoconvocatoria"], of["n_item"]))
    contratos = set(items["n_cod_contrato"])
    ruc_adj = adj.loc[adj["tipo_proveedor"].isin(TIPOS_CON_RUC), "ruc_proveedor"].drop_duplicates()
    filas = [
        ("convocatoria-ítem", "adjudicación", "codigoconvocatoria + n_item", _pct_en(k_conv, k_adj)),
        ("adjudicación", "ofertantes", "codigoconvocatoria + n_item", _pct_en(k_adj, k_of)),
        ("adjudicación", "contrato", "codigoconvocatoria + n_item / num_item",
         _pct_en(k_adj, set(zip(items["codigoconvocatoria"], items["num_item"])))),
        ("contrato-ítem", "adjudicación", "codigoconvocatoria + num_item / n_item",
         _pct_en(zip(items["codigoconvocatoria"], items["num_item"]), k_adj)),
        ("ampliación", "contrato", "codigocontrato = n_cod_contrato", _pct_en(amp["codigocontrato"], contratos)),
        ("arbitraje", "contrato", "n_cod_contrato", _pct_en(arb["n_cod_contrato"], contratos)),
        ("penalidad", "contrato", "id_contrato = n_cod_contrato", _pct_en(pen["id_contrato"], contratos)),
        ("penalidad", "proveedor adjudicado", "ruc_contratista = ruc_proveedor", _pct_en(pen["ruc_contratista"], ruc_adj)),
        ("adjudicación", "entidad", "codigoentidad (sin ceros)",
         _pct_en(adj["codigoentidad"].str.lstrip("0"), entidades["CODCONSUCODE"].str.lstrip("0"))),
        ("proveedor adjudicado (RUC)", "alguna sanción", "RUC", _pct_en(ruc_adj, eventos["ruc"])),
        ("proveedor adjudicado (RUC)", "alguna penalidad", "RUC", _pct_en(ruc_adj, pen["ruc_contratista"])),
    ]
    return pd.DataFrame(filas, columns=["desde", "hacia", "llave", "% con pareja"])


def analisis_consorcios(adj, items, eventos):
    """Cómo se identifican los consorcios y por qué no podemos ver sus sanciones."""
    ruc_sancionados = set(eventos["ruc"])
    proveedores = adj.drop_duplicates("ruc_proveedor")[["ruc_proveedor", "tipo_proveedor"]]
    por_tipo = proveedores.assign(sancionado=proveedores["ruc_proveedor"].isin(ruc_sancionados)) \
        .groupby("tipo_proveedor")["sancionado"].agg(proveedores="size", pct_sancionado="mean")
    ruc_solos = set(adj.loc[adj["tipo_proveedor"].isin(TIPOS_CON_RUC), "ruc_proveedor"])
    pagos = items.loc[items["patron_id"] == ETIQUETA_CONSORCIO, "ruc_destinatario_pago"].drop_duplicates().to_frame("ruc_pago")
    pagos["también_gana_solo"] = pagos["ruc_pago"].isin(ruc_solos)
    pagos["sancionado"] = pagos["ruc_pago"].isin(ruc_sancionados)
    por_pago = pagos.groupby("también_gana_solo")["sancionado"].agg(pagadores="size", pct_sancionado="mean")
    filas_consorcio = (adj["tipo_proveedor"] == "Consorcio").mean() * 100
    return por_tipo, por_pago, filas_consorcio


# ----------------------------------------------------------------------------
# 10. Primer vistazo al objetivo
# ----------------------------------------------------------------------------
def _fechas_por_ruc(ruc, fechas):
    return pd.Series(fechas.values, index=ruc.values).dropna().groupby(level=0).apply(
        lambda s: np.sort(s.values.astype("datetime64[ns]"))).to_dict()


def tabla_objetivo_adjudicaciones(adj, eventos, pen, postores, fecha_limite, horizonte_meses=12):
    """Una fila por ítem adjudicado a un proveedor con RUC propio (persona natural o jurídica),
    con la buena pro antes de ``fecha_limite`` para que la ventana esté completa.

    Marca si el proveedor recibió una sanción en los ``horizonte_meses`` siguientes a la
    buena pro y si tenía sanciones o penalidades antes (análisis descriptivo).
    """
    base = adj[adj["tipo_proveedor"].isin(TIPOS_CON_RUC)].drop_duplicates(CLAVE_ITEM).dropna(subset=["fecha_buenapro"])
    base = base[base["fecha_buenapro"] <= fecha_limite].copy()
    base["n_postores"] = postores.reindex(pd.MultiIndex.from_frame(base[CLAVE_ITEM])).values

    sanciones = _fechas_por_ruc(eventos["ruc"], eventos["fecha"])
    penalidades = _fechas_por_ruc(pen["ruc_contratista"], pen["fecha_penalidad"])
    vacio = np.array([], dtype="datetime64[ns]")
    f0 = base["fecha_buenapro"].values.astype("datetime64[ns]")
    f1 = (base["fecha_buenapro"] + pd.DateOffset(months=horizonte_meses)).values.astype("datetime64[ns]")
    y, previa, pen_previa, dias = [], [], [], []
    for ruc, a, b in zip(base["ruc_proveedor"], f0, f1):
        e = sanciones.get(ruc, vacio)
        i_a, i_b = np.searchsorted(e, a, "right"), np.searchsorted(e, b, "right")
        y.append(int(i_b > i_a))
        previa.append(int(i_a > 0))
        dias.append((e[i_a] - a) / np.timedelta64(1, "D") if i_a < len(e) else np.nan)
        pen_previa.append(int(np.searchsorted(penalidades.get(ruc, vacio), a, "right") > 0))
    base["sancion_12m"], base["sancion_previa"], base["penalidad_previa"] = y, previa, pen_previa
    base["dias_a_siguiente_sancion"] = dias

    base["quintil_monto"] = pd.qcut(base["monto_adjudicado_item_soles"].rank(method="first"), 5,
                                    labels=["Q1 (menor)", "Q2", "Q3", "Q4", "Q5 (mayor)"])
    base["competencia"] = pd.cut(base["n_postores"], [0, 1, 2, 4, np.inf],
                                 labels=["1 postor", "2 postores", "3-4 postores", "5+ postores"])
    base["antecedentes_sancion"] = base["sancion_previa"].map({0: "sin sanción previa", 1: "con sanción previa"})
    base["antecedentes_penalidad"] = base["penalidad_previa"].map({0: "sin penalidad previa", 1: "con penalidad previa"})
    return base


GRUPOS_OBJETIVO = [("tipo_proveedor", "Tipo de proveedor"), ("familia_proceso", "Familia de proceso"),
                   ("tipoentidad", "Tipo de entidad"), ("objetocontractual", "Objeto contractual"),
                   ("quintil_monto", "Quintil de monto adjudicado"), ("competencia", "Competencia en el ítem"),
                   ("antecedentes_sancion", "Sanción previa"), ("antecedentes_penalidad", "Penalidad previa")]
ORDEN_FIJO = {"quintil_monto", "competencia"}


def tasas_por_grupo(base, grupos=GRUPOS_OBJETIVO, minimo=100):
    """Tasa de sanción a 12 meses por categoría (solo categorías con al menos ``minimo`` ítems)."""
    tasas = {}
    for col, _ in grupos:
        t = base.groupby(col, observed=True)["sancion_12m"].agg(items="size", tasa="mean")
        tasas[col] = t[t["items"] >= minimo]
    return tasas


def graficar_tasas_por_grupo(base, tasas, grupos=GRUPOS_OBJETIVO):
    promedio = base["sancion_12m"].mean() * 100
    fig, axes = plt.subplots(2, 4, figsize=(21, 8))
    for ax, (col, titulo) in zip(axes.ravel(), grupos):
        t = tasas[col]
        orden = t.index if col in ORDEN_FIJO else t["tasa"].sort_values().index
        ax.barh([str(i) for i in orden], t.loc[orden, "tasa"] * 100, color=COLOR_ACENTO1)
        ax.axvline(promedio, color="gray", linestyle="--", alpha=0.7, label=f"Promedio ({promedio:.1f}%)")
        ax.set_xlabel("% con sanción en 12 meses")
        _estilo(ax, titulo, "x")
    axes[0, 0].legend(fontsize=9)
    fig.tight_layout()
    guardar_figura(fig, "tasas_grupo")
    return fig


def graficar_tiempo_hasta_sancion(base, horizonte_meses=12):
    meses = base["dias_a_siguiente_sancion"].dropna() / 30.4375
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.hist(meses, bins=45, color=COLOR_PRIMARIO, label="ítems adjudicados")
    ax.axvline(horizonte_meses, color=COLOR_SECUNDARIO, linestyle="--", label=f"{horizonte_meses} meses (horizonte del target)")
    ax.set_xlabel("Meses entre la buena pro y la siguiente sanción del proveedor")
    ax.set_ylabel("ítems adjudicados")
    ax.legend()
    _estilo(ax, "¿Cuánto tarda en llegar la siguiente sanción?", "both")
    fig.tight_layout()
    guardar_figura(fig, "tiempo_sancion")
    return fig



# ----------------------------------------------------------------------------
# 11. Resumen en Markdown
# ----------------------------------------------------------------------------
TITULOS_FIGURAS = {
    "conv_categoricas": "Convocatorias: variables categóricas principales",
    "conv_montos_fechas": "Convocatorias: montos referenciales e ítems por mes",
    "adj_tipo_montos": "Adjudicaciones: tipo de proveedor y montos",
    "adj_fechas": "Adjudicaciones: buenas pro por trimestre y año de archivo",
    "ofertantes": "Ofertantes: competencia y participación",
    "contratos_cobertura": "Contratos: cobertura por tipo de proceso",
    "contratos_fechas": "Contratos: firmas por trimestre y días desde la buena pro",
    "penalidades": "Penalidades por año, tipo y monto",
    "ampliaciones_arbitraje": "Ampliaciones y arbitrajes por año",
    "rnp": "RNP: tipo, estado y monto de multas",
    "sanciones_anio_motivo": "Sanciones por año y motivo",
    "tasas_grupo": "Tasa de sanción a 12 meses por grupo",
    "tiempo_sancion": "Tiempo hasta la siguiente sanción",
}

DECISIONES_EDA = [
    ("Todas", "Un archivo por año con las mismas columnas; encabezados en mayúscula", "Leer por carpeta sin depender del nombre y normalizar encabezados"),
    ("Adjudicaciones", "Cubre el 100% de los ítems convocados, con RUC y tipo del ganador, monto en soles y fecha de buena pro", "Es la base del historial del proveedor; fecha de disponibilidad = buena pro"),
    ("Adjudicaciones", "Consorcios con código corto y no domiciliados con código `L...`, sin RUC", "Excluirlos: no podemos observar sus sanciones; trabajamos con personas naturales y jurídicas"),
    ("Adjudicaciones", "El tipo de proveedor separa persona natural y jurídica", "Variable: persona jurídica (sí/no)"),
    ("Convocatorias", "~40 tipos de proceso con variantes; sector y sistema de contratación", "Agrupar en familias de proceso; proporciones por familia, tipo de entidad y sector"),
    ("Convocatorias", "Montos muy asimétricos", "`log1p` en los montos"),
    ("Ofertantes", "99% de cobertura; muchos ítems con un solo postor; participación muy desigual", "Variables de competencia (postores por ítem ganado) y de participación (ofertas, tasa de éxito); fecha = presentación de la propuesta (convocatoria si es imposible)"),
    ("Contratos", "Solo ~9% de lo adjudicado; una fila por modificación; modificaciones sin fecha", "Solo como complemento (duración, ampliaciones); no usar adicionales, reducciones ni prórrogas"),
    ("Penalidades", "Con fecha y RUC; líneas mal formadas, coma decimal y duplicados", "Leer línea por línea, quitar duplicados; antecedentes de penalidades antes del corte"),
    ("Ampliaciones", "Con fecha pero sin RUC; solo llegan al proveedor por contrato", "Evaluar si aportan; cobertura limitada"),
    ("Arbitraje", "Solo ~600 registros", "No usar como variable"),
    ("Entidades", "El código cruza solo sin ceros a la izquierda", "Normalizar el código; aporta poco frente a adjudicaciones"),
    ("Sanciones", "El RNP contiene casi todo CONOSCE; multas solo en el RNP", "Unir por (RUC, resolución, tipo) dando prioridad al RNP"),
    ("Sanciones", "Solo sanciones que terminaron en los últimos ~5 años", "Target completo desde 2022; antecedentes subestimados en los primeros cortes"),
    ("Sanciones", "Fecha de extracción oct-2026", "Cortes semestrales desde 2022 hasta el último con ventana de 12 meses completa"),
    ("Sanciones", "Motivos en texto libre; composición cambia por año", "Agrupar motivos; la prevalencia cambiará entre cortes"),
]


# Columnas raw que usa el preprocesamiento y para qué (el resto no se usa)
COLUMNAS_USADAS = {
    "convocatorias": {"codigoconvocatoria": "llave del ítem", "n_item": "llave del ítem",
                      "sector / nivel de gobierno": "sector de la entidad"},
    "adjudicaciones": {"codigoconvocatoria": "llave del ítem", "n_item": "llave del ítem",
                       "ruc proveedor": "identificador del proveedor", "tipo_proveedor": "población y tipo de contribuyente",
                       "fecha_buenapro": "fecha en que se conoce el ítem", "codigoentidad": "diversificación por entidad",
                       "tipoentidad": "composición por tipo de entidad", "objetocontractual": "composición por objeto",
                       "tipoprocesoseleccion": "familia de proceso", "monto_adjudicado_item_soles": "montos",
                       "monto_referencial_item_soles": "ratio adjudicado / referencial",
                       "departamento_item": "diversificación por departamento",
                       "entidad_departamento": "departamento si falta el del ítem"},
    "ofertantes": {"codigo_convocatoria": "llave del ítem", "n_item": "llave del ítem",
                   "ruc_codigo_postor": "identificador del postor", "fecha_presentacion_propuesta": "fecha de la oferta",
                   "fechaconvocatoria": "fecha de la oferta si la propuesta tiene fecha imposible"},
    "contratos": {"n_cod_contrato": "llave del contrato (para ampliaciones)", "num_item": "llave del contrato-ítem",
                  "ruc_contratista": "proveedor del contrato", "ruc_destinatario_pago": "identifica consorcios"},
    "ampliaciones": {"codigocontrato": "llave del contrato", "fecha_publicacion_ampliacion": "fecha de la ampliación",
                     "numero_documento": "quitar duplicados"},
    "penalidades": {"ruc_contratista": "identificador del proveedor", "fecha_penalidad": "fecha de la penalidad",
                    "tipo_penalidad": "penalidades por mora", "monto": "monto de penalidades"},
    "sancionados": {"RUC": "identificador del proveedor", "NUMERO_RESOLUCION": "unir con el RNP sin repetir",
                    "FECHA_INICIO": "fecha del evento", "FECHA_FIN": "vigencia e inhabilitación indefinida",
                    "DE_MOTIVO_INFRACCION": "grupo de motivo"},
    "rnp (inhabilitaciones)": {"ruc": "identificador del proveedor", "resolucion": "unir con CONOSCE sin repetir",
                               "desde": "fecha del evento", "hasta": "vigencia e inhabilitación indefinida",
                               "infraccion": "grupo de motivo"},
    "rnp (multas)": {"ruc": "identificador del proveedor", "resolucion": "llave de la multa",
                     "fecha_resolucion": "fecha del evento", "infraccion": "grupo de motivo"},
}
COLUMNAS_DERIVADAS = {"archivo", "anio_archivo", "inicio", "fin", "desde_dt", "hasta_dt", "fecha_resolucion_dt"}


def diccionario_datos_raw(tablas_raw):
    """Una fila por columna de cada fuente raw: tipo, nulos, valores distintos, ejemplo y uso.

    ``tablas_raw``: {nombre de la fuente: DataFrame tal como se leyó}.
    """
    partes = []
    for fuente, df in tablas_raw.items():
        perfil = perfil_columnas(df, excluir=COLUMNAS_DERIVADAS).drop(columns="tipo").reset_index()
        usadas = COLUMNAS_USADAS.get(fuente, {})
        perfil.insert(0, "fuente", fuente)
        perfil["se_usa"] = np.where(perfil["columna"].isin(usadas), "sí", "no")
        perfil["uso_en_el_preprocesamiento"] = perfil["columna"].map(usadas).fillna("")
        partes.append(perfil)
    return pd.concat(partes, ignore_index=True)


TABLAS = {
    "fuentes": "tables/fuentes.csv",
    "diccionario": "tables/diccionario_de_datos_raw.csv",
    "cruces": "tables/cruces_entre_fuentes.csv",
    "tasas": "tables/tasa_de_sancion_por_grupo.csv",
}


def tabla_decisiones_md():
    filas = ["| Fuente | Hallazgo | Qué hacemos en `02_preprocesamiento` |", "|---|---|---|"]
    return "\n".join(filas + [f"| {a} | {b} | {c} |" for a, b, c in DECISIONES_EDA])


def _md(df, index=False, decimales=2):
    df = df.reset_index() if index else df
    df = df.apply(lambda col: col.round(decimales) if col.dtype.kind == "f" else col)
    df = df.astype(str).apply(lambda col: col.str.replace("|", "\\|", regex=False).str.replace("\n", " ", regex=False))
    lineas = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * df.shape[1]]
    return "\n".join(lineas + ["| " + " | ".join(map(str, fila)) + " |" for fila in df.to_numpy()])


def escribir_resumen(r):
    """Escribe results/summaries/exploration/resumen.md y sus tablas a partir de los resultados del EDA.

    ``r`` es un diccionario con los objetos calculados en el notebook (o en ``main``).
    """
    inv = r["inventario"].groupby("carpeta").agg(archivos=("archivo", "size"), tamaño_MB=("tamaño_MB", "sum"))
    filas = r["tabla_archivos"].groupby("carpeta")["filas"].sum()
    filas = pd.concat([filas, pd.Series(r["filas_otras"])])
    inv["filas"] = filas.reindex(inv.index).fillna(0).astype(int)
    inv["tamaño_MB"] = inv["tamaño_MB"].round(1)
    est_adj, res_of, res_pen, res_amp = r["est_adj"], r["res_of"], r["res_pen"], r["res_amp"]
    postores = res_of["postores"]
    tasas = pd.concat({col: t.assign(tasa=lambda d: (d["tasa"] * 100).round(2)) for col, t in r["tasas"].items()})
    tasas.index.names = ["grupo", "categoría"]
    tasas = tasas.rename(columns={"tasa": "% sancionado en 12 meses"})
    por_tipo = r["consorcios_por_tipo"].assign(pct_sancionado=lambda d: (d["pct_sancionado"] * 100).round(2))
    eventos = r["eventos"]
    fechas = r["fechas_fuentes"]
    dic = r["diccionario_raw"]
    dic_resumen = dic.groupby("fuente", sort=False).agg(columnas=("columna", "size"),
                                                         usadas=("se_usa", lambda s: int((s == "sí").sum())))
    enlace = lambda clave: f"Tabla: [`{TABLAS[clave]}`]({TABLAS[clave]})"
    for clave, (tabla, con_indice) in {"fuentes": (inv, True), "diccionario": (dic, False),
                                       "cruces": (r["cruces"], False), "tasas": (tasas, True)}.items():
        ruta_tabla = SUMMARY_DIR / TABLAS[clave]
        ruta_tabla.parent.mkdir(parents=True, exist_ok=True)
        tabla.to_csv(ruta_tabla, index=con_indice, encoding="utf-8-sig")
    texto = f"""# Resumen del análisis exploratorio

Generado automáticamente por `src/exploration.py` (o por `notebooks/01_eda.ipynb`). Se reemplaza en cada ejecución.

## Fuentes

{_md(inv, index=True)}

{enlace("fuentes")}

## Diccionario de datos raw

Columnas de cada fuente tal como se leen (encabezados en minúscula en las fuentes del SEACE) y cuáles usa el preprocesamiento:

{_md(dic_resumen, index=True)}

<details>
<summary>Ver diccionario completo ({len(dic)} columnas)</summary>

{_md(dic)}

</details>

{enlace("diccionario")}

## Hallazgos por fuente

- Convocatorias: {r['n_convocatorias']:,} ítems de convocatoria (2022-2026), todos adjudicados; {r['n_tipos_proceso']} tipos de proceso con variantes.
- Adjudicaciones: {est_adj['items']:,} ítems con su ganador; cubren el 100% de las convocatorias. Ganadores: {', '.join(f'{k} {v / est_adj["filas"] * 100:.0f}%' for k, v in est_adj['tipo_proveedor'].items())}.
- Ofertantes: {len(r['ofertantes']):,} ofertas; el {res_of['pct_items_adj_con_postores']:.1f}% de los ítems adjudicados tiene postores y el ganador figura entre ellos en el {res_of['pct_ganador_entre_postores']:.1f}%. El {(postores == 1).mean() * 100:.0f}% de los ítems tuvo un solo postor.
- Contratos: solo el {r['pct_items_con_contrato']:.1f}% de los ítems adjudicados tiene contrato en el archivo; cada fila extra de un contrato es una modificación sin fecha.
- Penalidades: {res_pen['filas']:,} registros con fecha y RUC ({res_pen['duplicadas']} duplicados, {r['lineas_reparadas']} líneas mal formadas reparadas).
- Ampliaciones: {res_amp['filas']:,} registros con fecha pero sin RUC; solo el {res_amp['pct_en_contratos']:.0f}% corresponde a contratos del archivo.
- Arbitraje: solo {r['n_arbitrajes']} registros; no se usa.
- Sanciones: {len(eventos):,} eventos únicos ({(eventos['tipo'] == 'inhabilitación').sum():,} inhabilitaciones y {(eventos['tipo'] == 'multa').sum():,} multas) al unir RNP y CONOSCE. Las listas solo incluyen sanciones que terminaron después del {fechas.loc['RNP', 'fecha de fin más antigua'].date()} (consulta de los últimos 5 años del RNP). Fecha de extracción más temprana: {fechas['fecha de extracción'].min().date()}.

## Cruces entre fuentes

{_md(r['cruces'])}

{enlace("cruces")}

## Consorcios y no domiciliados

Solo tienen código, no RUC, así que no aparecen en las listas de sanciones:

{_md(por_tipo, index=True)}

## Primer vistazo al objetivo

Ítems adjudicados a personas naturales y jurídicas con la ventana de 12 meses completa: {len(r['base_objetivo']):,}. Tasa de sanción del proveedor en los 12 meses siguientes a la buena pro: {r['base_objetivo']['sancion_12m'].mean() * 100:.2f}%.

{_md(tasas, index=True)}

{enlace("tasas")}

## Decisiones para el preprocesamiento

{tabla_decisiones_md()}

## Gráficos

""" + "\n\n".join(f"### {titulo}\n\n![{titulo}](../../plots/exploration/{FIGURAS[clave]})"
                  for clave, titulo in TITULOS_FIGURAS.items()) + "\n"
    ruta = SUMMARY_DIR / "resumen.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return ruta

# ----------------------------------------------------------------------------
# Ejecución completa
# ----------------------------------------------------------------------------
def main():
    """Ejecuta todo el EDA, imprime los resúmenes y guarda gráficos y resumen en results/."""
    plt.switch_backend("Agg")
    limpiar_salidas()
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 40)

    def titulo(t):
        print("\n" + "=" * 80 + f"\n{t}\n" + "=" * 80)

    titulo("1. Inventario de archivos")
    inventario = inventario_archivos()
    print(inventario.to_string(index=False))
    fuentes = {c: leer_anuales(c) for c in ["convocatorias", "adjudicaciones", "ofertantes", "contratos",
                                            "ampliaciones", "arbitraje"]}
    archivos = tabla_archivos(fuentes)
    print(archivos.to_string(index=False))

    titulo("2. Convocatorias")
    conv = preparar_convocatorias(fuentes["convocatorias"][0])
    print(f"Ítems: {len(conv):,} | convocatorias: {conv['codigoconvocatoria'].nunique():,}")
    plt.close(graficar_categoricas_convocatorias(conv))
    plt.close(graficar_montos_fechas_convocatorias(conv))

    titulo("3. Adjudicaciones")
    adj = preparar_adjudicaciones(fuentes["adjudicaciones"][0])
    est_adj = estructura_adjudicaciones(adj, conv)
    print({k: v for k, v in est_adj.items() if np.isscalar(v)})
    print(est_adj["tipo_proveedor"].to_string())
    plt.close(graficar_adjudicaciones_tipo_montos(adj))
    plt.close(graficar_fechas_adjudicaciones(adj))

    titulo("4. Ofertantes")
    of, n_rep = preparar_ofertantes(fuentes["ofertantes"][0])
    res_of = resumen_ofertantes(of, adj)
    print(f"Postores repetidos eliminados: {n_rep} | ítems con postores: {res_of['pct_items_adj_con_postores']:.1f}% | "
          f"ganador entre postores: {res_of['pct_ganador_entre_postores']:.1f}%")
    part = participacion_proveedores(of, adj)
    plt.close(graficar_ofertantes(res_of["postores"], part))

    titulo("5. Contratos")
    contratos = preparar_contratos(fuentes["contratos"][0])
    items = items_contrato(contratos)
    est = estructura_contratos(contratos, items)
    print(f"Filas: {est['filas']:,} | contrato-ítem: {est['contrato_items']:,} | contratos: {est['contratos']:,}")
    tiene, por_archivo, por_proceso = cobertura_contratos(adj, items)
    print(por_archivo.to_string())
    plt.close(graficar_cobertura_contratos(por_proceso))
    cruce, coincide = contratos_vs_adjudicacion(items, adj)
    print("Contratista = ganador (%):", coincide.round(1).to_dict())
    plt.close(graficar_fechas_contratos(items, cruce))

    titulo("6. Ejecución: ampliaciones, arbitraje y penalidades")
    amp = preparar_ampliaciones(fuentes["ampliaciones"][0])
    arb = preparar_arbitraje(fuentes["arbitraje"][0])
    pen, _, reparadas = leer_penalidades()
    res_amp = resumen_ampliaciones(amp, contratos)
    res_pen = resumen_penalidades(pen, contratos, adj)
    print({k: v for k, v in res_amp.items() if np.isscalar(v)})
    print(f"Arbitrajes: {len(arb):,} | penalidades: {len(pen):,} (líneas reparadas: {reparadas})")
    print({k: v for k, v in res_pen.items() if np.isscalar(v)})
    plt.close(graficar_penalidades(pen))
    plt.close(graficar_ampliaciones_arbitraje(amp, arb))

    titulo("7. Entidades")
    entidades = leer_entidades()
    print(f"Entidades: {len(entidades):,} | cobertura desde adjudicaciones: {cobertura_entidades(adj['codigoentidad'], entidades):.2f}%")

    titulo("8. Sanciones")
    sanc_inh, _ = leer_sanciones_conosce()
    rnp_inh, rnp_mul, archivo_rnp = leer_rnp()
    print(resumen_sanciones_conosce(sanc_inh).to_string())
    print(solapamiento_inhabilitaciones(sanc_inh, rnp_inh).to_string())
    eventos, n_filas = construir_eventos(sanc_inh, rnp_inh, rnp_mul)
    fechas_fuentes = fechas_de_las_fuentes(sanc_inh, rnp_inh, archivo_rnp)
    print(f"Eventos: {n_filas:,} filas -> {len(eventos):,} únicos")
    print(fechas_fuentes.to_string())
    plt.close(graficar_rnp(rnp_inh, rnp_mul))
    plt.close(graficar_sanciones_anio_motivo(eventos))

    titulo("9. Relación entre fuentes")
    cruces = tabla_cruces(conv, adj, of, items, amp, arb, pen, entidades, eventos)
    print(cruces.to_string(index=False))
    por_tipo, por_pago, _ = analisis_consorcios(adj, items, eventos)
    print(por_tipo.round(3).to_string())
    print(por_pago.round(3).to_string())

    titulo("10. Primer vistazo al objetivo")
    fecha_limite = fechas_fuentes["fecha de extracción"].min() - pd.DateOffset(months=12)
    base = tabla_objetivo_adjudicaciones(adj, eventos, pen, res_of["postores"], fecha_limite)
    print(f"Ítems adjudicados (PN/PJ) con ventana completa: {len(base):,} | tasa: {base['sancion_12m'].mean()*100:.2f}%")
    tasas = tasas_por_grupo(base)
    for col, t in tasas.items():
        print(f"\n{col}\n{t.round(4).to_string()}")
    plt.close(graficar_tasas_por_grupo(base, tasas))
    plt.close(graficar_tiempo_hasta_sancion(base))

    ruta = escribir_resumen({
        "inventario": inventario, "tabla_archivos": archivos, "n_convocatorias": len(conv),
        "n_tipos_proceso": conv["tipoprocesoseleccion"].nunique(), "est_adj": est_adj, "res_of": res_of,
        "ofertantes": of, "pct_items_con_contrato": tiene.mean() * 100, "res_pen": res_pen, "res_amp": res_amp,
        "lineas_reparadas": reparadas, "n_arbitrajes": len(arb), "eventos": eventos, "fechas_fuentes": fechas_fuentes,
        "cruces": cruces, "consorcios_por_tipo": por_tipo, "base_objetivo": base, "tasas": tasas,
        "filas_otras": {"penalidades": len(pen), "sancionados": len(sanc_inh), "rnp": len(rnp_inh) + len(rnp_mul),
                        "entidades_contratantes": len(entidades)},
        "diccionario_raw": diccionario_datos_raw({
            **{c: fuentes[c][0] for c in fuentes}, "penalidades": pen, "sancionados": sanc_inh,
            "rnp (inhabilitaciones)": rnp_inh, "rnp (multas)": rnp_mul, "entidades_contratantes": entidades}),
    })
    print(f"\nGráficos guardados en: {PLOTS_DIR.relative_to(ROOT)}")
    for nombre in FIGURAS.values():
        print("  -", nombre)
    print(f"Resumen: {ruta.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
