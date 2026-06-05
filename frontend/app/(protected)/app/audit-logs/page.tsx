"use client";

import { FormEvent, useEffect, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { CompanyRequired, EmptyState, ErrorBox, PageHeader } from "@/components/ui";
import { listAuditLogs, toUiError } from "@/services/api";
import type { ApiError, AuditLogPublic } from "@/types/api";

export default function AuditLogsPage() {
  const { accessToken, activeCompany } = useAuth();
  const [logs, setLogs] = useState<AuditLogPublic[]>([]);
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function loadLogs() {
    if (!accessToken || !activeCompany) {
      return;
    }
    setError(null);
    setIsLoading(true);
    try {
      const response = await listAuditLogs(accessToken, activeCompany.id, {
        action,
        entity_type: entityType,
        limit: 50,
        offset: 0
      });
      setLogs(response.items);
    } catch (nextError) {
      setError(toUiError(nextError));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, activeCompany?.id]);

  function handleFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadLogs();
  }

  return (
    <>
      <PageHeader title="Historico operacional" />
      {!activeCompany ? (
        <CompanyRequired />
      ) : (
        <>
          <form className="toolbar panel" onSubmit={handleFilter}>
            <label>
              Acao
              <input onChange={(event) => setAction(event.target.value)} value={action} />
            </label>
            <label>
              Entidade
              <input onChange={(event) => setEntityType(event.target.value)} value={entityType} />
            </label>
            <button disabled={isLoading} type="submit">
              {isLoading ? "Carregando..." : "Filtrar"}
            </button>
          </form>

          {error ? <ErrorBox message={error.message} /> : null}

          <section className="panel">
            <div className="panelHeader">
              <h2>Eventos recentes</h2>
              <span className="statusPill">{logs.length} eventos</span>
            </div>
            {isLoading ? <EmptyState title="Carregando historico" /> : null}
            {!isLoading && logs.length === 0 ? (
              <EmptyState title="Nenhum evento encontrado">Execute fluxos mockados para gerar historico.</EmptyState>
            ) : (
              <div className="table">
                {logs.map((log) => (
                  <div className="row logRow" key={log.id}>
                    <span>
                      <strong>{log.action}</strong>
                      <small>{log.entity_type}</small>
                    </span>
                    <span>{new Date(log.created_at).toLocaleString("pt-BR")}</span>
                    <strong>{log.user_id ? "Usuario" : "Sistema"}</strong>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}
