import type { CampoAncora } from '../api';
import { dinheiro } from '../formato';
import { Brilho } from './Icones';
import './Valor.css';

type Props = {
  valor: number;
  campo: CampoAncora;
  aoTocar: (campo: CampoAncora) => void;
  /** Texto já formatado; por padrão, R$ 1.980,00. */
  texto?: string;
  className?: string;
};

/** Âncora ✦: um valor calculado que, ao ser tocado, abre o Hausto explicando de onde ele vem. */
export function Valor({ valor, campo, aoTocar, texto, className = '' }: Props) {
  const exibido = texto ?? dinheiro(valor);
  return (
    <button
      type="button"
      className={`valor ${className}`}
      onClick={() => aoTocar(campo)}
      aria-label={`${exibido}. Perguntar ao Hausto sobre esse valor`}
    >
      <span className="valor-numero">{exibido}</span>
      <Brilho className="valor-brilho" />
    </button>
  );
}
