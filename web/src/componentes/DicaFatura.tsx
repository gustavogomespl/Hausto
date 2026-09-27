import type { Simulacao } from '../api';
import { dinheiro } from '../formato';
import { Brilho } from './Icones';
import { Oculto } from './Oculto';
import './DicaFatura.css';

type Dica = { tom: 'bom' | 'alerta'; rotulo: string; acao: string; valor?: number };

/** Lê a simulação do backend: quanto dá para pagar da fatura hoje sem faltar para o essencial. */
export function dicaDaFatura(sim: Simulacao | null): Dica | null {
  if (!sim || 'erro' in sim) return null;
  if (sim.status === 'insuficiente') return { tom: 'alerta', rotulo: 'Dá pra pagar menos juros', acao: 'Ver como' };
  if (sim.recomendada === 'integral') return { tom: 'bom', rotulo: 'Dá pra pagar tudo', acao: 'Pague', valor: sim.valor_fatura };
  const valor = sim.recomendada ? sim.opcoes[sim.recomendada].valor_pago : undefined;
  if (valor === undefined) return null;
  return { tom: 'alerta', rotulo: 'Não pague tudo agora', acao: 'Pague', valor };
}

type Props = { simulacao: Simulacao | null; aoAbrir: () => void };

/** A dica do Hausto no card do cartão; tocar abre a conversa sobre a fatura. */
export function DicaFatura({ simulacao, aoAbrir }: Props) {
  const dica = dicaDaFatura(simulacao);
  if (!dica) return null;
  return (
    <button type="button" className={`dica-fatura ${dica.tom}`} onClick={aoAbrir} aria-label={`${dica.rotulo}. Conversar com o Hausto sobre a fatura`}>
      <span className="dica-rotulo">
        <Brilho tamanho={12} />
        {dica.rotulo}
      </span>
      <span className="dica-acao">
        {dica.valor === undefined ? <b>{dica.acao}</b> : dica.acao}
        {dica.valor !== undefined && (
          <>
            {' '}
            <b>
              <Oculto>{dinheiro(dica.valor)}</Oculto>
            </b>
          </>
        )}
      </span>
    </button>
  );
}
