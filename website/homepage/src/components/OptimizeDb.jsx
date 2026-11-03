import { useEffect, useState } from 'react'
import { Check, SkipForward, RotateCcw, Clock, PauseCircle } from 'lucide-react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion'
import { DOCS } from '../links'

// An illustrative overnight run: cubes largest first, each reordered once.
const CUBES = [
  { name: 'General Ledger', gb: 12.4, result: 'done',     after: 8.6 },
  { name: 'Sales',          gb: 8.1,  result: 'done',     after: 6.3 },
  { name: 'Workforce Plan', gb: 5.6,  result: 'done',     after: 4.1 },
  { name: 'Comments',       gb: 2.2,  result: 'skipped',  note: 'string elements' },
  { name: 'Capex',          gb: 1.4,  result: 'reverted', note: 'used more memory' },
  { name: 'FX Rates',       gb: 0.4,  result: 'done',     after: 0.3 },
]
const MAX = CUBES[0].gb

const FEATURES = [
  ['Plan first', 'A dry run builds the plan and shows what would be reordered, without touching anything.'],
  ['Stops on time', 'Give it a window, say 8 hours. It works through the plan and stops when time runs out. Resume picks up the rest.'],
  ['Safe by default', 'A cube that would use more memory is put back. Active chores can be disabled for the run and re-enabled after.'],
]

function Row({ c, state }) {
  const active = state === 'active'
  const finished = state === 'finished'
  const width = finished && c.result === 'done' ? (c.after / MAX) * 100 : (c.gb / MAX) * 100
  const Icon = c.result === 'done' ? Check : c.result === 'skipped' ? SkipForward : RotateCcw
  const colour = c.result === 'done' ? 'text-good' : c.result === 'skipped' ? 'text-ink-3' : 'text-amber'

  return (
    <div className={`grid grid-cols-[7.5rem_minmax(0,1fr)_7rem] sm:grid-cols-[9rem_minmax(0,1fr)_9rem] items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors ${active ? 'bg-brand/10' : ''}`}>
      <span className="truncate">{c.name}</span>
      <div className="h-2 rounded-full bg-ink/5">
        <div className={`h-2 rounded-full transition-[width,background-color] duration-1000 ease-out ${
          finished && c.result === 'done' ? 'bg-good' : active ? 'bg-brand animate-pulse' : 'bg-ink-3/50'
        }`} style={{ width: `${width}%` }} />
      </div>
      <span className="flex items-center justify-end gap-1.5 font-mono text-xs text-right">
        {finished ? (
          <>
            <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${colour}`} />
            <span className={`truncate ${colour}`}>
              {c.result === 'done' ? `${c.gb} → ${c.after} GB` : c.note}
            </span>
          </>
        ) : active ? <span className="text-brand">reordering…</span>
          : <span className="text-ink-3">{c.gb} GB</span>}
      </span>
    </div>
  )
}

export default function OptimizeDb() {
  const [ref, isVisible] = useScrollAnimation()
  const reduced = usePrefersReducedMotion()
  const [cursor, setCursor] = useState(-1)

  useEffect(() => {
    if (!isVisible) return
    if (reduced) { setCursor(CUBES.length); return }
    let alive = true
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
    ;(async () => {
      while (alive) {
        setCursor(-1)
        await sleep(1200)
        for (let i = 0; i <= CUBES.length && alive; i++) {
          setCursor(i)
          await sleep(i === CUBES.length ? 5000 : 1300)
        }
      }
    })()
    return () => { alive = false }
  }, [isVisible, reduced])

  const finished = Math.max(0, Math.min(cursor, CUBES.length))
  const hours = ((finished / CUBES.length) * 6.4).toFixed(1)
  const done = cursor >= CUBES.length
  const before = CUBES.reduce((a, c) => a + c.gb, 0)
  const after = CUBES.reduce((a, c) => a + (c.result === 'done' ? c.after : c.gb), 0)

  return (
    <section ref={ref} id="optimize-db" className="relative overflow-hidden py-24 bg-sunken border-y border-ink/5">
      <div className="gradient-orb w-[520px] h-[520px] bg-good top-1/4 right-0" />
      <div className="gradient-orb w-[420px] h-[420px] bg-brand-soft bottom-0 right-1/3" />
      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
        <div className={`lg:col-span-5 animate-on-scroll ${isVisible ? 'visible' : ''}`}>
          <span className="block text-good text-sm font-semibold uppercase tracking-wider mb-3">New in 2.0 · Optimize DB</span>
          <h2 className="text-3xl sm:text-4xl font-bold mb-4 leading-tight">Shrink the whole model overnight.</h2>
          <p className="text-ink-2 text-lg leading-relaxed mb-6">
            Optimize DB reorders every cube on an instance by leaf-element count, one cube at a time, within a
            time limit. It benchmarks nothing, so it's quick: run it first, restart TM1, then use Optimize on the
            cubes that still matter.
          </p>
          <dl className="space-y-4 mb-7">
            {FEATURES.map(([t, b]) => (
              <div key={t}>
                <dt className="font-semibold">{t}</dt>
                <dd className="text-ink-2 text-sm leading-relaxed">{b}</dd>
              </div>
            ))}
          </dl>
          <a href={DOCS.optimizeDbRun} className="text-brand hover:underline font-semibold">Optimize DB step by step →</a>
        </div>

        <div className={`lg:col-span-7 animate-on-scroll stagger-2 ${isVisible ? 'visible' : ''}`}>
          <div className="glass-tile overflow-hidden">
            <div className="flex items-center justify-between gap-3 border-b border-ink/10 px-4 py-2.5 text-xs">
              <span className="font-mono text-ink-2 truncate">tm1srv01 · Optimize DB · largest first</span>
              <span className="flex-shrink-0 text-ink-3">Illustrative run</span>
            </div>

            <div className="px-4 pt-4">
              <div className="flex items-center justify-between text-xs text-ink-3 mb-1.5">
                <span className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> Time limit 8 h</span>
                <span className="font-mono">{hours} h used</span>
              </div>
              <div className="h-1.5 rounded-full bg-ink/5 mb-4">
                <div className="h-1.5 rounded-full bg-navy transition-[width] duration-1000 ease-out"
                     style={{ width: `${(Number(hours) / 8) * 100}%` }} />
              </div>
            </div>

            <div className="px-2">
              {CUBES.map((c, i) => (
                <Row key={c.name} c={c} state={i < cursor ? 'finished' : i === cursor ? 'active' : 'waiting'} />
              ))}
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-ink/10 px-4 py-3 text-xs">
              <span className="flex items-center gap-1.5 text-ink-2">
                <PauseCircle className="w-3.5 h-3.5 text-amber" />
                {done ? '3 chores re-enabled' : cursor >= 0 ? '3 active chores disabled for the run' : 'Plan ready · 6 cubes'}
              </span>
              <span className={`font-mono transition-colors ${done ? 'text-good' : 'text-ink-3'}`}>
                {done ? `${before.toFixed(1)} → ${after.toFixed(1)} GB after restart` : `${before.toFixed(1)} GB in plan`}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
