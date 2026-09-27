import type { ProgressoPlano as Progresso } from '../../api';
import { dinheiro } from '../../formato';
import './ProgressoPlano.css';

const STATUS = {
  dentro: { icone: '✓', texto: 'dentro do plano' },
  acima: { icone: '⚠', texto: 'acima do plano' },
} as const;

type Props = { dados: Progresso; compacto?: boolean };

/** Gasto do dia a dia até hoje contra o previsto pelo plano (limite diário × dias decorridos). */
export function ProgressoPlano({ dados, compacto = false }: Props) {
  const { limite_diario, dias_decorridos, dias_totais, gasto_real, gasto_previsto, status } = dados;
  // A régua é o plano inteiro (ou o gasto, se já passou dele); o marcador mostra onde era para estar hoje.
  const escala = Math.max(limite_diario * dias_totais, gasto_real, gasto_previsto, 1);
  const posicao = (valor: number) => Math.min(100, (valor / escala) * 100);
  const { icone, texto } = STATUS[status];

  return (
    <div className={`progresso-plano ${status}${compacto ? ' compacto' : ''}`}>
      <div className="progresso-topo">
        <span>{`Dia ${dias_decorridos} de ${dias_totais}`}</span>
        <span className="progresso-status">
          <span aria-hidden="true">{icone}</span> {texto}
        </span>
      </div>
      <div
        className="progresso-trilho"
        role="img"
        aria-label={`Gasto de ${dinheiro(gasto_real)}; o plano previa ${dinheiro(gasto_previsto)} até hoje`}
      >
        <span className="progresso-barra" style={{ width: `${posicao(gasto_real)}%` }} />
        <span className="progresso-marcador" style={{ left: `${posicao(gasto_previsto)}%` }} />
      </div>
      <dl className="progresso-numeros">
        <div>
          <dt>Gasto até agora</dt>
          <dd>{dinheiro(gasto_real)}</dd>
        </div>
        <div>
          <dt>
            <span className="progresso-legenda-marcador" aria-hidden="true" />
            Previsto até hoje
          </dt>
          <dd>{dinheiro(gasto_previsto)}</dd>
        </div>
      </dl>
      {!compacto && (
        <p className="progresso-limite">
          Limite de <b className="nowrap">{dinheiro(limite_diario)}</b> por dia no dia a dia
        </p>
      )}
    </div>
  );
}
