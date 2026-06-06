"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { CompanyRequired, ErrorBox, PageHeader } from "@/components/ui";
import { listReturnNotes, toUiError } from "@/services/api";
import type { ApiError, ReturnNotePublic } from "@/types/api";

export default function DashboardPage() {
  const { accessToken, activeCompany, companies, user } = useAuth();
  const [notes, setNotes] = useState<ReturnNotePublic[]>([]);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    async function loadNotes() {
      if (!accessToken || !activeCompany) {
        setNotes([]);
        return;
      }
      setError(null);
      try {
        const response = await listReturnNotes(accessToken, activeCompany.id, { limit: 100, offset: 0 });
        setNotes(response.items);
      } catch (nextError) {
        setError(toUiError(nextError));
      }
    }

    void loadNotes();
  }, [accessToken, activeCompany]);

  const issuedCount = notes.filter((note) => note.status === "ISSUED").length;
  const queuedCount = notes.filter((note) => note.status === "QUEUED").length;
  const draftCount = notes.filter((note) => note.status === "DRAFT").length;

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
          {error ? <ErrorBox message={error.message} /> : null}
          <section className="metrics" aria-label="Indicadores operacionais">
            <div>
              <span>Empresas acessiveis</span>
              <strong>{companies.length}</strong>
            </div>
            <div>
              <span>Notas persistidas</span>
              <strong>{notes.length}</strong>
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
