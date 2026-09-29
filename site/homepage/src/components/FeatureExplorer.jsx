import { useState } from 'react'
import { FileJson, Layers, Pin, Zap, RotateCw, FileBarChart, ArrowLeftRight, Search, Package } from 'lucide-react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import { DOCS } from '../links'

const DOCS_BASE = DOCS.home.replace(/\/$/, '')

const FEATURES = [
  { key: 'json', icon: FileJson, title: 'JSON cube configs', short: 'One file per cube, kept and re-run.',
    body: 'Each cube is described in a JSON file. Keep it next to the model and run it again after every big change. The UI writes the same file for you.',
    kind: 'code', lang: 'sales.json',
    code: `{
  "instance": "tm1srv01",
  "cube": "Sales",
  "views": ["Optimus"],
  "executions": 10,
  "output": "csv",
  "update": false
}`,
    link: `${DOCS_BASE}/advanced/json-config-reference/`, cta: 'JSON config reference' },
  { key: 'multi', icon: Layers, title: 'Views and processes', short: 'Benchmark what people actually run.',
    body: 'List several views and TI processes, with parameters for each. Every one runs the set number of times and the median counts, so one slow run doesn\'t decide the result.',
    kind: 'code', lang: 'sales.json',
    code: `{
  "views": ["Daily Drill", "Monthly Summary"],
  "processes": ["Sales_Daily_Refresh"],
  "process_parameters": {
    "Sales_Daily_Refresh": { "pYear": "2026" }
  }
}`,
    link: `${DOCS_BASE}/advanced/multi-view-multi-process/`, cta: 'Multi-view / multi-process' },
  { key: 'rules', icon: Pin, title: 'Position rules', short: 'Keep a dimension where it must be.',
    body: 'Fix a dimension to a position while the rest are tested, and list orders you never want tried.',
    kind: 'code', lang: 'sales.json',
    code: `{
  "dimension_position_rules": [
    { "dimension": "Time", "position": 0 }
  ],
  "orders_to_ignore": []
}`,
    link: `${DOCS_BASE}/advanced/dimension-position-rules/`, cta: 'Dimension position rules' },
  { key: 'fast', icon: Zap, title: 'Fast mode', short: 'Fewer reorders on big cubes.',
    body: 'Starts from the order suggested by leaf counts and only refines the dimensions that are still undecided. Useful when every reorder takes minutes.',
    kind: 'code', lang: 'sales.json',
    code: `{
  "fast": true
}`,
    link: DOCS.optimize, cta: 'Optimize mode' },
  { key: 'resume', icon: RotateCw, title: 'Checkpoint and resume', short: 'Stopped runs pick up where they left off.',
    body: 'A reorder can take a long time on a big cube, and a connection can drop along the way. Every tested order is saved as it finishes, so running the same command again picks up where it left off, including an order that was mid-reorder when it stopped.',
    kind: 'code', lang: 'terminal',
    code: `optimuspy optimize sales.json               # continues
optimuspy optimize sales.json --no-resume   # starts over`,
    link: DOCS.checkpoints, cta: 'Checkpoints & resume' },
  { key: 'report', icon: FileBarChart, title: 'HTML report', short: 'Best overall, fastest and smallest.',
    body: 'Every run writes an HTML report: summary cards, the recommended order, a memory against time chart relative to the original, and the full table. A CSV or XLSX comes alongside.',
    kind: 'podium',
    link: DOCS.results, cta: 'Results page' },
  { key: 'sync', icon: ArrowLeftRight, title: 'Sync and export', short: 'Move a proven order to PROD.',
    body: 'Copy storage orders from one instance to another on the Sync Order page, or export them as configs and apply them later with Set.',
    kind: 'code', lang: 'terminal',
    code: `exports/
├── Sales.json
└── Budget.json

optimuspy set exports/Sales.json`,
    link: DOCS.production, cta: 'Taking an order to production' },
  { key: 'scan', icon: Search, title: 'Starter configs', short: 'Scan writes a config per big cube.',
    body: 'Scan lists the cubes that make up most of the instance\'s memory and writes a starter config for each. Add your views and run them.',
    kind: 'code', lang: 'terminal',
    code: `optimuspy scan --instance tm1srv01 --output configs/`,
    link: DOCS.scan, cta: 'Scan mode' },
  { key: 'bundle', icon: Package, title: 'Windows and Linux bundles', short: 'Unzip and run. No Python.',
    body: 'Each bundle holds the executable, an example config.ini and sample cube configs. With Python 3.9 or later you can install from the repository instead.',
    kind: 'code', lang: 'optimuspy/',
    code: `optimuspy/
├── optimuspy(.exe)
├── config/config.ini.example
└── samples/`,
    link: DOCS.install, cta: 'Installation' },
]

