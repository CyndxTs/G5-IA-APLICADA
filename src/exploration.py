"""Funciones del análisis exploratorio (EDA) de los datos raw.

El notebook ``notebooks/01_eda.ipynb`` usa estas funciones paso a paso y comenta
los resultados. También se puede ejecutar todo de una vez desde la raíz del
repositorio:

    python src/exploration.py

En ambos casos los gráficos se guardan (y se sobrescriben) en ``results/eda/``,
organizados en una carpeta por fuente.
"""

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
EDA_DIR = ROOT / "results" / "eda"

COLOR_PRIMARIO = "#1f77b4"
COLOR_SECUNDARIO = "#ff7f0e"
COLOR_ACENTO1 = "#2E86AB"
COLOR_ACENTO2 = "#A23B72"

FIGURAS = {
    "montos_monedas": "contratos/distribucion_de_montos_y_monedas.png",
    "fechas_contratos": "contratos/contratos_por_trimestre_y_anio_de_archivo.png",
    "categoricas_conv": "convocatorias/variables_categoricas_principales.png",
    "montos_fechas_conv": "convocatorias/montos_referenciales_e_items_por_mes.png",
    "cobertura": "convocatorias/cobertura_de_contratos_por_tipo_de_proceso.png",
    "rnp": "sanciones/rnp_tipo_estado_y_monto_de_multas.png",
    "sanciones_anio_motivo": "sanciones/sanciones_por_anio_y_motivo.png",
    "tasas_grupo": "objetivo/tasa_de_sancion_a_12_meses_por_grupo.png",
    "tiempo_sancion": "objetivo/tiempo_hasta_la_siguiente_sancion.png",
}

CLAVE_ITEM = ["n_cod_contrato", "num_item"]
ETIQUETA_CONSORCIO = "código de 6-8 dígitos (consorcio)"
ETIQUETA_RUC = "RUC de 11 dígitos"


def guardar_figura(fig, clave):
    """Guarda la figura en results/eda/ con el nombre definido en FIGURAS."""
    ruta = EDA_DIR / FIGURAS[clave]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, dpi=150, bbox_inches="tight")
    return ruta


def _estilo(ax, titulo, eje="y"):
    ax.set_title(titulo, fontsize=12, fontweight="bold")
    ax.grid(axis=eje, alpha=0.3)


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
    """Lee todos los Excel anuales de una carpeta como texto.

    Devuelve el DataFrame apilado (encabezados en minúscula solo para poder
    juntar los años) y un diccionario con los encabezados originales por archivo.
    """
    partes, encabezados = [], {}
    for f in sorted((raw / carpeta).glob("*.xlsx")):
        if verbose:
            print("Leyendo:", f.name)
        df = pd.read_excel(f, dtype=str, engine="openpyxl")
        encabezados[f.name] = list(df.columns)
        df.columns = [c.strip().lower() for c in df.columns]
        df["archivo"] = f.name
        partes.append(df)
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


def perfil_columnas(df, excluir=("archivo",)):
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


# ----------------------------------------------------------------------------
# 2. Contratos
# ----------------------------------------------------------------------------
def preparar_contratos(contratos_raw):
    """Convierte montos y fechas de contratos a su tipo real (sin limpiar nada más)."""
    contratos = contratos_raw.copy()
    for c in [x for x in contratos.columns if x.startswith("monto")]:
        contratos[c] = pd.to_numeric(contratos[c], errors="coerce")
    for c in [x for x in contratos.columns if x.startswith("fecha")]:
        contratos[c] = pd.to_datetime(contratos[c], errors="coerce")
    return contratos


def clasificar_identificador(ruc_contratista):
    """Clasifica ``ruc_contratista``: RUC, código de consorcio, extranjero u otro."""
    r = ruc_contratista.astype("string")
    return pd.Series(np.select(
        [r.str.fullmatch(r"\d{11}").fillna(False), r.str.fullmatch(r"\d{6,8}").fillna(False),
         r.str.match(r"^L\d+$").fillna(False)],
        [ETIQUETA_RUC, ETIQUETA_CONSORCIO, "código L... (extranjero)"], default="otro"), index=r.index)


