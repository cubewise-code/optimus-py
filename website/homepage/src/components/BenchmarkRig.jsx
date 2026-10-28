import { useEffect, useRef, useState } from 'react'
import { Lock, Check, X } from 'lucide-react'
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion'

// An illustrative greedy run on a sales cube. Memory comes back with each
// reorder; views and TI processes are timed over 5 executions and the median
// counts. Orders that don't beat the best so far are put back.

const DIMS = {
  customer: { name: 'Customer',      leaves: '21,000' },
  product:  { name: 'Product',       leaves: '8,400' },
  region:   { name: 'Region',        leaves: '140' },
  period:   { name: 'Period',        leaves: '17' },
  year:     { name: 'Year',          leaves: '12' },
  currency: { name: 'Currency',      leaves: '6' },
  version:  { name: 'Version',       leaves: '4' },
  measure:  { name: 'Sales Measure', leaves: '14', locked: true },
}

const ORIGINAL = {
  order: ['customer', 'product', 'region', 'period', 'year', 'currency', 'version', 'measure'],
  mem: 4.8, query: 1.84, ti: 42.0,
}

const STEPS = [
  { move: 'version', order: ['version', 'customer', 'product', 'region', 'period', 'year', 'currency', 'measure'], mem: 4.31, query: 1.62, ti: 39.1 },
  { move: 'currency', order: ['version', 'currency', 'customer', 'product', 'region', 'period', 'year', 'measure'], mem: 3.88, query: 1.41, ti: 36.0 },
  { move: 'currency', order: ['currency', 'version', 'customer', 'product', 'region', 'period', 'year', 'measure'], mem: 3.95, query: 1.52, ti: 37.2 },
  { move: 'year', order: ['version', 'currency', 'year', 'customer', 'product', 'region', 'period', 'measure'], mem: 3.41, query: 1.10, ti: 32.4 },
  { move: 'period', order: ['version', 'currency', 'year', 'period', 'customer', 'product', 'region', 'measure'], mem: 3.12, query: 0.86, ti: 30.1 },
  { move: 'region', order: ['version', 'currency', 'year', 'period', 'region', 'customer', 'product', 'measure'], mem: 2.96, query: 0.71, ti: 28.3 },
  { move: 'product', order: ['version', 'currency', 'year', 'period', 'region', 'product', 'customer', 'measure'], mem: 2.93, query: 0.61, ti: 27.4 },
  { move: 'period', order: ['version', 'currency', 'period', 'year', 'region', 'product', 'customer', 'measure'], mem: 3.01, query: 0.68, ti: 28.0 },
]

const RUN_NOISE = [0.07, -0.03, 0.12, 0.0, -0.05]   // the median of these is 0
const ROW = 34
const CELLS = 80

const isBetter = (a, b) => a.mem <= b.mem && a.query <= b.query

function finalState() {
  let best = ORIGINAL
  const history = STEPS.map((s) => {
    const kept = isBetter(s, best)
    if (kept) best = s
    return kept
  })
  return {
    order: best.order, moved: [], mem: best.mem, query: best.query, ti: best.ti,
    runs: RUN_NOISE.map((n) => best.query * (1 + n)), run: 5,
    phase: 'done', step: STEPS.length, verdict: null, history, best,
  }
}

const INITIAL = {
  order: ORIGINAL.order, moved: [], mem: ORIGINAL.mem, query: ORIGINAL.query, ti: ORIGINAL.ti,
  runs: [], run: 0, phase: 'baseline', step: -1, verdict: null, history: [], best: ORIGINAL,
}

// Counts smoothly from the last value to the new one.
function Num({ value, decimals = 2 }) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)
  useEffect(() => {
    const start = performance.now()
    const a = from.current
    let raf
    const tick = (now) => {
      const t = Math.min(1, (now - start) / 650)
      const e = 1 - Math.pow(1 - t, 3)
      const v = a + (value - a) * e
      setShown(v)
      from.current = v
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value])
  return <>{shown.toFixed(decimals)}</>
}

function Delta({ now, base, invert = false }) {
  const pct = ((now - base) / base) * 100
  if (Math.abs(pct) < 0.5) return <span className="text-ink-3">baseline</span>
  const good = invert ? pct > 0 : pct < 0
  return (
    <span className={good ? 'text-good' : 'text-bad'}>
      {pct > 0 ? '+' : '−'}{Math.abs(pct).toFixed(0)}%
    </span>
  )
}

