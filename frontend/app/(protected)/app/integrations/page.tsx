"use client";

import { FormEvent, useEffect, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { CompanyRequired, EmptyState, ErrorBox, PageHeader, SuccessBox } from "@/components/ui";
import { createIntegration, listIntegrations, toUiError } from "@/services/api";
import type { ApiError, IntegrationPublic } from "@/types/api";

const providers = ["TINY", "MERCADO_LIVRE", "SHOPEE"] as const;

export default function IntegrationsPage() {
  const { accessToken, activeCompany } = useAuth();
  const [integrations, setIntegrations] = useState<IntegrationPublic[]>([]);
  const [provider, setProvider] = useState<(typeof providers)[number]>("TINY");
  const [error, setError] = useState<ApiError | null>(null);
  const [success, setSuccess] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function loadIntegrations() {
    if (!accessToken || !activeCompany) {
      return;
    }
    setError(null);
    setIsLoading(true);
    try {
      setIntegrations(await listIntegrations(accessToken, activeCompany.id));
    } catch (nextError) {
      setError(toUiError(nextError));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadIntegrations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, activeCompany?.id]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || !activeCompany) {
      return;
    }
    setError(null);
    setSuccess("");
    setIsSubmitting(true);
    try {
      await createIntegration(accessToken, activeCompany.id, {
        provider,
        settings: { mock: true }
      });
      setSuccess("Integracao criada.");
      await loadIntegrations();
    } catch (nextError) {
      setError(toUiError(nextError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <PageHeader title="Conexoes" />
      {!activeCompany ? (
        <CompanyRequired />
      ) : (
        <section className="twoColumn">
          <form className="panel formPanel" onSubmit={handleSubmit}>
            <div className="panelHeader">
              <h2>Nova integracao</h2>
            </div>
            <div className="formBody">
              {error ? <ErrorBox message={error.message} /> : null}
              {success ? <SuccessBox message={success} /> : null}
              <label>
                Provedor
                <select onChange={(event) => setProvider(event.target.value as typeof provider)} value={provider}>
                  {providers.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <button disabled={isSubmitting} type="submit">
                {isSubmitting ? "Criando..." : "Criar integracao mock"}
              </button>
            </div>
          </form>

          <section className="panel">
            <div className="panelHeader">
              <h2>Integracoes da empresa</h2>
              <button className="secondaryButton" disabled={isLoading} onClick={loadIntegrations} type="button">
                Atualizar
              </button>
            </div>
            {isLoading ? <EmptyState title="Carregando integracoes" /> : null}
            {!isLoading && integrations.length === 0 ? (
              <EmptyState title="Nenhuma integracao criada">Crie conexoes mock para validar o fluxo.</EmptyState>
            ) : (
              <div className="table">
                {integrations.map((integration) => (
                  <div className="row" key={integration.id}>
                    <span>{integration.provider}</span>
                    <span>{integration.status}</span>
                    <strong>{integration.last_sync_at ? "Sync" : "Novo"}</strong>
                  </div>
                ))}
              </div>
            )}
          </section>
        </section>
      )}
    </>
  );
}