def items_contrato(contratos):
    """Una fila por contrato-ítem, con el patrón del identificador y el id del proveedor."""
    items = contratos.drop_duplicates(CLAVE_ITEM).copy()
    items["patron_id"] = clasificar_identificador(items["ruc_contratista"])
    es_consorcio = items["patron_id"] == ETIQUETA_CONSORCIO
    items["id_proveedor"] = items["ruc_destinatario_pago"].where(es_consorcio, items["ruc_contratista"])
    return items


def estructura_contratos(contratos, items):
    """Resume qué representa cada fila del archivo de contratos."""
    tam_grupo = contratos.groupby(CLAVE_ITEM).size()
    repetidos = contratos[contratos.duplicated(CLAVE_ITEM, keep=False)]
    cambian = pd.Series({c: int((repetidos.groupby(CLAVE_ITEM)[c].nunique(dropna=False) > 1).sum())
                         for c in contratos.columns if c not in CLAVE_ITEM + ["archivo"]})
    por_contrato = items.groupby("n_cod_contrato").agg(total=("monto_contratado_total", "first"),
                                                       suma_items=("monto_contratado_item", "sum"),
                                                       n_items=("num_item", "size"))
    return {
        "filas": len(contratos),
        "contrato_items": len(tam_grupo),
        "contratos": contratos["n_cod_contrato"].nunique(),
        "codigo_igual": bool((contratos["n_cod_contrato"] == contratos["codigo_contrato"]).all()),
        "en_dos_archivos": int((contratos.groupby(CLAVE_ITEM)["archivo"].nunique() > 1).sum()),
        "duplicadas": int(contratos.duplicated().sum()),
        "filas_por_item": tam_grupo.value_counts().sort_index(),
        "columnas_que_cambian": cambian[cambian > 0].rename("contrato-ítem donde cambia"),
        "pct_un_item": (por_contrato["n_items"] == 1).mean() * 100,
        "pct_total_igual_suma": np.isclose(por_contrato["total"], por_contrato["suma_items"], rtol=1e-3).mean() * 100,
    }


def graficar_montos_monedas(contratos_unicos):
    fig, ax = plt.subplots(1, 2, figsize=(13, 4))
    np.log10(contratos_unicos["monto_contratado_total"]).plot.hist(bins=40, ax=ax[0], color=COLOR_PRIMARIO)
    ax[0].set_xlabel("log10(monto)")
    ax[0].set_ylabel("contratos")
    _estilo(ax[0], "Monto contratado por contrato (log10)", "both")
    contratos_unicos["moneda"].value_counts().plot.bar(ax=ax[1], color=COLOR_PRIMARIO, rot=20)
    ax[1].set_xlabel("")
    ax[1].set_yscale("log")
    ax[1].set_ylabel("contratos (escala log)")
    _estilo(ax[1], "Moneda del contrato")
    fig.tight_layout()
    guardar_figura(fig, "montos_monedas")
    return fig


def contratos_por_trimestre(contratos_unicos, desde="2023Q1"):
    trimestre = contratos_unicos["fecha_suscripcion_contrato"].dt.to_period("Q")
    return trimestre[trimestre >= pd.Period(desde)].value_counts().sort_index()


def tabla_cohortes(contratos_unicos):
    """Cruce entre el año del archivo y el año de suscripción del contrato."""
    return pd.crosstab(contratos_unicos["archivo"].str.extract(r"(20\d{2})")[0].rename("archivo (año)"),
                       contratos_unicos["fecha_suscripcion_contrato"].dt.year.rename("año de suscripción"))


def graficar_fechas_contratos(contratos_unicos):
    por_trimestre = contratos_por_trimestre(contratos_unicos)
    fig, ax = plt.subplots(1, 2, figsize=(15, 4.2), gridspec_kw={"width_ratios": [1.6, 1]})
    ax[0].bar(por_trimestre.index.astype(str), por_trimestre.values, color=COLOR_PRIMARIO)
    ax[0].tick_params(axis="x", rotation=45)
    ax[0].set_ylabel("contratos")
    _estilo(ax[0], "Contratos por trimestre de suscripción")
    sns.heatmap(tabla_cohortes(contratos_unicos), annot=True, fmt="d", cmap="Blues", cbar=False, ax=ax[1])
    ax[1].set_title("Año del archivo vs año de suscripción", fontsize=12, fontweight="bold")
    fig.tight_layout()
    guardar_figura(fig, "fechas_contratos")
    return fig


