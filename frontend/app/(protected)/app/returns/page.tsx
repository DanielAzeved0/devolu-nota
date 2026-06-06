"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { CompanyRequired, EmptyState, ErrorBox, PageHeader, SuccessBox } from "@/components/ui";
import { createMockReturnNote, syncMockReturns, toUiError } from "@/services/api";
import { getStoredReturnNotes, storeReturnNote } from "@/services/ui-storage";
import type {
  ApiError,
  MarketplaceProvider,
  MockIntegrationScenario,
  ReturnNotePublic,
  ReturnOrderPublic
} from "@/types/api";

const marketplaces: MarketplaceProvider[] = ["MERCADO_LIVRE", "SHOPEE"];
const scenarios: MockIntegrationScenario[] = ["success", "invalid_token", "timeout", "external_error"];

export default function ReturnsPage() {
  const { accessToken, activeCompany } = useAuth();
  const [marketplace, setMarketplace] = useState<MarketplaceProvider>("MERCADO_LIVRE");
  const [scenario, setScenario] = useState<MockIntegrationScenario>("success");
  const [orders, setOrders] = useState<ReturnOrderPublic[]>([]);
  const [notes, setNotes] = useState<ReturnNotePublic[]>([]);
  const [summary, setSummary] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [creatingNoteId, setCreatingNoteId] = useState<string | null>(null);

  useEffect(() => {
    setOrders([]);
    setSummary("");
    setNotes(activeCompany ? getStoredReturnNotes(activeCompany.id) : []);
  }, [activeCompany]);

  const notesByReturnOrder = useMemo(
    () => new Map(notes.map((note) => [note.return_order_id, note])),
    [notes]
  );

  async function handleSync(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || !activeCompany) {
      return;
    }
    setError(null);
    setSummary("");
    setIsSyncing(true);
    try {
      const response = await syncMockReturns(accessToken, activeCompany.id, { marketplace, scenario });
      setOrders(response.items);
      setSummary(`Criadas ${response.created}, atualizadas ${response.updated}, ignoradas ${response.skipped}.`);
    } catch (nextError) {
      setError(toUiError(nextError));
    } finally {
      setIsSyncing(false);
    }
  }

  async function handleCreateNote(returnOrderId: string) {
    if (!accessToken || !activeCompany) {
      return;
    }
    setError(null);
    setCreatingNoteId(returnOrderId);
    try {
      const note = await createMockReturnNote(accessToken, activeCompany.id, returnOrderId, { scenario: "success" });
      storeReturnNote(activeCompany.id, note);
      setNotes(getStoredReturnNotes(activeCompany.id));
    } catch (nextError) {
      setError(toUiError(nextError));
    } finally {
      setCreatingNoteId(null);
    }
  }

  return (
    <>
      <PageHeader title="Fila de devolucoes" />
      {!activeCompany ? (
        <CompanyRequired />
      ) : (
        <>
          <form className="toolbar panel" onSubmit={handleSync}>
            <label>
              Marketplace
              <select onChange={(event) => setMarketplace(event.target.value as MarketplaceProvider)} value={marketplace}>
                {marketplaces.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Scenario
              <select onChange={(event) => setScenario(event.target.value as MockIntegrationScenario)} value={scenario}>
                {scenarios.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <button disabled={isSyncing} type="submit">
              {isSyncing ? "Sincronizando..." : "Sincronizar"}
            </button>
          </form>

          {error ? <ErrorBox message={error.message} /> : null}
          {summary ? <SuccessBox message={summary} /> : null}

          <section className="panel">
            <div className="panelHeader">
              <h2>Devolucoes retornadas</h2>
              <span className="statusPill">{orders.length} itens</span>
            </div>
            {orders.length === 0 ? (
              <EmptyState title="Nenhuma devolucao carregada">Execute uma sincronizacao mockada.</EmptyState>
            ) : (
              <div className="table">
                {orders.map((order) => {
                  const note = notesByReturnOrder.get(order.id);
                  return (
                    <div className="row actionRow" key={order.id}>
                      <span>
                        <strong>{order.external_order_id}</strong>
                        <small>{order.marketplace}</small>
                      </span>
                      <span>{note ? `Nota ${note.status}` : order.status}</span>
                      <button
                        className="secondaryButton"
                        disabled={Boolean(note) || creatingNoteId === order.id}
                        onClick={() => handleCreateNote(order.id)}
                        type="button"
                      >
                        {creatingNoteId === order.id ? "Criando..." : note ? "Criada" : "Criar nota"}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}
