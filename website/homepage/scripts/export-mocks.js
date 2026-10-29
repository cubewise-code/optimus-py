import { chromium } from 'playwright'
import { spawn } from 'child_process'
import { mkdirSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = resolve(__dirname, '../../../docs/assets/images/optimuspy/ui')

const PORT = 4179
const URL = `http://localhost:${PORT}/optimus-py/mocks-page.html`

const TARGETS = [
  { selector: '[data-mock="optimize-page"]',  file: 'optimize-page.png',   width: 1280, height: 720 },
  { selector: '[data-mock="sidebar-overview"]', file: 'sidebar-overview.png', width:  900, height: 600 },
]

async function main() {
  mkdirSync(OUT_DIR, { recursive: true })

  // Boot Vite preview
  const vite = spawn('npx', ['vite', 'preview', '--port', String(PORT)], { stdio: 'inherit' })
  await new Promise((r) => setTimeout(r, 2500))

  const browser = await chromium.launch()
  try {
    const page = await browser.newPage()
    for (const t of TARGETS) {
      await page.setViewportSize({ width: t.width, height: t.height })
      await page.goto(URL, { waitUntil: 'networkidle' })
      await page.waitForTimeout(1500) // let the mock entrance animation settle
      const el = await page.$(t.selector)
      if (!el) throw new Error(`Selector ${t.selector} not found on ${URL}`)
      const out = resolve(OUT_DIR, t.file)
      await el.screenshot({ path: out, omitBackground: false })
      console.log(`✓ wrote ${out}`)
    }
  } finally {
    await browser.close()
    vite.kill('SIGTERM')
  }
}

main().catch((e) => { console.error(e); process.exit(1) })