def anomalias_fechas(contratos_unicos):
    """Cuenta fechas raras en los contratos. Devuelve la tabla y los días firma -> publicación."""
    cu = contratos_unicos
    dias_pub = (cu["fecha_publicacion_contrato"] - cu["fecha_suscripcion_contrato"]).dt.days
    duracion = (cu["fecha_vigencia_final"] - cu["fecha_vigencia_inicial"]).dt.days
    tabla = pd.DataFrame([
        {"revisión": "firma antes de 2023", "contratos": int((cu["fecha_suscripcion_contrato"] < "2023-01-01").sum())},
        {"revisión": "publicación antes de la firma", "contratos": int((dias_pub < 0).sum())},
        {"revisión": "publicación más de 1 año después de la firma", "contratos": int((dias_pub > 365).sum())},
        {"revisión": "vigencia final antes de la inicial", "contratos": int((duracion < 0).sum())},
        {"revisión": "duración mayor a 10 años", "contratos": int((duracion > 3650).sum())},
        {"revisión": "vigencia actualizada (ampliación de plazo)",
         "contratos": int((cu["fecha_vigencia_fin_actualizada"] > cu["fecha_vigencia_final"]).sum())},
    ])
    return tabla, dias_pub


def tabla_identificadores(items):
    """Patrones del identificador del proveedor y su relación con el RUC de pago."""
    t = items.assign(
        pago_11=items["ruc_destinatario_pago"].str.fullmatch(r"\d{11}").fillna(False),
        igual_pago=items["ruc_contratista"] == items["ruc_destinatario_pago"],
    ).groupby("patron_id").agg(contrato_items=("n_cod_contrato", "size"),
                               pago_con_RUC_11=("pago_11", "mean"),
                               contratista_igual_a_pago=("igual_pago", "mean"))
    t["%"] = (t["contrato_items"] / len(items) * 100).round(1)
    return t.sort_values("contrato_items", ascending=False)


def pct_modificaciones(contratos):
    """% de contratos con al menos un adicional, reducción o prórroga."""
    por_contrato = contratos.groupby("n_cod_contrato").agg(
        adicional=("monto_adicional", "max"), reduccion=("monto_reduccion", "max"), prorroga=("monto_prorroga", "max"))
    return ((por_contrato > 0).mean() * 100).round(1).rename("% de contratos con al menos una")


# ----------------------------------------------------------------------------
# 3. Convocatorias
# ----------------------------------------------------------------------------
def preparar_convocatorias(convocatorias_raw):
    """Convierte montos y fechas y une SECTOR / NIVEL DE GOBIERNO con COL_10."""
    conv = convocatorias_raw.copy()
    conv["monto_referencial_item"] = pd.to_numeric(conv["monto_referencial_item"], errors="coerce")
    for c in ["fecha_convocatoria", "fechaintegracionbases", "fechapresentacionpropuesta"]:
        conv[c] = pd.to_datetime(conv[c], errors="coerce")
    conv["sector_nivel_gobierno"] = conv["sector / nivel de gobierno"].fillna(conv["col_10"])
    return conv


def comparar_sector_col10(convocatorias):
    """% de filas con dato en cada columna, por archivo, y valores de COL_10 que no están en SECTOR."""
    sector, col10 = convocatorias["sector / nivel de gobierno"], convocatorias["col_10"]
    tabla = (convocatorias.assign(sector_lleno=sector.notna(), col_10_lleno=col10.notna())
             .groupby("archivo")[["sector_lleno", "col_10_lleno"]].mean().round(2))
    return tabla, sorted(set(col10.dropna()) - set(sector.dropna()))


def graficar_categoricas_convocatorias(convocatorias,
                                       columnas=("tipoentidad", "objetocontractual",
                                                 "tipoprocesoseleccion", "sistema_contratacion")):
    fig, ax = plt.subplots(2, 2, figsize=(14, 7.5))
    for a, c in zip(ax.ravel(), columnas):
        convocatorias[c].value_counts().head(8).sort_values().plot.barh(ax=a, color=COLOR_PRIMARIO)
        a.set_ylabel("")
        a.set_xlabel("ítems")
        _estilo(a, c, "x")
    fig.tight_layout()
    guardar_figura(fig, "categoricas_conv")
    return fig


