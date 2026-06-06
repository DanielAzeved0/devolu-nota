"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { CompanyRequired, EmptyState, ErrorBox, PageHeader, SuccessBox } from "@/components/ui";
import { createMockEmissionBatch, listReturnNotes, toUiError } from "@/services/api";
import type { ApiError, EmissionBatchCreatedResponse, MockEmissionScenario, ReturnNotePublic } from "@/types/api";

const scenarios: MockEmissionScenario[] = ["success", "partial_failure", "failure"];

export default function EmissionsPage() {
  const { accessToken, activeCompany } = useAuth();
  const [notes, setNotes] = useState<ReturnNotePublic[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [scenario, setScenario] = useState<MockEmissionScenario>("success");
  const [batch, setBatch] = useState<EmissionBatchCreatedResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [success, setSuccess] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    async function loadNotes() {
      setSelectedIds([]);
      setBatch(null);
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

  const eligibleNotes = useMemo(
    () => notes.filter((note) => note.status === "DRAFT" || note.status === "READY_TO_EMIT"),
    [notes]
  );

  function toggleNote(noteId: string) {
    setSelectedIds((currentIds) =>
      currentIds.includes(noteId) ? currentIds.filter((id) => id !== noteId) : [...currentIds, noteId]
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || !activeCompany || selectedIds.length === 0) {
      return;
    }
    setError(null);
    setSuccess("");
    setIsSubmitting(true);
    try {
      const response = await createMockEmissionBatch(accessToken, activeCompany.id, {
        return_note_ids: selectedIds,
        scenario
      });
      setBatch(response);
      const notesResponse = await listReturnNotes(accessToken, activeCompany.id, { limit: 100, offset: 0 });
      setNotes(notesResponse.items);
      setSelectedIds([]);
      setSuccess("Lote de emissao mockada criado.");
    } catch (nextError) {
      setError(toUiError(nextError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <PageHeader title="Emissoes mockadas" />
      {!activeCompany ? (
        <CompanyRequired />
      ) : (
        <>
          <form className="toolbar panel" onSubmit={handleSubmit}>
            <label>
              Scenario
              <select onChange={(event) => setScenario(event.target.value as MockEmissionScenario)} value={scenario}>
                {scenarios.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <button disabled={isSubmitting || selectedIds.length === 0} type="submit">
              {isSubmitting ? "Criando..." : `Criar lote (${selectedIds.length})`}
            </button>
          </form>

          {error ? <ErrorBox message={error.message} /> : null}
          {success ? <SuccessBox message={success} /> : null}

          <section className="panel">
            <div className="panelHeader">
              <h2>Notas elegiveis da sessao</h2>
              <span className="statusPill">{eligibleNotes.length} elegiveis</span>
            </div>
            {eligibleNotes.length === 0 ? (
              <EmptyState title="Nenhuma nota elegivel">
                Crie notas mockadas na tela de devolucoes para emitir lote.
              </EmptyState>
            ) : (
              <div className="list">
                {eligibleNotes.map((note) => (
                  <label className="checkItem" key={note.id}>
                    <input
                      checked={selectedIds.includes(note.id)}
                      onChange={() => toggleNote(note.id)}
                      type="checkbox"
                    />
                    <span>
                      <strong>{note.original_nfe_key}</strong>
                      <small>{note.status}</small>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </section>

          {batch ? (
            <section className="panel">
              <div className="panelHeader">
                <h2>Lote criado</h2>
                <span className="statusPill">{batch.status}</span>
              </div>
              <div className="table">
                {batch.jobs.map((job) => (
                  <div className="row" key={job.id}>
                    <span>{job.return_note_id}</span>
                    <span>{job.status}</span>
                    <strong>{job.attempts}</strong>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </>
      )}
    </>
  );
}
