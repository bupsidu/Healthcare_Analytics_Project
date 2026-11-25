// frontend/src/components/triage/TriageSection.jsx
import React, { useState, useEffect } from 'react'
import { Stethoscope, User, PlusCircle, CheckCircle2, AlertCircle, Inbox, RefreshCw } from 'lucide-react'
import Card from '../ui/Card'
import Button from '../ui/Button'
import SelectField from '../ui/SelectField'
import { intakeService } from '../../services/intakeService'

const RANGOS_ETARIOS = [
  { value: 'Menores de 1', label: '< 1 año (Lactante menor)' },
  { value: '1-4', label: '1 a 4 años' },
  { value: '5-14', label: '5 a 14 años' },
  { value: '15-64', label: '15 a 64 años' },
  { value: '65+', label: '65 años y más' },
]

const CAUSAS_CONSULTA = [
  'IRA Alta (Infección Respiratoria Aguda)',
  'Bronquitis / Bronquiolitis aguda',
  'Neumonía / Sospecha de Neumonía',
  'Crisis Asmática / SBO',
  'Influenza / Síndrome Gripal',
  'Otras patologías respiratorias',
]

function formatearFechaHora(fechaIso, createdIso) {
  if (createdIso) {
    const f = new Date(createdIso)
    if (!isNaN(f.getTime())) {
      const horaStr = f.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })
      const fechaStr = f.toLocaleDateString('es-CL', { day: '2-digit', month: 'short' }).replace('.', '')
      return `${fechaStr}, ${horaStr}`
    }
  }
  if (fechaIso) {
    const partes = String(fechaIso).split('-')
    if (partes.length === 3) {
      const f = new Date(parseInt(partes[0], 10), parseInt(partes[1], 10) - 1, parseInt(partes[2], 10))
      const fechaStr = f.toLocaleDateString('es-CL', { day: '2-digit', month: 'short' }).replace('.', '')
      return `${fechaStr}`
    }
  }
  return 'Hoy'
}

