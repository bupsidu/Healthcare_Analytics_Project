// frontend/src/components/reports/ReportsSection.jsx
import React, { useState, useEffect } from 'react'
import {
  TrendingUp,
  Users,
  Stethoscope,
  Calendar,
  RefreshCw,
  Inbox,
  AlertCircle,
  Filter,
} from 'lucide-react'
import Card from '../ui/Card'
import Button from '../ui/Button'
import { intakeService } from '../../services/intakeService'

// Opciones de periodo
const PERIODOS = [
  { id: 'semana_actual', label: 'Esta Semana (Últimos 7 días)', dias: 7 },
  { id: 'semana_anterior', label: 'Semana Anterior', dias: 7 },
  { id: 'mes', label: 'Últimos 30 días', dias: 30 },
  { id: 'todo', label: 'Historial Completo', dias: null },
]

function formatearFechaBonita(isoDate) {
  if (!isoDate) return ''
  const [y, m, d] = isoDate.split('-').map(Number)
  const f = new Date(y, m - 1, d)
  return f.toLocaleDateString('es-CL', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

export default function ReportsSection({ establecimiento }) {
  const [registros, setRegistros] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [periodoSeleccionado, setPeriodoSeleccionado] = useState('semana_actual')

  const cargarDatos = async () => {
    if (!establecimiento?.id) return
    setCargando(true)
    setError('')
    try {
      const datos = await intakeService.getHistorialIngresos(establecimiento.id)
      const parseados = (datos || []).map((item) => {
        // Causa persistida en localStorage o fallback
        const causa =
          localStorage.getItem(`ingreso_causa_${item.id}`) ||
          sessionStorage.getItem(`ingreso_causa_${item.id}`) ||
          'Patología Respiratoria'

        return {
          id: item.id,
          fecha: item.fecha, // "YYYY-MM-DD"
          casos: item.casos_respiratorios || 1,
          grupoEtario: item.grupo_etario,
          causa: causa,
          createdAt: item.created_at,
        }
      })
      setRegistros(parseados)
    } catch (err) {
      setError(err.message || 'No fue posible cargar el historial de reportes.')
    } finally {
      setCargando(false)
    }
  }

  useEffect(() => {
    cargarDatos()
  }, [establecimiento?.id])

  // --- FILTRADO POR PERIODO ---
  const hoy = new Date()
  const hoyMidnight = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate())

  const registrosFiltrados = registros.filter((reg) => {
    if (periodoSeleccionado === 'todo') return true

    const [y, m, d] = reg.fecha.split('-').map(Number)
    const fechaReg = new Date(y, m - 1, d)
    const diffDias = Math.floor((hoyMidnight - fechaReg) / (1000 * 60 * 60 * 24))

    if (periodoSeleccionado === 'semana_actual') {
      return diffDias >= 0 && diffDias < 7
    }
    if (periodoSeleccionado === 'semana_anterior') {
      return diffDias >= 7 && diffDias < 14
    }
    if (periodoSeleccionado === 'mes') {
      return diffDias >= 0 && diffDias < 30
    }
    return true
  })

  // --- CÁLCULO DE LOS 3 KPIS ---
  // 1. Total y Promedio
  const totalConsultas = registrosFiltrados.reduce((acc, r) => acc + r.casos, 0)
  const configPeriodo = PERIODOS.find((p) => p.id === periodoSeleccionado)
  const diasPeriodo = configPeriodo?.dias || (registrosFiltrados.length > 0 ? 30 : 1)
  const promedioDiario = totalConsultas > 0 ? (totalConsultas / diasPeriodo).toFixed(1) : '0.0'

  // 2. Rango Etario Más Frecuente
  const conteoEtario = {}
  for (const r of registrosFiltrados) {
    conteoEtario[r.grupoEtario] = (conteoEtario[r.grupoEtario] || 0) + r.casos
  }
  let topEtario = null
  let maxEtario = 0
  for (const [grupo, cant] of Object.entries(conteoEtario)) {
    if (cant > maxEtario) {
      maxEtario = cant
      topEtario = grupo
    }
  }
  const pctEtario = totalConsultas > 0 ? Math.round((maxEtario / totalConsultas) * 100) : 0

  // 3. Enfermedad / Causa Más Frecuente
  const conteoCausas = {}
  for (const r of registrosFiltrados) {
    conteoCausas[r.causa] = (conteoCausas[r.causa] || 0) + r.casos
  }
  let topCausa = null
  let maxCausa = 0
  for (const [causa, cant] of Object.entries(conteoCausas)) {
    if (cant > maxCausa) {
      maxCausa = cant
      topCausa = causa
    }
  }
  const pctCausa = totalConsultas > 0 ? Math.round((maxCausa / totalConsultas) * 100) : 0

  // --- AGRUPACIÓN POR DÍA PARA LA VISTA DETALLADA ---
  const diasAgrupados = {}
  for (const r of registrosFiltrados) {
    if (!diasAgrupados[r.fecha]) {
      diasAgrupados[r.fecha] = {
        fecha: r.fecha,
        total: 0,
        etarios: {},
        causas: {},
        items: [],
      }
    }
    diasAgrupados[r.fecha].total += r.casos
    diasAgrupados[r.fecha].etarios[r.grupoEtario] = (diasAgrupados[r.fecha].etarios[r.grupoEtario] || 0) + r.casos
    diasAgrupados[r.fecha].causas[r.causa] = (diasAgrupados[r.fecha].causas[r.causa] || 0) + r.casos
    diasAgrupados[r.fecha].items.push(r)
  }

  // Ordenados de más reciente a más antiguo
  const listaDias = Object.values(diasAgrupados).sort((a, b) => b.fecha.localeCompare(a.fecha))

  if (cargando) {
    return (
      <Card className="!p-10 text-center flex flex-col items-center justify-center gap-2">
        <div className="w-6 h-6 border-2 border-clinical-600 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs font-semibold text-slate-600">
          Cargando reportes y consolidado epidemiológico...
        </p>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className="!p-6 border-rose-200 bg-rose-50/50">
        <div className="flex items-start gap-3 text-xs text-rose-800">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div className="space-y-2 flex-1">
            <p className="font-semibold text-rose-900">Error al cargar reportes:</p>
            <p>{error}</p>
            <div>
              <Button type="button" variant="outline" onClick={cargarDatos} icon={RefreshCw} className="!w-auto !py-1.5 !px-3 !text-xs !bg-white">
                Reintentar
              </Button>
            </div>
          </div>
        </div>
      </Card>
    )
  }

  return (
    <div className="space-y-6 font-sans">
      
      {/* 1. Barra de Control de Periodo */}
      <Card className="!p-4 sm:!p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5 mr-2">
              <Filter className="w-3.5 h-3.5 text-slate-500" />
              Periodo:
            </span>
            {PERIODOS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setPeriodoSeleccionado(p.id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition cursor-pointer ${
                  periodoSeleccionado === p.id
                    ? 'bg-clinical-600 text-white shadow-xs'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200/80 hover:text-slate-900'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 self-end sm:self-auto">
            <Button
              type="button"
              variant="outline"
              icon={RefreshCw}
              onClick={cargarDatos}
              className="!w-auto !py-1.5 !px-3 !text-xs !bg-white"
            >
              Actualizar
            </Button>
          </div>
        </div>
      </Card>

      {/* 2. LAS 3 TARJETAS KPI DE REPORTE */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        
        {/* KPI 1: Promedio Semanal */}
        <Card className="!p-5 border-2 border-sky-400/80 bg-sky-50/20 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              Promedio de Afluencia
            </span>
            <div className="w-9 h-9 rounded-xl bg-sky-100 text-sky-700 flex items-center justify-center">
              <TrendingUp className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-slate-900 tracking-tight font-mono">
              {promedioDiario}
            </span>
            <span className="text-xs text-slate-500 font-medium">pacientes / día</span>
          </div>
          <div className="mt-3 pt-3 border-t border-slate-200/60 flex items-center justify-between text-xs text-slate-500">
            <span>{totalConsultas} consultas en el periodo</span>
            <span className="font-semibold text-slate-700 font-mono">{diasPeriodo} días</span>
          </div>
        </Card>

        {/* KPI 2: Rango Etario Más Frecuente */}
        <Card className="!p-5 border-2 border-violet-400/80 bg-violet-50/20 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              Grupo Etario Predominante
            </span>
            <div className="w-9 h-9 rounded-xl bg-violet-100 text-violet-700 flex items-center justify-center">
              <Users className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-xl font-extrabold text-slate-900 tracking-tight block truncate">
              {topEtario || 'Sin atenciones'}
            </span>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-200/60 flex items-center justify-between text-xs text-slate-500">
            <span>{maxEtario} atenciones registradas</span>
            {totalConsultas > 0 && (
              <span className="font-bold text-violet-700 bg-violet-100 px-2 py-0.5 rounded-md text-[11px]">
                {pctEtario}% del total
              </span>
            )}
          </div>
        </Card>

        {/* KPI 3: Enfermedad / Causa Más Frecuente */}
        <Card className="!p-5 border-2 border-emerald-400/80 bg-emerald-50/20 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              Enfermedad Más Frecuente
            </span>
            <div className="w-9 h-9 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center">
              <Stethoscope className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-xl font-extrabold text-slate-900 tracking-tight block truncate">
              {topCausa || 'Sin atenciones'}
            </span>
          </div>
          <div className="mt-4 pt-3 border-t border-slate-200/60 flex items-center justify-between text-xs text-slate-500">
            <span>{maxCausa} casos diagnosticados</span>
            {totalConsultas > 0 && (
              <span className="font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-md text-[11px]">
                {pctCausa}% del total
              </span>
            )}
          </div>
        </Card>

      </div>

      {/* 3. DESGLOSE DÍA POR DÍA */}
      <Card className="!p-6">
        <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-100">
          <div>
            <h3 className="text-sm font-bold text-slate-900">Desglose de Atenciones por Jornada</h3>
            <p className="text-xs text-slate-500">
              Detalle cronológico de consultas, edades y patologías respiratorias
            </p>
          </div>
          <span className="px-3 py-1 rounded-full bg-slate-100 text-slate-700 text-xs font-semibold font-mono">
            {listaDias.length} jornadas con atenciones
          </span>
        </div>

        {listaDias.length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-xs flex flex-col items-center justify-center gap-2">
            <Inbox className="w-8 h-8 text-slate-300" />
            <p className="font-medium text-slate-600">No hay atenciones en el periodo seleccionado</p>
            <p className="text-[11px] text-slate-400">Selecciona otro rango de fechas o registra nuevas consultas en Triage.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {listaDias.map((dia) => (
              <div
                key={dia.fecha}
                className="p-4 rounded-2xl border border-slate-200/80 bg-slate-50/40 hover:bg-slate-50 transition-colors"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-200/60">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-clinical-600" />
                    <span className="text-xs font-bold text-slate-900 capitalize">
                      {formatearFechaBonita(dia.fecha)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-0.5 rounded-full bg-clinical-50 text-clinical-700 border border-clinical-200 font-bold text-xs font-mono">
                      {dia.total} {dia.total === 1 ? 'paciente' : 'pacientes'}
                    </span>
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                  {/* Desglose por Edad */}
                  <div>
                    <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                      Distribución por Edad:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(dia.etarios).map(([grupo, cant]) => (
                        <span
                          key={grupo}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-700 text-[11px]"
                        >
                          <Users className="w-3 h-3 text-slate-400" />
                          <span>{grupo}:</span>
                          <strong className="font-mono text-slate-900">{cant}</strong>
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Desglose por Causa */}
                  <div>
                    <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                      Diagnósticos del Día:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(dia.causas).map(([causa, cant]) => (
                        <span
                          key={causa}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-700 text-[11px]"
                        >
                          <span className="w-1.5 h-1.5 rounded-full bg-clinical-500" />
                          <span>{causa}:</span>
                          <strong className="font-mono text-slate-900">{cant}</strong>
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

    </div>
  )
}