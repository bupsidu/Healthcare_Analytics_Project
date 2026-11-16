// frontend/src/services/dashboardService.js
import { authClient } from './authClient'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export const dashboardService = {
  /**
   * Obtiene los datos reales de clima, atenciones y proyección para el hospital en sesión.
   */
  async obtenerDatosDashboard(establecimiento) {
    const token = authClient.getToken()
    if (!token) {
      throw new Error('No hay una sesión activa. Inicie sesión nuevamente.')
    }

    if (!establecimiento?.id) {
      throw new Error('No se ha detectado un establecimiento válido en la sesión.')
    }

    const hospitalId = establecimiento.id
    const capacidadMax = establecimiento.capacidad_camas || 50

    // 1. Consultar el clima real del hospital en Open-Meteo vía FastAPI
    const respClima = await fetch(`${API_BASE_URL}/establecimientos/${hospitalId}/clima`, {
      headers: { Authorization: `Bearer ${token}` },
    })

    if (!respClima.ok) {
      throw new Error('No fue posible obtener el clima del establecimiento desde el servidor.')
    }

    const climaData = await respClima.json()
    const horas = climaData.pronostico_horario || []

    if (horas.length === 0) {
      throw new Error('El servicio meteorológico no entregó datos horarios.')
    }

    // Datos del momento actual (primera hora)
    const actual = horas[0]
    const tempActual = actual.temperatura_c ?? 15
    const icaActual = actual.indice_calidad_aire_us ?? 40
    const pm25Actual = actual.pm2_5_ug_m3 ?? 10
    const lluviaActual = actual.precipitacion_mm ?? 0

    // Temperaturas mínimas y máximas de las próximas 24 horas
    const primeras24 = horas.slice(0, 24).map((h) => h.temperatura_c).filter((t) => t !== null)
    const tempMin = primeras24.length ? Math.min(...primeras24) : tempActual
    const tempMax = primeras24.length ? Math.max(...primeras24) : tempActual

    // 2. Consultar atenciones reales de hoy en PostgreSQL
    let atencionesHoy = 0
    try {
      const respIngresos = await fetch(`${API_BASE_URL}/ingresos?establecimiento_id=${hospitalId}&limit=100`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (respIngresos.ok) {
        const ingresosData = await respIngresos.json()
        atencionesHoy = (ingresosData.items || []).reduce((acc, curr) => acc + (curr.casos_respiratorios || 1), 0)
      }
    } catch {
      // Si falla la suma de ingresos, se mantiene en 0
    }

    // 3. Proyección ML de hoy y mañana desde FastAPI
    let pacientesHoy = null
    let pacientesManana = null

    try {
      const respProy = await fetch(`${API_BASE_URL}/predict/proyeccion-96h`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (respProy.ok) {
        const proyData = await respProy.json()
        const dias = proyData.dias || []
        
        if (dias[0] && dias[0].pacientes_predichos !== null) {
          pacientesHoy = dias[0].pacientes_predichos
        }
        if (dias[1] && dias[1].pacientes_predichos !== null) {
          pacientesManana = dias[1].pacientes_predichos
        }
      }
    } catch {
      // Si el modelo aún no tiene histórico previo, se mantiene en null
    }

    // Si hay proyección IA la usamos; si no, mostramos las atenciones reales de hoy
    const valorAfluencia = pacientesHoy !== null ? pacientesHoy : atencionesHoy
    const porcentajeOcupacion = Math.min(Math.round((valorAfluencia / capacidadMax) * 100), 100)

    // Cálculo de tendencia Hoy vs Mañana
    let comparativaManana = null
    if (pacientesManana !== null && pacientesHoy !== null && pacientesHoy > 0) {
      const diffPct = Math.round(((pacientesManana - pacientesHoy) / pacientesHoy) * 100)
      comparativaManana = {
        valor: pacientesManana,
        diffTexto: diffPct >= 0 ? `+${diffPct}%` : `${diffPct}%`,
        esAlza: diffPct > 0,
      }
    }

    return {
      demanda: {
        valor: valorAfluencia,
        esProyeccionIA: pacientesHoy !== null,
        capacidadMaxima: capacidadMax,
        porcentajeOcupacion,
        atencionesHoy,
        comparativaManana,
      },
        clima: {
            temperatura: `${Math.round(tempActual * 10) / 10}°C`,
            minMax: `${Math.round(tempMin)}°C / ${Math.round(tempMax)}°C`,
            tempMinNum: Math.round(tempMin * 10) / 10,
            lluvia: lluviaActual,
            alertaFrio: tempMin <= 2,
            zona: establecimiento.comuna || establecimiento.region || 'Local',
      },
      ica: {
        valor: Math.round(icaActual),
        pm25: Math.round(pm25Actual * 10) / 10,
        estado: icaActual > 150 ? 'Preemergencia' : icaActual > 100 ? 'Alerta Ambiental' : icaActual > 50 ? 'Regular' : 'Bueno',
      },
      horasPronostico: horas,
    }
  },
}