import type { OpcaoVisual } from '../../api';
import { dinheiro } from '../../formato';
import './ComparaOpcoes.css';

/** De onde vêm os juros quando a conta também fica negativa (sem folga). Só do cartão: nada a explicar. */
function origemDosJuros(o: OpcaoVisual) {
  const cartao = o.juros_cartao ?? 0;
  const conta = o.juros_conta ?? 0;
  if (cartao > 0 && conta > 0) return `juros do cartão ${dinheiro(cartao)} + juros da conta ${dinheiro(conta)}`;
  if (conta > 0) return 'juros do limite da conta';
  return null;
}

/** Uma linha por opção de pagamento: a barra é o custo em juros (sem juros, só o selo); embaixo, quanto sai agora e quanto fica. */
export function ComparaOpcoes({ opcoes }: { opcoes: OpcaoVisual[] }) {
  const maiorCusto = Math.max(...opcoes.map((o) => o.custo), 1);
  // Se nenhuma cabe, o resumo do card já avisa: repetir em cada opção só pesa a leitura.
  const algumaCabe = opcoes.some((o) => o.cabe);

  return (
    <ul className="opcoes">
      {opcoes.map((o, i) => (
        <li
          key={`${i}-${o.rotulo}`}
          className={`opcao${o.destaque ? ' destaque' : ''}`}
          data-destaque={o.destaque || undefined}
        >
          <div className="opcao-topo">
            <strong>{o.rotulo}</strong>
            {o.custo > 0 ? (
              <span className="nowrap">{dinheiro(o.custo)} de juros</span>
            ) : (
              <span className="opcao-sem-juros">Sem juros</span>
            )}
          </div>
          {/* Sem juros não há o que medir: uma trilha vazia pareceria "não carregou". */}
          {o.custo > 0 && (
            <div className="opcao-trilho" aria-hidden="true">
              <span style={{ width: `${Math.max(3, (o.custo / maiorCusto) * 100)}%` }} />
            </div>
          )}
          {origemDosJuros(o) && <div className="opcao-juros">{origemDosJuros(o)}</div>}
          <div className="opcao-detalhe">
            Paga <b>{dinheiro(o.pago)}</b> agora ·{' '}
            {o.divida_restante > 0 ? (
              <>
                fica <b>{dinheiro(o.divida_restante)}</b> de dívida
              </>
            ) : (
              'não fica dívida'
            )}
          </div>
          {!o.cabe && algumaCabe && (
            <div className="opcao-alerta">
              <span aria-hidden="true">⚠</span> aperta os essenciais
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
