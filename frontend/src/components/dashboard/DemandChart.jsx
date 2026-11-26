// frontend/src/components/dashboard/DemandChart.jsx
import React from 'react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts'
import { TrendingUp, RefreshCw, Info } from 'lucide-react'
import Card from '../ui/Card'

function CustomTooltip({ active, payload }) {
  if (!active || !payload || payload.length === 0) return null

  const punto = payload[0]?.payload

  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-lg p-3.5 text-xs space-y-2 min-w-[190px]">
      <div className="flex items-center justify-between gap-2 pb-1.5 border-b border-slate-100">
        <span className="font-bold text-slate-800">{punto?.diaCompleto}</span>
        {punto?.esHoy && (
          <span className="px-1.5 py-0.5 rounded-md bg-clinical-100 text-clinical-700 font-bold text-[10px] uppercase">
            Hoy
          </span>
        )}
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between gap-4">
          <span className="inline-flex items-center gap-1.5 text-slate-600 font-medium">
            <span className="w-2.5 h-2.5 rounded-full bg-sky-600" />
            Registros
          </span>
          <span className="font-mono font-bold text-slate-900">
            {punto?.registros !== null && punto?.registros !== undefined
              ? `${punto.registros} pac.`
              : 'Sin registro'}
          </span>
        </div>

        <div className="flex items-center justify-between gap-4">
          <span className="inline-flex items-center gap-1.5 text-slate-600 font-medium">
            <span className="w-2.5 h-2.5 rounded-full bg-violet-600" />
            Predicción ML
          </span>
          <span className="font-mono font-bold text-slate-900">
            {punto?.prediccion !== null && punto?.prediccion !== undefined
              ? `${punto.prediccion} pac.`
              : 'No disponible'}
          </span>
        </div>
      </div>
    </div>
  )
}

export default function DemandChart({ grafico, establecimiento, onRefresh }) {
  if (!grafico) return null

  const { serieSemanal, hayPredicciones } = grafico
  const puntoHoy = serieSemanal.find((p) => p.esHoy)

  return (
    <Card className="!p-6 sm:!p-7 font-sans">
      {/* Cabecera del gráfico */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-100">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-clinical-50 text-clinical-600 flex items-center justify-center shrink-0">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight">
              Demanda Semanal: Registros vs. Predicción (96h)
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {establecimiento?.nombre || 'Establecimiento'} · Monitoreo de consultas de urgencia
            </p>
          </div>
        </div>

        {/* Leyenda y botón actualizar */}
        <div className="flex items-center flex-wrap gap-3">
          <div className="flex items-center gap-4 text-xs font-semibold text-slate-600 bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-200/70">
            <span className="inline-flex items-center gap-1.5">
              <span className="w-3 h-0.5 bg-sky-600 rounded-full" />
              Registros
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="w-3 h-0.5 border-t-2 border-dashed border-violet-600" />
              Predicción ML
            </span>
          </div>

          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 hover:text-slate-900 transition-colors cursor-pointer"
              title="Actualizar datos en vivo"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Actualizar
            </button>
          )}
        </div>
      </div>

      {/* Contenedor del Gráfico Recharts */}
      <div className="mt-6 h-[320px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={serieSemanal} margin={{ top: 15, right: 20, left: 0, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />

            <XAxis
              dataKey="dia"
              tick={{ fill: '#475569', fontSize: 12, fontWeight: 600 }}
              axisLine={{ stroke: '#cbd5e1' }}
              tickLine={false}
              dy={8}
            />

            <YAxis
              allowDecimals={false}
              domain={[0, (dataMax) => Math.max(Math.ceil(dataMax * 1.25), 8)]}
              tick={{ fill: '#64748b', fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              width={45}
              label={{
                value: 'Pacientes',
                angle: -90,
                position: 'insideLeft',
                style: { fill: '#64748b', fontSize: 11, fontWeight: 600 },
                offset: 10,
              }}
            />

            <Tooltip content={<CustomTooltip />} />

            {/* Línea vertical para marcar el día de Hoy */}
            {puntoHoy && (
              <ReferenceLine
                x={puntoHoy.dia}
                stroke="#94a3b8"
                strokeDasharray="4 4"
                label={{
                  value: 'Hoy',
                  position: 'top',
                  fill: '#475569',
                  fontSize: 11,
                  fontWeight: 700,
                }}
              />
            )}

            {/* LÍNEA 1: Registros Reales (PostgreSQL) */}
            <Line
              type="monotone"
              dataKey="registros"
              name="Registros"
              stroke="#0284c7"
              strokeWidth={3}
              dot={{ r: 5, fill: '#0284c7', stroke: '#ffffff', strokeWidth: 2 }}
              activeDot={{ r: 7, fill: '#0369a1', stroke: '#ffffff', strokeWidth: 2 }}
              connectNulls={false}
            />

            {/* LÍNEA 2: Predicción Modelo ML (96h) */}
            <Line
              type="monotone"
              dataKey="prediccion"
              name="Predicción ML"
              stroke="#7c3aed"
              strokeWidth={3}
              strokeDasharray="6 4"
              dot={{ r: 5, fill: '#7c3aed', stroke: '#ffffff', strokeWidth: 2 }}
              activeDot={{ r: 7, fill: '#6d28d9', stroke: '#ffffff', strokeWidth: 2 }}
              connectNulls={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {!hayPredicciones && (
        <div className="mt-4 pt-3 border-t border-slate-100 flex items-start gap-2 text-xs text-slate-500">
          <Info className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
          <p>
            Aún no hay predicciones calculadas para los próximos días porque el modelo ML requiere
            contar con registros de demanda de 4 días previos en la base de datos para este establecimiento.
          </p>
        </div>
      )}
    </Card>
  )
}