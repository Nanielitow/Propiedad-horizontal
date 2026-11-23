"use client";

// Selector de Google Drive (Google Identity Services + Google Picker).
//
// Alcance `drive.file`: la app solo obtiene acceso a los archivos que el usuario
// ELIGE en el selector, nunca al resto de su Drive. El token de acceso dura ~1 h,
// vive solo en memoria y se envía a la API únicamente para descargar lo elegido.

export interface GoogleConfig {
  enabled: true;
  clientId: string;
  apiKey: string;
  appId: string;
}

export interface ArchivoElegido {
  id: string;
  name: string;
  mimeType: string;
}

const SCOPE = "https://www.googleapis.com/auth/drive.file";
const MIME_ADMITIDOS = [
  "application/pdf",
  "application/vnd.google-apps.document",
  "application/vnd.google-apps.presentation",
  "application/vnd.google-apps.spreadsheet",
].join(",");

// --- Tipos mínimos de las librerías de Google (evita una dependencia solo de tipos) ---

interface TokenResponse {
  access_token?: string;
  error?: string;
}
interface TokenClient {
  callback: (r: TokenResponse) => void;
  error_callback?: (e: { type: string }) => void;
  requestAccessToken: (opts?: { prompt?: string }) => void;
}
interface PickerDoc {
  id: string;
  name: string;
  mimeType: string;
}
interface PickerData {
  action: string;
  docs?: PickerDoc[];
}
interface PickerBuilder {
  addView: (v: unknown) => PickerBuilder;
  setOAuthToken: (t: string) => PickerBuilder;
  setDeveloperKey: (k: string) => PickerBuilder;
  setAppId: (id: string) => PickerBuilder;
  setLocale: (l: string) => PickerBuilder;
  setTitle: (t: string) => PickerBuilder;
  enableFeature: (f: unknown) => PickerBuilder;
  setCallback: (cb: (d: PickerData) => void) => PickerBuilder;
  build: () => { setVisible: (v: boolean) => void };
}
interface DocsView {
  setMimeTypes: (m: string) => DocsView;
  setIncludeFolders: (v: boolean) => DocsView;
  setSelectFolderEnabled: (v: boolean) => DocsView;
  setEnableDrives: (v: boolean) => DocsView;
  setOwnedByMe: (v: boolean) => DocsView;
  setParent: (id: string) => DocsView;
  setLabel?: (label: string) => DocsView; // no está en todas las versiones del Picker
}
interface GoogleGlobal {
  accounts: {
    oauth2: {
      initTokenClient: (cfg: { client_id: string; scope: string; callback: (r: TokenResponse) => void }) => TokenClient;
      revoke?: (token: string, done: () => void) => void;
    };
  };
  picker: {
    PickerBuilder: new () => PickerBuilder;
    DocsView: new (viewId?: unknown) => DocsView;
    ViewId: { DOCS: unknown };
    Feature: { MULTISELECT_ENABLED: unknown; SUPPORT_DRIVES: unknown };
    Action: { PICKED: string; CANCEL: string };
  };
}
interface GapiGlobal {
  load: (lib: string, cb: { callback: () => void; onerror: () => void }) => void;
}
declare global {
  interface Window {
    google?: GoogleGlobal;
    gapi?: GapiGlobal;
  }
}

// --- Carga de scripts -------------------------------------------------------------

const cargados = new Map<string, Promise<void>>();

function cargarScript(src: string): Promise<void> {
  const existente = cargados.get(src);
  if (existente) return existente;
  const promesa = new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => {
      cargados.delete(src);
      reject(new Error("No se pudo cargar Google: revise su conexión"));
    };
    document.head.appendChild(s);
  });
  cargados.set(src, promesa);
  return promesa;
}

/** Precarga todo lo necesario. Conviene llamarla al abrir el diálogo: el navegador
 *  solo permite la ventana de permisos de Google si se abre en el mismo clic. */
