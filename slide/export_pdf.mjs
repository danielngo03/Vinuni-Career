// Export deck.html -> VinUni-Career-Pitch.pdf (15 pages, 16:9 13.333x7.5in).
// Run from the main frontend dir (has @playwright/test):
//   cd frontend && node ../<worktree>/slide/export_pdf.mjs <deckUrl> <outPdf>
import { createRequire } from 'node:module';
// resolve @playwright/test from the main frontend checkout (has node_modules)
const require = createRequire('/Users/anhtuan/Desktop/Vinuni/Build/C2-App-037/frontend/package.json');
const { chromium } = require('@playwright/test');

const [url, out] = process.argv.slice(2);
const browser = await chromium.launch({ channel: 'chrome' }).catch(() => chromium.launch());
const page = await browser.newPage();
await page.goto(url, { waitUntil: 'networkidle' });
await page.emulateMedia({ media: 'print' });
await page.pdf({
  path: out,
  width: '13.333in',
  height: '7.5in',
  printBackground: true,
  margin: { top: 0, bottom: 0, left: 0, right: 0 },
});
await browser.close();
console.log('PDF written:', out);
