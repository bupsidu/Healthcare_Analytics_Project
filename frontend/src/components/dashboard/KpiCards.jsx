// frontend/src/components/dashboard/KpiCards.jsx
import React from 'react'
import { Users, CloudSun, Wind, TrendingUp, TrendingDown } from 'lucide-react'
import Card from '../ui/Card'

export default function KpiCards({ data }) {
  if (!data) return null

  const { demanda, clima, ica } = data

  // 1. Evaluación Semafórica de Demanda vs Promedio
  const estadoDemanda = demanda.semaforo || 'verde'

  // 2. Evaluación Semafórica de Clima
  const tempMin = clima.tempMinNum ?? (clima.alertaFrio ? 2 : 10)
  const estadoClima = (tempMin <= 0 || clima.lluvia >= 30)
    ? 'rojo'
    : (clima.alertaFrio || clima.lluvia >= 10)
    ? 'amarillo'
    : 'verde'

  // 3. Evaluación Semafórica de Calidad del Aire (ICA)
  const estadoIca = ica.valor > 150
    ? 'rojo'
    : ica.valor > 50
    ? 'amarillo'
    : 'verde'

  // Mapas de estilos por color activo
  const estilosPorColor = {
    verde: {
      card: '!border-2 !border-emerald-400 !bg-emerald-50/20 hover:!border-emerald-500',
      icono: 'bg-emerald-100 text-emerald-700',
      badge: 'bg-emerald-100 text-emerald-800',
      dot: 'bg-emerald-500',
    },
    amarillo: {
      card: '!border-2 !border-amber-400 !bg-amber-50/25 hover:!border-amber-500',
      icono: 'bg-amber-100 text-amber-700',
      badge: 'bg-amber-100 text-amber-800',
      dot: 'bg-amber-500',
    },
    rojo: {
      card: '!border-2 !border-rose-500 !bg-rose-50/30 hover:!border-rose-600',
      icono: 'bg-rose-100 text-rose-600',
      badge: 'bg-rose-100 text-rose-700',
      dot: 'bg-rose-500',
    },
  }

  const estiloDemanda = estilosPorColor[estadoDemanda]
  const estiloClima = estilosPorColor[estadoClima]
  const estiloIca = estilosPorColor[estadoIca]

  // Textos descriptivos del semáforo de Demanda
  const textoDemanda = estadoDemanda === 'rojo'
    ? `${demanda.diffTexto} sobre promedio (Pico)`
    : estadoDemanda === 'amarillo'
    ? `${demanda.diffTexto} sobre promedio`
    : 'Flujo Habitual'

  const textoClima = estadoClima === 'rojo'
    ? (tempMin <= 0 ? 'Helada Severa' : 'Temporal Extremo')
    : estadoClima === 'amarillo'
    ? (clima.alertaFrio ? 'Alerta Frío (Riesgo IRA)' : 'Lluvia Moderada')
    : 'Condición Favorable'

  const textoIca = estadoIca === 'rojo'
    ? 'Preemergencia'
    : ica.valor > 100
    ? 'Alerta Ambiental'
    : ica.valor > 50
    ? 'Calidad Regular'
    : 'Calidad Favorable'

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-5 font-sans">
      
      {/* TARJETA 1: Demanda vs. Promedio Histórico del Centro */}
      <Card className={`!p-5 transition-all duration-300 shadow-xs ${estiloDemanda.card}`}>
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-slate-600 uppercase tracking-wider">
            {demanda.esProyeccionIA ? 'Afluencia Estimada Hoy' : 'Demanda de Hoy'}
          </span>
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${estiloDemanda.icono}`}>
            <Users className="w-5 h-5" />
          </div>
        </div>

        <div className="mt-3 flex items-baseline gap-2">
          <span className="text-3xl font-extrabold text-slate-900 tracking-tight font-mono">
            {demanda.valor}
          </span>
          <span className="text-xs text-slate-500 font-medium">
            {demanda.valor === 1 ? 'paciente' : 'pacientes'}
          </span>
        </div>

        {/* Semáforo inferior y comparación con el promedio del centro */}
        <div className="mt-3 flex items-center justify-between text-xs pt-3 border-t border-slate-200/60">
          <span className={`inline-flex items-center gap-1.5 font-semibold px-2 py-0.5 rounded-md text-[11px] ${estiloDemanda.badge}`}>
            <span className={`w-2 h-2 rounded-full ${estiloDemanda.dot}`} />
            {textoDemanda}
          </span>

          <span className="text-[11px] font-medium text-slate-500">
            Promedio: <strong className="font-mono text-slate-700">{demanda.promedioSemanal}</strong> pac/día
          </span>
        </div>

        {/* Proyección de mañana (si está disponible) */}
        {demanda.comparativaManana && (
          <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-slate-100">
            <span className="inline-flex items-center gap-1">
              {demanda.comparativaManana.esAlza ? (
                <TrendingUp className="w-3.5 h-3.5 text-rose-500" />
              ) : (
                <TrendingDown className="w-3.5 h-3.5 text-emerald-500" />
              )}
              <span>Mañana: <strong className="text-slate-700">{demanda.comparativaManana.valor} pac</strong></span>
            </span>
            <span className={`font-semibold font-mono text-[10px] px-1.5 py-0.5 rounded ${
              demanda.comparativaManana.esAlza ? 'bg-rose-50 text-rose-700' : 'bg-emerald-50 text-emerald-700'
            }`}>
              {demanda.comparativaManana.diffTexto} vs hoy
            </span>
          </div>
        )}
      </Card>

      {/* TARJETA 2: Alerta Climática */}
      <Card className={`!p-5 transition-all duration-300 shadow-xs ${estiloClima.card}`}>
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-slate-600 uppercase tracking-wider">
            Clima · {clima.zona}
          </span>
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${estiloClima.icono}`}>
            <CloudSun className="w-5 h-5" />
          </div>
        </div>

        <div className="mt-3 flex items-baseline gap-2">
          <span className="text-3xl font-extrabold text-slate-900 tracking-tight font-mono">
            {clima.temperatura}
          </span>
          <span className="text-xs text-slate-500 font-medium font-mono">
            ({clima.minMax})
          </span>
        </div>

        <div className="mt-3 flex items-center justify-between text-xs pt-3 border-t border-slate-200/60">
          <span className={`inline-flex items-center gap-1.5 font-semibold px-2 py-0.5 rounded-md text-[11px] ${estiloClima.badge}`}>
            <span className={`w-2 h-2 rounded-full ${estiloClima.dot}`} />
            {textoClima}
          </span>
          <span className="text-[11px] text-slate-500 font-mono">
            Lluvia: {clima.lluvia} mm
          </span>
        </div>
      </Card>

      {/* TARJETA 3: Calidad del Aire (ICA) */}
      <Card className={`!p-5 transition-all duration-300 shadow-xs ${estiloIca.card}`}>
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-slate-600 uppercase tracking-wider">
            Calidad del Aire (ICA)
          </span>
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${estiloIca.icono}`}>
            <Wind className="w-5 h-5" />
          </div>
        </div>

        <div className="mt-3 flex items-baseline gap-2">
          <span className="text-3xl font-extrabold text-slate-900 tracking-tight font-mono">
            {ica.valor}
          </span>
          <span className="text-xs text-slate-400 font-medium font-mono">
            MP2.5: {ica.pm25} µg/m³
          </span>
        </div>

        <div className="mt-3 flex items-center justify-between text-xs pt-3 border-t border-slate-200/60">
          <span className={`inline-flex items-center gap-1.5 font-semibold px-2 py-0.5 rounded-md text-[11px] ${estiloIca.badge}`}>
            <span className={`w-2 h-2 rounded-full ${estiloIca.dot}`} />
            {textoIca}
          </span>
          <span className="text-[11px] text-slate-500">Estación Regional</span>
        </div>
      </Card>

    </div>
  )
}