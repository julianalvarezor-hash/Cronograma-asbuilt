import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import requests
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Control de Producción As-Built (LPS)", layout="wide")
st.title("🏗️ Control de Producción As-Built — Last Planner System")

# --- CONEXIÓN A GOOGLE SHEETS (BASE DE DATOS PERSISTENTE) ---
URL_GOOGLE_SHEETS = "https://docs.google.com/spreadsheets/d/1zAseM8s_jkTo8YFjAL39SUAk15lNJs63-0WKDR7pbuI/edit?usp=sharing"

conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=5)
def cargar_datos():
    df_raw = conn.read(spreadsheet=URL_GOOGLE_SHEETS, ttl="5s")
    # Limpiar espacios en nombres de columnas si existen
    df_raw.columns = df_raw.columns.str.strip()
    # Convertir columna de inicio a tipo fecha
    df_raw['Inicio'] = pd.to_datetime(df_raw['Inicio']).dt.date
    return df_raw

try:
    df = cargar_datos()
except Exception as e:
    st.error(f"Error al conectar con Google Sheets: {e}")
    st.stop()

# --- SECCIÓN 1: SELECTOR MANUAL DE FESTIVOS NO LABORABLES ---
st.sidebar.header("⚙️ Configuración de Calendario")
festivos_manuales = st.sidebar.multiselect(
    "Selecciona los festivos que NO se trabajarán:",
    options=[
        datetime.date(2026, 8, 7),   # Batalla de Boyacá
        datetime.date(2026, 8, 17),  # La Asunción
        datetime.date(2026, 10, 12), # Día de la Raza
        datetime.date(2026, 11, 2),  # Todos los Santos
        datetime.date(2026, 11, 16), # Independencia de Cartagena
        datetime.date(2026, 12, 8),  # Inmaculada Concepción
        datetime.date(2026, 12, 25)  # Navidad
    ],
    default=[datetime.date(2026, 8, 7)]
)

# Función para calcular fecha fin excluyendo fines de semana y festivos
def calcular_fecha_fin(fecha_inicio, dias_estimados, festivos_no_lab):
    if pd.isna(fecha_inicio) or pd.isna(dias_estimados):
        return fecha_inicio
    
    # Asegurar formato datetime.date
    if isinstance(fecha_inicio, str):
        fecha_inicio = pd.to_datetime(fecha_inicio).date()
    elif isinstance(fecha_inicio, pd.Timestamp):
        fecha_inicio = fecha_inicio.date()
        
    fecha_actual = fecha_inicio
    dias_sumados = 0
    while dias_sumados < int(dias_estimados):
        fecha_actual += datetime.timedelta(days=1)
        es_fin_de_semana = fecha_actual.weekday() >= 5
        es_festivo_no_laboral = fecha_actual in festivos_no_lab
        
        if not es_fin_de_semana and not es_festivo_no_laboral:
            dias_sumados += 1
    return fecha_actual

# Asignar una Fecha Fin inicial antes de mostrar en la tabla
df['Fecha Fin'] = df.apply(lambda row: calcular_fecha_fin(row['Inicio'], row['Días'], festivos_manuales), axis=1)

# --- VISTA 1: TABLA EDITABLE ---
st.subheader("📋 Registro de Actividades As-Built")

# Desplegamos la tabla editable (sin permitir modificar Fecha Fin directamente, ya que se calcula)
df_editado = st.data_editor(
    df[['Actividad', 'Responsable', 'Inicio', 'Días', 'Fecha Fin', 'Estado', 'Comentarios']],
    use_container_width=True,
    num_rows="dynamic",
    column_config={
        "Estado": st.column_config.SelectboxColumn(
            "Estado del Compromiso",
            help="Selecciona el estado actual de la actividad",
            options=["Pendiente", "En proceso", "Completado"],
            required=True
        ),
        "Inicio": st.column_config.DateColumn("Inicio", format="YYYY-MM-DD"),
        "Fecha Fin": st.column_config.DateColumn("Fecha Fin (Calculada)", format="YYYY-MM-DD", disabled=True)
    }
)

# 🔥 RECALCULAR FECHA FIN EN TIEMPO REAL TRAS EDICIÓN DE ENTRADAS 🔥
df_editado['Fecha Fin'] = df_editado.apply(
    lambda row: calcular_fecha_fin(row['Inicio'], row['Días'], festivos_manuales), axis=1
)

# BOTÓN PARA GUARDAR CAMBIOS PERMANENTES EN LA BASE DE DATOS
col1, col2 = st.columns([1, 4])
with col1:
    if st.button("💾 Guardar Cambios Permanentes"):
        try:
            # Seleccionar solo las columnas origen para guardar en Google Sheets
            df_para_guardar = df_editado[['Actividad', 'Responsable', 'Inicio', 'Días', 'Estado', 'Comentarios']]
            conn.update(spreadsheet=URL_GOOGLE_SHEETS, data=df_para_guardar)
            st.success("¡Datos guardados con éxito en la base de datos!")
            st.cache_data.clear()
        except Exception as err:
            st.error(f"Error al guardar los cambios: {err}")

st.markdown("---")

# --- VISTA 2: GANTT / LÍNEA DE TIEMPO INTERACTIVA ---
st.subheader("📅 Cronograma y Línea de Tiempo Interactiva")

fig = px.timeline(
    df_editado, 
    x_start="Inicio", 
    x_end="Fecha Fin", 
    y="Actividad", 
    color="Estado",
    text="Responsable",
    title="Línea de Tiempo por Actividad",
    color_discrete_map={"Pendiente": "#7f8c8d", "En proceso": "#3498db", "Completado": "#2ecc71"}
)

fig.update_yaxes(autorange="reversed")
fig.update_layout(xaxis_title="Fecha", yaxis_title="Actividades", height=450)

st.plotly_chart(fig, use_container_width=True)

# --- SECCIÓN 3: CONEXIÓN REAL A SLACK ---
st.markdown("---")
slack_webhook_url = st.text_input("Ingresa tu Webhook URL de Slack (Opcional):", type="password")

if st.button("🔔 Notificar Avance a Slack"):
    if slack_webhook_url:
        mensaje = {
            "text": "🚨 *Actualización de Cronograma As-Built (LPS)*\nEl estado del proyecto se ha actualizado. Revisa el dashboard para más detalles."
        }
        response = requests.post(slack_webhook_url, json=mensaje)
        if response.status_code == 200:
            st.success("¡Mensaje enviado a Slack con éxito!")
        else:
            st.error("Error al enviar el mensaje a Slack. Revisa la URL del Webhook.")
    else:
        st.warning("Para notificar a Slack, primero ingresa la URL de tu Webhook en la casilla superior.")