// The report's top cards, drawn with the illustrative run from the hero.
const PODIUM = [
  { label: 'Best overall', rank: '#7', value: '0.61 s · 2.93 GB', tone: 'text-good' },
  { label: '#1 Fastest query', rank: '#7', value: '0.61 s (−67%)', tone: 'text-brand' },
  { label: '#1 Lowest RAM', rank: '#7', value: '2.93 GB (−39%)', tone: 'text-navy' },
]
const BEST = ['Version', 'Currency', 'Year', 'Period', 'Region', 'Product', 'Customer', 'Sales Measure']

function Podium() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5" aria-label="Example report cards">
      {PODIUM.map((c) => (
        <div key={c.label} className="rounded-lg border border-ink/10 bg-surface/80 p-3">
          <div className={`text-[10px] font-semibold uppercase tracking-wider ${c.tone}`}>{c.label}</div>
          <div className="mt-1 text-lg font-bold">{c.rank}</div>
          <div className="font-mono text-xs text-ink-2 mb-2">{c.value}</div>
          <div className="flex flex-wrap gap-1">
            {BEST.map((d) => <span key={d} className="rounded bg-ink/[0.06] px-1.5 py-0.5 text-[10px] text-ink-2">{d}</span>)}
          </div>
        </div>
      ))}
    </div>
  )
}

function Detail({ f }) {
  return (
    <div key={f.key} className="glass-tile p-6 sm:p-7 h-full flex flex-col feature-enter">
      <div className="flex items-center gap-2 mb-3">
        <f.icon className="w-5 h-5 text-brand" />
        <h3 className="text-xl font-bold">{f.title}</h3>
      </div>
      <p className="text-ink-2 leading-relaxed mb-5">{f.body}</p>
      {f.kind === 'code' ? (
        <div className="rounded-lg border border-ink/10 bg-ink/[0.92] overflow-hidden">
          <div className="px-4 py-1.5 border-b border-white/10 font-mono text-[11px] text-white/50">{f.lang}</div>
          <pre className="px-4 py-4 text-[13px] leading-relaxed text-white/85 font-mono overflow-x-auto"><code>{f.code}</code></pre>
        </div>
      ) : (
        <Podium />
      )}
      <a href={f.link} className="mt-auto pt-5 text-sm text-brand hover:underline">{f.cta} →</a>
    </div>
  )
}

export default function FeatureExplorer() {
  const [ref, isVisible] = useScrollAnimation()
  const [active, setActive] = useState(FEATURES[0].key)
  const current = FEATURES.find((f) => f.key === active)

  return (
    <section ref={ref} id="features" className="relative overflow-hidden py-24 bg-sunken border-y border-ink/5">
      <div className="gradient-orb w-[480px] h-[480px] bg-brand-soft -top-32 right-1/4" />
      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl mb-12">
          <span className={`block text-brand text-sm font-semibold uppercase tracking-wider mb-3 animate-on-scroll ${isVisible ? 'visible' : ''}`}>
            Also in 2.0
          </span>
          <h2 className={`text-3xl sm:text-4xl font-bold mb-4 animate-on-scroll stagger-2 ${isVisible ? 'visible' : ''}`}>
            Browse the rest of the release.
          </h2>
          <p className={`text-ink-2 text-lg animate-on-scroll stagger-3 ${isVisible ? 'visible' : ''}`}>
            Pick a tile to see what it does and how to use it.{' '}
            <a href={DOCS.whatsNew} className="text-brand hover:underline whitespace-nowrap">Everything new in 2.0 →</a>
          </p>
        </div>

        <div className={`grid grid-cols-1 lg:grid-cols-12 gap-6 animate-on-scroll stagger-3 ${isVisible ? 'visible' : ''}`}>
          <div role="tablist" aria-label="2.0 features" className="lg:col-span-6 grid grid-cols-2 sm:grid-cols-3 gap-3 content-start">
            {FEATURES.map((f) => {
              const on = f.key === active
              return (
                <button key={f.key} role="tab" aria-selected={on} onClick={() => setActive(f.key)}
                        className={`group text-left rounded-xl border p-4 transition-all duration-200 backdrop-blur-sm ${
                          on ? 'border-brand/50 bg-surface shadow-lg shadow-brand/10 -translate-y-0.5'
                             : 'border-ink/10 bg-surface/55 hover:bg-surface/85 hover:border-ink/20'
                        }`}>
                  <f.icon className={`w-5 h-5 mb-3 transition-colors ${on ? 'text-brand' : 'text-ink-3 group-hover:text-brand'}`} />
                  <div className="font-semibold text-sm mb-1">{f.title}</div>
                  <div className="text-xs text-ink-3 leading-snug">{f.short}</div>
                </button>
              )
            })}
          </div>
          <div className="lg:col-span-6" role="tabpanel">
            <Detail f={current} />
          </div>
        </div>
      </div>
    </section>
  )
}
