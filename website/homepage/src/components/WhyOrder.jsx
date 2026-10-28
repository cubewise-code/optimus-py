import { MemoryStick, Gauge, Timer, Server } from 'lucide-react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import { DOCS } from '../links'

const POINTS = [
  { icon: MemoryStick, title: 'Memory',
    body: 'TM1 holds every cube in RAM. A better order stores the same cells in less of it.',
    before: 100, after: 61 },
  { icon: Gauge, title: 'Query speed',
    body: 'Views and reports read the cube in its storage order. The right order makes them faster.',
    before: 100, after: 33 },
  { icon: Timer, title: 'TI time',
    body: 'Loads and calculations write through the same structure, so they speed up too.',
    before: 100, after: 65 },
  { icon: Server, title: 'Headroom',
    body: 'Less memory per cube means more room on the same server and less to load when TM1 starts.',
    before: 100, after: 61 },
]

export default function WhyOrder() {
  const [ref, isVisible] = useScrollAnimation()

  return (
    <section ref={ref} className="py-24 bg-canvas">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl mb-14">
          <span className={`block text-brand text-sm font-semibold uppercase tracking-wider mb-3 animate-on-scroll ${isVisible ? 'visible' : ''}`}>
            Why the order matters
          </span>
          <h2 className={`text-3xl sm:text-4xl font-bold mb-4 animate-on-scroll stagger-2 ${isVisible ? 'visible' : ''}`}>
            Nothing changes in the model. Only the order does.
          </h2>
          <p className={`text-ink-2 text-lg leading-relaxed animate-on-scroll stagger-3 ${isVisible ? 'visible' : ''}`}>
            Reordering a cube's dimensions keeps every rule, view and value as it is. What changes is how TM1 lays
            the cells out in memory, and that can be the difference between a cube that fits and one that doesn't.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {POINTS.map((p, i) => {
            const Icon = p.icon
            return (
              <div key={p.title}
                   className={`rounded-xl border border-ink/10 bg-surface/70 backdrop-blur-sm p-6 animate-on-scroll stagger-${i + 2} ${isVisible ? 'visible' : ''}`}>
                <Icon className="w-6 h-6 text-brand mb-4" />
                <h3 className="text-lg font-semibold mb-2">{p.title}</h3>
                <p className="text-ink-2 text-sm leading-relaxed mb-5">{p.body}</p>
                <div className="space-y-1.5" aria-hidden="true">
                  <div className="h-1.5 rounded-full bg-ink-3/40" />
                  <div className="h-1.5 rounded-full bg-good transition-[width] duration-[1400ms] ease-out"
                       style={{ width: isVisible ? `${p.after}%` : '100%', transitionDelay: `${400 + i * 150}ms` }} />
                </div>
              </div>
            )
          })}
        </div>

        <p className={`mt-6 text-sm text-ink-3 animate-on-scroll stagger-5 ${isVisible ? 'visible' : ''}`}>
          Bars show the illustrative run above: original order in grey, best order in green. Your cubes will differ, which is why OptimusPy measures instead of guessing.{' '}
          <a href={DOCS.tradeoff} className="text-brand hover:underline">RAM vs query time →</a>
        </p>
      </div>
    </section>
  )
}
