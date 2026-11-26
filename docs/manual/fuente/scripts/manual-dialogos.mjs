// Segunda pasada: abre los diálogos y formularios principales (sin guardar) y una respuesta real del buscador.
import { chromium, devices } from "playwright";
import { readFileSync, writeFileSync } from "node:fs";

const BASE = "http://localhost:3000";
const OUT = "../manual/shots";
const P = "/los-pinos";
const id = JSON.parse(readFileSync("../manual/ids.json", "utf8"));
const browser = await chromium.launch();
const errores = [];
const textos = {};

async function entrar(page, email) {
  await page.goto(`${BASE}/login`);
  await page.fill("#email", email);
  await page.fill("#password", "Demo1234!");
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30000 });
}
async function esperar(page, ms = 500) {
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(ms);
}
async function guardarTexto(page, clave) {
  textos[clave] = await page.evaluate(() => {
    const d = document.querySelector('[role="dialog"], [role="alertdialog"]') || document.querySelector("main") || document.body;
    return (d.innerText || "").replace(/\s+/g, " ").trim().slice(0, 2500);
  });
}
/** Abre un diálogo con el botón `boton` en `ruta`, toma la captura y lo cierra. */
async function dialogo(page, clave, ruta, boton, antes) {
  try {
    if (ruta) {
      await page.goto(`${BASE}${P}/${ruta}`);
      await esperar(page);
    }
    if (antes) await antes(page);
    await page.getByRole("button", { name: boton, exact: false }).first().click();
    await page.locator('[role="dialog"], [role="alertdialog"]').first().waitFor({ timeout: 8000 });
    await page.waitForTimeout(700);
    await page.screenshot({ path: `${OUT}/dlg-${clave}.png` });
    await guardarTexto(page, `dlg-${clave}`);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    console.log("✓", clave);
  } catch (e) {
    errores.push(`${clave}: ${e.message.split("\n")[0]}`);
  }
}
async function pantalla(page, clave, ruta, accion) {
  try {
    if (ruta) {
      await page.goto(`${BASE}${P}/${ruta}`);
      await esperar(page);
    }
    if (accion) await accion(page);
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${OUT}/flu-${clave}.png` });
    await guardarTexto(page, `flu-${clave}`);
    console.log("✓", clave);
  } catch (e) {
    errores.push(`${clave}: ${e.message.split("\n")[0]}`);
  }
}

try {
  const a = await (await browser.newContext({ viewport: { width: 1366, height: 860 } })).newPage();
  await entrar(a, "admin@lospinos.demo");

  // Buscador: una pregunta real (respuesta con citas)
  await pantalla(a, "buscador-respuesta", "search", async (p) => {
    await p.getByRole("button", { name: "¿Qué dice el manual sobre las mascotas?" }).click();
    await p.waitForTimeout(2000);
    await p.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
    await p.waitForTimeout(4000);
  });
  // Menú de cuenta (desplegado)
  await pantalla(a, "menu-cuenta", "documents", async (p) => {
    await p.getByRole("button", { name: "Mi cuenta" }).click();
    await p.getByRole("menuitem", { name: "Cerrar sesión" }).waitFor();
  });
  await a.keyboard.press("Escape");
  // Selector de copropiedad (demo: el administrador de Los Pinos solo tiene una; se ilustra igual)
  await pantalla(a, "vencimientos-calendario", "deadlines", async (p) => {
    await p.getByRole("tab", { name: "Calendario" }).click();
  });

  await dialogo(a, "subir-documentos", "documents", "Subir documentos");
  await dialogo(a, "nueva-comparacion", "quotes", "Nueva comparación");
  await dialogo(a, "subir-acta", "minutes", "Subir acta");
  await dialogo(a, "nueva-unidad", "unidades", "Nueva unidad");
  await dialogo(a, "agregar-persona", `unidades/${id.unidad}`, "Agregar persona");
  await dialogo(a, "programar-asamblea", "asambleas", "Programar asamblea");
  await dialogo(a, "facturar-mes", "cartera/periodos", "Facturar mes");
  await dialogo(a, "cuota-extra", "cartera/periodos", "Cuota extraordinaria o multa");
  await dialogo(a, "registrar-pago", "cartera/pagos", "Registrar pago");
  await dialogo(a, "paz-y-salvo", `cartera/unidades/${id.unidad}`, "Paz y salvo");
  await dialogo(a, "nuevo-concepto", "recaudos/configuracion", "Nuevo concepto");
  await dialogo(a, "nueva-zona", "recaudos/configuracion", "Nueva zona");
  await dialogo(a, "consignar", "recaudos/conciliacion", "Consignar");
  await dialogo(a, "verificar-extracto", "recaudos/conciliacion", "Verificar en extracto");
  await dialogo(a, "nuevo-activo", "activos", "Nuevo activo");
  await dialogo(a, "etiquetas-qr", "activos", "Etiquetas QR");
  await dialogo(a, "reportar-falla", "activos/novedades", "Reportar falla");
  await dialogo(a, "registrar-mantenimiento", `activos/${id.activo}`, "Registrar mantenimiento");
  await dialogo(a, "ejecutar", "activos/calendario", "Ejecutar");
  await dialogo(a, "nuevo-plan", "activos/planes", "Nuevo plan");
  await dialogo(a, "nuevo-contratista", "activos/contratistas", "Nuevo contratista");
  await dialogo(a, "nueva-recomendacion", "activos/recomendaciones", "Nueva");
  await dialogo(a, "radicar-pqrs", "portal/pqrs", "Radicar PQRS");
  await dialogo(a, "responder-pqrs", `portal/pqrs/${id.pqrs}`, "Responder oficialmente");
  await dialogo(a, "nueva-circular", "portal/circulares", "Nueva circular");
  await dialogo(a, "reglas-zona", "portal/reservas", "Reglas");
  await pantalla(a, "reportes-recaudos-informe", "recaudos/reportes", async (p) => {
    await p.getByRole("button", { name: "Ver informe" }).click();
    await esperar(p, 1500);
  });
  await pantalla(a, "reportes-activos-informe", "activos/reportes", async (p) => {
    await p.getByRole("button", { name: /Costos y proyección/ }).click();
    await esperar(p, 1500);
  });
  await pantalla(a, "pqrs-bandeja-vencidas", "portal/pqrs", async (p) => {
    await p.getByRole("button", { name: "Vencidas" }).click();
    await esperar(p);
  });

  // Recepción: registrar un parqueadero (sin guardar) y su caja
  const r = await (await browser.newContext({ viewport: { width: 1366, height: 860 } })).newPage();
  await entrar(r, "recepcion@lospinos.demo");
  await pantalla(r, "recaudo-parqueadero", "recaudos/nuevo", async (p) => {
    await p.getByRole("radio", { name: /Parqueadero de visitantes/ }).click().catch(async () => {
      await p.getByRole("button", { name: /Parqueadero de visitantes/ }).click();
    });
    await p.waitForTimeout(500);
    const placa = p.getByLabel(/Placa/i).first();
    if (await placa.count()) await placa.fill("ABC123");
  });
  await pantalla(r, "recaudo-zona", "recaudos/nuevo", async (p) => {
    await p.getByRole("radio", { name: /Alquiler de zonas sociales/ }).click().catch(async () => {
      await p.getByRole("button", { name: /Alquiler de zonas sociales/ }).click();
    });
  });
  await dialogo(r, "cerrar-caja", "recaudos/caja", "Cerrar caja");
  await dialogo(r, "entregar-administracion", "recaudos/caja", "Entregar a administración");

  // Técnico: celular
  const t = await (await browser.newContext({ ...devices["iPhone 13"] })).newPage();
  await entrar(t, "tecnico@lospinos.demo");
  await pantalla(t, "tecnico-movil", "activos/mi-trabajo");
  await dialogo(t, "tecnico-ejecutar", "activos/mi-trabajo", "Ejecutar");

  // Residente
  const res = await (await browser.newContext({ viewport: { width: 1366, height: 860 } })).newPage();
  await entrar(res, "residente@lospinos.demo");
  await dialogo(res, "nueva-pqrs", "mi-portal/pqrs", "Nueva PQRS");
  await pantalla(res, "reservar-salon", "mi-portal/reservas", async (p) => {
    await p.getByRole("button", { name: /Salón social/ }).click();
    await esperar(p);
  });
  await pantalla(res, "circular-abierta", "mi-portal/circulares", async (p) => {
    await p.getByRole("button", { name: /Convocatoria a la asamblea/ }).first().click();
    await esperar(p);
  });
  await pantalla(res, "asamblea-residente", `asambleas/${id.asambleaCerrada}`);
} catch (e) {
  errores.push(`FALLO: ${e.message.split("\n")[0]}`);
} finally {
  writeFileSync("../manual/dialogos.json", JSON.stringify(textos, null, 1));
  await browser.close();
  console.log(errores.length ? `\n${errores.length} error(es):\n- ${errores.join("\n- ")}` : "\nTODO OK");
}
