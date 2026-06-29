"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/components/auth-provider";
import { ApiHealthBadge } from "@/components/api-health-badge";

const navItems = [
  { href: "/app", label: "Dashboard" },
  { href: "/app/companies", label: "Empresas" },
  { href: "/app/integrations", label: "Conexoes" },
  { href: "/app/returns", label: "Devolucoes" },
  { href: "/app/emissions", label: "Emissoes" },
  { href: "/app/documents", label: "Documentos" },
  { href: "/app/audit-logs", label: "Historico" }
];

export function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const {
    accessToken,
    activeCompany,
    companies,
    isBootstrapping,
    logout,
    selectCompany,
    user
  } = useAuth();

  useEffect(() => {
    if (!isBootstrapping && !accessToken) {
      router.replace("/login");
    }
  }, [accessToken, isBootstrapping, router]);

  if (isBootstrapping) {
    return <main className="centeredState">Carregando sessao...</main>;
  }

  if (!accessToken) {
    return <main className="centeredState">Redirecionando...</main>;
  }

  return (
    <main className="shell">
      <aside className="sidebar" aria-label="Navegacao principal">
        <div>
          <strong className="brand">Notas de Devolucao</strong>
          <span className="tenant">{activeCompany?.trade_name ?? activeCompany?.legal_name ?? "Sem empresa ativa"}</span>
        </div>

        <nav>
          {navItems.map((item) => (
            <Link
              className={pathname === item.href ? "active" : ""}
              href={item.href}
              key={item.href}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="sidebarFooter">
          <label className="fieldLabel" htmlFor="active-company">
            Empresa ativa
          </label>
          <select
            id="active-company"
            onChange={(event) => selectCompany(event.target.value)}
            value={activeCompany?.id ?? ""}
          >
            {companies.length === 0 ? <option value="">Nenhuma empresa</option> : null}
            {companies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.trade_name ?? company.legal_name}
              </option>
            ))}
          </select>
          <span className="mutedText">{user?.email}</span>
          <button className="secondaryButton" onClick={logout} type="button">
            Sair
          </button>
        </div>
      </aside>

      <section className="workspace">
        <div className="topbar compact">
          <div />
          <ApiHealthBadge />
        </div>
        {children}
      </section>
    </main>
  );
}
