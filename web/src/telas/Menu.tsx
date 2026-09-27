import { Brilho, Seta } from '../componentes/Icones';
import './Grade.css';

const ITENS = ['Cartões', 'Investimentos', 'Empréstimos', 'Seguros', 'Limites', 'Trocar persona', 'Hausto', 'Segurança', 'Ajuda'];

export function Menu({ aoAbrirDemo }: { aoAbrirDemo: () => void }) {
  return (
    <div className="pagina">
      <h1 className="pagina-titulo">Menu</h1>
      <div className="grade">
        {ITENS.map((rotulo) => (
          <div key={rotulo} className="grade-item">
            {rotulo}
          </div>
        ))}
      </div>
      <button type="button" className="menu-demo" onClick={aoAbrirDemo}>
        <span className="menu-demo-icone">
          <Brilho tamanho={14} />
        </span>
        <span className="menu-demo-texto">
          <strong>Modo demonstração</strong>
          <small>Trocar persona ou cliente</small>
        </span>
        <Seta tamanho={20} />
      </button>
    </div>
  );
}
