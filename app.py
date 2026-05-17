import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.express as px
import requests
from datetime import date
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------
# CONFIGURACIÓN GENERAL
# -----------------------------

st.set_page_config(
    page_title="Dashboard Financiero - Práctica 4",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Dashboard Financiero Automatizado")
st.caption("Práctica 4 - Laboratorio de Visualización de Datos Financieros")
st.caption(f"Última actualización automática: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")

# -----------------------------
# TOKEN BANXICO
# -----------------------------
# Para correr local, puedes pegar temporalmente tu token aquí.
# Para publicar, después lo vamos a mover a Streamlit Secrets.

BANXICO_TOKEN = st.secrets.get("BANXICO_TOKEN", "")

# -----------------------------
# SIDEBAR
# -----------------------------

st.sidebar.header("Configuración del análisis")

tickers_big_seven = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "TSLA", "AMZN"]
tickers_extra = ["JPM", "BRK-B", "V", "XOM", "LLY"]

all_tickers = tickers_big_seven + tickers_extra

selected_tickers = st.sidebar.multiselect(
    "Selecciona empresas:",
    options=all_tickers,
    default=tickers_big_seven
)

start_date = st.sidebar.date_input("Fecha inicial", pd.to_datetime("2023-01-01"))
end_date = st.sidebar.date_input("Fecha final", pd.to_datetime("today"))

START = pd.to_datetime(start_date).strftime("%Y-%m-%d")
END = pd.to_datetime(end_date).strftime("%Y-%m-%d")

st.sidebar.markdown("---")
st.sidebar.write("Big Seven incluidas:")
st.sidebar.write(", ".join(tickers_big_seven))

st.sidebar.write("Empresas adicionales:")
st.sidebar.write(", ".join(tickers_extra))


# -----------------------------
# FUNCIONES DE DESCARGA
# -----------------------------

@st.cache_data(ttl=3600)
def get_stock_prices(tickers, start, end):
    data = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False
    )

    if data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        prices = data["Close"].copy()
    else:
        prices = data[["Close"]].copy()
        prices.columns = tickers

    prices = prices.dropna(how="all")
    prices.index = pd.to_datetime(prices.index)
    prices.index.name = "Fecha"

    return prices


@st.cache_data(ttl=3600)
def download_yahoo_series(ticker, column_name, start, end):
    data = yf.download(
        ticker,
        start=start,
        end=end,
        progress=False,
        auto_adjust=False
    )

    if data.empty:
        return pd.DataFrame()

    close = data["Close"]

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    df = close.reset_index()
    df.columns = ["Fecha", column_name]
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df[column_name] = pd.to_numeric(df[column_name], errors="coerce")

    return df.dropna()


@st.cache_data(ttl=3600)
def get_treasury_10y(start, end):
    df = download_yahoo_series("^TNX", "Treasury_10Y", start, end)

    if df.empty:
        return df

    # Yahoo a veces trae ^TNX como 43.5 en vez de 4.35.
    if df["Treasury_10Y"].median() > 20:
        df["Treasury_10Y"] = df["Treasury_10Y"] / 10

    return df


@st.cache_data(ttl=3600)
def get_usd_mxn_yahoo(start, end):
    df = download_yahoo_series("MXN=X", "USD_MXN", start, end)

    if df.empty:
        df = download_yahoo_series("USDMXN=X", "USD_MXN", start, end)

    return df


@st.cache_data(ttl=3600)
def get_usd_eur(start, end):
    df = download_yahoo_series("USDEUR=X", "USD_EUR", start, end)

    if not df.empty:
        return df

    eur_usd = download_yahoo_series("EURUSD=X", "EUR_USD", start, end)

    if eur_usd.empty:
        return pd.DataFrame()

    eur_usd["USD_EUR"] = 1 / eur_usd["EUR_USD"]

    return eur_usd[["Fecha", "USD_EUR"]]


@st.cache_data(ttl=3600)
def get_banxico_series(series_id, column_name, start, end, token):
    if not token or token == "PEGA_AQUI_TU_TOKEN":
        return pd.DataFrame()

    url = (
        f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/"
        f"{series_id}/datos/{start}/{end}"
    )

    response = requests.get(
        url,
        headers={"Bmx-Token": token},
        timeout=30
    )

    response.raise_for_status()

    data = response.json()
    observations = data["bmx"]["series"][0].get("datos", [])

    df = pd.DataFrame(observations)

    if df.empty:
        return pd.DataFrame()

    df["Fecha"] = pd.to_datetime(df["fecha"], format="%d/%m/%Y", errors="coerce")
    df[column_name] = pd.to_numeric(
        df["dato"].astype(str).str.replace(",", "", regex=False),
        errors="coerce"
    )

    df = df[["Fecha", column_name]]
    df = df.dropna()
    df = df.sort_values("Fecha")

    return df


