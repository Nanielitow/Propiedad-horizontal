import { Building2, FileSearch, ScanText, ShieldCheck } from "lucide-react";

const FEATURES = [
  {
    icon: FileSearch,
    title: "Respuestas con la fuente exacta",
    text: "Cada respuesta indica el documento y la página de donde sale la información.",
  },
  {
    icon: ShieldCheck,
    title: "Información protegida",
    text: "Cada copropiedad y cada rol ven únicamente los documentos que les corresponden.",
  },
  {
    icon: ScanText,
    title: "También documentos escaneados",
    text: "Las actas firmadas y certificados en papel se pueden consultar como cualquier otro texto.",
  },
];

/** Marco de las páginas sin sesión (entrar, activar la cuenta, recuperar la contraseña). */
export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      {/* Panel institucional */}
      <aside className="relative hidden flex-col justify-between bg-sidebar p-10 text-sidebar-foreground lg:flex">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
            <Building2 className="size-5" />
          </div>
          <span className="text-lg font-semibold tracking-tight text-white">PH Gestión</span>
        </div>

        <div className="max-w-md">
          <h1 className="text-3xl leading-tight font-semibold text-white">
            La información de su copropiedad, a una pregunta de distancia.
          </h1>
          <p className="mt-3 text-sidebar-muted">
            Reglamentos, actas, contratos y mantenimientos en un solo lugar, con un asistente que responde
            citando los documentos oficiales.
          </p>
          <ul className="mt-10 space-y-6">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-4">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-sidebar-accent">
                  <Icon className="size-4.5 text-white" />
                </div>
                <div>
                  <p className="font-medium text-white">{title}</p>
                  <p className="mt-0.5 text-sm text-sidebar-muted">{text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-sidebar-muted">Administración de Propiedad Horizontal · Ley 675 de 2001</p>
      </aside>

      {/* Contenido */}
      <main className="flex items-center justify-center bg-background px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <div className="flex size-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Building2 className="size-5" />
            </div>
            <span className="text-lg font-semibold tracking-tight">PH Gestión</span>
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}