def graficar_montos_fechas_convocatorias(convocatorias):
    fig, ax = plt.subplots(1, 2, figsize=(14, 4))
    np.log10(convocatorias["monto_referencial_item"].clip(lower=1)).plot.hist(bins=40, ax=ax[0], color=COLOR_PRIMARIO)
    ax[0].set_ylabel("ítems")
    _estilo(ax[0], "Monto referencial por ítem (log10)", "both")
    por_mes = convocatorias["fecha_convocatoria"].dt.to_period("M").value_counts().sort_index()
    ax[1].plot(por_mes.index.astype(str), por_mes.values, marker="o", color=COLOR_PRIMARIO, markersize=3)
    ax[1].set_xticks(range(0, len(por_mes), 3))
    ax[1].set_xticklabels(por_mes.index.astype(str)[::3], rotation=45)
    _estilo(ax[1], "Ítems convocados por mes", "both")
    fig.tight_layout()
    guardar_figura(fig, "montos_fechas_conv")
    return fig


def cobertura_contratos(convocatorias, items, top=10):
    """Marca qué ítems de convocatoria tienen contrato y resume la cobertura."""
    claves = set(zip(items["codigoconvocatoria"], items["num_item"]))
    tiene = pd.Series([(a, b) in claves for a, b in zip(convocatorias["codigoconvocatoria"], convocatorias["n_item"])],
                      index=convocatorias.index, name="tiene_contrato")
    por_archivo = tiene.groupby(convocatorias["archivo"]).agg(items="size", con_contrato="sum")
    por_archivo["%_con_contrato"] = (por_archivo["con_contrato"] / por_archivo["items"] * 100).round(1)
    por_proceso = (tiene.groupby(convocatorias["tipoprocesoseleccion"]).agg(items="size", pct="mean")
                   .sort_values("items", ascending=False).head(top))
    return tiene, por_archivo, por_proceso


def graficar_cobertura(por_proceso):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    (por_proceso["pct"] * 100).sort_values().plot.barh(ax=ax, color=COLOR_SECUNDARIO)
    ax.set_xlabel("% de ítems convocados con contrato en nuestros datos")
    ax.set_ylabel("")
    _estilo(ax, "Cobertura de contratos por tipo de proceso (top 10 por volumen)", "x")
    fig.tight_layout()
    guardar_figura(fig, "cobertura")
    return fig


# ----------------------------------------------------------------------------
# 4. Entidades
# ----------------------------------------------------------------------------
def leer_entidades(raw=RAW):
    return pd.read_csv(raw / "entidades_contratantes" / "entidades_contratantes.csv",
                       sep="|", encoding="cp1252", dtype=str)


def cobertura_entidades(items, entidades):
    """% de contrato-ítem cuyo código de entidad existe en la tabla (sin ceros a la izquierda)."""
    codigos = set(entidades["CODCONSUCODE"].str.lstrip("0"))
    return items["codigoentidad"].str.lstrip("0").isin(codigos).mean() * 100


# ----------------------------------------------------------------------------
# 5. Sanciones
# ----------------------------------------------------------------------------
def leer_sanciones_conosce(raw=RAW):
    """Inhabilitaciones y multas de CONOSCE, con fechas convertidas."""
    inh = pd.read_csv(raw / "sancionados" / "sancionados.csv", sep="|", encoding="cp1252", dtype=str)
    mul = pd.read_csv(raw / "sancionados" / "sancionados_multa.csv", sep="|", encoding="cp1252", dtype=str)
    for df in (inh, mul):
        df["inicio"] = pd.to_datetime(df["FECHA_INICIO"], format="%Y%m%d", errors="coerce")
        df["fin"] = pd.to_datetime(df["FECHA_FIN"], format="%Y%m%d", errors="coerce")
    mul["MONTO"] = pd.to_numeric(mul["MONTO"], errors="coerce")
    return inh, mul


def resumen_sanciones_conosce(inh, mul):
    filas = []
    for nombre, df in [("inhabilitaciones", inh), ("multas", mul)]:
        originales = [c for c in df.columns if c not in ("inicio", "fin")]
        filas.append({
            "fuente": nombre, "filas": len(df), "RUC distintos": df["RUC"].nunique(),
            "RUC de 11 dígitos %": round(df["RUC"].str.fullmatch(r"\d{11}").mean() * 100, 1),
            "filas duplicadas": int(df.duplicated(subset=originales).sum()),
            "RUC+resolución repetidos": int(df.duplicated(["RUC", "NUMERO_RESOLUCION"]).sum()),
            "sin fecha fin": int(df["fin"].isna().sum()),
            "fin antes de inicio": int((df["fin"] < df["inicio"]).sum()),
            "fecha de corte": df["FECHA_CORTE"].unique()[0],
        })
    return pd.DataFrame(filas).set_index("fuente")


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
        df["desde_dt"] = pd.to_datetime(df["desde"], format="%d/%m/%Y", errors="coerce")
        df["hasta_dt"] = pd.to_datetime(df["hasta"], format="%d/%m/%Y", errors="coerce")
    mul["fecha_resolucion_dt"] = pd.to_datetime(mul["fecha_resolucion"], format="%d/%m/%Y", errors="coerce")
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


