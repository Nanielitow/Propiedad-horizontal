// Copia el worker de pdf.js a /public para servirlo como archivo estático.
// Se toma la MISMA versión que usa react-pdf (si las versiones no coinciden,
// pdf.js falla en tiempo de ejecución). Se ejecuta antes de dev y build.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const candidates = [
  join("node_modules", "react-pdf", "node_modules", "pdfjs-dist"), // versión anidada (si la hay)
  join("node_modules", "pdfjs-dist"), // versión elevada (hoisted)
];
const pdfjsDir = candidates.find((dir) => existsSync(join(dir, "package.json")));
if (!pdfjsDir) {
  console.error("No se encontró pdfjs-dist. ¿Ejecutó npm install?");
  process.exit(1);
}

mkdirSync("public", { recursive: true });
copyFileSync(join(pdfjsDir, "build", "pdf.worker.min.mjs"), join("public", "pdf.worker.min.mjs"));
console.log(`pdf.worker.min.mjs copiado desde ${pdfjsDir}`);
