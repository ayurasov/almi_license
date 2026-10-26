// A terminal window with the real output of a command, as a picture for the guides.
//   node tools/screenshots/terminal.cjs output.txt picture.png ["window title"]
// The text is taken as it is (UTF-8); lines starting with "$ " are drawn as commands.
const fs = require('node:fs')
const { chromium } = require('playwright')

const [input, output, title = 'almi@license: ~/almi_license/deploy/central'] = process.argv.slice(2)
const escape = (text) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const colour = (line) => {
  if (line.startsWith('$ ')) return `<span class="cmd">${escape(line)}</span>`
  if (/^(ok|\[install\]|\[upgrade\])/.test(line)) return `<span class="ok">${escape(line)}</span>`
  if (/^(warn)/.test(line)) return `<span class="warn">${escape(line)}</span>`
  if (/^(FAIL|\[install\] error|ERROR)/.test(line)) return `<span class="fail">${escape(line)}</span>`
  return escape(line)
}

async function main() {
  const lines = fs.readFileSync(input, 'utf8').replace(/\s+$/, '').split('\n')
  const html = `<!doctype html><meta charset="utf-8"><style>
    body { margin: 0; background: #e9edf2; padding: 16px; font-family: 'DejaVu Sans', sans-serif; }
    .window { display: inline-block; min-width: 860px; max-width: 1360px; border-radius: 8px;
      box-shadow: 0 6px 24px rgba(0,0,0,.25); overflow: hidden; }
    .bar { background: #2b2f36; color: #c9d1d9; font-size: 13px; padding: 7px 12px; }
    .bar i { display: inline-block; width: 11px; height: 11px; border-radius: 50%; margin-right: 6px; }
    pre { margin: 0; background: #0d1117; color: #e6edf3; padding: 14px 16px; font-size: 14px;
      line-height: 1.45; font-family: 'DejaVu Sans Mono', monospace; white-space: pre-wrap; }
    .cmd { color: #7ee787; } .ok { color: #c9d1d9; } .warn { color: #e3b341; } .fail { color: #ff7b72; }
  </style><div class="window"><div class="bar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i>
  <i style="background:#28c840"></i>&nbsp;${escape(title)}</div><pre>${lines.map(colour).join('\n')}</pre></div>`
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1400, height: 400 }, deviceScaleFactor: 1 })
  await page.setContent(html)
  await page.locator('.window').screenshot({ path: output })
  await browser.close()
}

void main()
