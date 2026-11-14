// frontend/src/components/auth/LoginView.jsx
import React, { useState } from 'react'
import { Hospital, Mail, Lock, HelpCircle, AlertCircle } from 'lucide-react'
import Card from '../ui/Card'
import Button from '../ui/Button'
import InputField from '../ui/InputField'
import { authClient } from '../../services/authClient'

export default function LoginView({ onLoginSuccess }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [recordarme, setRecordarme] = useState(false)
  const [cargando, setCargando] = useState(false)

  // Estados de errores para validación visual propia
  const [errores, setErrores] = useState({})
  const [errorServidor, setErrorServidor] = useState('')

  const validarCampos = () => {
    const nuevosErrores = {}

    if (!email.trim()) {
      nuevosErrores.email = 'Por favor, ingrese su correo institucional.'
    } else if (!/\S+@\S+\.\S+/.test(email)) {
      nuevosErrores.email = 'El formato de correo no es válido (ej: medico@hospital.cl).'
    }

    if (!password) {
      nuevosErrores.password = 'Por favor, ingrese su contraseña.'
    } else if (password.length < 4) {
      nuevosErrores.password = 'La contraseña debe tener al menos 4 caracteres.'
    }

    setErrores(nuevosErrores)
    return Object.keys(nuevosErrores).length === 0
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrorServidor('')

    // 1. Si los campos están vacíos o inválidos, React muestra los mensajes y se detiene
    if (!validarCampos()) {
      return
    }

    setCargando(true)

    try {
      const sesion = await authClient.login(email, password)
      if (onLoginSuccess) {
        onLoginSuccess(sesion.user)
      }
    } catch (err) {
      setErrorServidor(err.message || 'Error al iniciar sesión.')
    } finally {
      setCargando(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-between py-6 px-4 sm:px-8 font-sans text-slate-800">
      
      {/* 1. Encabezado Superior (Logo a la izquierda y Centro de Ayuda a la derecha) */}
      <header className="w-full flex items-center justify-between">
        <div className="flex items-center gap-2.5 bg-white border border-slate-200/80 px-4 py-2 rounded-xl shadow-xs">
          <div className="w-8 h-8 rounded-lg bg-clinical-600 flex items-center justify-center text-white">
            <Hospital className="w-4 h-4" />
          </div>
          <div className="leading-tight">
            <span className="block text-xs font-bold tracking-tight text-slate-900">HealthCare</span>
            <span className="block text-[10px] text-clinical-700 font-medium -mt-0.5">Analytics Project</span>
          </div>
        </div>

        <button
          type="button"
          onClick={() => alert('Mesa de ayuda: Contacte al administrador de turno del SAPU.')}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 transition-colors cursor-pointer"
        >
          <HelpCircle className="w-4 h-4 text-slate-400" />
          <span>Centro de Ayuda</span>
        </button>
      </header>

      {/* 2. Tarjeta Central Flotante (Mockup Slide 14) */}
      <main className="w-full max-w-md mx-auto my-6">
        <Card>
          
          {/* Ícono de Hospital en Círculo Verde Suave */}
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 rounded-2xl bg-clinical-50 flex items-center justify-center text-clinical-600 border border-clinical-100">
              <Hospital className="w-8 h-8" strokeWidth={1.8} />
            </div>
          </div>

          {/* Títulos */}
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Ingreso a HealthCare</h1>
            <p className="text-xs sm:text-sm text-slate-500 mt-1">Acceda de forma segura a su entorno clínico</p>
          </div>

          {/* Banner de Error si fallan las credenciales contra PostgreSQL */}
          {errorServidor && (
            <div className="mb-5 p-3.5 rounded-xl bg-rose-50 border border-rose-200 flex items-start gap-2.5 text-xs text-rose-800 animate-in fade-in">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              <span>{errorServidor}</span>
            </div>
          )}

          {/* Formulario con noValidate para apagar popups del navegador */}
          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            
            <InputField
              label="Correo electrónico"
              id="email"
              type="email"
              icon={Mail}
              placeholder="ejemplo@sapuprovidencia.cl"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value)
                if (errores.email) setErrores((prev) => ({ ...prev, email: '' }))
              }}
              error={errores.email}
            />

            <InputField
              label="Contraseña"
              id="password"
              isPassword={true}
              icon={Lock}
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value)
                if (errores.password) setErrores((prev) => ({ ...prev, password: '' }))
              }}
              error={errores.password}
            />

            {/* Opciones */}
            <div className="flex items-center justify-between pt-1 pb-2">
              <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-600">
                <input
                  type="checkbox"
                  checked={recordarme}
                  onChange={(e) => setRecordarme(e.target.checked)}
                  className="w-3.5 h-3.5 rounded text-clinical-600 focus:ring-clinical-500 border-slate-300 cursor-pointer"
                />
                <span>Recordarme</span>
              </label>
              <button
                type="button"
                onClick={() => alert('Por seguridad clínica, solicite el restablecimiento de credenciales con la jefatura médica.')}
                className="text-xs font-medium text-clinical-700 hover:text-clinical-800 transition-colors cursor-pointer"
              >
                ¿Olvidé mi contraseña?
              </button>
            </div>

            {/* Botón Modular con Spinner */}
            <Button type="submit" variant="primary" isLoading={cargando}>
              Iniciar Sesión
            </Button>
          </form>

          {/* Sello de Seguridad */}
          <div className="mt-8 pt-6 border-t border-slate-100 flex items-center justify-center gap-2 text-center">
            <Lock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <p className="text-[11px] text-slate-400 font-normal">
              Conexión encriptada con cifrado de grado médico SSL de 256 bits.
            </p>
          </div>

        </Card>
      </main>

      {/* 3. Pie de Página */}
      <footer className="w-full flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-400 gap-2 border-t border-slate-200/60 pt-4">
        <p>© 2026 HealthCare Analytics Project. Todos los derechos reservados.</p>
        <div className="flex items-center gap-4">
          <span className="hover:text-slate-600 cursor-pointer">Privacidad</span>
          <span className="hover:text-slate-600 cursor-pointer">Términos</span>
        </div>
      </footer>

    </div>
  )
}