import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import requests
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Control de Producción As-Built (LPS)", layout="wide")
st.title("🏗️ Control de Producción As-Built — Last Planner System")

# --- CONEXIÓN A GOOGLE SHEETS Y LIMPIEZA DE SECRETS ---
try:
    if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        pk = st.secrets["connections"]["gsheets"].get("private_key", "")
        if "\\n" in pk:
            st.secrets["connections"]["gsheets"]["private_key"] = pk.replace("\\n", "\n")
            
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Error en configuración de Secrets: {e}")

def cargar_datos():
    df_raw = conn.read(ttl=0)
    
    columnas_esperadas = ['Actividad', 'Responsable', 'Inicio', 'Días', 'Estado', 'Comentarios']
    
    # Si la hoja está completamente vacía, creamos la estructura base
    if df_raw.empty or len(df_raw.columns) == 0:
        df_raw = pd.DataFrame(columns=columnas_esperadas)
        
    for col in columnas_esperadas:
        if col not in df_raw.columns:
            df_raw[col] = ""  # Usamos cadena vacía, NO el valor None
            
    df_raw.columns = df_raw.columns.str.strip()
    
    # Limpiamos cualquier "None" fantasma que haya quedado guardado en tu Sheets
    for col in ['Actividad', 'Responsable', 'Comentarios']:
        df_raw[col] = df_raw[col].fillna("")
        df_raw[col] = df_raw[col].astype(str).replace("None", "").replace("nan", "")

    df_raw['Inicio'] = pd.to_datetime(df_raw['Inicio'], errors='coerce').dt.date
    df_raw['Días'] = pd.to_numeric(df_raw['Días'], errors='coerce').fillna(1).astype(int)
    
    return df_raw

if "df_datos_base" not in st.session_state:
    try:
        st.session_state.df_datos_base = cargar_datos()
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        st.stop()

# --- SECCIÓN 1: SIDEBAR (LÍMITES DEL PROYECTO Y FESTIVOS) ---
st.sidebar.header("⚙️ Configuración del Proyecto")

# 1. DOS RECUADROS INDEPENDIENTES PARA LÍMITE DE PROYECTO
st.sidebar.subheader("📅 Límites del Proyecto")
fecha_inicio_proyecto = st.sidebar.date_input(
    "Fecha Inicio del Proyecto:", 
    value=datetime.date.today()
)
fecha_fin_proyecto = st.sidebar.date_input(
    "Fecha Fin del Proyecto:", 
    value=datetime.date.today() + datetime.timedelta(days=30)
)

st.sidebar.markdown("---")

# 2. SELECTOR DE FESTIVOS
st.sidebar.subheader("🏖️ Días No Laborables")
festivos_manuales = st.sidebar.multiselect(
    "Selecciona los festivos que NO se trabajarán:",
    options=[
        datetime.date(2026, 8, 7),   
        datetime.date(2026, 8, 17),  
        datetime.date(2026, 10, 12), 
        datetime.date(2026, 11, 2),  
        datetime.date(2026, 11, 16), 
        datetime.date(2026, 12, 8),  
        datetime.date(2026, 12, 25)  
    ],
    default=[datetime.date(2026, 8, 7)]
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
        # Configuramos explícitamente las columnas de texto para que sean de escritura libre
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
            df_para_guardar = df_editado[['Actividad', 'Responsable', 'Inicio', 'Días', 'Estado', 'Comentarios']].copy()
            
            df_para_guardar['Estado'] = df_para_guardar['Estado'].fillna('Pendiente')
            df_para_guardar['Días'] = df_para_guardar['Días'].fillna(1)
            
            conn.update(data=df_para_guardar)
            
            st.session_state.df_datos_base = df_para_guardar
            
            st.success("¡Datos guardados con éxito en Google Sheets!")
        except Exception as err:
            st.error(f"Error al guardar los cambios: {err}")

st.markdown("---")

# --- VISTA 2: GANTT / LÍNEA DE TIEMPO INTERACTIVA ---
st.subheader("📅 Cronograma y Línea de Tiempo Interactiva")

df_grafico = df_editado.dropna(subset=['Inicio', 'Fecha Fin']).copy()
# Filtrar aquellas filas que no tengan un texto de actividad válido para que Plotly no falle
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
    
    # Restricción del gráfico a las fechas del menú lateral
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
