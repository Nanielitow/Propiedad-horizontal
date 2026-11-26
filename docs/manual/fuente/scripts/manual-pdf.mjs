// Genera el manual en PDF en dos pasadas: la primera ubica cada sección; la segunda escribe las páginas en el índice.
import { chromium } from "playwright";
import { getDocument } from "pdfjs-dist/legacy/build/pdf.mjs";
import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";

const HTML = path.resolve("../manual/manual-jpg.html");
const SALIDA = path.resolve("../manual/Manual-de-usuario-PH-Gestion.pdf");
const TMP = path.resolve("../manual/_pase1.pdf");

const pie = `
  <div style="width:100%;font-family:Segoe UI,Arial,sans-serif;font-size:7.5pt;color:#8a929e;padding:0 16mm;display:flex;justify-content:space-between">
    <span>PH Gestión · Manual de usuario</span>
    <span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span>
  </div>`;

async function render(paginas, destino) {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  if (paginas) await page.addInitScript((p) => { window.__paginas = p; }, paginas);
  await page.goto(pathToFileURL(HTML).href, { waitUntil: "load" });
  await page.waitForFunction(() => [...document.images].every((i) => i.complete && i.naturalWidth > 0), null, { timeout: 60000 });
  const titulos = await page.evaluate(() =>
    [...document.querySelectorAll("[data-indice]")].map((h) => ({
      id: h.id,
      // texto visible del título sin el rótulo «Parte N» (para buscarlo en el PDF)
      texto: (h.dataset.nivel === "parte" ? h.dataset.indice.split("·").pop() : h.textContent).replace(/\s+/g, " ").trim(),
    })),
  );
  await page.pdf({
    path: destino,
    format: "A4",
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: "<span></span>",
    footerTemplate: pie,
    margin: { top: "18mm", bottom: "20mm", left: "16mm", right: "16mm" },
    preferCSSPageSize: true,
    outline: true,
    tagged: true,
  });
  await browser.close();
  return titulos;
}

const norm = (s) => s.normalize("NFC").replace(/\s+/g, " ").trim();

const titulos = await render(null, TMP);
const pdf = await getDocument({ data: new Uint8Array(readFileSync(TMP)) }).promise;
const textos = [];
for (let i = 1; i <= pdf.numPages; i++) {
  const c = await (await pdf.getPage(i)).getTextContent();
  textos.push(norm(c.items.map((x) => x.str).join(" ")));
}
// Las primeras páginas son portada e índice: se busca después de ellas
const inicio = textos.findIndex((t) => t.includes("Cómo usar este manual") && !t.includes("Contenido"));
const paginas = {};
let desde = Math.max(inicio, 0);
for (const t of titulos) {
  const idx = textos.findIndex((tx, i) => i >= desde && tx.includes(norm(t.texto)));
  if (idx >= 0) {
    paginas[t.id] = idx + 1;
    desde = idx;
  } else console.log("sin ubicar:", t.texto);
}
await render(paginas, SALIDA);
const final = await getDocument({ data: new Uint8Array(readFileSync(SALIDA)) }).promise;
console.log(`PDF listo: ${final.numPages} páginas · ${Object.keys(paginas).length}/${titulos.length} secciones con página`);
writeFileSync("../manual/paginas.json", JSON.stringify(paginas, null, 1));
