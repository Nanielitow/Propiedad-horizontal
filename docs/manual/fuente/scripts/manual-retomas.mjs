// Retomas: buscador con la respuesta completa, menú de cuenta, y acciones que no abren diálogo.
import { chromium } from "playwright";
import { readFileSync, writeFileSync } from "node:fs";

const BASE = "http://localhost:3000";
const OUT = "../manual/shots";
const P = "/los-pinos";
const id = JSON.parse(readFileSync("../manual/ids.json", "utf8"));
const browser = await chromium.launch();
const errores = [];
const textos = JSON.parse(readFileSync("../manual/dialogos.json", "utf8"));

async function entrar(page, email) {
  await page.goto(`${BASE}/login`);
  await page.fill("#email", email);
  await page.fill("#password", "Demo1234!");
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30000 });
}
async function esperar(page, ms = 600) {
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(ms);
}
async function paso(page, clave, ruta, accion) {
  try {
    if (ruta) {
      await page.goto(`${BASE}${P}/${ruta}`);
      await esperar(page);
    }
    if (accion) await accion(page);
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${OUT}/flu-${clave}.png` });
    textos[`flu-${clave}`] = await page.evaluate(() =>
      (document.querySelector('[role="dialog"]') || document.querySelector("main") || document.body).innerText.replace(/\s+/g, " ").slice(0, 2500),
    );
    console.log("✓", clave);
  } catch (e) {
    errores.push(`${clave}: ${e.message.split("\n")[0]}`);
  }
}

try {
  const a = await (await browser.newContext({ viewport: { width: 1366, height: 860 } })).newPage();
  await entrar(a, "admin@lospinos.demo");
  await paso(a, "buscador-respuesta", "search", async (p) => {
    await p.getByRole("button", { name: "¿Qué dice el manual sobre las mascotas?" }).click();
    // Esperar a que el texto deje de crecer (la respuesta llega por partes)
    let previo = -1;
    for (let i = 0; i < 60; i++) {
      await p.waitForTimeout(1000);
      const largo = (await p.locator("main").innerText()).length;
      if (largo === previo && i > 4) break;
      previo = largo;
    }
  });
  await paso(a, "menu-cuenta", "documents", async (p) => {
    await p.getByRole("button", { name: "Mi cuenta" }).click();
    await p.getByRole("menuitem", { name: "Cerrar sesión" }).waitFor();
  });
  await a.keyboard.press("Escape");
  await paso(a, "responder-pqrs", `portal/pqrs/${id.pqrs}`, async (p) => {
    await p.getByText("Responder oficialmente", { exact: true }).first().click();
  });
  await paso(a, "conciliacion-consignar", "recaudos/conciliacion", async (p) => {
    const casillas = p.locator('input[type="checkbox"], [role="checkbox"]');
    if (await casillas.count()) await casillas.first().click();
    await p.waitForTimeout(400);
    const boton = p.getByRole("button", { name: "Consignar" });
    if (await boton.isEnabled()) {
      await boton.click();
      await p.locator('[role="dialog"]').first().waitFor({ timeout: 5000 }).catch(() => {});
    }
  });
  await a.keyboard.press("Escape");
  await paso(a, "verificar-extracto", "recaudos/conciliacion", async (p) => {
    await p.getByText("Verificar en extracto").first().click();
    await p.waitForTimeout(800);
  });

  const res = await (await browser.newContext({ viewport: { width: 1366, height: 860 } })).newPage();
  await entrar(res, "residente@lospinos.demo");
  await paso(res, "reservar-salon", "mi-portal/reservas", async (p) => {
    await p.getByText("Salón social", { exact: false }).nth(1).click();
    await esperar(p);
  });
} catch (e) {
  errores.push(`FALLO: ${e.message.split("\n")[0]}`);
} finally {
  writeFileSync("../manual/dialogos.json", JSON.stringify(textos, null, 1));
  await browser.close();
  console.log(errores.length ? `\n${errores.length} error(es):\n- ${errores.join("\n- ")}` : "\nTODO OK");
}
