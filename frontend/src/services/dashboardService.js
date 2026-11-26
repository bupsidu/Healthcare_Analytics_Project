// frontend/src/services/dashboardService.js
import { authClient } from './authClient'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

const DIAS_SEMANA_CORTOS = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb']
const DIAS_SEMANA_LARGOS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']
const MESES_CORTOS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

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
    const headers = { Authorization: `Bearer ${token}` }

    // 1. Clima de Open-Meteo vía FastAPI
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
      // Continúa sin bloquear
    }

    try {
      const queryDeis = codigoDeis ? `?id_establecimiento=${encodeURIComponent(codigoDeis)}&limit=30` : '?limit=30'
      const respDemanda = await fetch(`${API_BASE_URL}/demanda-diaria${queryDeis}`, { headers })
      if (respDemanda.ok) {
        const demandaData = await respDemanda.json()
        for (const item of demandaData.items || []) {
          if (item.fecha === hoyISO) {
            registrosPorFecha[item.fecha] = Math.max(registrosPorFecha[item.fecha] || 0, item.total)
            atencionesHoy = registrosPorFecha[item.fecha]
          } else {
            registrosPorFecha[item.fecha] = item.total
          }
        }
      }
    } catch {
      // Continúa sin bloquear
    }

    // 3. Predicciones reales ML (/predict/proyeccion-96h y /predicciones/historial)
    const prediccionesPorFecha = {}
    let pacientesHoy = null
    let pacientesManana = null
    let diasProyeccion = []

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
      // Sin histórico previo
    }

    // 4. Cálculo del Promedio Diario Histórico del propio centro
    const fechasConRegistro = Object.keys(registrosPorFecha).filter(
      (f) => f <= hoyISO && registrosPorFecha[f] !== null && registrosPorFecha[f] !== undefined
    )
    let promedioHistorico = 0
    if (fechasConRegistro.length > 0) {
      const sumaHistorica = fechasConRegistro.reduce((acc, f) => acc + registrosPorFecha[f], 0)
      promedioHistorico = Math.round((sumaHistorica / fechasConRegistro.length) * 10) / 10
    } else {
      promedioHistorico = (pacientesHoy !== null ? pacientesHoy : atencionesHoy) || 1
    }

    // Valor de demanda de hoy (IA si existe, si no registros reales)
    const valorAfluencia = pacientesHoy !== null ? pacientesHoy : atencionesHoy

    // Desvío porcentual respecto al promedio habitual
    const diffPromedioPct =
      promedioHistorico > 0
        ? Math.round(((valorAfluencia - promedioHistorico) / promedioHistorico) * 100)
        : 0

    // Semáforo relativo al promedio:
    // Verde: dentro del flujo normal (<= +15%)
    // Amarillo: aumento moderado (+16% a +35%)
    // Rojo: pico inusual de consultas (> +35%)
    const semaforoDemanda =
      diffPromedioPct > 35 ? 'rojo' : diffPromedioPct > 15 ? 'amarillo' : 'verde'

    // Comparativa de mañana (si la IA la calculó)
    let comparativaManana = null
    if (pacientesManana !== null && valorAfluencia > 0) {
      const diffPct = Math.round(((pacientesManana - valorAfluencia) / valorAfluencia) * 100)
      comparativaManana = {
        valor: pacientesManana,
        diffTexto: diffPct >= 0 ? `+${diffPct}%` : `${diffPct}%`,
        esAlza: diffPct > 0,
      }
    }

    // Serie semanal para el gráfico
    const fechasSet = new Set()
    for (let offset = -3; offset <= 3; offset++) {
      const d = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() + offset)
      fechasSet.add(formatFechaISO(d))
    }
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

      const registros = esFuturo
        ? null
        : registrosPorFecha[fechaISO] !== undefined
        ? registrosPorFecha[fechaISO]
        : fechaISO === hoyISO
        ? atencionesHoy
        : null

      const prediccion =
        prediccionesPorFecha[fechaISO] !== undefined
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

    return {
      demanda: {
        valor: valorAfluencia,
        esProyeccionIA: pacientesHoy !== null,
        atencionesHoy,
        promedioSemanal: promedioHistorico,
        diffPromedioPct,
        diffTexto: diffPromedioPct >= 0 ? `+${diffPromedioPct}%` : `${diffPromedioPct}%`,
        comparativaManana,
        semaforo: semaforoDemanda,
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
        hayPredicciones,
        hayRegistros,
      },
      horasPronostico: horas,
    }
  },
}