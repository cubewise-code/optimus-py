import { ArrowRight, Download } from 'lucide-react'
import BenchmarkRig from './BenchmarkRig'
import { DOCS, RELEASES_URL } from '../links'

export default function Hero() {
  return (
    <section className="relative overflow-hidden pt-28 pb-16 lg:pt-32 lg:pb-24 hero-grid">
      <div className="gradient-orb w-[560px] h-[560px] bg-brand-soft -top-48 -left-48" />
      <div className="gradient-orb w-[480px] h-[480px] bg-amber-soft top-1/3 -right-48" />

      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-10 items-center">
        <div className="lg:col-span-5">
          <a href="#v12" className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-surface/70 backdrop-blur px-3 py-1 mb-7 text-sm text-ink-2 hover:border-brand/40 transition-colors">
            <span className="rounded-full bg-amber-soft/30 px-2 py-0.5 text-xs font-semibold text-amber">New in 2.0</span>
            Now on TM1 v12 · Web UI · Optimize DB
            <ArrowRight className="w-3.5 h-3.5" />
          </a>

          <h1 className="text-4xl sm:text-5xl lg:text-[3.25rem] xl:text-[3.75rem] font-bold leading-[1.1] tracking-tight mb-6">
            Same data.
            <br />
            <span className="text-brand">Less RAM.<br />Faster queries.</span>
          </h1>

          <p className="text-ink-2 text-lg leading-relaxed mb-8 max-w-xl">
            The order of a cube's dimensions decides how much memory TM1 needs to hold it and how fast
            views and TI processes read it. OptimusPy tries real orders on your server, measures each
            one, and hands you the best.
          </p>

          <div className="flex flex-col sm:flex-row gap-3">
            <a href={DOCS.guide}
               className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-6 py-3 font-semibold text-white hover:opacity-90 transition-opacity">
              Start with the User Guide <ArrowRight className="w-4 h-4" />
            </a>
            <a href={RELEASES_URL} target="_blank" rel="noopener noreferrer"
               className="inline-flex items-center justify-center gap-2 rounded-lg border border-ink/20 px-6 py-3 text-ink hover:border-brand hover:text-brand transition-colors">
              <Download className="w-4 h-4" /> Download 2.0
            </a>
          </div>

          <p className="mt-5 text-sm text-ink-3">
            Free and open source. Windows and Linux bundles, no Python needed.
          </p>
        </div>

        <div className="lg:col-span-7">
          <BenchmarkRig />
        </div>
      </div>
    </section>
  )
}
