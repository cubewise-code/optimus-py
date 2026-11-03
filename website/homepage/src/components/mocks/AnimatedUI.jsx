import { useEffect, useState } from 'react'
import { Database, Play, Search, Layers, BarChart3, Settings, Activity, ChevronRight } from 'lucide-react'

const CUBES = [
  { name: 'Sales',   dims: 12, ram: '4.2 GB', pct: 88, optimized: false },
  { name: 'PnL',     dims: 10, ram: '2.1 GB', pct: 62, optimized: false },
  { name: 'Balance', dims:  8, ram: '1.0 GB', pct: 38, optimized: false },
  { name: 'CashFlow',dims:  9, ram: '0.9 GB', pct: 32, optimized: true  },
  { name: 'HR',      dims:  6, ram: '0.4 GB', pct: 18, optimized: true  },
]

export default function AnimatedUI() {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setIsVisible(true), 200)
    return () => clearTimeout(t)
  }, [])

  return (
    <div
      className="relative w-full max-w-5xl mx-auto"
      style={{ perspective: '2000px', perspectiveOrigin: '50% 30%' }}
      role="img"
      aria-label="Mockup of the OptimusPy web UI Optimize page, showing a sidebar with five sections and a list of candidate cubes ranked by RAM."
    >
      {/* Browser chrome */}
      <div
        className="bg-slate-900 border border-white/10 rounded-xl shadow-2xl overflow-hidden transition-all duration-1000"
        style={{
          transform: isVisible
            ? 'rotateX(2deg) rotateY(-8deg) translateZ(0)'
            : 'rotateX(8deg) rotateY(-15deg) translateZ(-100px)',
          opacity: isVisible ? 1 : 0,
        }}
      >
        {/* Title bar */}
        <div className="flex items-center px-4 py-2.5 bg-slate-950 border-b border-white/10">
          <div className="flex items-center space-x-2">
            <div className="w-3 h-3 rounded-full bg-red-500/70" />
            <div className="w-3 h-3 rounded-full bg-amber-500/70" />
            <div className="w-3 h-3 rounded-full bg-green-500/70" />
          </div>
          <div className="mx-auto bg-slate-800 px-4 py-1 rounded text-xs text-slate-400 font-mono">
            127.0.0.1:8765 — OptimusPy
          </div>
        </div>

        {/* Body: sidebar + main */}
        <div className="flex" style={{ minHeight: '420px' }}>
          {/* Sidebar */}
          <aside className="w-48 bg-slate-950/60 border-r border-white/5 p-4 flex flex-col">
            <div className="flex items-center space-x-2 px-3 py-2 mb-4 bg-slate-800/50 rounded-md">
              <Database className="w-4 h-4 text-accent-cyan" />
              <span className="text-xs text-text-secondary truncate">tm1srv01</span>
            </div>
            <nav className="space-y-1 text-sm flex-1">
              <NavItem icon={Layers}     label="Optimize"    active />
              <NavItem icon={ChevronRight} label="Sync Order" />
              <NavItem icon={BarChart3}  label="Results" />
              <NavItem icon={Activity}   label="Jobs" />
              <NavItem icon={Settings}   label="Settings" />
            </nav>
            <div className="mt-auto p-3 bg-bg-tertiary/50 rounded-md border border-white/5">
              <div className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Activity</div>
              <div className="flex items-center space-x-2">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-[11px] text-text-secondary">Idle</span>
              </div>
            </div>
          </aside>

          {/* Main column */}
          <section className="flex-1 p-6">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="text-text-primary font-semibold text-base">Candidate cubes</h3>
                <p className="text-text-muted text-xs mt-0.5">Sorted by RAM, top 60% of model</p>
              </div>
              <div className="flex items-center space-x-2">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
                  <input
                    readOnly
                    value="Sales"
                    className="bg-slate-800 border border-white/10 rounded-md pl-8 pr-3 py-1.5 text-xs text-text-secondary w-40"
                  />
                </div>
                <button className="bg-gradient-to-r from-accent-cyan to-accent-violet text-bg-primary text-xs font-semibold px-4 py-1.5 rounded-md inline-flex items-center space-x-1.5">
                  <Play className="w-3 h-3" />
                  <span>Optimize</span>
                </button>
              </div>
            </div>

            <div className="space-y-2">
              {CUBES.map((c, i) => (
                <CubeRow key={c.name} cube={c} delay={300 + i * 80} isVisible={isVisible} />
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

function NavItem({ icon: Icon, label, active }) {
  return (
    <div className={`flex items-center space-x-2 px-3 py-1.5 rounded-md ${active ? 'bg-accent-cyan/10 text-accent-cyan' : 'text-text-secondary hover:text-text-primary'}`}>
      <Icon className="w-4 h-4" />
      <span>{label}</span>
    </div>
  )
}

function CubeRow({ cube, delay, isVisible }) {
  return (
    <div
      className="bg-slate-800/40 border border-white/5 rounded-md px-4 py-3 transition-all duration-700"
      style={{
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? 'translateY(0)' : 'translateY(8px)',
        transitionDelay: `${delay}ms`,
      }}
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center space-x-2">
          <span className="text-text-primary text-sm font-medium">{cube.name}</span>
          {cube.optimized && (
            <span className="text-[10px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded">optimized</span>
          )}
        </div>
        <div className="text-text-muted text-xs">
          {cube.dims} dims · {cube.ram}
        </div>
      </div>
      <div className="h-1.5 bg-slate-900/60 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${cube.optimized ? 'bg-emerald-500/70' : 'bg-gradient-to-r from-accent-cyan to-accent-violet'}`}
          style={{ width: isVisible ? `${cube.pct}%` : '0%', transition: `width 1.2s ease-out ${delay + 200}ms` }}
        />
      </div>
    </div>
  )
}
