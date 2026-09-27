import type { Aviso } from '../api';
import { Brilho } from './Icones';
import './CardAviso.css';

type Props = {
  aviso: Aviso;
  aoAbrir: (aviso: Aviso) => void;
  aoDispensar?: () => void;
};

export function CardAviso({ aviso, aoAbrir, aoDispensar }: Props) {
  return (
    <article className="aviso">
      <span className="aviso-selo">
        <Brilho tamanho={11} />
        {aviso.rotulo}
      </span>
      <h2 className="aviso-titulo">{aviso.titulo}</h2>
      <p className="aviso-texto">{aviso.texto}</p>
      <div className="aviso-acoes">
        <button type="button" className="botao-laranja" onClick={() => aoAbrir(aviso)}>
          {aviso.cta}
        </button>
        {aoDispensar && (
          <button type="button" className="aviso-dispensar" onClick={aoDispensar}>
            Agora não
          </button>
        )}
      </div>
    </article>
  );
}
