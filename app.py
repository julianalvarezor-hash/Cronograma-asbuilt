import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import requests
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Control de Producción As-Built (LPS)", layout="wide")
st.title("🏗️ Control de Producción As-Built — Last Planner System")

# --- CONEXIÓN A GOOGLE SHEETS ---
try:
    if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        pk = st.secrets["connections"]["gsheets"].get("private_key", "")
        if "\\n" in pk:
            st.secrets["connections"]["gsheets"]["private_key"] = pk.replace("\\n", "\n")
            
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Error en configuración de Secrets: {e}")

# --- CARGA DE DATOS (ACTIVIDADES Y CONFIGURACIÓN) ---
def cargar_datos():
    # 1. Cargar tabla de Actividades
    try:
        df_raw = conn.read(worksheet="Actividades", ttl=0)
    except Exception:
        df_raw = pd.DataFrame()
        
    columnas_esperadas = ['Actividad', 'Responsable', 'Inicio', 'Días', 'Estado', 'Comentarios']
    
    if df_raw.empty or len(df_raw.columns) == 0:
        df_raw = pd.DataFrame(columns=columnas_esperadas)
        
    for col in columnas_esperadas:
        if col not in df_raw.columns:
            df_raw[col] = ""
            
    df_raw.columns = df_raw.columns.str.strip()
    
    for col in ['Actividad', 'Responsable', 'Comentarios']:
        df_raw[col] = df_raw[col].fillna("")
        df_raw[col] = df_raw[col].astype(str).replace("None", "").replace("nan", "")

    df_raw['Inicio'] = pd.to_datetime(df_raw['Inicio'], errors='coerce').dt.date
    df_raw['Días'] = pd.to_numeric(df_raw['Días'], errors='coerce').fillna(1).astype(int)
    
    # 2. Cargar parámetros de Configuración
    try:
        df_config = conn.read(worksheet="Configuracion", ttl=0)
        df_config = df_config.set_index("Parametro")
        
        f_inicio = pd.to_datetime(df_config.loc["Fecha Inicio", "Valor"]).date()
        f_fin = pd.to_datetime(df_config.loc["Fecha Fin", "Valor"]).date()
        
        festivos_str = str(df_config.loc["Festivos", "Valor"])
        if festivos_str and festivos_str.lower() != "nan":
            festivos_lista = [pd.to_datetime(d.strip()).date() for d in festivos_str.split(",") if d.strip()]
        else:
            festivos_lista = []
    except Exception:
        # Valores por defecto si la pestaña está vacía la primera vez
        f_inicio = datetime.date.today()
        f_fin = datetime.date.today() + datetime.timedelta(days=30)
        festivos_lista = [datetime.date(2026, 8, 7)]

    return df_raw, f_inicio, f_fin, festivos_lista

if "datos_cargados" not in st.session_state:
    try:
        df_base, f_in, f_out, festivos_guardados = cargar_datos()
        st.session_state.df_datos_base = df_base
        st.session_state.fecha_inicio_def = f_in
        st.session_state.fecha_fin_def = f_out
        st.session_state.festivos_def = festivos_guardados
        st.session_state.datos_cargados = True
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        st.stop()

# --- SECCIÓN 1: SIDEBAR (LÍMITES Y FESTIVOS) ---
st.sidebar.header("⚙️ Configuración del Proyecto")

st.sidebar.subheader("📅 Límites del Proyecto")
fecha_inicio_proyecto = st.sidebar.date_input(
    "Fecha Inicio del Proyecto:", 
    value=st.session_state.fecha_inicio_def
)
fecha_fin_proyecto = st.sidebar.date_input(
    "Fecha Fin del Proyecto:", 
    value=st.session_state.fecha_fin_def
)

st.sidebar.markdown("---")
st.sidebar.subheader("🏖️ Días No Laborables")

# Opciones por defecto + los que ya tenías guardados
opciones_festivos = list(set(st.session_state.festivos_def + [
    datetime.date(2026, 8, 7), datetime.date(2026, 8, 17), 
    datetime.date(2026, 10, 12), datetime.date(2026, 11, 2), 
    datetime.date(2026, 11, 16), datetime.date(2026, 12, 8), datetime.date(2026, 12, 25)
]))

festivos_manuales = st.sidebar.multiselect(
    "Selecciona los festivos que NO se trabajarán:",
    options=opciones_festivos,
    default=st.session_state.festivos_def
)

def calcular_fecha_fin(fecha_inicio, dias_estimados, festivos_no_lab):
    if pd.isna(fecha_inicio) or pd.isna(dias_estimados):
        return fecha_inicio
    
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

