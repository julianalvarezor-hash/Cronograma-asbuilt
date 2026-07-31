import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import requests # Para enviar las notificaciones a Slack

st.set_page_config(page_title="Control de Producción As-Built (LPS)", layout="wide")
st.title("🏗️ Control de Producción As-Built — Last Planner System")

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
    default=[datetime.date(2026, 8, 7)] # Opción por defecto
)

# Función de cálculo de fecha fin (Excluye Fines de Semana + Festivos Seleccionados)
def calcular_fecha_fin(fecha_inicio, dias_estimados, festivos_no_lab):
    fecha_actual = fecha_inicio
    dias_sumados = 0
    while dias_sumados < dias_estimados:
        fecha_actual += datetime.timedelta(days=1)
        es_fin_de_semana = fecha_actual.weekday() >= 5 # 5=Sábado, 6=Domingo
        es_festivo_no_laboral = fecha_actual in festivos_no_lab
        
        if not es_fin_de_semana and not es_festivo_no_laboral:
            dias_sumados += 1
    return fecha_actual

# --- SECCIÓN 2: DATOS DE ACTIVIDADES ---
datos_iniciales = [
    {"Actividad": "Muros Exteriores", "Responsable": "Julian Alvarez", "Inicio": datetime.date(2026, 7, 31), "Días": 5, "Estado": "En proceso", "Comentarios": "Falta coordinación de planos"},
    {"Actividad": "Muros Interiores", "Responsable": "Julian Alvarez", "Inicio": datetime.date(2026, 7, 31), "Días": 5, "Estado": "Pendiente", "Comentarios": ""},
    {"Actividad": "Pisos", "Responsable": "Carlos Gómez", "Inicio": datetime.date(2026, 7, 31), "Días": 2, "Estado": "Pendiente", "Comentarios": "Revisión de cotas"},
    {"Actividad": "Puertas", "Responsable": "Ana Martínez", "Inicio": datetime.date(2026, 8, 5), "Días": 4, "Estado": "En proceso", "Comentarios": ""},
    {"Actividad": "Ventanas", "Responsable": "Ana Martínez", "Inicio": datetime.date(2026, 8, 10), "Días": 2, "Estado": "Completado", "Comentarios": ""},
    {"Actividad": "Documentación y Planos", "Responsable": "Julian Alvarez", "Inicio": datetime.date(2026, 8, 12), "Días": 4, "Estado": "Pendiente", "Comentarios": "Ajustes finales de obra"}
]

df = pd.DataFrame(datos_iniciales)

# Cálculo dinámico usando la lista de festivos manuales
df['Fecha Fin'] = df.apply(lambda row: calcular_fecha_fin(row['Inicio'], row['Días'], festivos_manuales), axis=1)

# --- VISTA 1: TABLA EDITABLE CON LISTA DESPLEGABLE ---
st.subheader("📋 Registro de Actividades As-Built")

df_editado = st.data_editor(
    df[['Actividad', 'Responsable', 'Inicio', 'Días', 'Fecha Fin', 'Estado', 'Comentarios']],
    use_container_width=True,
    num_rows="dynamic",
    column_config={
        "Estado": st.column_config.SelectboxColumn(
            "Estado del Compromiso",
            help="Selecciona el estado actual de la actividad",
            options=[
                "Pendiente",
                "En proceso",
                "Completado"
            ],
            required=True
        )
    }
)

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
