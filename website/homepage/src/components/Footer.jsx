import { Github, ExternalLink } from 'lucide-react'
import { OptimusPyLogo } from './logos/OptimusPyLogo'
import { CubewiseLogo } from './logos/CubewiseLogo'
import { DOCS, GITHUB_URL, RELEASES_URL } from '../links'

const DOC_LINKS = [
  [DOCS.guide, 'User Guide'],
  [DOCS.install, 'Installation'],
  [DOCS.whatsNew, "What's new in 2.0"],
  [DOCS.ui, 'Web UI'],
  [DOCS.cli, 'CLI reference'],
]

const RESOURCES = [
  [RELEASES_URL, 'Releases'],
  [GITHUB_URL, 'GitHub'],
  [`${GITHUB_URL}/issues`, 'Report an issue'],
  ['https://www.cubewise.com', 'Cubewise'],
]

export default function Footer() {
  return (
    <footer className="py-12 bg-canvas border-t border-ink/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          <div className="md:col-span-2">
            <div className="mb-4"><OptimusPyLogo height={44} /></div>
            <p className="text-ink-2 max-w-sm mb-4">
              Finds a better dimension order for your TM1 cubes, measured on your server. Free and open source.
            </p>
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" aria-label="OptimusPy on GitHub"
               className="inline-block text-ink-3 hover:text-ink transition-colors">
              <Github className="w-5 h-5" aria-hidden="true" />
            </a>
          </div>

          <div>
            <h4 className="font-semibold mb-4">Documentation</h4>
            <ul className="space-y-2">
              {DOC_LINKS.map(([href, label]) => (
                <li key={label}><a href={href} className="text-ink-2 hover:text-brand transition-colors">{label}</a></li>
              ))}
            </ul>
          </div>

          <div>
            <h4 className="font-semibold mb-4">Resources</h4>
            <ul className="space-y-2">
              {RESOURCES.map(([href, label]) => (
                <li key={label}>
                  <a href={href} target="_blank" rel="noopener noreferrer"
                     className="text-ink-2 hover:text-brand transition-colors inline-flex items-center gap-1">
                    {label}<ExternalLink className="w-3 h-3" />
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-12 pt-8 border-t border-ink/10 flex flex-col sm:flex-row justify-between items-center gap-4">
          <p className="text-ink-3 text-sm">&copy; {new Date().getFullYear()} Cubewise. Open source under the MIT License.</p>
          <a href="https://www.cubewise.com" target="_blank" rel="noopener noreferrer"
             className="flex items-center gap-2 text-ink-3 hover:text-ink-2 transition-colors">
            <span className="text-sm">A Cubewise project</span>
            <CubewiseLogo height={24} />
          </a>
        </div>
      </div>
    </footer>
  )
}
