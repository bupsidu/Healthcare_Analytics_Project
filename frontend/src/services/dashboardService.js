// frontend/src/services/dashboardService.js
import { authClient } from './authClient'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

const DIAS_SEMANA_CORTOS = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb']
const DIAS_SEMANA_LARGOS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']
const MESES_CORTOS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

// Parsea "YYYY-MM-DD" en hora local para evitar desfases de zona horaria en Chile
function parseFechaLocal(isoDate) {
  const [y, m, d] = isoDate.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function formatFechaISO(dateObj) {
  const y = dateObj.getFullYear()
  const m = String(dateObj.getMonth() + 1).padStart(2, '0')
  const d = String(dateObj.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export const dashboardService = {
  /**
   * Obtiene los datos reales de clima, atenciones, historial diario y proyección ML
   * para el hospital en sesión.
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
    const codigoDeis = establecimiento.id_establecimiento
    const capacidadMax = establecimiento.capacidad_camas || 50
    const headers = { Authorization: `Bearer ${token}` }

    // 1. Consultar el clima real del hospital en Open-Meteo vía FastAPI
    const respClima = await fetch(`${API_BASE_URL}/establecimientos/${hospitalId}/clima`, { headers })

    if (!respClima.ok) {
      throw new Error('No fue posible obtener el clima del establecimiento desde el servidor.')
    }

    const climaData = await respClima.json()
    const horas = climaData.pronostico_horario || []

    if (horas.length === 0) {
      throw new Error('El servicio meteorológico no entregó datos horarios.')
    }

    const actual = horas[0]
    const tempActual = actual.temperatura_c ?? 15
    const icaActual = actual.indice_calidad_aire_us ?? 40
    const pm25Actual = actual.pm2_5_ug_m3 ?? 10
    const lluviaActual = actual.precipitacion_mm ?? 0

    const primeras24 = horas.slice(0, 24).map((h) => h.temperatura_c).filter((t) => t !== null)
    const tempMin = primeras24.length ? Math.min(...primeras24) : tempActual
    const tempMax = primeras24.length ? Math.max(...primeras24) : tempActual

    // Fecha de hoy en formato local YYYY-MM-DD
    const hoy = new Date()
    const hoyISO = formatFechaISO(hoy)

    // 2. Consultar registros reales en PostgreSQL (/ingresos y /demanda-diaria)
    const registrosPorFecha = {}
    let atencionesHoy = 0

    try {
      const respIngresos = await fetch(
        `${API_BASE_URL}/ingresos?establecimiento_id=${hospitalId}&limit=100`,
        { headers }
      )
      if (respIngresos.ok) {
        const ingresosData = await respIngresos.json()
        for (const item of ingresosData.items || []) {
          const fecha = item.fecha
          const casos = item.casos_respiratorios ?? 1
          registrosPorFecha[fecha] = (registrosPorFecha[fecha] || 0) + casos
        }
        atencionesHoy = registrosPorFecha[hoyISO] || 0
      }
    } catch {
      // Si falla la consulta de ingresos, continúa sin bloquear la pantalla
    }

    try {
      const queryDeis = codigoDeis ? `?id_establecimiento=${encodeURIComponent(codigoDeis)}&limit=30` : '?limit=30'
      const respDemanda = await fetch(`${API_BASE_URL}/demanda-diaria${queryDeis}`, { headers })
      if (respDemanda.ok) {
        const demandaData = await respDemanda.json()
        for (const item of demandaData.items || []) {
          // La tabla demanda_diaria guarda el total consolidado del día;
          // si hoy ya tiene registros en Triage, conservamos el mayor valor real.
          if (item.fecha === hoyISO) {
            registrosPorFecha[item.fecha] = Math.max(registrosPorFecha[item.fecha] || 0, item.total)
            atencionesHoy = registrosPorFecha[item.fecha]
          } else {
            registrosPorFecha[item.fecha] = item.total
          }
        }
      }
    } catch {
      // Si no hay demanda histórica cargada, se mantiene solo lo de /ingresos
    }

    // 3. Consultar predicciones reales del modelo ML (/predicciones/historial y /predict/proyeccion-96h)
    const prediccionesPorFecha = {}
    let pacientesHoy = null
    let pacientesManana = null
    let diasProyeccion = []

    try {
      const queryDeis = codigoDeis ? `?id_establecimiento=${encodeURIComponent(codigoDeis)}&limit=30` : '?limit=30'
      const respHistPred = await fetch(`${API_BASE_URL}/predicciones/historial${queryDeis}`, { headers })
      if (respHistPred.ok) {
        const histPredData = await respHistPred.json()
        for (const item of histPredData.items || []) {
          if (item.pacientes_predichos !== null && prediccionesPorFecha[item.fecha] === undefined) {
            prediccionesPorFecha[item.fecha] = item.pacientes_predichos
          }
        }
      }
    } catch {
      // Si aún no hay predicciones guardadas, continúa sin error
    }

    try {
      const respProy = await fetch(
        `${API_BASE_URL}/predict/proyeccion-96h?establecimiento_id=${hospitalId}`,
        { headers }
      )
      if (respProy.ok) {
        const proyData = await respProy.json()
        diasProyeccion = proyData.dias || []

        for (const d of diasProyeccion) {
          if (d.pacientes_predichos !== null) {
            prediccionesPorFecha[d.fecha] = d.pacientes_predichos
          }
        }

        if (diasProyeccion[0] && diasProyeccion[0].pacientes_predichos !== null) {
          pacientesHoy = diasProyeccion[0].pacientes_predichos
        }
        if (diasProyeccion[1] && diasProyeccion[1].pacientes_predichos !== null) {
          pacientesManana = diasProyeccion[1].pacientes_predichos
        }
      }
    } catch {
      // Si el modelo aún no tiene histórico previo de 4 días, se mantiene en null
    }

    // 4. Armar la serie de 7 días de la semana (3 días atrás + Hoy + 3 días futuros)
    const fechasSet = new Set()
    for (let offset = -3; offset <= 3; offset++) {
      const d = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() + offset)
      fechasSet.add(formatFechaISO(d))
    }
    // Asegurar que todos los días devueltos por proyeccion-96h estén incluidos
    for (const d of diasProyeccion) {
      if (d.fecha) fechasSet.add(d.fecha)
    }

    const fechasOrdenadas = Array.from(fechasSet).sort()
    const serieSemanal = fechasOrdenadas.map((fechaISO) => {
      const fechaObj = parseFechaLocal(fechaISO)
      const diaCorto = DIAS_SEMANA_CORTOS[fechaObj.getDay()]
      const diaLargo = DIAS_SEMANA_LARGOS[fechaObj.getDay()]
      const mesCorto = MESES_CORTOS[fechaObj.getMonth()]
      const numDia = fechaObj.getDate()
      const esFuturo = fechaISO > hoyISO

      // Para días futuros los registros siempre son null (aún no ocurren)
      const registros = esFuturo
        ? null
        : registrosPorFecha[fechaISO] !== undefined
        ? registrosPorFecha[fechaISO]
        : fechaISO === hoyISO
        ? atencionesHoy
        : null

      const prediccion = prediccionesPorFecha[fechaISO] !== undefined
        ? prediccionesPorFecha[fechaISO]
        : null

      return {
        fecha: fechaISO,
        dia: `${diaCorto} ${numDia}`,
        diaCompleto: `${diaLargo} ${numDia} ${mesCorto}`,
        esHoy: fechaISO === hoyISO,
        registros,
        prediccion,
      }
    })

    const hayPredicciones = serieSemanal.some((p) => p.prediccion !== null)
    const hayRegistros = serieSemanal.some((p) => p.registros !== null)

    // Si hay proyección IA la usamos en la tarjeta 1; si no, mostramos las atenciones reales de hoy
    const valorAfluencia = pacientesHoy !== null ? pacientesHoy : atencionesHoy
    const porcentajeOcupacion = Math.min(Math.round((valorAfluencia / capacidadMax) * 100), 100)

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
      grafico: {
        serieSemanal,
        capacidadMaxima: capacidadMax,
        hayPredicciones,
        hayRegistros,
      },
      horasPronostico: horas,
    }
  },
}