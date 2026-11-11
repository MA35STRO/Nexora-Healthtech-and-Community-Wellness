// Renders poster.html to print files:
//   node poster/build.mjs
// → poster/out/kawan-poster-A1.pdf          594 × 841 mm (trim size)
// → poster/out/kawan-poster-A1-bleed3mm.pdf 600 × 847 mm (3 mm bleed, for print shops that ask)
// → poster/out/preview.png                  quick look (~1300 px wide)
// Also reports any element that overflows the page or its box, so nothing is clipped.
import { mkdirSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { chromium } from "../frontend/node_modules/playwright/index.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "out");
mkdirSync(out, { recursive: true });
const url = pathToFileURL(join(here, "poster.html")).href;
const MM = 96 / 25.4; // css px per mm

const browser = await chromium.launch();
async function render(bleed, pdfName) {
  const page = await browser.newPage({
    viewport: {
      width: Math.round((594 + 2 * bleed) * MM),
      height: Math.round((841 + 2 * bleed) * MM),
    },
  });
  await page.goto(url + (bleed ? `?bleed=${bleed}` : ""));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForLoadState("networkidle");
  const problems = await page.evaluate(() => {
    const issues = [];
    const sheet = document.querySelector(".sheet").getBoundingClientRect();
    for (const el of document.querySelectorAll(".sheet *")) {
      const r = el.getBoundingClientRect();
      if (r.width === 0) continue;
      if (r.bottom > sheet.bottom + 0.5 || r.right > sheet.right + 0.5)
        issues.push(
          `off page: <${el.tagName.toLowerCase()} class="${el.className}">`,
        );
      const cs = getComputedStyle(el);
      if (
        cs.overflow === "hidden" &&
        el.scrollHeight > el.clientHeight + 2 &&
        !el.matches(".shot, .sheet")
      )
        issues.push(`clipped text in .${el.className}`);
    }
    const content = document.querySelector(".content");
    const free =
      content.getBoundingClientRect().bottom -
      [...content.children].at(-1).getBoundingClientRect().bottom;
    return {
      issues: [...new Set(issues)].slice(0, 15),
      freeMm: free / (96 / 25.4),
    };
  });
  console.log(
    `${pdfName}: free space at bottom of content = ${problems.freeMm.toFixed(1)} mm`,
  );
  for (const p of problems.issues) console.log("  ⚠", p);
  await page.pdf({
    path: join(out, pdfName),
    preferCSSPageSize: true,
    printBackground: true,
  });
  return page;
}

const page = await render(0, "kawan-poster-A1.pdf");
await page.screenshot({
  path: join(out, "preview.png"),
  scale: "css",
  fullPage: false,
});
await render(3, "kawan-poster-A1-bleed3mm.pdf");
await browser.close();
console.log("written to", out);
