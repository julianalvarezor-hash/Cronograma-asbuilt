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
    df_raw.columns = df_raw.columns.str.strip()
    
    # Aseguramos que la columna Inicio sea formato fecha
    if 'Inicio' in df_raw.columns:
        df_raw['Inicio'] = pd.to_datetime(df_raw['Inicio'], errors='coerce').dt.date
    
    # Si la columna Fecha Fin no existe en tu Google Sheets, la creamos vacía temporalmente
    if 'Fecha Fin' not in df_raw.columns:
        df_raw['Fecha Fin'] = None
    df_raw['Fecha Fin'] = pd.to_datetime(df_raw['Fecha Fin'], errors='coerce').dt.date
    
    # Mantenemos Días como dato informativo, pero ya no afecta el cálculo
    if 'Días' in df_raw.columns:
        df_raw['Días'] = pd.to_numeric(df_raw['Días'], errors='coerce').fillna(1).astype(int)
        
    return df_raw

if "df_datos_base" not in st.session_state:
    try:
        st.session_state.df_datos_base = cargar_datos()
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        st.stop()

# --- VISTA 1: TABLA EDITABLE ---
st.subheader("📋 Registro de Actividades As-Built")

# Ahora la tabla incluye Fecha Fin para que la edites manualmente
df_editado = st.data_editor(
    st.session_state.df_datos_base[['Actividad', 'Responsable', 'Inicio', 'Fecha Fin', 'Días', 'Estado', 'Comentarios']],
    use_container_width=True,
    num_rows="dynamic",
    key="editor_tabla",
    column_config={
        "Estado": st.column_config.SelectboxColumn(
            "Estado del Compromiso",
            options=["Pendiente", "En proceso", "Completado"]
        ),
        "Inicio": st.column_config.DateColumn("Inicio", format="YYYY-MM-DD"),
        "Fecha Fin": st.column_config.DateColumn("Fecha Fin (Manual)", format="YYYY-MM-DD"),
        "Días": st.column_config.NumberColumn("Días (Informativo)", min_value=1, step=1)
    }
)

# --- BOTÓN DE GUARDADO PERMANENTE ---
col1, col2 = st.columns([1, 4])
with col1:
    if st.button("💾 Guardar Cambios en la Nube"):
        try:
            # Ahora guardamos también la Fecha Fin
            df_para_guardar = df_editado[['Actividad', 'Responsable', 'Inicio', 'Fecha Fin', 'Días', 'Estado', 'Comentarios']].copy()
            
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

# Filtramos los datos válidos para el gráfico
df_grafico = df_editado.dropna(subset=['Inicio', 'Fecha Fin']).copy()

# Agregamos el selector de fechas al menú lateral (Sidebar)
st.sidebar.markdown("---")
st.sidebar.subheader("🔎 Filtro del Gantt")

if not df_grafico.empty:
    min_date = df_grafico['Inicio'].min()
    max_date = df_grafico['Fecha Fin'].max()
else:
    min_date = datetime.date.today()
    max_date = datetime.date.today() + datetime.timedelta(days=15)

rango_fechas = st.sidebar.date_input(
    "Selecciona el rango a visualizar:",
    value=(min_date, max_date)
)

if not df_grafico.empty:
    if isinstance(rango_fechas, tuple) and len(rango_fechas) == 2:
        fecha_inicio_filtro, fecha_fin_filtro = rango_fechas
        
        df_grafico_filtrado = df_grafico[
            (df_grafico['Fecha Fin'] >= fecha_inicio_filtro) & 
            (df_grafico['Inicio'] <= fecha_fin_filtro)
        ]
        
        if not df_grafico_filtrado.empty:
            fig = px.timeline(
                df_grafico_filtrado, 
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
                    range=[str(fecha_inicio_filtro), str(fecha_fin_filtro)]
                )
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hay actividades en el rango de fechas seleccionado.")
    else:
        st.info("Por favor, selecciona una fecha de inicio y una de fin en el menú lateral.")
else:
    st.info("Agrega fechas de inicio y fin a las actividades para visualizar el cronograma.")

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
