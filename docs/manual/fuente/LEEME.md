# Fuente del manual de usuario

- `manual.html`: el manual (HTML + CSS de impresión). Las imágenes están en `jpg/`.
- `scripts/`: recorridos de Playwright que toman las capturas (contra la versión de producción de la web en local,
  `node .next/standalone/server.js`, con los datos de demostración restaurados) y `manual-pdf.mjs`, que genera el PDF
  en dos pasadas (la segunda escribe las páginas en el índice). Requiere `playwright` y `pdfjs-dist`.

Para actualizar: rehacer las capturas que cambiaron, editar `manual.html` y volver a generar el PDF.
Las capturas usan el conjunto de demostración Los Pinos (datos ficticios).