def solapamiento_sanciones(sanc_inh, sanc_mul, rnp_inh, rnp_mul):
    """Cuántas resoluciones (RUC, número) están en ambas fuentes o solo en una."""
    claves = {
        "inhabilitación": (set(zip(sanc_inh["RUC"], normalizar_resolucion(sanc_inh["NUMERO_RESOLUCION"]))),
                           set(zip(rnp_inh["ruc"], normalizar_resolucion(rnp_inh["resolucion"])))),
        "multa": (set(zip(sanc_mul["RUC"], normalizar_resolucion(sanc_mul["NUMERO_RESOLUCION"]))),
                  set(zip(rnp_mul["ruc"], normalizar_resolucion(rnp_mul["resolucion"])))),
    }
    return pd.DataFrame([{"tipo": t, "en ambas": len(a & b), "solo en RNP": len(b - a), "solo en CONOSCE": len(a - b)}
                         for t, (a, b) in claves.items()]).set_index("tipo")


def diferencia_fechas_multas(sanc_mul, rnp_mul):
    """Días entre FECHA_INICIO de CONOSCE y las fechas del RNP para la misma multa."""
    a = sanc_mul.assign(k=list(zip(sanc_mul["RUC"], normalizar_resolucion(sanc_mul["NUMERO_RESOLUCION"]))))
    b = rnp_mul.assign(k=list(zip(rnp_mul["ruc"], normalizar_resolucion(rnp_mul["resolucion"]))))
    m = a.merge(b, on="k")
    return pd.DataFrame({
        "inicio CONOSCE - resolución RNP": (m["inicio"] - m["fecha_resolucion_dt"]).dt.days.describe(),
        "inicio CONOSCE - desde RNP": (m["inicio"] - m["desde_dt"]).dt.days.describe(),
    }).loc[["count", "25%", "50%", "75%"]]


def agrupar_motivo(motivo):
    """Agrupa el texto libre del motivo de infracción en pocas categorías."""
    m = motivo.fillna("").str.upper()
    return pd.Series(np.select(
        [m.str.strip().eq(""), m.str.contains("INEXACTA"), m.str.contains("FALSO|ADULTERAD"), m.str.contains("IMPEDID"),
         m.str.contains("PERFECCIONAR|SUSCRIBIR|FORMALIZAR|MANTENER"), m.str.contains("RESUEL|RESCISI|RESOLUCI")],
        ["sin motivo registrado", "información inexacta", "documentos falsos", "contratar estando impedido",
         "no perfeccionar / no suscribir el contrato", "resolución del contrato"], default="otros"), index=motivo.index)


def construir_eventos(sanc_inh, sanc_mul, rnp_inh, rnp_mul):
    """Une las cuatro tablas en eventos (RUC, resolución, tipo), dando prioridad al RNP.

    Fecha del evento: inicio de la inhabilitación o fecha de resolución de la multa.
    """
    eventos = pd.concat([
        pd.DataFrame({"ruc": rnp_inh["ruc"], "res": normalizar_resolucion(rnp_inh["resolucion"]), "tipo": "inhabilitación",
                      "fecha": rnp_inh["desde_dt"], "motivo": rnp_inh["infraccion"], "fuente": "RNP"}),
        pd.DataFrame({"ruc": rnp_mul["ruc"], "res": normalizar_resolucion(rnp_mul["resolucion"]), "tipo": "multa",
                      "fecha": rnp_mul["fecha_resolucion_dt"], "motivo": rnp_mul["infraccion"], "fuente": "RNP"}),
        pd.DataFrame({"ruc": sanc_inh["RUC"], "res": normalizar_resolucion(sanc_inh["NUMERO_RESOLUCION"]),
                      "tipo": "inhabilitación", "fecha": sanc_inh["inicio"],
                      "motivo": sanc_inh["DE_MOTIVO_INFRACCION"], "fuente": "CONOSCE"}),
        pd.DataFrame({"ruc": sanc_mul["RUC"], "res": normalizar_resolucion(sanc_mul["NUMERO_RESOLUCION"]),
                      "tipo": "multa", "fecha": sanc_mul["inicio"],
                      "motivo": sanc_mul["DE_MOTIVO_INFRACCION"], "fuente": "CONOSCE"}),
    ], ignore_index=True)
    n_filas = len(eventos)
    eventos = eventos.drop_duplicates(["ruc", "res", "tipo"]).dropna(subset=["fecha"]).reset_index(drop=True)
    eventos["motivo_grupo"] = agrupar_motivo(eventos["motivo"])
    return eventos, n_filas


