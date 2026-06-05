export function PageHeader({
  children,
  eyebrow,
  title
}: {
  children?: React.ReactNode;
  eyebrow?: string;
  title: string;
}) {
  return (
    <header className="pageHeader">
      <div>
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h1>{title}</h1>
      </div>
      {children}
    </header>
  );
}

export function EmptyState({ children, title }: { children?: React.ReactNode; title: string }) {
  return (
    <div className="emptyState">
      <strong>{title}</strong>
      {children ? <p>{children}</p> : null}
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return <div className="errorBox">{message}</div>;
}

export function SuccessBox({ message }: { message: string }) {
  return <div className="successBox">{message}</div>;
}

export function CompanyRequired() {
  return (
    <EmptyState title="Selecione ou crie uma empresa">
      As operacoes de devolucao, integracoes, emissao e historico dependem de uma empresa ativa.
    </EmptyState>
  );
}
