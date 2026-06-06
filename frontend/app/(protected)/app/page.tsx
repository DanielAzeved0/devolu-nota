"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useAuth } from "@/components/auth-provider";
import { CompanyRequired, PageHeader } from "@/components/ui";
import { getStoredReturnNotes } from "@/services/ui-storage";

export default function DashboardPage() {
  const { activeCompany, activeCompanyId, companies, user } = useAuth();
  const storedNotes = useMemo(
    () => (activeCompanyId ? getStoredReturnNotes(activeCompanyId) : []),
    [activeCompanyId]
  );

  const issuedCount = storedNotes.filter((note) => note.status === "ISSUED").length;
  const queuedCount = storedNotes.filter((note) => note.status === "QUEUED").length;
  const draftCount = storedNotes.filter((note) => note.status === "DRAFT").length;

  return (
    <>
      <PageHeader eyebrow={user?.name} title="Dashboard operacional">
        <Link className="buttonLink" href="/app/returns">
          Sincronizar devolucoes
        </Link>
      </PageHeader>

      {!activeCompany ? (
        <CompanyRequired />
      ) : (
        <>
          <section className="metrics" aria-label="Indicadores operacionais">
            <div>
              <span>Empresas acessiveis</span>
              <strong>{companies.length}</strong>
            </div>
            <div>
              <span>Notas na sessao</span>
              <strong>{storedNotes.length}</strong>
            </div>
            <div>
              <span>Emitidas mockadas</span>
              <strong>{issuedCount}</strong>
            </div>
          </section>

          <section className="panel">
            <div className="panelHeader">
              <h2>{activeCompany.trade_name ?? activeCompany.legal_name}</h2>
              <span className="statusPill">{activeCompany.status}</span>
            </div>
            <div className="summaryGrid">
              <div>
                <span>Rascunho</span>
                <strong>{draftCount}</strong>
              </div>
              <div>
                <span>Na fila</span>
                <strong>{queuedCount}</strong>
              </div>
              <div>
                <span>CNPJ/documento</span>
                <strong>{activeCompany.document}</strong>
              </div>
            </div>
          </section>
        </>
      )}
    </>
  );
}
