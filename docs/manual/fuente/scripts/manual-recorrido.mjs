// Recorre todas las pantallas por rol: captura + estructura (títulos, botones, pestañas, columnas, campos, texto).
// Solo lectura (no hace clic en acciones que guarden). Salida: ../manual/shots/*.png y ../manual/pantallas.json
import { chromium, devices } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";

const BASE = "http://localhost:3000";
const OUT = "../manual/shots";
mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const datos = {};
const errores = [];

async function entrar(page, email) {
  await page.goto(`${BASE}/login`);
  await page.fill("#email", email);
  await page.fill("#password", "Demo1234!");
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30000 });
}

async function esperar(page) {
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  for (let i = 0; i < 20; i++) {
    if (!(await page.locator('[data-slot="skeleton"], .animate-pulse').count())) break;
    await page.waitForTimeout(300);
  }
  await page.waitForTimeout(400);
}

async function estructura(page) {
  return page.evaluate(() => {
    const txt = (el) => (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
    const uniq = (a) => [...new Set(a.filter(Boolean))];
    const main = document.querySelector("main") || document.body;
    return {
      titulo: txt(document.querySelector("h1") || {}),
      botones: uniq([...main.querySelectorAll("button, a[role=button], a[data-slot=button]")].map(txt)).slice(0, 60),
      pestanas: uniq([...document.querySelectorAll('[role="tab"]')].map(txt)),
      columnas: uniq([...main.querySelectorAll("th")].map(txt)),
      campos: uniq([...main.querySelectorAll("label")].map(txt)).slice(0, 60),
      texto: txt(main).slice(0, 3500),
    };
  });
}

async function capturar(page, rol, clave, ruta, opciones = {}) {
  try {
    if (ruta) await page.goto(`${BASE}${ruta}`);
    await esperar(page);
    const archivo = `${rol}-${clave}.png`;
    await page.screenshot({ path: `${OUT}/${archivo}`, fullPage: !!opciones.completa });
    datos[`${rol}/${clave}`] = { ruta, archivo, ...(await estructura(page)) };
    console.log("✓", rol, clave);
  } catch (e) {
    errores.push(`${rol} ${clave}: ${e.message.split("\n")[0]}`);
  }
}

async function ids(page) {
  return page.evaluate(async () => {
    const j = (u) => fetch(`/api/proxy${u}`).then((r) => (r.ok ? r.json() : null));
    const me = await j("/auth/me");
    const t = me.memberships.find((m) => m.tenant_slug === "los-pinos").tenant_id;
    const b = `/tenants/${t}`;
    const primero = (x) => (Array.isArray(x) ? x[0] : x?.items?.[0]);
    const [unidades, activos, asambleas, actas, cotiz, pqrs] = await Promise.all([
      j(`${b}/unidades`), j(`${b}/activos`), j(`${b}/asambleas`), j(`${b}/minutes`), j(`${b}/quote-comparisons`), j(`${b}/portal/pqrs`),
    ]);
    const cerrada = asambleas?.find((a) => a.estado === "CERRADA") ?? asambleas?.[0];
    const enCurso = asambleas?.find((a) => a.estado !== "CERRADA") ?? asambleas?.[0];
    return {
      unidad: primero(unidades)?.id, activo: primero(activos)?.id, asambleaCerrada: cerrada?.id, asambleaOtra: enCurso?.id,
      acta: primero(actas)?.document_id ?? primero(actas)?.id, cotizacion: primero(cotiz)?.id, pqrs: primero(pqrs)?.id,
    };
  });
}

const P = "/los-pinos";
try {
  // --- Pantallas públicas ---------------------------------------------------------------------
  const pub = await (await browser.newContext({ viewport: { width: 1366, height: 860 } })).newPage();
  await capturar(pub, "publico", "login", "/login");
  await capturar(pub, "publico", "recuperar", "/recuperar");
  await capturar(pub, "publico", "demo", "/demo");
  await capturar(pub, "publico", "privacidad", "/privacidad");

  // --- Administración ---------------------------------------------------------------------------
  const adm = await (await browser.newContext({ viewport: { width: 1366, height: 860 } })).newPage();
  await entrar(adm, "admin@lospinos.demo");
  const id = await ids(adm);
  writeFileSync("../manual/ids.json", JSON.stringify(id, null, 2));
  const rutasAdmin = [
    ["buscador", "search"], ["documentos", "documents"], ["vencimientos", "deadlines"], ["cotizaciones", "quotes"],
    ["actas", "minutes"], ["unidades", "unidades"], ["directorio", "unidades/directorio"], ["importar", "unidades/importar"],
    ["asambleas", "asambleas"], ["usuarios", "usuarios"],
    ["cartera", "cartera"], ["cartera-periodos", "cartera/periodos"], ["cartera-pagos", "cartera/pagos"],
    ["cartera-morosos", "cartera/morosos"], ["cartera-config", "cartera/configuracion"],
    ["recaudos", "recaudos"], ["recaudos-nuevo", "recaudos/nuevo"], ["recaudos-movimientos", "recaudos/movimientos"],
    ["recaudos-caja", "recaudos/caja"], ["recaudos-conciliacion", "recaudos/conciliacion"], ["recaudos-alertas", "recaudos/alertas"],
    ["recaudos-reportes", "recaudos/reportes"], ["recaudos-config", "recaudos/configuracion"],
    ["activos-panel", "activos/panel"], ["activos", "activos"], ["activos-calendario", "activos/calendario"],
    ["activos-novedades", "activos/novedades"], ["activos-recomendaciones", "activos/recomendaciones"],
    ["activos-planes", "activos/planes"], ["activos-contratistas", "activos/contratistas"], ["activos-reportes", "activos/reportes"],
    ["portal-pqrs", "portal/pqrs"], ["portal-circulares", "portal/circulares"], ["portal-reservas", "portal/reservas"],
  ];
  for (const [clave, r] of rutasAdmin) await capturar(adm, "admin", clave, `${P}/${r}`);
  const detalles = [
    ["unidad", `unidades/${id.unidad}`], ["activo", `activos/${id.activo}`], ["asamblea-cerrada", `asambleas/${id.asambleaCerrada}`],
    ["asamblea-otra", `asambleas/${id.asambleaOtra}`], ["acta", `minutes/${id.acta}`], ["cotizacion", `quotes/${id.cotizacion}`],
    ["pqrs", `portal/pqrs/${id.pqrs}`], ["estado-cuenta", `cartera/unidades/${id.unidad}`],
  ];
  for (const [clave, r] of detalles) await capturar(adm, "admin", clave, `${P}/${r}`);
  // Pestañas de la ficha de unidad y del activo
  for (const [base, r] of [["unidad", `unidades/${id.unidad}`], ["activo", `activos/${id.activo}`]]) {
    await adm.goto(`${BASE}${P}/${r}`);
    await esperar(adm);
    const tabs = await adm.locator('[role="tab"]').allInnerTexts();
    for (const [i, t] of tabs.entries()) {
      if (i === 0) continue;
      await adm.locator('[role="tab"]').nth(i).click();
      await capturar(adm, "admin", `${base}-tab${i}`, null);
      datos[`admin/${base}-tab${i}`].pestana = t;
    }
  }
  // Menú de cuenta
  await adm.goto(`${BASE}${P}/search`);
  await esperar(adm);
  await adm.getByRole("button", { name: "Mi cuenta" }).click();
  await capturar(adm, "admin", "menu-cuenta", null);
  await adm.keyboard.press("Escape");

  // --- Otros roles ------------------------------------------------------------------------------
  const roles = [
    ["recepcion", "recepcion@lospinos.demo", ["recaudos-nuevo", "recaudos/nuevo"], ["recaudos-caja", "recaudos/caja"], ["portal-pqrs", "portal/pqrs"], ["unidades", "unidades"]],
    ["contabilidad", "contabilidad@lospinos.demo", ["recaudos", "recaudos"], ["recaudos-conciliacion", "recaudos/conciliacion"], ["cartera", "cartera"]],
    ["consejo", "consejo@lospinos.demo", ["recaudos", "recaudos"], ["activos-panel", "activos/panel"], ["cartera", "cartera"]],
    ["tecnico", "tecnico@lospinos.demo", ["mi-trabajo", "activos/mi-trabajo"], ["activos-novedades", "activos/novedades"]],
  ];
  for (const [rol, email, ...rutas] of roles) {
    const p = await (await browser.newContext({ viewport: { width: 1366, height: 860 } })).newPage();
    await entrar(p, email);
    await capturar(p, rol, "inicio", null);
    for (const [clave, r] of rutas) await capturar(p, rol, clave, `${P}/${r}`);
    await p.context().close();
  }

  // --- Residente: escritorio y celular ------------------------------------------------------------
  const rutasRes = [["inicio", "inicio"], ["mi-cuenta", "mi-cuenta"], ["pqrs", "mi-portal/pqrs"], ["circulares", "mi-portal/circulares"],
    ["reservas", "mi-portal/reservas"], ["asambleas", "asambleas"], ["mi-unidad", "mi-unidad"], ["buscador", "search"], ["documentos", "documents"]];
  const res = await (await browser.newContext({ viewport: { width: 1366, height: 860 } })).newPage();
  await entrar(res, "residente@lospinos.demo");
  for (const [clave, r] of rutasRes) await capturar(res, "residente", clave, `${P}/${r}`);
  const movil = await (await browser.newContext({ ...devices["iPhone 13"] })).newPage();
  await entrar(movil, "residente@lospinos.demo");
  for (const [clave, r] of rutasRes.slice(0, 5)) await capturar(movil, "movil", clave, `${P}/${r}`);
} catch (e) {
  errores.push(`FALLO: ${e.message.split("\n")[0]}`);
} finally {
  writeFileSync("../manual/pantallas.json", JSON.stringify(datos, null, 1));
  await browser.close();
  console.log(`\n${Object.keys(datos).length} pantallas`, errores.length ? `\n${errores.length} error(es):\n- ${errores.join("\n- ")}` : "");
}