# --- VISTA 1: TABLA EDITABLE ---
st.subheader("📋 Registro de Actividades As-Built")

df_editado = st.data_editor(
    st.session_state.df_datos_base[['Actividad', 'Responsable', 'Inicio', 'Días', 'Estado', 'Comentarios']],
    use_container_width=True,
    num_rows="dynamic",
    key="editor_tabla",
    column_config={
        "Actividad": st.column_config.TextColumn("Actividad"),
        "Responsable": st.column_config.TextColumn("Responsable"),
        "Comentarios": st.column_config.TextColumn("Comentarios"),
        "Estado": st.column_config.SelectboxColumn(
            "Estado del Compromiso",
            options=["Pendiente", "En proceso", "Completado"]
        ),
        "Inicio": st.column_config.DateColumn(
            "Inicio", 
            format="YYYY-MM-DD",
            min_value=fecha_inicio_proyecto,
            max_value=fecha_fin_proyecto
        ),
        "Días": st.column_config.NumberColumn("Días Duración", min_value=1, step=1)
    }
)

df_editado['Fecha Fin'] = df_editado.apply(
    lambda row: calcular_fecha_fin(row['Inicio'], row['Días'], festivos_manuales), axis=1
)

with st.expander("👁️ Ver Fechas Finales Calculadas Dinámicamente", expanded=True):
    st.dataframe(
        df_editado[['Actividad', 'Inicio', 'Días', 'Fecha Fin', 'Estado']],
        use_container_width=True,
        hide_index=True
    )

# --- BOTÓN DE GUARDADO PERMANENTE ---
col1, col2 = st.columns([1, 4])
with col1:
    if st.button("💾 Guardar Cambios en la Nube"):
        try:
            # 1. Guardar tabla de Actividades
            df_para_guardar = df_editado[['Actividad', 'Responsable', 'Inicio', 'Días', 'Estado', 'Comentarios']].copy()
            df_para_guardar['Estado'] = df_para_guardar['Estado'].fillna('Pendiente')
            df_para_guardar['Días'] = df_para_guardar['Días'].fillna(1)
            conn.update(worksheet="Actividades", data=df_para_guardar)
            
            # 2. Guardar parámetros de Configuración
            festivos_str = ", ".join([f.strftime("%Y-%m-%d") for f in festivos_manuales])
            df_config_save = pd.DataFrame({
                "Parametro": ["Fecha Inicio", "Fecha Fin", "Festivos"],
                "Valor": [fecha_inicio_proyecto.strftime("%Y-%m-%d"), fecha_fin_proyecto.strftime("%Y-%m-%d"), festivos_str]
            })
            conn.update(worksheet="Configuracion", data=df_config_save)
            
            # 3. Actualizar memoria de la sesión
            st.session_state.df_datos_base = df_para_guardar
            st.session_state.fecha_inicio_def = fecha_inicio_proyecto
            st.session_state.fecha_fin_def = fecha_fin_proyecto
            st.session_state.festivos_def = festivos_manuales
            
            st.success("¡Datos y configuración guardados con éxito en Google Sheets!")
        except Exception as err:
            st.error(f"Error al guardar los cambios: {err}")

st.markdown("---")

# --- VISTA 2: GANTT / LÍNEA DE TIEMPO INTERACTIVA ---
st.subheader("📅 Cronograma y Línea de Tiempo Interactiva")

df_grafico = df_editado.dropna(subset=['Inicio', 'Fecha Fin']).copy()
df_grafico = df_grafico[df_grafico['Actividad'].str.strip() != ""]

if not df_grafico.empty:
    fig = px.timeline(
        df_grafico, 
        x_start="Inicio", 
        x_end="Fecha Fin", 
        y="Actividad", 
        color="Estado",
        text="Responsable",
        title="Línea de Tiempo por Actividad",
        color_discrete_map={"Pendiente": "#7f8c8d", "En proceso": "#3498db", "Completado": "#2ecc71"}
    )

    fig.update_yaxes(autorange="reversed")
    
    fig.update_layout(
        xaxis_title="Fecha", 
        yaxis_title="Actividades", 
        height=450,
        xaxis=dict(
            range=[str(fecha_inicio_proyecto), str(fecha_fin_proyecto)]
        )
    )

    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Agrega el nombre y fechas de inicio a las actividades para visualizar el cronograma.")

# --- SECCIÓN 3: CONEXIÓN A SLACK ---
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
