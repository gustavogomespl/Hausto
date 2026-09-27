import { diaMesNumerico } from '../formato';
import { Balao, Busca, Sino } from './Icones';
import './Topo.css';

/** `simulando`: data da simulação escolhida no admin, para ninguém confundir o "hoje" na demo. */
type Props = { iniciais: string; simulando?: string; aoAbrirChat: () => void };

export function Topo({ iniciais, simulando, aoAbrirChat }: Props) {
  return (
    <header className="topo">
      <span className="topo-avatar">{iniciais}</span>
      {/* Na demo com data escolhida, o aviso da simulação ocupa o lugar do nível (não cabem os dois). */}
      {simulando ? (
        <span className="topo-simulando">Simulando {diaMesNumerico(simulando)}</span>
      ) : (
        <span className="topo-nivel">
          <span className="topo-nivel-ponto">4</span>
          Nível 4
        </span>
      )}
      <div className="topo-icones">
        <span className="topo-icone">
          <Busca tamanho={26} />
        </span>
        <span className="topo-icone topo-sino">
          <Sino tamanho={26} fill="currentColor" />
        </span>
        <button type="button" className="topo-icone" onClick={aoAbrirChat} aria-label="Conversar com o Hausto">
          <Balao tamanho={26} />
        </button>
      </div>
    </header>
  );
}