def latest_value(df, column):
    if df.empty:
        return None, None

    latest_date = df["Fecha"].iloc[-1]
    value = df[column].iloc[-1]

    return latest_date, value


# -----------------------------
# DESCARGA DE DATOS
# -----------------------------

if not selected_tickers:
    st.warning("Selecciona al menos una empresa.")
    st.stop()

prices = get_stock_prices(selected_tickers, START, END)

if prices.empty:
    st.error("No se pudieron descargar datos de acciones. Revisa los tickers o las fechas.")
    st.stop()

treasury = get_treasury_10y(START, END)
usd_mxn_yahoo = get_usd_mxn_yahoo(START, END)
usd_eur = get_usd_eur(START, END)

# Banxico
cetes = get_banxico_series("SF43936", "CETES_28D", START, END, BANXICO_TOKEN)
usd_mxn_banxico = get_banxico_series("SF43718", "USD_MXN", START, END, BANXICO_TOKEN)

# Si Banxico falla para USD/MXN, usamos Yahoo como respaldo.
if not usd_mxn_banxico.empty:
    usd_mxn = usd_mxn_banxico.copy()
    usd_mxn_source = "Banxico FIX"
else:
    usd_mxn = usd_mxn_yahoo.copy()
    usd_mxn_source = "Yahoo Finance"


# -----------------------------
# CÁLCULOS DE ACCIONES
# -----------------------------

returns = prices.pct_change()
normalized_prices = prices / prices.iloc[0] * 100

cumulative_return = (prices.iloc[-1] / prices.iloc[0] - 1) * 100
volatility = returns.std() * np.sqrt(252) * 100

drawdown = prices / prices.cummax() - 1
max_drawdown = drawdown.min() * 100

metrics = pd.DataFrame({
    "Rendimiento acumulado (%)": cumulative_return,
    "Volatilidad anualizada (%)": volatility,
    "Máximo drawdown (%)": max_drawdown
}).round(2)

best_stock = metrics["Rendimiento acumulado (%)"].idxmax()
worst_stock = metrics["Rendimiento acumulado (%)"].idxmin()
highest_vol_stock = metrics["Volatilidad anualizada (%)"].idxmax()


# -----------------------------
# ÚLTIMOS VALORES MACRO
# -----------------------------

cetes_date, cetes_latest = latest_value(cetes, "CETES_28D")
treasury_date, treasury_latest = latest_value(treasury, "Treasury_10Y")
usdmxn_date, usdmxn_latest = latest_value(usd_mxn, "USD_MXN")
usdeur_date, usdeur_latest = latest_value(usd_eur, "USD_EUR")


# -----------------------------
# TABS
# -----------------------------

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Panorama general",
    "Acciones",
    "Tasas y tipo de cambio",
    "Alertas",
    "Datos y metodología"
])


# -----------------------------
# TAB 1: PANORAMA GENERAL
# -----------------------------

with tab1:
    st.subheader("1. Panorama general")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Empresas analizadas",
        len(selected_tickers)
    )

    col2.metric(
        "Mejor rendimiento",
        best_stock,
        f"{metrics.loc[best_stock, 'Rendimiento acumulado (%)']}%"
    )

    col3.metric(
        "Peor rendimiento",
        worst_stock,
        f"{metrics.loc[worst_stock, 'Rendimiento acumulado (%)']}%"
    )

    col4.metric(
        "Mayor volatilidad",
        highest_vol_stock,
        f"{metrics.loc[highest_vol_stock, 'Volatilidad anualizada (%)']}%"
    )

    st.markdown("### Indicadores macroeconómicos")

    m1, m2, m3, m4 = st.columns(4)

    if cetes_latest is not None:
        m1.metric("CETES 28 días", f"{cetes_latest:.2f}%")
    else:
        m1.metric("CETES 28 días", "Sin datos")

    if treasury_latest is not None:
        m2.metric("Treasury 10Y", f"{treasury_latest:.2f}%")
    else:
        m2.metric("Treasury 10Y", "Sin datos")

    if usdmxn_latest is not None:
        m3.metric("USD/MXN", f"{usdmxn_latest:.2f}")
    else:
        m3.metric("USD/MXN", "Sin datos")

    if usdeur_latest is not None:
        m4.metric("USD/EUR", f"{usdeur_latest:.4f}")
    else:
        m4.metric("USD/EUR", "Sin datos")

    st.markdown("### Historia financiera del dashboard")

    st.write(
        "Este dashboard analiza cómo se comportan las principales acciones tecnológicas "
        "frente a variables macroeconómicas como tasas de interés y tipo de cambio. "
        "La idea central es comparar si el rendimiento de la renta variable compensa el riesgo "
        "asumido en un entorno donde los instrumentos de renta fija, como CETES y bonos del Tesoro, "
        "también ofrecen rendimientos relevantes."
    )