export default function TriageSection({ establecimiento }) {
  const [grupoEtario, setGrupoEtario] = useState('')
  const [causaConsulta, setCausaConsulta] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [errores, setErrores] = useState({})
  const [mensajeExito, setMensajeExito] = useState(false)
  const [errorServidor, setErrorServidor] = useState('')

  const [registros, setRegistros] = useState([])
  const [cargandoHistorial, setCargandoHistorial] = useState(true)

  const recargarHistorial = async () => {
    if (!establecimiento?.id) {
      setCargandoHistorial(false)
      return
    }
    setCargandoHistorial(true)
    try {
      const datos = await intakeService.getHistorialIngresos(establecimiento.id)
      const formateados = (datos || []).map((item) => {
        const fechaStr = formatearFechaHora(item.fecha, item.created_at)
        const etiquetaGrupo = RANGOS_ETARIOS.find((r) => r.value === item.grupo_etario)?.label || item.grupo_etario
        const causaGuardada = sessionStorage.getItem(`ingreso_causa_${item.id}`) || 'Patología Respiratoria'

        return {
          id: String(item.id).padStart(2, '0'),
          grupoEtario: etiquetaGrupo,
          causa: causaGuardada,
          hora: fechaStr,
        }
      })
      setRegistros(formateados)
    } catch (err) {
      console.error('Error al sincronizar historial:', err)
    } finally {
      setCargandoHistorial(false)
    }
  }

  useEffect(() => {
    recargarHistorial()
  }, [establecimiento?.id])

  const validar = () => {
    const err = {}
    if (!grupoEtario) err.grupoEtario = 'Seleccione el rango etario del paciente.'
    if (!causaConsulta) err.causaConsulta = 'Seleccione la causa respiratoria de la consulta.'
    setErrores(err)
    return Object.keys(err).length === 0
  }

  const handleRegistrar = async (e) => {
    e.preventDefault()
    setErrorServidor('')
    setMensajeExito(false)

    if (!validar()) return

    if (!establecimiento?.id) {
      setErrorServidor('No se puede registrar la atención: la cuenta no tiene un centro de salud asignado. Contacte a la administración.')
      return
    }

    setGuardando(true)

    try {
      const nuevo = await intakeService.registrarIngreso({
        establecimientoId: establecimiento.id,
        grupoEtario: grupoEtario,
        casos: 1,
      })

      if (nuevo?.id) {
        sessionStorage.setItem(`ingreso_causa_${nuevo.id}`, causaConsulta)
      }

      await recargarHistorial()
      setMensajeExito(true)

      setGrupoEtario('')
      setCausaConsulta('')
      setTimeout(() => setMensajeExito(false), 3500)
    } catch (err) {
      const mensaje = err.message?.includes('fetch')
        ? 'No se pudo conectar con el servidor central. Verifique su conexión de red.'
        : err.message || 'No fue posible guardar la atención. Por favor intente nuevamente.'
      setErrorServidor(mensaje)
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="space-y-4 font-sans">
      <div>
        <h2 className="text-xl font-bold text-slate-900 tracking-tight">Registro de Consulta</h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Ingresa los datos de la consulta para alimentar el modelo predictivo de demanda
        </p>
      </div>

            {/* Contenedor Grid con items-stretch para igualar la altura de ambas cards */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        
        {/* Formulario (Columna Izquierda) */}
        <div className="lg:col-span-5 flex flex-col">
          <Card className="!p-6 flex-1 flex flex-col justify-between">
            
            <div>
              <div className="flex items-center gap-3 pb-5 mb-5 border-b border-slate-100">
                <div className="w-10 h-10 rounded-xl bg-clinical-50 text-clinical-600 flex items-center justify-center border border-clinical-100">
                  <Stethoscope className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Nueva consulta</h3>
                  <p className="text-xs text-slate-500">
                    Enfermedades respiratorias · {establecimiento?.tipo || 'Centro'}
                  </p>
                </div>
              </div>

              {errorServidor && (
                <div className="mb-4 p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-800 flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                  <span>{errorServidor}</span>
                </div>
              )}

              {mensajeExito && (
                <div className="mb-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2 animate-in fade-in">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>Atención clínica registrada exitosamente.</span>
                </div>
              )}

              <form onSubmit={handleRegistrar} noValidate className="space-y-4">
                <SelectField
                  label="Rango Etario"
                  id="grupoEtario"
                  required
                  placeholder="Selecciona un rango etario"
                  options={RANGOS_ETARIOS}
                  value={grupoEtario}
                  onChange={(e) => {
                    setGrupoEtario(e.target.value)
                    if (errores.grupoEtario) setErrores({ ...errores, grupoEtario: '' })
                  }}
                  error={errores.grupoEtario}
                />

                <SelectField
                  label="Causa de Consulta"
                  id="causaConsulta"
                  required
                  placeholder="Selecciona una causa de consulta"
                  options={CAUSAS_CONSULTA}
                  value={causaConsulta}
                  onChange={(e) => {
                    setCausaConsulta(e.target.value)
                    if (errores.causaConsulta) setErrores({ ...errores, causaConsulta: '' })
                  }}
                  error={errores.causaConsulta}
                />

                <div className="pt-2">
                  <Button type="submit" variant="primary" isLoading={guardando} icon={PlusCircle}>
                    Registrar consulta
                  </Button>
                  <p className="text-[11px] text-slate-400 text-center mt-2">
                    Los campos marcados con <span className="text-rose-500">*</span> son obligatorios
                  </p>
                </div>
              </form>
            </div>

          </Card>
        </div>

        {/* Historial en Tiempo Real con Scroll Interno (Columna Derecha) */}
        <div className="lg:col-span-7 flex flex-col">
          <Card className="!p-6 flex-1 flex flex-col min-h-[440px]">
            
            {/* Cabecera fija de la tarjeta */}
            <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-100 shrink-0">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Atenciones de la jornada</h3>
                <p className="text-xs text-slate-500">
                  Historial de pacientes ingresados en este centro
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={recargarHistorial}
                  disabled={cargandoHistorial}
                  title="Actualizar lista de atenciones"
                  className="p-1 text-slate-400 hover:text-clinical-700 transition rounded-lg hover:bg-slate-100 disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${cargandoHistorial ? 'animate-spin text-clinical-600' : ''}`} />
                </button>
                <span className="px-3 py-1 rounded-full bg-clinical-50 text-clinical-700 text-xs font-semibold border border-clinical-200/60 font-mono">
                  {registros.length} registros
                </span>
              </div>
            </div>

            {/* Contenedor del contenido */}
            {cargandoHistorial && registros.length === 0 ? (
              <div className="py-10 text-center text-slate-400 text-xs flex-1 flex flex-col items-center justify-center gap-2">
                <div className="w-5 h-5 border-2 border-clinical-600 border-t-transparent rounded-full animate-spin" />
                <span>Cargando atenciones registradas...</span>
              </div>
            ) : registros.length === 0 ? (
              <div className="py-10 text-center text-slate-400 text-xs flex-1 flex flex-col items-center justify-center gap-2">
                <Inbox className="w-8 h-8 text-slate-300" />
                <p className="font-medium text-slate-600">No hay atenciones registradas para este centro</p>
                <p className="text-[11px] text-slate-400">Ingresa la primera consulta con el formulario de la izquierda.</p>
              </div>
            ) : (
              /* Contenedor con scroll vertical limitado y cabecera fija */
              <div className="overflow-x-auto overflow-y-auto flex-1 max-h-[340px] pr-1">
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 bg-white z-10">
                    <tr className="text-slate-400 font-semibold border-b border-slate-100">
                      <th className="pb-3 pl-2 w-10 bg-white">#</th>
                      <th className="pb-3 bg-white">RANGO ETARIO</th>
                      <th className="pb-3 bg-white">DIAGNÓSTICO</th>
                      <th className="pb-3 pr-2 text-right bg-white">REGISTRADO</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100/80">
                    {registros.map((reg) => (
                      <tr key={reg.id} className="hover:bg-slate-50/60 transition-colors">
                        <td className="py-3 pl-2 font-mono text-slate-400 font-medium">
                          {reg.id}
                        </td>
                        <td className="py-3">
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 text-slate-700 font-medium text-[11px]">
                            <User className="w-3 h-3 text-slate-400" />
                            <span>{reg.grupoEtario}</span>
                          </span>
                        </td>
                        <td className="py-3">
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-clinical-50 text-clinical-700 font-medium text-[11px] border border-clinical-100">
                            <span className="w-1.5 h-1.5 rounded-full bg-clinical-500" />
                            <span>{reg.causa}</span>
                          </span>
                        </td>
                        <td className="py-3 pr-2 text-right text-slate-400 font-mono text-[11px]">
                          {reg.hora}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

          </Card>
        </div>

      </div>
    </div>
  )
}