export async function prepararGoogle(): Promise<void> {
  await Promise.all([cargarScript("https://accounts.google.com/gsi/client"), cargarScript("https://apis.google.com/js/api.js")]);
  await new Promise<void>((resolve, reject) => {
    window.gapi?.load("picker", { callback: resolve, onerror: () => reject(new Error("No se pudo cargar el selector de Google")) });
  });
}

// --- Token y selector --------------------------------------------------------------

let tokenClient: TokenClient | null = null;
let tokenActual: { valor: string; vence: number } | null = null;
let elegirCuenta = false;

/** Olvida la cuenta actual: el próximo permiso muestra el selector de cuentas de Google. */
export function cambiarCuenta(): void {
  if (tokenActual) window.google?.accounts.oauth2.revoke?.(tokenActual.valor, () => undefined);
  tokenActual = null;
  elegirCuenta = true;
}

export function hayCuentaConectada(): boolean {
  return tokenActual !== null && tokenActual.vence > Date.now();
}

function pedirToken(config: GoogleConfig): Promise<string> {
  if (tokenActual && tokenActual.vence > Date.now() + 60_000) return Promise.resolve(tokenActual.valor);
  const google = window.google;
  if (!google) return Promise.reject(new Error("Google no está cargado"));
  return new Promise((resolve, reject) => {
    tokenClient ??= google.accounts.oauth2.initTokenClient({ client_id: config.clientId, scope: SCOPE, callback: () => undefined });
    tokenClient.callback = (r) => {
      if (r.error || !r.access_token) return reject(new Error("Google no concedió el permiso"));
      tokenActual = { valor: r.access_token, vence: Date.now() + 55 * 60_000 };
      elegirCuenta = false;
      resolve(r.access_token);
    };
    tokenClient.error_callback = (e) =>
      reject(new Error(e.type === "popup_closed" ? "Se cerró la ventana de Google" : "El navegador bloqueó la ventana de Google"));
    // "" reutiliza la cuenta que ya dio permiso; "select_account" deja elegir otra
    tokenClient.requestAccessToken({ prompt: elegirCuenta ? "select_account" : "" });
  });
}

/** Abre el selector de Google y devuelve el token y los archivos elegidos (null si cancela). */
export async function elegirDeDrive(config: GoogleConfig): Promise<{ token: string; archivos: ArchivoElegido[] } | null> {
  const token = await pedirToken(config);
  const google = window.google;
  if (!google) throw new Error("Google no está cargado");
  // Una pestaña por origen. Ojo: setEnableDrives(true) convierte la vista en "solo
  // unidades compartidas", por eso Mi unidad y lo compartido van en pestañas aparte.
  const nueva = (etiqueta: string) => {
    const v = new google.picker.DocsView(google.picker.ViewId.DOCS)
      .setMimeTypes(MIME_ADMITIDOS)
      .setIncludeFolders(true)
      .setSelectFolderEnabled(false);
    return v.setLabel?.(etiqueta) ?? v;
  };
  const miUnidad = nueva("Mi unidad").setParent("root"); // carpetas propias desde la raíz
  const compartidos = nueva("Compartidos conmigo").setOwnedByMe(false);
  const unidades = nueva("Unidades compartidas").setEnableDrives(true);
  return new Promise((resolve) => {
    new google.picker.PickerBuilder()
      .addView(miUnidad)
      .addView(compartidos)
      .addView(unidades)
      .setOAuthToken(token)
      .setDeveloperKey(config.apiKey)
      // Imprescindible con drive.file: así Google concede acceso a los archivos elegidos
      .setAppId(config.appId)
      .setLocale("es")
      .setTitle("Elija los documentos a importar")
      .enableFeature(google.picker.Feature.MULTISELECT_ENABLED)
      .enableFeature(google.picker.Feature.SUPPORT_DRIVES)
      .setCallback((d) => {
        if (d.action === google.picker.Action.PICKED) {
          resolve({ token, archivos: (d.docs ?? []).map(({ id, name, mimeType }) => ({ id, name, mimeType })) });
        } else if (d.action === google.picker.Action.CANCEL) {
          resolve(null);
        }
      })
      .build()
      .setVisible(true);
  });
}
