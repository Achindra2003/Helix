import { Logo } from "../components/ui/Logo";

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <div className="grid min-h-full place-items-center app-glow px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo size={36} />
          <h1 className="mt-6 text-xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 text-sm text-muted">{subtitle}</p>
        </div>
        <div className="rounded-2xl border border-line bg-surface/80 p-6 backdrop-blur">
          {children}
        </div>
        <p className="mt-6 text-center text-sm text-muted">{footer}</p>
      </div>
    </div>
  );
}
