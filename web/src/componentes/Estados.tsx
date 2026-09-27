import './Estados.css';

export function Carregando({ texto = 'Carregando…' }: { texto?: string }) {
  return (
    <div className="estado" role="status">
      <span className="estado-roda" />
      {texto}
    </div>
  );
}

export function Falha({ mensagem, aoTentar }: { mensagem: string; aoTentar?: () => void }) {
  return (
    <div className="estado estado-falha" role="alert">
      <p>{mensagem}</p>
      {aoTentar && (
        <button type="button" className="botao-laranja" onClick={aoTentar}>
          Tentar de novo
        </button>
      )}
    </div>
  );
}