# -----------------------------
# TAB 2: ACCIONES
# -----------------------------

with tab2:
    st.subheader("2. Comparación de precios normalizados")

    normalized_long = normalized_prices.reset_index().melt(
        id_vars="Fecha",
        var_name="Ticker",
        value_name="Precio normalizado"
    )

    fig_normalized = px.line(
        normalized_long,
        x="Fecha",
        y="Precio normalizado",
        color="Ticker",
        title="Evolución de precios normalizados base 100"
    )

    fig_normalized.update_layout(
        legend_title_text="Empresa",
        hovermode="x unified"
    )

    st.plotly_chart(fig_normalized, use_container_width=True)

    st.info(
        "Esta gráfica normaliza todos los activos a base 100 para comparar su desempeño, "
        "aunque sus precios originales sean diferentes."
    )

    # -----------------------------
    # RANKING + SCATTER
    # -----------------------------

    st.subheader("3. Rendimiento y riesgo de las empresas")

    metrics_plot = metrics.copy()
    metrics_plot["Ticker"] = metrics_plot.index
    metrics_plot["Riesgo por drawdown"] = metrics_plot["Máximo drawdown (%)"].abs()

    col_a, col_b = st.columns([1, 1])

    with col_a:
        ranking = metrics_plot.sort_values("Rendimiento acumulado (%)", ascending=True)

        fig_ranking = px.bar(
            ranking,
            x="Rendimiento acumulado (%)",
            y="Ticker",
            orientation="h",
            title="Ranking de rendimiento acumulado",
            text="Rendimiento acumulado (%)"
        )

        fig_ranking.update_traces(
            texttemplate="%{text:.1f}%",
            textposition="outside"
        )

        fig_ranking.update_layout(
            xaxis_title="Rendimiento acumulado (%)",
            yaxis_title="Empresa",
            showlegend=False
        )

        st.plotly_chart(fig_ranking, use_container_width=True)

    with col_b:
        fig_risk_return = px.scatter(
            metrics_plot,
            x="Volatilidad anualizada (%)",
            y="Rendimiento acumulado (%)",
            size="Riesgo por drawdown",
            color="Ticker",
            hover_name="Ticker",
            title="Riesgo vs rendimiento",
            hover_data={
                "Volatilidad anualizada (%)": ":.2f",
                "Rendimiento acumulado (%)": ":.2f",
                "Máximo drawdown (%)": ":.2f",
                "Riesgo por drawdown": False
            }
        )

        fig_risk_return.update_layout(
            xaxis_title="Volatilidad anualizada (%)",
            yaxis_title="Rendimiento acumulado (%)",
            legend_title_text="Empresa"
        )

        st.plotly_chart(fig_risk_return, use_container_width=True)

    st.caption(
        "El gráfico de riesgo vs rendimiento permite observar si las empresas con mayor rendimiento "
        "también asumieron mayor volatilidad o mayores caídas desde máximos."
    )

    # -----------------------------
    # CORRELACIÓN
    # -----------------------------

    st.subheader("4. Mapa de correlación entre acciones")

    corr_matrix = returns.corr().round(2)

    fig_corr = px.imshow(
        corr_matrix,
        text_auto=True,
        aspect="auto",
        title="Correlación de rendimientos diarios"
    )

    fig_corr.update_layout(
        xaxis_title="Empresa",
        yaxis_title="Empresa"
    )

    st.plotly_chart(fig_corr, use_container_width=True)

    st.info(
        "La correlación muestra qué tan parecido se mueven las acciones entre sí. "
        "Valores cercanos a 1 indican que dos acciones tienden a moverse en la misma dirección."
    )

    # -----------------------------
    # DRAWDOWN
    # -----------------------------

    st.subheader("5. Caídas máximas desde máximos históricos")

    drawdown_plot = metrics_plot.sort_values("Máximo drawdown (%)", ascending=True)

    fig_drawdown = px.bar(
        drawdown_plot,
        x="Máximo drawdown (%)",
        y="Ticker",
        orientation="h",
        title="Máximo drawdown por empresa",
        text="Máximo drawdown (%)"
    )

    fig_drawdown.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="outside"
    )

    fig_drawdown.update_layout(
        xaxis_title="Máximo drawdown (%)",
        yaxis_title="Empresa",
        showlegend=False
    )

    st.plotly_chart(fig_drawdown, use_container_width=True)

    st.caption(
        "El drawdown ayuda a medir qué tanto llegó a caer cada acción desde su punto máximo dentro del periodo analizado."
    )

    # -----------------------------
    # TABLA
    # -----------------------------

    st.subheader("6. Tabla de métricas financieras")

    st.dataframe(metrics, use_container_width=True)


