"use client";

import { FormEvent, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { ErrorBox, EmptyState, PageHeader, SuccessBox } from "@/components/ui";
import { createCompany, toUiError } from "@/services/api";
import type { ApiError } from "@/types/api";

export default function CompaniesPage() {
  const { accessToken, activeCompanyId, companies, refreshCompanies, selectCompany } = useAuth();
  const [legalName, setLegalName] = useState("");
  const [tradeName, setTradeName] = useState("");
  const [document, setDocument] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [success, setSuccess] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken) {
      return;
    }
    setError(null);
    setSuccess("");
    setIsSubmitting(true);
    try {
      const company = await createCompany(accessToken, {
        legal_name: legalName,
        trade_name: tradeName || null,
        document
      });
      await refreshCompanies();
      selectCompany(company.id);
      setLegalName("");
      setTradeName("");
      setDocument("");
      setSuccess("Empresa criada e selecionada.");
    } catch (nextError) {
      setError(toUiError(nextError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <PageHeader title="Empresas" />

      <section className="twoColumn">
        <form className="panel formPanel" onSubmit={handleSubmit}>
          <div className="panelHeader">
            <h2>Criar empresa</h2>
          </div>
          <div className="formBody">
            {error ? <ErrorBox message={error.message} /> : null}
            {success ? <SuccessBox message={success} /> : null}
            <label>
              Razao social
              <input onChange={(event) => setLegalName(event.target.value)} required value={legalName} />
            </label>
            <label>
              Nome fantasia
              <input onChange={(event) => setTradeName(event.target.value)} value={tradeName} />
            </label>
            <label>
              Documento
              <input onChange={(event) => setDocument(event.target.value)} required value={document} />
            </label>
            <button disabled={isSubmitting} type="submit">
              {isSubmitting ? "Criando..." : "Criar empresa"}
            </button>
          </div>
        </form>

        <section className="panel">
          <div className="panelHeader">
            <h2>Empresas acessiveis</h2>
          </div>
          {companies.length === 0 ? (
            <EmptyState title="Nenhuma empresa encontrada">Crie uma empresa para liberar as operacoes.</EmptyState>
          ) : (
            <div className="list">
              {companies.map((company) => (
                <button
                  className={company.id === activeCompanyId ? "listItem selected" : "listItem"}
                  key={company.id}
                  onClick={() => selectCompany(company.id)}
                  type="button"
                >
                  <span>
                    <strong>{company.trade_name ?? company.legal_name}</strong>
                    <small>{company.document}</small>
                  </span>
                  <span className="statusPill">{company.status}</span>
                </button>
              ))}
            </div>
          )}
        </section>
      </section>
    </>
  );
}