def fechas_fin_minimas(sanc_inh, sanc_mul, rnp_inh):
    """Fecha de fin más antigua en cada fuente: antes de ella las listas están incompletas."""
    return {"RNP": rnp_inh["hasta_dt"].min(), "CONOSCE": min(sanc_inh["fin"].min(), sanc_mul["fin"].min())}


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
# 6. Relación entre fuentes
# ----------------------------------------------------------------------------
def _pct_en(a, b):
    return round(pd.Series(list(a)).isin(set(b)).mean() * 100, 2)


def cruces_llaves(items, convocatorias, entidades, eventos):
    """% de filas que encuentran su pareja en la otra fuente."""
    ruc_sancionados = set(eventos["ruc"])
    return pd.Series({
        "contrato-ítem -> convocatoria-ítem": _pct_en(zip(items["codigoconvocatoria"], items["num_item"]),
                                                       set(zip(convocatorias["codigoconvocatoria"], convocatorias["n_item"]))),
        "contrato -> entidad (código sin ceros)": _pct_en(items["codigoentidad"].str.lstrip("0"),
                                                          entidades["CODCONSUCODE"].str.lstrip("0")),
        "contrato-ítem -> alguna sanción (ruc_contratista)": _pct_en(items["ruc_contratista"], ruc_sancionados),
        "contrato-ítem -> alguna sanción (id_proveedor)": _pct_en(items["id_proveedor"], ruc_sancionados),
    }, name="% con coincidencia")


def analisis_consorcios(items, eventos):
    """Compara la proporción de sancionados entre RUC propios y RUC de pago de consorcios."""
    ruc_sancionados = set(eventos["ruc"])
    proveedores = items.drop_duplicates("id_proveedor")[["id_proveedor", "patron_id"]].copy()
    proveedores["sancionado_alguna_vez"] = proveedores["id_proveedor"].isin(ruc_sancionados)
    ruc_solos = set(items.loc[items["patron_id"] == ETIQUETA_RUC, "ruc_contratista"])
    pagos = proveedores[proveedores["patron_id"] == ETIQUETA_CONSORCIO].copy()
    pagos["también_contrata_solo"] = pagos["id_proveedor"].isin(ruc_solos)
    por_tipo = proveedores.groupby("patron_id")["sancionado_alguna_vez"].agg(proveedores="size", pct_sancionado="mean")
    por_pago = pagos.groupby("también_contrata_solo")["sancionado_alguna_vez"].agg(pagadores="size", pct_sancionado="mean")
    return por_tipo, por_pago, pagos


# ----------------------------------------------------------------------------
# 7. Primer vistazo al objetivo
# ----------------------------------------------------------------------------
def familia_proceso(tipo_proceso):
    """Agrupa los ~40 tipos de proceso en familias."""
    tp = tipo_proceso.fillna("").str.upper()
    return pd.Series(np.select(
        [tp.str.contains("SIMPLIFICADA"), tp.str.contains("SUBASTA"), tp.str.contains("LICITACI"),
         tp.str.contains("CONCURSO"), tp.str.contains("DIRECTA")],
        ["Adjudicación simplificada", "Subasta inversa", "Licitación pública", "Concurso público", "Contratación directa"],
        default="Otros"), index=tipo_proceso.index)


