import { Search, SlidersHorizontal, Activity, FileBarChart } from 'lucide-react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import { DOCS } from '../links'

const STEPS = [
  { icon: Search, title: 'Find the cubes worth it',
    body: 'Scan lists the cubes that make up most of the instance\'s memory, largest first.' },
  { icon: SlidersHorizontal, title: 'Say what fast means',
    body: 'Pick the views and TI processes that matter, and how many times to run each.' },
  { icon: Activity, title: 'Measure real orders',
    body: 'Each order is applied on the server. Views and processes run with a cleared cache, and the median counts. Orders that can\'t win are skipped.' },
  { icon: FileBarChart, title: 'Decide with numbers',
    body: 'An HTML report shows the best overall, fastest and smallest orders. Apply the best order, or keep the original.' },
]

export default function HowItWorks() {
  const [ref, isVisible] = useScrollAnimation()

  return (
    <section ref={ref} id="how-it-works" className="py-24 bg-sunken border-y border-ink/5">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl mb-14">
          <span className={`block text-navy text-sm font-semibold uppercase tracking-wider mb-3 animate-on-scroll ${isVisible ? 'visible' : ''}`}>
            How it works
          </span>
          <h2 className={`text-3xl sm:text-4xl font-bold mb-4 animate-on-scroll stagger-2 ${isVisible ? 'visible' : ''}`}>
            Measured on your server, not guessed from a rule of thumb.
          </h2>
        </div>

        <ol className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
          {STEPS.map((s, i) => {
            const Icon = s.icon
            return (
              <li key={s.title}
                  className={`relative rounded-xl border border-ink/10 bg-surface/70 backdrop-blur-sm p-6 animate-on-scroll stagger-${i + 2} ${isVisible ? 'visible' : ''}`}>
                <div className="flex items-center justify-between mb-4">
                  <Icon className="w-6 h-6 text-navy" />
                  <span className="font-mono text-sm text-ink-3">0{i + 1}</span>
                </div>
                <h3 className="font-semibold text-lg mb-2">{s.title}</h3>
                <p className="text-ink-2 text-sm leading-relaxed">{s.body}</p>
              </li>
            )
          })}
        </ol>

        <div className={`mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm animate-on-scroll stagger-5 ${isVisible ? 'visible' : ''}`}>
          <a href={DOCS.howItWorks} className="text-brand hover:underline">How a run works →</a>
          <a href={DOCS.firstRun} className="text-brand hover:underline">Your first optimization →</a>
        </div>
      </div>
    </section>
  )
}
