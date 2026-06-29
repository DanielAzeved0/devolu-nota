"use client";

import { FormEvent, useEffect, useState } from "react";
import { useAuth } from "@/components/auth-provider";
import { CompanyRequired, EmptyState, ErrorBox, PageHeader, SuccessBox } from "@/components/ui";
import { downloadFiscalDocument, listFiscalDocuments, toUiError } from "@/services/api";
import type { ApiError, FiscalDocumentPublic } from "@/types/api";

export default function DocumentsPage() {
  const { accessToken, activeCompany } = useAuth();
  const [documents, setDocuments] = useState<FiscalDocumentPublic[]>([]);
  const [returnNoteId, setReturnNoteId] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [success, setSuccess] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  async function loadDocuments(nextReturnNoteId = returnNoteId) {
    if (!accessToken || !activeCompany) {
      return;
    }
    setError(null);
    setSuccess("");
    setIsLoading(true);
    try {
      const response = await listFiscalDocuments(accessToken, activeCompany.id, {
        return_note_id: nextReturnNoteId.trim() || undefined,
        limit: 50,
        offset: 0
      });
      setDocuments(response.items);
    } catch (nextError) {
      setError(toUiError(nextError));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    setReturnNoteId("");
    void loadDocuments("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, activeCompany?.id]);

  function handleFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadDocuments();
  }

  async function handleDownload(document: FiscalDocumentPublic) {
    if (!accessToken || !activeCompany) {
      return;
    }
    setError(null);
    setSuccess("");
    setDownloadingId(document.id);
    try {
      const blob = await downloadFiscalDocument(accessToken, activeCompany.id, document.id);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = buildFilename(document);
      anchor.click();
      URL.revokeObjectURL(url);
      setSuccess("Download iniciado.");
    } catch (nextError) {
      setError(toUiError(nextError));
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <>
      <PageHeader title="Documentos fiscais" />
      {!activeCompany ? (
        <CompanyRequired />
      ) : (
        <>
          <form className="toolbar panel" onSubmit={handleFilter}>
            <label>
              Nota de devolucao
              <input
                onChange={(event) => setReturnNoteId(event.target.value)}
                placeholder="UUID da nota"
                value={returnNoteId}
              />
            </label>
            <button disabled={isLoading} type="submit">
              {isLoading ? "Carregando..." : "Filtrar"}
            </button>
          </form>

          {error ? <ErrorBox message={error.message} /> : null}
          {success ? <SuccessBox message={success} /> : null}

          <section className="panel">
            <div className="panelHeader">
              <h2>Arquivos armazenados</h2>
              <span className="statusPill">{documents.length} documentos</span>
            </div>
            {isLoading ? <EmptyState title="Carregando documentos" /> : null}
            {!isLoading && documents.length === 0 ? (
              <EmptyState title="Nenhum documento fiscal encontrado">
                Processe uma emissao mockada para gerar XML e DANFE armazenados.
              </EmptyState>
            ) : (
              <div className="table">
                {documents.map((document) => (
                  <div className="row documentRow" key={document.id}>
                    <span>
                      <strong>{document.document_type}</strong>
                      <small>{document.access_key ?? document.id}</small>
                    </span>
                    <span>
                      {document.status}
                      <small>
                        {document.issued_at
                          ? new Date(document.issued_at).toLocaleString("pt-BR")
                          : "Sem emissao"}
                      </small>
                    </span>
                    <span>
                      {document.return_note_id}
                      <small>{new Date(document.created_at).toLocaleString("pt-BR")}</small>
                    </span>
                    <button
                      className="secondaryButton"
                      disabled={downloadingId === document.id}
                      onClick={() => handleDownload(document)}
                      type="button"
                    >
                      {downloadingId === document.id ? "Baixando..." : "Baixar"}
                    </button>
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

function buildFilename(document: FiscalDocumentPublic): string {
  const extension = document.document_type === "DANFE_PDF" ? "pdf" : "xml";
  return `${document.document_type.toLowerCase()}-${document.id}.${extension}`;
}
