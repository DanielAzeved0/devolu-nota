import { ApiHealthBadge } from "@/components/api-health-badge";

const queueItems = [
  { marketplace: "Mercado Livre", status: "Pronto", total: 18 },
  { marketplace: "Shopee", status: "Aguardando NF original", total: 7 },
  { marketplace: "Tiny ERP", status: "Falha tratada", total: 3 }
];

const navItems = ["Dashboard", "Conexoes", "Historico", "Erros"];

export default function Home() {
  return (
    <main className="shell">
      <aside className="sidebar" aria-label="Navegacao principal">
        <div>
          <strong className="brand">Notas de Devolucao</strong>
          <span className="tenant">Empresa ativa</span>
        </div>
        <nav>
          {navItems.map((item) => (
            <a href="#" className={item === "Dashboard" ? "active" : ""} key={item}>
              {item}
            </a>
          ))}
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>Fila de devolucoes</h1>
            <p>Operacao inicial para acompanhar notas prontas, pendentes e falhas.</p>
          </div>
          <ApiHealthBadge />
        </header>

        <section className="metrics" aria-label="Indicadores da fila">
          <div>
            <span>Prontas para emitir</span>
            <strong>18</strong>
          </div>
          <div>
            <span>Pendentes de cruzamento</span>
            <strong>7</strong>
          </div>
          <div>
            <span>Falhas tratadas</span>
            <strong>3</strong>
          </div>
        </section>

        <section className="panel" aria-label="Resumo operacional">
          <div className="panelHeader">
            <h2>Status por origem</h2>
            <button type="button">Atualizar</button>
          </div>
          <div className="table">
            {queueItems.map((item) => (
              <div className="row" key={item.marketplace}>
                <span>{item.marketplace}</span>
                <span>{item.status}</span>
                <strong>{item.total}</strong>
              </div>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}