function Metric({ label, sub, value, unit, base, decimals, children }) {
  return (
    <div className="min-w-0 rounded-lg border border-ink/10 bg-surface/55 px-2.5 py-2 sm:px-3 sm:py-2.5">
      <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between text-[11px] uppercase tracking-wider text-ink-3">
        <span>{label}</span>
        <span className="font-mono normal-case tracking-normal"><Delta now={value} base={base} /></span>
      </div>
      <div className="mt-1 font-mono text-lg sm:text-2xl text-ink tabular-nums">
        <Num value={value} decimals={decimals} /><span className="ml-1 text-sm text-ink-3">{unit}</span>
      </div>
      <div className="hidden sm:block text-[11px] text-ink-3 truncate">{sub}</div>
      {children}
    </div>
  )
}

export default function BenchmarkRig() {
  const reduced = usePrefersReducedMotion()
  const [s, setS] = useState(INITIAL)

  useEffect(() => {
    if (reduced) { setS(finalState()); return }
    let alive = true
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

    ;(async () => {
      while (alive) {
        setS(INITIAL)
        await sleep(1800)
        let best = ORIGINAL
        const history = []
        for (let i = 0; i < STEPS.length && alive; i++) {
          const st = STEPS[i]
          const moved = [st.move]
          // Reorder: TM1 reports the memory change right away.
          setS((p) => ({ ...p, step: i, phase: 'apply', order: st.order, moved, mem: st.mem, runs: [], run: 0, verdict: null }))
          await sleep(1100)
          // Time the view 5 times.
          for (let r = 1; r <= 5 && alive; r++) {
            const runs = RUN_NOISE.slice(0, r).map((n) => st.query * (1 + n))
            setS((p) => ({ ...p, phase: 'measure', run: r, runs }))
            await sleep(260)
          }
          if (!alive) break
          setS((p) => ({ ...p, query: st.query, ti: st.ti }))
          await sleep(500)
          const kept = isBetter(st, best)
          if (kept) best = st
          history.push(kept)
          setS((p) => ({ ...p, phase: 'verdict', verdict: kept ? 'kept' : 'discarded', history: [...history], best }))
          await sleep(kept ? 700 : 900)
          if (!kept) {
            setS((p) => ({ ...p, order: best.order, moved: [], mem: best.mem, query: best.query, ti: best.ti }))
            await sleep(700)
          }
        }
        if (!alive) break
        setS((p) => ({ ...p, phase: 'done', order: best.order, moved: [], mem: best.mem, query: best.query, ti: best.ti, verdict: null }))
        await sleep(6500)
      }
    })()
    return () => { alive = false }
  }, [reduced])

  const lit = Math.round((CELLS * s.mem) / ORIGINAL.mem)
  const status =
    s.phase === 'baseline' ? 'Measuring the original order' :
    s.phase === 'done'     ? 'Best order found' :
    s.phase === 'apply'    ? `Reordering · order ${s.step + 1} of ${STEPS.length}` :
    s.phase === 'measure'  ? `Running view · execution ${s.run} of 5` :
    s.verdict === 'kept'   ? 'Better on memory and time · kept' :
                             'Not better · original put back'

  const done = s.phase === 'done'
  const speedup = ORIGINAL.query / s.best.query

  return (
    <div className="relative glass-tile overflow-hidden">
      {/* Title bar */}
      <div className="flex items-center justify-between gap-3 border-b border-ink/10 px-4 py-2.5 text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`h-2 w-2 flex-shrink-0 rounded-full ${done ? 'bg-good' : 'bg-amber animate-pulse'}`} />
          <span className="font-mono text-ink-2 truncate">tm1srv01 · Sales · greedy · 5 executions</span>
        </div>
        <span className="flex-shrink-0 text-ink-3">Illustrative run</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-4 p-4">
        {/* Storage order */}
        <div>
          <div className="mb-2 flex justify-between text-[11px] uppercase tracking-wider text-ink-3">
            <span>Storage order</span><span>Leaves</span>
          </div>
          <div className="relative" style={{ height: ROW * ORIGINAL.order.length }}>
            {ORIGINAL.order.map((key) => {
              const d = DIMS[key]
              const idx = s.order.indexOf(key)
              const moved = s.moved.includes(key)
              return (
                <div key={key}
                     className={`absolute left-0 right-0 flex items-center gap-2 rounded-md border px-2 text-sm transition-[top,border-color,background-color] duration-700 ease-[cubic-bezier(.65,0,.35,1)] ${
                       moved ? 'border-amber/60 bg-amber/10' : 'border-ink/10 bg-surface/60'
                     }`}
                     style={{ top: idx * ROW, height: ROW - 6 }}>
                  <span className="w-4 font-mono text-[11px] text-ink-3">{idx + 1}</span>
                  <span className="flex-1 truncate text-ink">{d.name}</span>
                  {d.locked && <Lock className="h-3 w-3 text-amber" aria-label="locked last: string elements" />}
                  <span className="font-mono text-xs text-ink-3 tabular-nums">{d.leaves}</span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Measurements */}
        <div className="grid grid-cols-3 gap-2 sm:flex sm:flex-col">
          <Metric label="Memory" sub="reported by TM1 after the reorder" value={s.mem} unit="GB" base={ORIGINAL.mem} decimals={2} />
          <Metric label="Query time" sub="view Sales Report · median of 5" value={s.query} unit="s" base={ORIGINAL.query} decimals={2}>
            <div className="mt-1.5 flex h-5 items-end gap-1" aria-hidden="true">
              {[0, 1, 2, 3, 4].map((k) => {
                const v = s.runs[k]
                return (
                  <div key={k} className="flex h-full flex-1 items-end rounded-sm bg-ink/5">
                    <div className="w-full rounded-sm bg-brand/70 transition-all duration-200"
                         style={{ height: v ? `${Math.min(100, (v / ORIGINAL.query) * 100)}%` : 0, minHeight: v ? 2 : 0 }} />
                  </div>
                )
              })}
            </div>
          </Metric>
          <Metric label="TI time" sub="process load.sales · median of 5" value={s.ti} unit="s" base={ORIGINAL.ti} decimals={1} />
        </div>
      </div>

      {/* RAM cells */}
      <div className="px-4">
        <div className="mb-1.5 flex justify-between text-[11px] uppercase tracking-wider text-ink-3">
          <span>Cube memory</span>
          <span className="font-mono normal-case tracking-normal">{lit}/{CELLS} blocks</span>
        </div>
        <div className="grid gap-[3px]" style={{ gridTemplateColumns: 'repeat(20, minmax(0, 1fr))' }} aria-hidden="true">
          {Array.from({ length: CELLS }, (_, i) => (
            <div key={i}
                 className={`h-2.5 rounded-[2px] transition-colors duration-500 ${i < lit ? 'bg-brand/80' : 'bg-ink/[0.07]'}`}
                 style={{ transitionDelay: `${(CELLS - i) * 6}ms` }} />
          ))}
        </div>
      </div>

      {/* Status line and tested orders */}
      <div className="mt-4 flex items-center justify-between gap-3 border-t border-ink/10 px-4 py-3 text-xs">
        <span className={`flex items-center gap-1.5 font-mono ${
          s.verdict === 'kept' ? 'text-good' : s.verdict === 'discarded' ? 'text-bad' : 'text-ink-2'
        }`} aria-live="polite">
          {s.verdict === 'kept' && <Check className="h-3.5 w-3.5" />}
          {s.verdict === 'discarded' && <X className="h-3.5 w-3.5" />}
          {status}
        </span>
        <div className="flex items-center gap-1" aria-label="orders tested">
          {STEPS.map((_, i) => {
            const h = s.history[i]
            return <span key={i} className={`h-2 w-2 rounded-full ${
              h === true ? 'bg-good' : h === false ? 'bg-bad' : i === s.step ? 'bg-amber' : 'bg-ink/10'
            }`} />
          })}
        </div>
      </div>

      {/* Result */}
      <div className={`grid grid-cols-3 border-t border-good/30 bg-good/[0.08] transition-all duration-700 ${
        done ? 'max-h-24 opacity-100' : 'max-h-0 opacity-0'
      }`}>
        {[
          ['Memory', `−${Math.round((1 - s.best.mem / ORIGINAL.mem) * 100)}%`],
          ['Queries', `${speedup.toFixed(1)}× faster`],
          ['TI', `−${Math.round((1 - s.best.ti / ORIGINAL.ti) * 100)}%`],
        ].map(([k, v]) => (
          <div key={k} className="px-4 py-3 text-center">
            <div className="font-mono text-lg font-semibold text-good">{v}</div>
            <div className="text-[11px] uppercase tracking-wider text-ink-3">{k}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
