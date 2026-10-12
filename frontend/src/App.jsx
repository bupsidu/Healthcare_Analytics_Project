
/* Prueba de que los componentes de la tarea 4.0 están funcionando correctamente */
import React from 'react'
import { Stethoscope, Activity, AlertTriangle, CheckCircle2, TrendingUp } from 'lucide-react'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'

// Datos simulados de prueba para comprobar Recharts
const datosPrueba = [
  { dia: 'Lun', pacientes: 140 },
  { dia: 'Mar', pacientes: 155 },
  { dia: 'Mié', pacientes: 210 },
  { dia: 'Jue (Pico)', pacientes: 260 },
  { dia: 'Vie', pacientes: 220 },
]

export default function App() {
  const apiUrl = import.meta.env.VITE_API_URL
  const useMock = import.meta.env.VITE_USE_MOCK

  return (
    <div className="min-h-screen p-8 bg-slate-50 text-slate-800">
      <div className="max-w-4xl mx-auto space-y-6">
        
        {/* Encabezado con Iconos de Lucide y Colores Clínicos */}
        <header className="flex items-center justify-between p-6 bg-white border border-slate-200 rounded-2xl shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-clinical-50 text-clinical-600 rounded-xl">
              <Stethoscope className="w-8 h-8" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900">HealthCare Analytics Project</h1>
              <p className="text-sm text-slate-500">Verificación de Cimientos — Tarea 4.0 (Frontend)</p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-semibold text-emerald-700 bg-emerald-50 rounded-full border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5" /> Entorno Listo
          </span>
        </header>

        {/* Verificación de Variables de Entorno */}
        <section className="p-6 bg-white border border-slate-200 rounded-2xl shadow-sm space-y-3">
          <h2 className="text-lg font-semibold text-slate-900 flex items-center gap-2">
            <Activity className="w-5 h-5 text-clinical-600" /> Estado de la Configuración (.env)
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100">
              <span className="text-slate-400 block text-xs font-medium">URL DE LA API</span>
              <code className="text-slate-700 font-mono text-xs">{apiUrl || 'No definida'}</code>
            </div>
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100">
              <span className="text-slate-400 block text-xs font-medium">MODO DE DESARROLLO</span>
              <span className="font-semibold text-clinical-700">
                {useMock === 'true' ? 'Autónomo (Mock Activo)' : 'Conectado a Backend'}
              </span>
            </div>
          </div>
        </section>

        {/* Verificación de Paleta Clínica y Alertas de Tailwind */}
        <section className="p-6 bg-white border border-slate-200 rounded-2xl shadow-sm space-y-4">
          <h2 className="text-lg font-semibold text-slate-900">Tokens de Diseño y Semáforo de Alertas</h2>
          <div className="flex flex-wrap gap-3">
            <button className="px-5 py-2.5 bg-clinical-600 hover:bg-clinical-700 text-white font-medium text-sm rounded-xl shadow-sm transition">
              Botón Primario Clínico
            </button>
            <span className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium bg-emerald-100 text-emerald-800 rounded-lg">
              Estado Normal
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium bg-amber-100 text-amber-800 rounded-lg">
              <AlertTriangle className="w-3.5 h-3.5" /> Alerta Moderada
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium bg-rose-100 text-rose-800 rounded-lg">
              Alerta Crítica
            </span>
          </div>
        </section>

        {/* Verificación del Motor de Gráficos Recharts */}
        <section className="p-6 bg-white border border-slate-200 rounded-2xl shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900 flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-clinical-600" /> Prueba de Gráfico (Recharts)
            </h2>
            <span className="text-xs text-slate-400">Curva reactiva de afluencia</span>
          </div>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={datosPrueba}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="dia" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" />
                <Tooltip />
                <Line 
                  type="monotone" 
                  dataKey="pacientes" 
                  stroke="#0d9488" 
                  strokeWidth={3} 
                  dot={{ r: 5, fill: "#0d9488" }} 
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>

      </div>
    </div>
  )
}