# -----------------------------
# TAB 3: TASAS Y TIPO DE CAMBIO
# -----------------------------

with tab3:
    st.subheader("6. Tasas de interés: CETES vs Treasury 10Y")

    rate_frames = []

    if not cetes.empty:
        temp_cetes = cetes.copy()
        temp_cetes["Indicador"] = "CETES 28D"
        temp_cetes = temp_cetes.rename(columns={"CETES_28D": "Valor"})
        rate_frames.append(temp_cetes[["Fecha", "Indicador", "Valor"]])

    if not treasury.empty:
        temp_treasury = treasury.copy()
        temp_treasury["Indicador"] = "Treasury 10Y"
        temp_treasury = temp_treasury.rename(columns={"Treasury_10Y": "Valor"})
        rate_frames.append(temp_treasury[["Fecha", "Indicador", "Valor"]])

    if rate_frames:
        rates_long = pd.concat(rate_frames)

        fig_rates = px.line(
            rates_long,
            x="Fecha",
            y="Valor",
            color="Indicador",
            title="Comparación histórica de tasas"
        )

        st.plotly_chart(fig_rates, use_container_width=True)
    else:
        st.warning("No se descargaron datos de tasas.")

    st.subheader("7. Tipo de cambio USD/MXN y USD/EUR")

    fx_frames = []

    if not usd_mxn.empty:
        temp_mxn = usd_mxn.copy()
        temp_mxn["Indicador"] = f"USD/MXN ({usd_mxn_source})"
        temp_mxn = temp_mxn.rename(columns={"USD_MXN": "Valor"})
        fx_frames.append(temp_mxn[["Fecha", "Indicador", "Valor"]])

    if not usd_eur.empty:
        temp_eur = usd_eur.copy()
        temp_eur["Indicador"] = "USD/EUR"
        temp_eur = temp_eur.rename(columns={"USD_EUR": "Valor"})
        fx_frames.append(temp_eur[["Fecha", "Indicador", "Valor"]])

    if fx_frames:
        fx_long = pd.concat(fx_frames)

        fig_fx = px.line(
            fx_long,
            x="Fecha",
            y="Valor",
            color="Indicador",
            title="Evolución del tipo de cambio"
        )

        st.plotly_chart(fig_fx, use_container_width=True)
    else:
        st.warning("No se descargaron datos de tipo de cambio.")

    st.markdown("### Interpretación")

    st.write(
        "La comparación entre CETES, bonos del Tesoro y tipo de cambio permite entender el entorno macrofinanciero. "
        "Si las tasas de Estados Unidos suben, las acciones de crecimiento pueden verse presionadas. "
        "Por otro lado, tasas altas en México pueden hacer más atractiva la renta fija local y afectar decisiones "
        "entre invertir en pesos, dólares o acciones."
    )


# -----------------------------
# TAB 4: ALERTAS
# -----------------------------

