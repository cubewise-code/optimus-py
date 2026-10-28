import { useState } from 'react'
import { Terminal, BookOpen, Github, Download, Copy, Check } from 'lucide-react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import { DOCS, GITHUB_URL, RELEASES_URL } from '../links'

const TABS = [
  { key: 'bundle', label: 'Bundle',
    note: 'Download optimuspy-windows.zip or optimuspy-linux.tar.gz from Releases, unpack it, then:',
    code: '# Windows: double-click optimuspy.exe\n# Linux:\n./optimuspy ui\n# The UI opens at http://127.0.0.1:8765' },
  { key: 'python', label: 'Python',
    note: 'With Python 3.9 or later:',
    code: `git clone ${GITHUB_URL}.git\ncd optimus-py\npip install -e .\noptimuspy ui` },
  { key: 'cli', label: 'Command line',
    note: 'Find the cubes worth optimizing, add your views to each config, then run one:',
    code: 'optimuspy scan --instance tm1srv01 --output configs/\noptimuspy optimize configs/Sales.json' },
]

export default function GetStarted() {
  const [ref, isVisible] = useScrollAnimation()
  const [tab, setTab] = useState('bundle')
  const [copied, setCopied] = useState(false)
  const active = TABS.find((t) => t.key === tab)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(active.code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch { /* clipboard blocked: nothing to do */ }
  }

  return (
    <section ref={ref} id="get-started" className="py-24 bg-canvas">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <h2 className={`text-3xl sm:text-4xl font-bold mb-3 text-center animate-on-scroll ${isVisible ? 'visible' : ''}`}>
          Try it on a DEV instance
        </h2>
        <p className={`text-ink-2 text-center mb-10 animate-on-scroll stagger-2 ${isVisible ? 'visible' : ''}`}>
          OptimusPy changes the cube while it measures, so point it at a copy of the model with spare memory.
        </p>

        <div className={`animate-on-scroll stagger-3 ${isVisible ? 'visible' : ''}`}>
          <div role="tablist" className="flex justify-center gap-2 mb-4">
            {TABS.map((t) => (
              <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
                      className={`px-4 py-2 text-sm rounded-md font-medium transition-colors ${
                        tab === t.key ? 'bg-surface text-brand border border-brand/40' : 'border border-transparent text-ink-2 hover:text-ink'
                      }`}>
                {t.label}
              </button>
            ))}
          </div>

          <div className="rounded-xl border border-ink/10 bg-canvas overflow-hidden">
            <div className="flex items-center justify-between gap-3 px-4 py-2 bg-surface border-b border-ink/10 text-xs text-ink-3">
              <span className="flex items-center gap-2 min-w-0"><Terminal className="w-4 h-4 flex-shrink-0" /><span className="truncate">{active.note}</span></span>
              <button onClick={copy} className="flex-shrink-0 inline-flex items-center gap-1 hover:text-brand transition-colors">
                {copied ? <><Check className="w-3.5 h-3.5" />Copied</> : <><Copy className="w-3.5 h-3.5" />Copy</>}
              </button>
            </div>
            <pre className="px-5 py-5 text-sm text-ink-2 font-mono leading-relaxed overflow-x-auto"><code>{active.code}</code></pre>
          </div>
        </div>

        <div className={`grid grid-cols-1 sm:grid-cols-3 gap-3 mt-10 animate-on-scroll stagger-4 ${isVisible ? 'visible' : ''}`}>
          {[
            { href: DOCS.guide, icon: BookOpen, label: 'User Guide' },
            { href: RELEASES_URL, icon: Download, label: 'Releases', external: true },
            { href: GITHUB_URL, icon: Github, label: 'GitHub', external: true },
          ].map(({ href, icon: Icon, label, external }) => (
            <a key={label} href={href} {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
               className="inline-flex items-center justify-center gap-2 rounded-lg border border-ink/10 bg-surface px-4 py-4 text-ink-2 hover:border-brand hover:text-ink transition-colors">
              <Icon className="w-5 h-5" />{label}
            </a>
          ))}
        </div>
      </div>
    </section>
  )
}
