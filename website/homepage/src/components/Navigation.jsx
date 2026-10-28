import { Menu, X, Github, BookOpen } from 'lucide-react'
import { useState } from 'react'
import { OptimusPyLogo } from './logos/OptimusPyLogo'
import { DOCS, GITHUB_URL } from '../links'

const LINKS = [
  ['#v12', 'TM1 v12'],
  ['#web-ui', 'Web UI'],
  ['#optimize-db', 'Optimize DB'],
  ['#how-it-works', 'How it works'],
  ['#features', 'Features'],
  ['#get-started', 'Get started'],
]

export default function Navigation() {
  const [isMenuOpen, setIsMenuOpen] = useState(false)

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-surface/85 backdrop-blur-lg border-b border-ink/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <a href={import.meta.env.BASE_URL} className="flex items-center" aria-label="OptimusPy home">
            <OptimusPyLogo height={36} />
          </a>

          <div className="hidden lg:flex items-center gap-7">
            {LINKS.map(([href, label]) => (
              <a key={href} href={href} className="text-ink-2 hover:text-brand transition-colors">{label}</a>
            ))}
            <a href={DOCS.home} className="text-ink-2 hover:text-brand transition-colors inline-flex items-center gap-1">
              <BookOpen className="w-4 h-4" />Docs
            </a>
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer"
               className="bg-surface border border-ink/10 text-ink px-4 py-2 rounded-lg hover:border-brand transition-colors inline-flex items-center gap-2">
              <Github className="w-4 h-4" />GitHub
            </a>
          </div>

          <button onClick={() => setIsMenuOpen(!isMenuOpen)} aria-label="Toggle navigation menu" aria-expanded={isMenuOpen}
                  className="lg:hidden text-ink p-2">
            {isMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>

        {isMenuOpen && (
          <div className="lg:hidden pb-4 space-y-1">
            {LINKS.map(([href, label]) => (
              <a key={href} href={href} onClick={() => setIsMenuOpen(false)} className="block text-ink-2 hover:text-brand py-2">{label}</a>
            ))}
            <a href={DOCS.home} className="block text-ink-2 hover:text-brand py-2">Docs</a>
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="block text-ink-2 hover:text-brand py-2">GitHub</a>
          </div>
        )}
      </div>
    </nav>
  )
}
