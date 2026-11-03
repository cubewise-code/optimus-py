import React from 'react'
import ReactDOM from 'react-dom/client'
import './index.css'
import AnimatedUI from './components/mocks/AnimatedUI'

function MocksPage() {
  return (
    <div className="bg-bg-primary p-12 space-y-16">
      <section data-mock="optimize-page" className="bg-bg-primary p-8">
        <AnimatedUI />
      </section>
      <section data-mock="sidebar-overview" className="bg-bg-primary p-4 max-w-md">
        <AnimatedUI />
      </section>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('mocks-root')).render(<MocksPage />)
