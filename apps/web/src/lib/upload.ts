"use client";

/** Huella SHA-256 del archivo, calculada en el navegador (Web Crypto). El backend
 *  la usa para detectar duplicados y el worker para verificar la integridad. */
export async function sha256Hex(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** PUT directo al almacenamiento S3 con la URL firmada. Se usa XMLHttpRequest
 *  porque fetch no informa del progreso de subida. */
export function putWithProgress(
  url: string,
  file: File,
  headers: Record<string, string>,
  onProgress: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(`El almacenamiento rechazó el archivo (HTTP ${xhr.status})`));
    xhr.onerror = () => reject(new Error("No se pudo conectar con el almacenamiento de archivos"));
    xhr.send(file);
  });
}
