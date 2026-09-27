import type { CampoAncora } from '../api';
import { dinheiro } from '../formato';
import { Brilho } from './Icones';
import { MASCARA, useValoresOcultos } from './Oculto';
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
  const { ocultos } = useValoresOcultos();
  const exibido = texto ?? dinheiro(valor);
  return (
    <button
      type="button"
      className={`valor ${className}${ocultos ? ' oculto' : ''}`}
      onClick={() => aoTocar(campo)}
      aria-label={`${ocultos ? 'Valor oculto' : exibido}. Perguntar ao Hausto sobre esse valor`}
    >
      <span className="valor-numero">{ocultos ? MASCARA : exibido}</span>
      <Brilho className="valor-brilho" />
    </button>
  );
}
