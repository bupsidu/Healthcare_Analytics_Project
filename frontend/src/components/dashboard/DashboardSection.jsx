// frontend/src/components/dashboard/DashboardSection.jsx
import React, { useState, useEffect } from 'react'
import KpiCards from './KpiCards'
import Card from '../ui/Card'
import Button from '../ui/Button'
import { dashboardService } from '../../services/dashboardService'
import { RefreshCw, AlertCircle } from 'lucide-react'

export default function DashboardSection({ establecimiento }) {
  const [datos, setDatos] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')

  const cargarDatos = async () => {
    if (!establecimiento?.id) return
    setCargando(true)
    setError('')
    try {
      const res = await dashboardService.obtenerDatosDashboard(establecimiento)
      setDatos(res)
    } catch (err) {
      setError(err.message || 'No fue posible cargar las métricas en vivo.')
    } finally {
      setCargando(false)
    }
  }

  useEffect(() => {
    cargarDatos()
  }, [establecimiento?.id])

  if (cargando) {
    return (
      <Card className="!p-8 text-center flex flex-col items-center justify-center gap-2">
        <div className="w-6 h-6 border-2 border-clinical-600 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs font-semibold text-slate-600">
          Cargando indicadores de demanda y clima regional...
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
            <p className="font-semibold text-rose-900">Aviso del panel de control:</p>
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
    <div className="space-y-6">
      <KpiCards data={datos} />
    </div>
  )
}