def tabla_objetivo_contratos(items, convocatorias, eventos, horizonte_meses=12):
    """Una fila por contrato de proveedores con RUC propio y si el proveedor fue sancionado
    en los ``horizonte_meses`` siguientes a la firma (análisis descriptivo)."""
    conv_items = convocatorias.drop_duplicates(["codigoconvocatoria", "n_item"])
    cont = (items.drop_duplicates("n_cod_contrato")
            .merge(conv_items[["codigoconvocatoria", "n_item", "tipoentidad", "objetocontractual", "tipoprocesoseleccion"]],
                   left_on=["codigoconvocatoria", "num_item"], right_on=["codigoconvocatoria", "n_item"], how="left"))
    cont = cont[cont["patron_id"] == ETIQUETA_RUC].copy()

    fechas = eventos.groupby("ruc")["fecha"].apply(lambda s: np.sort(s.values)).to_dict()
    vacio = np.array([], dtype="datetime64[ns]")
    firma = cont["fecha_suscripcion_contrato"].values
    fin = (cont["fecha_suscripcion_contrato"] + pd.DateOffset(months=horizonte_meses)).values
    sancion, previa, dias = [], [], []
    for ruc, f0, f1 in zip(cont["id_proveedor"], firma, fin):
        f = fechas.get(ruc, vacio)
        posteriores = f[f > f0]
        sancion.append(int(((posteriores <= f1)).any()))
        previa.append(int((f <= f0).any()))
        dias.append((posteriores.min() - f0) / np.timedelta64(1, "D") if len(posteriores) else np.nan)
    cont["sancion_12m"], cont["sancion_previa"], cont["dias_a_siguiente_sancion"] = sancion, previa, dias

    cont["tipo_contribuyente"] = (cont["id_proveedor"].str[:2]
                                  .map({"20": "persona jurídica (20)", "10": "persona natural (10)"}).fillna("otro"))
    cont["familia_proceso"] = familia_proceso(cont["tipoprocesoseleccion"])
    cont["quintil_monto"] = pd.qcut(cont["monto_contratado_total"].rank(method="first"), 5,
                                    labels=["Q1 (menor)", "Q2", "Q3", "Q4", "Q5 (mayor)"])
    cont["antecedentes"] = cont["sancion_previa"].map({0: "sin sanción previa", 1: "con sanción previa"})
    return cont


GRUPOS_OBJETIVO = [("tipo_contribuyente", "Tipo de contribuyente"), ("familia_proceso", "Familia de proceso"),
                   ("tipoentidad", "Tipo de entidad"), ("objetocontractual", "Objeto contractual"),
                   ("quintil_monto", "Quintil de monto del contrato"), ("antecedentes", "Antecedentes")]


def tasas_por_grupo(cont, grupos=GRUPOS_OBJETIVO, minimo=30):
    """Tasa de sanción a 12 meses por categoría (solo categorías con al menos ``minimo`` contratos)."""
    tasas = {}
    for col, _ in grupos:
        t = cont.groupby(col, observed=True)["sancion_12m"].agg(contratos="size", tasa="mean")
        tasas[col] = t[t["contratos"] >= minimo]
    return tasas


def graficar_tasas_por_grupo(cont, tasas, grupos=GRUPOS_OBJETIVO):
    promedio = cont["sancion_12m"].mean() * 100
    fig, axes = plt.subplots(2, 3, figsize=(17, 8))
    for ax, (col, titulo) in zip(axes.ravel(), grupos):
        t = tasas[col]
        orden = t.index if col == "quintil_monto" else t["tasa"].sort_values().index
        ax.barh([str(i) for i in orden], t.loc[orden, "tasa"] * 100, color=COLOR_ACENTO1)
        ax.axvline(promedio, color="gray", linestyle="--", alpha=0.7, label=f"Promedio ({promedio:.1f}%)")
        ax.set_xlabel("% con sanción en 12 meses")
        _estilo(ax, titulo, "x")
    axes[0, 0].legend(fontsize=9)
    fig.tight_layout()
    guardar_figura(fig, "tasas_grupo")
    return fig


def graficar_tiempo_hasta_sancion(cont, horizonte_meses=12):
    meses = cont["dias_a_siguiente_sancion"].dropna() / 30.4375
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.hist(meses, bins=40, color=COLOR_PRIMARIO, label="contratos")
    ax.axvline(horizonte_meses, color=COLOR_SECUNDARIO, linestyle="--", label=f"{horizonte_meses} meses (horizonte del target)")
    ax.set_xlabel("Meses entre la firma del contrato y la siguiente sanción del proveedor")
    ax.set_ylabel("contratos")
    ax.legend()
    _estilo(ax, "¿Cuánto tarda en llegar la siguiente sanción?", "both")
    fig.tight_layout()
    guardar_figura(fig, "tiempo_sancion")
    return fig


