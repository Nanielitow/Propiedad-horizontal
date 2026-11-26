import { Building2 } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { POLITICA_FECHA } from "@/lib/politica";

export const metadata: Metadata = { title: "Política de tratamiento de datos" };

// La versión está en lib/politica.ts y debe coincidir con la de la API. Si cambia el texto de fondo, se suben las dos
// y quienes aceptaron la anterior la vuelven a aceptar al entrar.
const CORREO = "9bgonzalezdaniel@gmail.com";
const WHATSAPP = "311 494 0699";

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
        <article className="space-y-5 text-sm leading-relaxed [&_h2]:mt-8 [&_h2]:text-base [&_h2]:font-semibold [&_h3]:mt-4 [&_h3]:font-semibold [&_li]:ml-5 [&_li]:list-disc">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Política de tratamiento de datos personales</h1>
            <p className="mt-1 text-muted-foreground">
              Vigente desde el {POLITICA_FECHA} · Ley 1581 de 2012, Decreto 1074 de 2015 (capítulos 25 y 26) y demás normas
              concordantes
            </p>
          </div>

          <h2>1. Quién trata sus datos</h2>
          <p>
            <strong>Responsable del tratamiento:</strong> la copropiedad (persona jurídica de propiedad horizontal, Ley 675 de
            2001) a la que usted pertenece como propietario, arrendatario, residente, miembro del consejo o colaborador. Ella
            decide qué datos se registran y para qué, y es ante quien usted ejerce principalmente sus derechos. Cada
            copropiedad tiene, además, su propia política de tratamiento de datos.
          </p>
          <p>
            <strong>Encargado del tratamiento:</strong> la plataforma <strong>PH Gestión</strong>, que la copropiedad usa para
            su administración, operada por:
          </p>
          <ul>
            <li>
              <strong>Daniel Alejandro González Floriano</strong>, persona natural, nombre comercial «PH Gestión».
            </li>
            <li>Domicilio: Bogotá D. C., Colombia. Dirección: Calle 29 # 32-30, Edificio Romac PH.</li>
            <li>
              Correo:{" "}
              <a href={`mailto:${CORREO}`} className="text-primary underline-offset-4 hover:underline">
                {CORREO}
              </a>{" "}
              · Teléfono y WhatsApp:{" "}
              <a href="https://wa.me/573114940699" className="text-primary underline-offset-4 hover:underline">
                {WHATSAPP}
              </a>
            </li>
          </ul>
          <p>
            El encargado trata los datos únicamente por cuenta de la copropiedad y según sus instrucciones, en virtud de un
            contrato de transmisión de datos. No los usa para fines propios, no los vende ni los comparte con terceros para
            publicidad.
          </p>

          <h2>2. Qué datos se tratan</h2>
          <ul>
            <li>Identificación y contacto: nombre, tipo y número de documento, correo electrónico y teléfonos.</li>
            <li>Relación con la copropiedad: unidad, calidad (propietario, arrendatario, residente, autorizado), coeficiente y vehículos.</li>
            <li>Información financiera de la copropiedad: cuotas, pagos, saldos, paz y salvos y recaudos.</li>
            <li>Solicitudes y participación: PQRS, reservas de zonas comunes, asistencia, poderes y votos en asambleas.</li>
            <li>Documentos de la copropiedad que cargue la administración (actas, contratos, reglamentos), con su texto.</li>
            <li>
              Datos técnicos y de seguridad: fechas de ingreso, dirección IP (para prevenir abusos y limitar intentos) y
              registros de los cambios hechos en la plataforma. Las contraseñas se guardan cifradas de forma irreversible.
            </li>
          </ul>
          <p>
            No se solicitan datos sensibles (salud, origen racial, orientación política o religiosa, biométricos). Si un
            documento cargado los contuviera, se tratarán con la reserva que exige la ley y solo para la finalidad del documento.
          </p>

          <h2>3. Para qué se usan (finalidades)</h2>
          <ul>
            <li>Administrar la copropiedad: facturación y recaudo de cuotas, cartera, paz y salvos, recaudos y conciliación.</li>
            <li>Comunicaciones: circulares, respuestas a PQRS, avisos de reservas, recordatorios y convocatorias.</li>
            <li>Asambleas: verificación de quórum por coeficiente, registro de asistencia y poderes, votaciones y actas.</li>
            <li>Mantenimiento y seguridad de las zonas comunes, y reconocimiento de residentes y vehículos.</li>
            <li>
              Consulta inteligente de documentos: el buscador y el análisis automático (vencimientos, cotizaciones y actas)
              procesan el texto de los documentos con inteligencia artificial para responder preguntas y extraer datos.
            </li>
            <li>Seguridad de la plataforma, soporte técnico y cumplimiento de obligaciones legales.</li>
          </ul>

          <h2>4. Datos de personas que no tienen cuenta</h2>
          <p>
            La administración puede registrar en el censo a propietarios, residentes o autorizados que no usan la plataforma.
            En ese caso, es la copropiedad, como responsable, quien debe contar con la autorización de esas personas (por
            ejemplo, en su formato de registro de residentes) o con otra base legal para el tratamiento. PH Gestión trata esos
            datos solo por instrucción de la copropiedad.
          </p>

          <h2>5. Datos de niñas, niños y adolescentes</h2>
          <p>
            El censo puede incluir a menores de edad que viven en una unidad. Solo se registran los datos indispensables para
            identificarlos como residentes (nombre, documento y relación con la unidad), respetando su interés superior y sus
            derechos fundamentales, y con la autorización de su representante legal, que la copropiedad debe obtener. La
            plataforma no crea cuentas para menores de edad.
          </p>

          <h2>6. Sus derechos</h2>
          <p>Como titular puede, de forma gratuita:</p>
          <ul>
            <li>Conocer, actualizar y rectificar sus datos.</li>
            <li>Pedir prueba de la autorización que otorgó.</li>
            <li>Ser informado sobre el uso que se ha dado a sus datos.</li>
            <li>
              Revocar la autorización o pedir la supresión de sus datos cuando no exista un deber legal o contractual de
              conservarlos (por ejemplo, los registros contables y de pagos de la copropiedad).
            </li>
            <li>Acceder a sus datos al menos una vez al mes, y cada vez que la política cambie de fondo.</li>
            <li>Presentar quejas ante la Superintendencia de Industria y Comercio, después de agotar el trámite de consulta o reclamo.</li>
          </ul>
          <p>
            Responder preguntas sobre datos sensibles o sobre datos de niñas, niños y adolescentes es facultativo.
          </p>

          <h2>7. Cómo ejercer sus derechos</h2>
          <p>
            Diríjase preferiblemente a la administración de su copropiedad (por ejemplo, radicando una PQRS en el portal).
            También puede escribir al encargado a{" "}
            <a href={`mailto:${CORREO}`} className="text-primary underline-offset-4 hover:underline">
              {CORREO}
            </a>
            , que dará traslado a la copropiedad cuando corresponda. La solicitud debe indicar su nombre, documento de
            identidad, la copropiedad y unidad, lo que pide y un medio para responderle.
          </p>
          <h3>Consultas</h3>
          <p>
            Se responden en un máximo de <strong>10 días hábiles</strong> desde que se reciben. Si no es posible, se le
            informarán los motivos y la nueva fecha, que no superará <strong>5 días hábiles</strong> adicionales.
          </p>
          <h3>Reclamos (corrección, actualización, supresión o incumplimiento)</h3>
          <ul>
            <li>
              Deben incluir su identificación, la descripción de los hechos, la dirección para responderle y los documentos que
              quiera hacer valer.
            </li>
            <li>
              Si el reclamo está incompleto, se le pedirá completarlo dentro de los 5 días siguientes; si pasan 2 meses sin que
              lo haga, se entenderá que desistió.
            </li>
            <li>Mientras se resuelve, los datos se marcan como «reclamo en trámite» (en máximo 2 días hábiles).</li>
            <li>
              Se responden en un máximo de <strong>15 días hábiles</strong>. Si no es posible, se le informarán los motivos y la
              nueva fecha, que no superará <strong>8 días hábiles</strong> adicionales.
            </li>
          </ul>

          <h2>8. Seguridad y proveedores</h2>
          <p>
            Cada copropiedad está aislada de las demás en la base de datos y cada rol solo ve lo que le corresponde. Las
            conexiones van cifradas (HTTPS), las contraseñas se guardan con algoritmos de una sola vía, cada cambio queda en un
            registro de auditoría y la base de datos se respalda todos los días.
          </p>
          <p>
            Para operar, el encargado usa proveedores de infraestructura que actúan como subencargados y pueden almacenar o
            procesar datos fuera de Colombia (transmisión internacional), bajo sus condiciones contractuales de protección de
            datos:
          </p>
          <ul>
            <li>Railway (Estados Unidos): alojamiento de la aplicación.</li>
            <li>Neon (Estados Unidos): base de datos y sus respaldos de corto plazo.</li>
            <li>Cloudflare (red global): almacenamiento de archivos, respaldos diarios y dominio.</li>
            <li>Resend (Brasil y Estados Unidos): envío de correos.</li>
            <li>
              Google (Estados Unidos): inteligencia artificial para el buscador y el análisis de documentos, en su modalidad de
              pago, en la que Google no usa los datos para entrenar sus modelos.
            </li>
            <li>Sentry (Estados Unidos): registro de errores técnicos, configurado para no recibir datos personales.</li>
          </ul>

          <h2>9. Cookies</h2>
          <p>
            La plataforma usa solo cookies técnicas, indispensables para mantener su sesión abierta de forma segura. No usa
            cookies de publicidad ni de analítica de terceros.
          </p>

          <h2>10. Conservación y vigencia</h2>
          <p>
            Los datos se conservan mientras usted tenga relación con la copropiedad, mientras la copropiedad use la plataforma
            y durante los plazos que exigen las normas contables y de propiedad horizontal. Si la copropiedad deja de usar PH
            Gestión, el encargado le entrega una copia de sus datos y los elimina de la plataforma; las copias de respaldo se
            eliminan automáticamente con su rotación (las diarias a los 30 días y las mensuales a los 12 meses).
          </p>
          <p>
            Esta política está vigente desde el {POLITICA_FECHA}. Si cambia de fondo, se le informará y se le pedirá aceptarla
            de nuevo al entrar a la plataforma.
          </p>
        </article>
      </main>
    </div>
  );
}
