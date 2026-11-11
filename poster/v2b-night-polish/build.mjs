// Renders V2B Night Polish to print files:
//   node poster/v2b-night-polish/build.mjs
// → poster/v2b-night-polish/out/kawan-poster-v2B-night-polish.pdf (+ -bleed3mm.pdf, preview.png)
// Warns about anything that overflows the page.
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "../../frontend/node_modules/playwright/index.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "out");
mkdirSync(out, { recursive: true });
const url = pathToFileURL(join(here, "poster.html")).href;
const MM = 96 / 25.4;
const only = process.argv[2]; // optional: "A" or "B"

const browser = await chromium.launch();
async function render({ variant, bleed, pdf, preview }) {
  const w = Math.round((594 + 2 * bleed) * MM);
  const h = Math.round((841 + 2 * bleed) * MM);
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  const qs = new URLSearchParams();
  if (variant === "B") qs.set("v", "day");
  if (bleed) qs.set("bleed", String(bleed));
  await page.goto(url + (qs.size ? `?${qs}` : ""));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForLoadState("networkidle");
  const report = await page.evaluate((MM) => {
    const sheet = document.querySelector(".sheet");
    const issues = [];
    const sb = sheet.getBoundingClientRect();
    for (const el of sheet.querySelectorAll(
      "section, header, footer, .panel, .frame, .phone, .evalp, .voices, .tests",
    )) {
      const r = el.getBoundingClientRect();
      if (r.bottom > sb.bottom + 0.5)
        issues.push(`off page: ${el.tagName.toLowerCase()}.${el.className}`);
    }
    const last = [...sheet.children].at(-1).getBoundingClientRect();
    return {
      issues: issues.slice(0, 10),
      overflowMm: (sheet.scrollHeight - sheet.clientHeight) / MM,
      footerBottomMm: (sb.bottom - last.bottom) / MM,
    };
  }, MM);
  console.log(
    `${pdf}: content overflow ${report.overflowMm.toFixed(1)} mm, space under footer ${report.footerBottomMm.toFixed(1)} mm`,
  );
  for (const i of report.issues) console.log("  ⚠", i);
  await page.pdf({
    path: join(out, pdf),
    preferCSSPageSize: true,
    printBackground: true,
  });
  if (preview)
    await page.screenshot({ path: join(out, preview), scale: "css" });
  await page.close();
}

for (const v of ["A"]) {
  if (only && only !== v) continue;
  const name = "kawan-poster-v2B-night-polish";
  await render({
    variant: v,
    bleed: 0,
    pdf: `${name}.pdf`,
    preview: "preview.png",
  });
  await render({ variant: v, bleed: 3, pdf: `${name}-bleed3mm.pdf` });
}
await browser.close();
console.log("written to", out);