# ----------------------------------------------------------------------------
# Ejecución completa
# ----------------------------------------------------------------------------
def main():
    """Ejecuta todo el EDA, imprime los resúmenes y guarda los gráficos en results/eda/."""
    plt.switch_backend("Agg")
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 40)

    def titulo(t):
        print("\n" + "=" * 80 + f"\n{t}\n" + "=" * 80)

    def cerrar(fig):
        plt.close(fig)

    titulo("1. Inventario de archivos")
    print(inventario_archivos().to_string(index=False))
    contratos_raw, enc_c = leer_anuales("contratos")
    convocatorias_raw, enc_v = leer_anuales("convocatorias")
    print(tabla_archivos({"contratos": (contratos_raw, enc_c), "convocatorias": (convocatorias_raw, enc_v)}).to_string(index=False))

    titulo("2. Contratos")
    contratos = preparar_contratos(contratos_raw)
    items = items_contrato(contratos)
    unicos = items.drop_duplicates("n_cod_contrato")
    est = estructura_contratos(contratos, items)
    print(f"Filas: {est['filas']:,} | contrato-ítem: {est['contrato_items']:,} | contratos: {est['contratos']:,}")
    print(est["columnas_que_cambian"].to_string())
    cerrar(graficar_montos_monedas(unicos))
    cerrar(graficar_fechas_contratos(unicos))
    print(anomalias_fechas(unicos)[0].to_string(index=False))
    print(tabla_identificadores(items).to_string())
    print(pct_modificaciones(contratos).to_string())

    titulo("3. Convocatorias")
    convocatorias = preparar_convocatorias(convocatorias_raw)
    print(comparar_sector_col10(convocatorias)[0].to_string())
    cerrar(graficar_categoricas_convocatorias(convocatorias))
    cerrar(graficar_montos_fechas_convocatorias(convocatorias))
    tiene, por_archivo, por_proceso = cobertura_contratos(convocatorias, items)
    print(por_archivo.to_string())
    print(f"Ítems con contrato: {tiene.mean()*100:.1f}%")
    cerrar(graficar_cobertura(por_proceso))

    titulo("4. Entidades")
    entidades = leer_entidades()
    print(f"Entidades: {len(entidades):,} | cobertura desde contratos: {cobertura_entidades(items, entidades):.2f}%")

    titulo("5. Sanciones")
    sanc_inh, sanc_mul = leer_sanciones_conosce()
    rnp_inh, rnp_mul, archivo_rnp = leer_rnp()
    print(resumen_sanciones_conosce(sanc_inh, sanc_mul).to_string())
    print(f"RNP ({archivo_rnp.name}): {len(rnp_inh):,} inhabilitaciones | {len(rnp_mul):,} multas")
    cerrar(graficar_rnp(rnp_inh, rnp_mul))
    print(solapamiento_sanciones(sanc_inh, sanc_mul, rnp_inh, rnp_mul).to_string())
    print(diferencia_fechas_multas(sanc_mul, rnp_mul).to_string())
    eventos, n_filas = construir_eventos(sanc_inh, sanc_mul, rnp_inh, rnp_mul)
    print(f"Eventos: {n_filas:,} filas -> {len(eventos):,} únicos | fechas de fin mínimas: "
          f"{ {k: str(v.date()) for k, v in fechas_fin_minimas(sanc_inh, sanc_mul, rnp_inh).items()} }")
    cerrar(graficar_sanciones_anio_motivo(eventos))

    titulo("6. Relación entre fuentes")
    print(cruces_llaves(items, convocatorias, entidades, eventos).to_string())
    por_tipo, por_pago, _ = analisis_consorcios(items, eventos)
    print(por_tipo.round(3).to_string())
    print(por_pago.round(3).to_string())

    titulo("7. Primer vistazo al objetivo")
    cont = tabla_objetivo_contratos(items, convocatorias, eventos)
    tasas = tasas_por_grupo(cont)
    for col, t in tasas.items():
        print(f"\n{col}\n{t.round(4).to_string()}")
    cerrar(graficar_tasas_por_grupo(cont, tasas))
    cerrar(graficar_tiempo_hasta_sancion(cont))

    print(f"\nGráficos guardados en: {EDA_DIR}")
    for clave, nombre in FIGURAS.items():
        print("  -", nombre)


if __name__ == "__main__":
    main()
