import React, { useState } from 'react'
import './App.css'
import { LoginSimple } from './components/LoginSimple.jsx'

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  return (
    <main className="app-shell">
      <section className="app-card">
        <header className="app-header">
          <p className="app-kicker">SISTEMA HOSPITALARIO</p>
          <h1>Sistema Hospitalario de Alerta Temprana</h1>
        </header>

        {isAuthenticated ? (
          <section className="home-panel" aria-live="polite">
            <p className="success-message">Sistema hospitalario funcionando</p>
          </section>
        ) : (
          <LoginSimple onLogin={() => setIsAuthenticated(true)} />
        )}
      </section>
    </main>
  )
}

export default App
