import { Balao, Busca, Sino } from './Icones';
import './Topo.css';

type Props = { iniciais: string; aoAbrirChat: () => void };

export function Topo({ iniciais, aoAbrirChat }: Props) {
  return (
    <header className="topo">
      <span className="topo-avatar">{iniciais}</span>
      <div className="topo-icones">
        <span className="topo-icone">
          <Busca tamanho={26} />
        </span>
        <span className="topo-icone">
          <Sino tamanho={26} fill="currentColor" />
        </span>
        <button type="button" className="topo-icone" onClick={aoAbrirChat} aria-label="Conversar com o Hausto">
          <Balao tamanho={26} />
        </button>
      </div>
    </header>
  );
}
