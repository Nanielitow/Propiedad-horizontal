import { Building2 } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Política de tratamiento de datos" };

// Debe coincidir con POLITICA_VERSION de la API (app/services/cuentas/enlaces.py): si cambia el texto de fondo,
// se sube la versión y quienes ya aceptaron la anterior la vuelven a aceptar.
const VERSION = "25 de noviembre de 2026";
const CONTACTO = process.env.NEXT_PUBLIC_CONTACT_EMAIL;

export default function Page() {
  return (
    <div className="min-h-dvh bg-background">
      <header className="flex items-center gap-2.5 bg-sidebar px-4 py-3 sm:px-6">
        <div className="flex size-8 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
          <Building2 className="size-4.5" />
        </div>
        <Link href="/login" className="font-semibold tracking-tight text-white">
          PH Gestión
        </Link>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
        <article className="space-y-5 text-sm leading-relaxed [&_h2]:mt-8 [&_h2]:text-base [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Política de tratamiento de datos personales</h1>
            <p className="mt-1 text-muted-foreground">Versión del {VERSION} · Ley 1581 de 2012 y Decreto 1074 de 2015</p>
          </div>

          <h2>1. Quién trata sus datos</h2>
          <p>
            <strong>Responsable:</strong> la copropiedad (persona jurídica de propiedad horizontal, Ley 675 de 2001) a la
            que usted pertenece como propietario, residente, miembro del consejo o colaborador. Ella decide qué datos se
            registran y para qué.
          </p>
          <p>
            <strong>Encargado:</strong> PH Gestión, la plataforma que la copropiedad usa para su administración. Trata
            los datos únicamente por cuenta y según las instrucciones de la copropiedad, y no los usa para fines propios
            ni los vende.
          </p>

          <h2>2. Qué datos se tratan</h2>
          <ul>
            <li>Identificación y contacto: nombre, tipo y número de documento, correo electrónico y teléfonos.</li>
            <li>Relación con la copropiedad: unidad, calidad (propietario, arrendatario, residente), coeficiente y vehículos.</li>
            <li>Información financiera de la copropiedad: cuotas, pagos, saldos, paz y salvos y recaudos.</li>
            <li>Solicitudes y participación: PQRS, reservas de zonas comunes, asistencia y votos en asambleas.</li>
            <li>Datos de la cuenta: fechas de ingreso y registros técnicos de seguridad (no se guardan contraseñas legibles).</li>
          </ul>
          <p>No se solicitan datos sensibles. Si un documento cargado los contuviera, se tratarán con la reserva que exige la ley.</p>

          <h2>3. Para qué se usan</h2>
          <ul>
            <li>Administrar la copropiedad: facturación y recaudo de cuotas, cartera, paz y salvos y contabilidad.</li>
            <li>Comunicaciones: circulares, respuestas a PQRS, avisos de reservas, recordatorios y convocatorias.</li>
            <li>Asambleas: verificación de quórum por coeficiente, votaciones y actas.</li>
            <li>Mantenimiento y seguridad de las zonas comunes, y cumplimiento de obligaciones legales.</li>
            <li>Seguridad de la plataforma: controlar el acceso y prevenir usos indebidos.</li>
          </ul>

          <h2>4. Sus derechos</h2>
          <p>Como titular puede, de forma gratuita:</p>
          <ul>
            <li>Conocer, actualizar y rectificar sus datos.</li>
            <li>Pedir prueba de la autorización que otorgó.</li>
            <li>Saber qué uso se ha dado a sus datos.</li>
            <li>Revocar la autorización o pedir la supresión cuando no exista un deber legal o contractual de conservarlos.</li>
            <li>Presentar quejas ante la Superintendencia de Industria y Comercio.</li>
          </ul>

          <h2>5. Cómo ejercerlos</h2>
          <p>
            Diríjase a la administración de su copropiedad (por ejemplo, radicando una PQRS en el portal). Las consultas se
            responden en máximo 10 días hábiles y los reclamos en máximo 15 días hábiles, según la Ley 1581 de 2012.
            {CONTACTO && (
              <>
                {" "}
                Para asuntos sobre la plataforma puede escribir a{" "}
                <a href={`mailto:${CONTACTO}`} className="text-primary underline-offset-4 hover:underline">
                  {CONTACTO}
                </a>
                .
              </>
            )}
          </p>

          <h2>6. Seguridad y proveedores</h2>
          <p>
            Cada copropiedad está aislada de las demás en la base de datos y cada rol solo ve lo que le corresponde. Las
            conexiones van cifradas y las contraseñas se guardan con algoritmos de una sola vía. Para operar, la plataforma
            usa proveedores de infraestructura que pueden almacenar o procesar datos fuera de Colombia (principalmente en
            Estados Unidos): alojamiento de la aplicación y de la base de datos, almacenamiento de archivos, envío de
            correos y análisis de documentos con inteligencia artificial. Estos proveedores actúan bajo contratos que les
            impiden usar los datos para fines propios.
          </p>

          <h2>7. Conservación y cambios</h2>
          <p>
            Los datos se conservan mientras usted tenga relación con la copropiedad y durante los plazos que exigen las
            normas contables y de propiedad horizontal. Si esta política cambia de fondo, se le pedirá aceptarla de nuevo
            al entrar.
          </p>
        </article>
      </main>
    </div>
  );
}