with tab4:
    st.subheader("8. Sistema de alertas financieras")

    st.write(
        "Las alertas se activan automáticamente cuando algún indicador supera un umbral crítico definido."
    )

    alert_triggered = False

    st.markdown("### Alertas macroeconómicas")

    if usdmxn_latest is not None and usdmxn_latest > 18.50:
        st.warning(f"⚠️ USD/MXN alto: {usdmxn_latest:.2f}. Umbral: 18.50")
        alert_triggered = True

    if treasury_latest is not None and treasury_latest > 4.50:
        st.warning(f"⚠️ Treasury 10Y alto: {treasury_latest:.2f}%. Umbral: 4.50%")
        alert_triggered = True

    if cetes_latest is not None and cetes_latest > 10.00:
        st.warning(f"⚠️ CETES 28D alto: {cetes_latest:.2f}%. Umbral: 10.00%")
        alert_triggered = True

    st.markdown("### Alertas de acciones")

    for ticker in metrics.index:
        dd = metrics.loc[ticker, "Máximo drawdown (%)"]
        vol = metrics.loc[ticker, "Volatilidad anualizada (%)"]

        if dd <= -20:
            st.warning(f"⚠️ {ticker}: drawdown mayor a 20%. Caída máxima: {dd:.2f}%")
            alert_triggered = True

        if vol >= 35:
            st.warning(f"⚠️ {ticker}: volatilidad alta. Volatilidad: {vol:.2f}%")
            alert_triggered = True

    if not alert_triggered:
        st.success("No hay alertas críticas activas con los umbrales actuales.")

    st.markdown("### Definición de umbrales")

    thresholds = pd.DataFrame({
        "Indicador": [
            "USD/MXN",
            "Treasury 10Y",
            "CETES 28D",
            "Máximo drawdown",
            "Volatilidad anualizada"
        ],
        "Umbral": [
            "Mayor a 18.50",
            "Mayor a 4.50%",
            "Mayor a 10.00%",
            "Menor o igual a -20%",
            "Mayor o igual a 35%"
        ],
        "Interpretación": [
            "Posible presión sobre el peso mexicano",
            "Presión sobre valuaciones de acciones de crecimiento",
            "Renta fija mexicana muy atractiva frente a activos riesgosos",
            "Caída relevante desde máximos históricos",
            "Activo con riesgo elevado por alta variación de precios"
        ]
    })

    st.dataframe(thresholds, use_container_width=True)


# -----------------------------
# TAB 5: DATOS Y METODOLOGÍA
# -----------------------------

with tab5:
    st.subheader("9. Datos integrados y metodología")

    st.write(
        "El dashboard integra precios históricos de acciones, tasas de interés y tipos de cambio. "
        "Los datos se descargan automáticamente al ejecutar la aplicación, por lo que no es necesario "
        "hacer una descarga manual diaria."
    )

    methodology = pd.DataFrame({
        "Conjunto de datos": [
            "Big Seven",
            "Cinco empresas adicionales",
            "CETES 28 días",
            "Bonos del Tesoro de EE.UU.",
            "USD/MXN",
            "USD/EUR"
        ],
        "Fuente usada": [
            "Yahoo Finance mediante yfinance",
            "Yahoo Finance mediante yfinance",
            "Banxico API",
            "Yahoo Finance usando ^TNX como proxy del Treasury 10Y",
            f"{usd_mxn_source}",
            "Yahoo Finance"
        ],
        "Uso en el dashboard": [
            "Comparar desempeño de grandes tecnológicas",
            "Comparar sectores adicionales",
            "Referencia de tasa en pesos mexicanos",
            "Referencia de tasa en dólares",
            "Tipo de cambio peso-dólar",
            "Tipo de cambio dólar-euro"
        ]
    })

    st.dataframe(methodology, use_container_width=True)

    st.subheader("10. Vista previa de datos")

    st.markdown("### Acciones")
    st.dataframe(prices.tail(), use_container_width=True)

    st.markdown("### CETES")
    st.dataframe(cetes.tail(), use_container_width=True)

    st.markdown("### Treasury 10Y")
    st.dataframe(treasury.tail(), use_container_width=True)

    st.markdown("### USD/MXN")
    st.dataframe(usd_mxn.tail(), use_container_width=True)

    st.markdown("### USD/EUR")
    st.dataframe(usd_eur.tail(), use_container_width=True)

    st.subheader("11. Conclusión")

    st.markdown(f"""
    El dashboard permitió integrar información financiera de distintas fuentes para analizar tasas de interés, 
    tipo de cambio y precios históricos de acciones. Durante el periodo analizado, la empresa con mayor rendimiento 
    acumulado fue **{best_stock}**, mientras que la empresa con menor rendimiento fue **{worst_stock}**.

    La comparación entre acciones, CETES y Treasury 10Y permite observar que la decisión de inversión no depende 
    únicamente del rendimiento, sino también del riesgo y del entorno de tasas. Las alertas ayudan a identificar 
    condiciones críticas como aumentos en tasas, presión cambiaria o caídas fuertes en acciones.
    """)
