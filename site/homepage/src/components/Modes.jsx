import { Sparkles, ListChecks, Crosshair, Move, PenLine, Search, Database, ArrowLeftRight } from 'lucide-react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import { DOCS } from '../links'

const GROUPS = [
  {
    title: 'Find the best order for one cube',
    modes: [
      { icon: Sparkles, name: 'Greedy', link: DOCS.optimize,
        body: 'Searches for the best order from scratch. Fast mode starts from a suggested order and refines it.' },
      { icon: ListChecks, name: 'Predefined', link: DOCS.predefined,
        body: 'Tests only the orders you list, head to head.' },
      { icon: Crosshair, name: 'Position', link: DOCS.position,
        body: 'Finds the best dimension for one slot.' },
      { icon: Move, name: 'Dimension', link: DOCS.dimension,
        body: 'Finds the best slot for one dimension.' },
    ],
  },
  {
    title: 'Apply and promote',
    modes: [
      { icon: PenLine, name: 'Set', link: DOCS.set,
        body: 'Applies an order you already trust, without benchmarking.' },
      { icon: ArrowLeftRight, name: 'Sync Order', link: DOCS.sync, tag: 'UI',
        body: 'Copies storage orders from one instance to another, or exports them as configs for Set.' },
    ],
  },
  {
    title: 'Work across an instance',
    modes: [
      { icon: Search, name: 'Scan', link: DOCS.scan,
        body: 'Lists the cubes that hold most of the memory and writes a starter config for each.' },
      { icon: Database, name: 'Optimize DB', link: DOCS.optimizeDb, tag: 'New',
        body: 'Reorders every cube on the instance within a time limit.' },
    ],
  },
]

export default function Modes() {
  const [ref, isVisible] = useScrollAnimation()

  return (
    <section ref={ref} id="modes" className="py-24 bg-canvas">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl mb-14">
          <span className={`block text-amber text-sm font-semibold uppercase tracking-wider mb-3 animate-on-scroll ${isVisible ? 'visible' : ''}`}>
            Modes
          </span>
          <h2 className={`text-3xl sm:text-4xl font-bold mb-4 animate-on-scroll stagger-2 ${isVisible ? 'visible' : ''}`}>
            One question per mode.
          </h2>
          <p className={`text-ink-2 text-lg animate-on-scroll stagger-3 ${isVisible ? 'visible' : ''}`}>
            From "what's the best order for this cube?" to "shrink the whole model before Monday".{' '}
            <a href={DOCS.guide} className="text-brand hover:underline whitespace-nowrap">Choose a mode →</a>
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-5">
          {GROUPS.map((g, gi) => (
            <div key={g.title}
                 className={`${gi === 0 ? 'lg:col-span-2' : ''} animate-on-scroll stagger-${gi + 2} ${isVisible ? 'visible' : ''}`}>
              <h3 className="text-sm text-ink-3 mb-3">{g.title}</h3>
              <div className={`grid gap-3 ${gi === 0 ? 'sm:grid-cols-2' : 'sm:grid-cols-2 lg:grid-cols-1'}`}>
                {g.modes.map((m) => {
                  const Icon = m.icon
                  return (
                    <a key={m.name} href={m.link}
                       className="group rounded-xl border border-ink/10 bg-surface/70 backdrop-blur-sm p-5 hover:border-brand/40 transition-colors">
                      <div className="flex items-center gap-2 mb-2">
                        <Icon className="w-5 h-5 text-brand" />
                        <span className="font-semibold group-hover:text-brand transition-colors">{m.name}</span>
                        {m.tag && (
                          <span className={`ml-auto rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${
                            m.tag === 'New' ? 'bg-good/15 text-good' : 'bg-ink/5 text-ink-3'
                          }`}>{m.tag}</span>
                        )}
                      </div>
                      <p className="text-ink-2 text-sm leading-relaxed">{m.body}</p>
                    </a>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
