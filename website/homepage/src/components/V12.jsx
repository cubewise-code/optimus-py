import { Cloud, Server, Check } from 'lucide-react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import { OptimusPyIcon } from './logos/OptimusPyLogo'
import { DOCS } from '../links'

const METRIC_SERVICE_URL = 'https://tm1py.org/latest/reference/services/metricservice/'

const POINTS = [
  'One code path for both versions: every mode, the UI and Optimize DB work the same on v11 and v12.',
  'Memory is read through TM1py\'s MetricService, the same call on v11 and v12.',
  'Cube size matters even more on v12: with high availability every replica holds its own copy of your cubes, so smaller cubes mean smaller replicas and lower running costs.',
]

function Node({ children, className = '' }) {
  return (
    <div className={`rounded-xl border border-ink/10 bg-surface/80 px-4 py-3 shadow-sm ${className}`}>{children}</div>
  )
}

// OptimusPy → TM1py MetricService → v11 / v12, with the unit each server reports.
function Diagram() {
  return (
    <div className="glass-tile p-6 sm:p-8">
      <div className="flex justify-center">
        <Node className="flex items-center gap-2.5">
          <OptimusPyIcon size={26} />
          <div>
            <div className="font-semibold">OptimusPy</div>
            <div className="text-xs text-ink-3">optimize · scan · optimize-db · UI</div>
          </div>
        </Node>
      </div>

      <div className="flex justify-center py-2" aria-hidden="true">
        <svg viewBox="0 0 10 40" className="h-10 w-3"><line x1="5" y1="0" x2="5" y2="40" className="flow-line" stroke="rgb(var(--brand))" strokeWidth="2" /></svg>
      </div>

      <div className="flex justify-center">
        <a href={METRIC_SERVICE_URL} target="_blank" rel="noopener noreferrer"
           className="group rounded-xl border-2 border-brand/40 bg-brand/[0.06] px-5 py-3 text-center hover:border-brand transition-colors">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-brand">TM1py MetricService</div>
          <div className="font-mono text-sm text-ink mt-0.5">tm1.metrics.by_cube()</div>
          <div className="text-xs text-ink-3 mt-1 group-hover:text-brand transition-colors">One call, both versions ↗</div>
        </a>
      </div>

      <svg viewBox="0 0 300 50" preserveAspectRatio="none" className="block h-12 w-full" aria-hidden="true">
        <path d="M150 0 C150 25, 75 25, 75 50" className="flow-line" fill="none" stroke="rgb(var(--brand))" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        <path d="M150 0 C150 25, 225 25, 225 50" className="flow-line" fill="none" stroke="rgb(var(--amber-soft))" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>

      <div className="grid grid-cols-2 gap-3">
        <Node>
          <div className="flex items-center gap-2 mb-0.5"><Server className="h-4 w-4 text-brand" /><span className="font-semibold">TM1 v11</span></div>
          <div className="text-xs text-ink-3 mb-3">Planning Analytics Local</div>
          <div className="font-mono text-xs text-ink-2">memory in <span className="rounded bg-ink/[0.06] px-1">B</span></div>
        </Node>
        <Node className="border-2 border-amber-soft/70">
          <div className="flex items-center gap-2 mb-0.5">
            <Cloud className="h-4 w-4 text-amber" /><span className="font-semibold">TM1 v12</span>
            <span className="ml-auto rounded bg-amber-soft/25 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber">New</span>
          </div>
          <div className="text-xs text-ink-3 mb-3">PAoC and PAaaS</div>
          <div className="font-mono text-xs text-ink-2">memory in <span className="rounded bg-ink/[0.06] px-1">KB</span></div>
        </Node>
      </div>

      <div className="mt-4 flex items-center justify-center gap-2 rounded-lg bg-good/[0.08] px-3 py-2 text-sm text-good">
        <Check className="h-4 w-4" aria-hidden="true" />
        Two versions, same numbers: every comparison is like for like
      </div>
    </div>
  )
}

export default function V12() {
  const [ref, isVisible] = useScrollAnimation()

  return (
    <section ref={ref} id="v12" className="relative overflow-hidden py-24 bg-sunken border-y border-ink/5">
      <div className="gradient-orb w-[520px] h-[520px] bg-amber-soft -top-20 right-10" />
      <div className="gradient-orb w-[460px] h-[460px] bg-brand-soft bottom-0 right-1/3" />

      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
        <div className={`lg:col-span-6 animate-on-scroll ${isVisible ? 'visible' : ''}`}>
          <span className="flex items-center gap-2 text-amber text-sm font-semibold uppercase tracking-wider mb-3">
            <Cloud className="h-4 w-4" /> New in 2.0 · TM1 v12
          </span>
          <h2 className="text-3xl sm:text-4xl font-bold mb-4 leading-tight">Now on TM1 v12.<br />Cloud or <span className="whitespace-nowrap">on-premise</span>, one tool.</h2>
          <p className="text-ink-2 text-lg leading-relaxed mb-6">
            Point OptimusPy at Planning Analytics on Cloud or as a Service the same way you point it at a local server.
            It's powered by the new{' '}
            <a href={METRIC_SERVICE_URL} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline">MetricService in TM1py</a>,
            which reads cube memory the same way on v11 and v12.
          </p>
          <ul className="space-y-3 mb-7">
            {POINTS.map((p) => (
              <li key={p} className="flex gap-2.5 text-ink-2 leading-relaxed">
                <Check className="mt-1 h-4 w-4 flex-shrink-0 text-good" />{p}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-x-6 gap-y-2 font-semibold">
            <a href={DOCS.v12} className="text-brand hover:underline">How v12 support works →</a>
          </div>
        </div>

        <div className={`lg:col-span-6 animate-on-scroll stagger-2 ${isVisible ? 'visible' : ''}`}>
          <Diagram />
        </div>
      </div>
    </section>
  )
}
