import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { MonitorSmartphone, Check, LayoutList, SlidersHorizontal, ArrowLeftRight, Settings } from 'lucide-react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion'
import { DOCS } from '../links'

const img = (name) => `${import.meta.env.BASE_URL}img/${name}.jpg`

const TOUR = [
  { key: 'optimize', label: 'Optimize', icon: LayoutList, src: img('ui-optimize'),
    caption: 'Cubes listed by memory. Pick one to see its dimensions, leaf counts and a suggested order.' },
  { key: 'configure', label: 'Configure', icon: SlidersHorizontal, src: img('ui-configure'),
    caption: 'Choose the mode, views and dimensions. The JSON config builds itself as you go.' },
  { key: 'sync', label: 'Sync Order', icon: ArrowLeftRight, src: img('ui-sync'),
    caption: 'Copy optimized orders from one instance to another, or export them for later.' },
  { key: 'settings', label: 'Settings', icon: Settings, src: img('ui-settings'),
    caption: 'Add and test TM1 instances. Light and dark themes.' },
]

const TOUR_MS = 5500

function UiTour() {
  const reduced = usePrefersReducedMotion()
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  const tabs = useRef([])
  const [pill, setPill] = useState({ left: 0, width: 0 })

  // Slide the white highlight under the selected tab.
  useLayoutEffect(() => {
    const place = () => {
      const el = tabs.current[active]
      if (el) setPill({ left: el.offsetLeft, width: el.offsetWidth })
    }
    place()
    window.addEventListener('resize', place)
    return () => window.removeEventListener('resize', place)
  }, [active])

  useEffect(() => {
    if (reduced || paused) return
    const t = setTimeout(() => setActive((a) => (a + 1) % TOUR.length), TOUR_MS)
    return () => clearTimeout(t)
  }, [active, paused, reduced])

  return (
    <div onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div className="mb-4 max-w-full overflow-x-auto">
        <div role="tablist" aria-label="Web UI pages"
             className="relative inline-flex rounded-full border border-ink/10 bg-ink/[0.05] p-1">
          <span aria-hidden="true"
                className="absolute top-1 bottom-1 rounded-full bg-surface shadow-sm ring-1 ring-ink/5 transition-[left,width] duration-300 ease-[cubic-bezier(.4,0,.2,1)] overflow-hidden"
                style={{ left: pill.left, width: pill.width }}>
            {!paused && !reduced && (
              <span key={active} className="tour-progress absolute left-3 right-3 bottom-0 h-[2px] rounded-full bg-brand/70"
                    style={{ animationDuration: `${TOUR_MS}ms` }} />
            )}
          </span>
          {TOUR.map((t, i) => {
            const on = i === active
            const Icon = t.icon
            return (
              <button key={t.key} ref={(el) => { tabs.current[i] = el }} role="tab" aria-selected={on}
                      onClick={() => { setActive(i); setPaused(true) }}
                      className={`relative z-10 inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ${
                        on ? 'text-brand' : 'text-ink-3 hover:text-ink'
                      }`}>
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                {t.label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="rounded-xl border border-ink/10 bg-ink/90 p-1.5 shadow-xl shadow-ink/10">
        <div className="flex items-center gap-1.5 px-2 pb-1.5 pt-0.5" aria-hidden="true">
          <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
          <span className="ml-3 font-mono text-[11px] text-white/50">127.0.0.1:8765</span>
        </div>
        <div className="relative aspect-[16/10] overflow-hidden rounded-lg">
          {TOUR.map((t, i) => (
            <img key={t.key} src={t.src} alt={`OptimusPy ${t.label} page`} width="1600" height="1000"
                 loading={i === 0 ? 'eager' : 'lazy'}
                 className={`absolute inset-0 h-full w-full object-cover object-left-top transition-opacity duration-700 ${
                   i === active ? 'opacity-100' : 'opacity-0'
                 }`} />
          ))}
        </div>
      </div>
      <p className="mt-3 min-h-[3rem] text-sm text-ink-2" aria-live="polite">{TOUR[active].caption}</p>
    </div>
  )
}

const POINTS = [
  'Double-click the executable and it opens in your browser. No Python, nothing to install.',
  'Runs on your machine and talks only to your TM1 servers.',
  'Follow a run live, with its log and a Stop button, then open the report from the cube\'s Results tab.',
  'Optimize DB has its own page: build the plan, set the time limit, and start it.',
]

export default function WebUI() {
  const [ref, isVisible] = useScrollAnimation()

  return (
    <section ref={ref} id="web-ui" className="relative overflow-hidden py-24 bg-canvas">
      <div className="gradient-orb w-[560px] h-[560px] bg-brand-soft top-10 -left-40" />

      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
        <div className={`lg:col-span-7 lg:order-1 order-2 glass-tile p-5 sm:p-6 animate-on-scroll stagger-2 ${isVisible ? 'visible' : ''}`}>
          <UiTour />
        </div>

        <div className={`lg:col-span-5 lg:order-2 order-1 animate-on-scroll ${isVisible ? 'visible' : ''}`}>
          <span className="flex items-center gap-2 text-brand text-sm font-semibold uppercase tracking-wider mb-3">
            <MonitorSmartphone className="h-4 w-4" /> New in 2.0 · Web UI
          </span>
          <h2 className="text-3xl sm:text-4xl font-bold mb-4 leading-tight">From scan to sync, in your browser.</h2>
          <p className="text-ink-2 text-lg leading-relaxed mb-6">
            The whole workflow, with a screen for each step: pick a cube, configure the run, watch it,
            read the result, and copy the order to another instance.
          </p>
          <ul className="space-y-3 mb-7">
            {POINTS.map((p) => (
              <li key={p} className="flex gap-2.5 text-ink-2 leading-relaxed">
                <Check className="mt-1 h-4 w-4 flex-shrink-0 text-good" />{p}
              </li>
            ))}
          </ul>
          <a href={DOCS.ui} className="font-semibold text-brand hover:underline">Tour the UI →</a>
        </div>
      </div>
    </section>
  )
}
