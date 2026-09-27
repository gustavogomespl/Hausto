import type { EtapaCaixa } from '../../api';
import { dinheiro } from '../../formato';
import './DivisaoDinheiro.css';

type Fatia = { rotulo: string; valor: number; papel: string };

/** Cor fixa por papel, lida pelo começo do rótulo: a fatura é sempre laranja, em qualquer mensagem. */
const PAPEIS: [prefixo: string, papel: string][] = [
  ['fatura', 'fatura'],
  ['essenciais', 'essenciais'],
  ['reserva', 'reserva'],
  ['dia a dia', 'dia-a-dia'],
  ['entradas e saídas', 'movimento'],
  ['movimento', 'movimento'],
  ['despesas informadas', 'despesas'],
  ['saldo negativo', 'saldo-negativo'],
];

const papel = (rotulo: string) =>
  PAPEIS.find(([prefixo]) => rotulo.toLowerCase().startsWith(prefixo))?.[1] ?? 'outro';

/**
 * Do saldo de hoje e das variações até a próxima renda, separa o que a pessoa tem
 * (saldo positivo + entradas) do que precisa sair (saídas + saldo negativo de hoje).
 */
export function dividir(etapas: EtapaCaixa[]) {
  const saldo = etapas.find((e) => e.tipo === 'inicio')?.valor ?? 0;
  const resultado = etapas.find((e) => e.tipo === 'resultado');
  const entradas = etapas.filter((e) => e.tipo === 'entrada').reduce((soma, e) => soma + e.valor, 0);

  const saidas: Fatia[] = etapas
    .filter((e) => e.tipo === 'saida')
    .map((e) => ({ rotulo: e.rotulo, valor: Math.abs(e.valor), papel: papel(e.rotulo) }));
  if (saldo < 0) saidas.push({ rotulo: 'Saldo negativo hoje', valor: -saldo, papel: 'saldo-negativo' });

  const tem = Math.max(saldo, 0) + entradas;
  const precisa = saidas.reduce((soma, s) => soma + s.valor, 0);
  return {
    tem,
    precisa,
    saidas,
    // O número exibido é sempre o do backend; a conta local só entra se ele não vier.
    resultado: resultado?.valor ?? tem - precisa,
  };
}

const porcento = (parte: number, total: number) => {
  const p = (parte / total) * 100;
  return p > 0 && p < 1 ? '<1%' : `${Math.round(p)}%`;
};

function Segmento({ fatia }: { fatia: Fatia }) {
  return (
    <span
      className={`divisao-segmento papel-${fatia.papel}`}
      style={{ flexGrow: fatia.valor }}
      title={`${fatia.rotulo}: ${dinheiro(fatia.valor)}`}
    />
  );
}

function Legenda({ fatias, total }: { fatias: Fatia[]; total: number }) {
  return (
    <ul className="divisao-legenda">
      {fatias.map((f, i) => (
        <li key={`${i}-${f.rotulo}`} className={`papel-${f.papel}`}>
          <span className="divisao-bolinha" aria-hidden="true" />
          <span>{f.rotulo}</span>
          <b className="nowrap">{dinheiro(f.valor)}</b>
          <small>{porcento(f.valor, total)}</small>
        </li>
      ))}
    </ul>
  );
}

/** Para onde vai o dinheiro até a próxima renda: o que a pessoa tem, dividido entre as saídas e a sobra (ou a falta). */
export function DivisaoDinheiro({ etapas, resumo }: { etapas: EtapaCaixa[]; resumo: string }) {
  // A data já vem no título do card ("Para onde vai o seu dinheiro até 07/01"); aqui só os valores.
  const { tem, precisa, saidas, resultado } = dividir(etapas);

  if (resultado >= 0) {
    const fatias = [...saidas, { rotulo: 'Sobra', valor: resultado, papel: 'sobra' }];
    return (
      <div className="divisao">
        <p className="divisao-manchete">
          Você tem <b className="nowrap">{dinheiro(tem)}</b>
        </p>
        <div className="divisao-barra" role="img" aria-label={resumo}>
          {fatias.map((f, i) => (
            <Segmento key={i} fatia={f} />
          ))}
        </div>
        <Legenda fatias={fatias} total={tem || 1} />
      </div>
    );
  }

  const falta = Math.abs(resultado);
  // A falta cabe dentro do tracejado só se ele for largo o bastante; senão vai para baixo da barra.
  const faltaDentro = falta / precisa >= 0.4;
  const rotuloFalta = `Falta ${dinheiro(falta)}`;

  return (
    <div className="divisao falta">
      <p className="divisao-manchete">
        <span aria-hidden="true">⚠</span> Falta <b className="nowrap">{dinheiro(falta)}</b>
      </p>
      <div className="divisao-grafico" role="img" aria-label={resumo}>
        <div className="divisao-linha">
          <span>O que você tem</span>
          <b className="nowrap">{dinheiro(tem)}</b>
        </div>
        <div className="divisao-barra">
          {tem > 0 && <span className="divisao-segmento papel-tem" style={{ flexGrow: tem }} />}
          <span className="divisao-falta" style={{ flexGrow: precisa - tem }}>
            {faltaDentro && rotuloFalta}
          </span>
        </div>
        {!faltaDentro && <p className="divisao-falta-fora">{rotuloFalta}</p>}
        <div className="divisao-linha">
          <span>O que precisa sair</span>
          <b className="nowrap">{dinheiro(precisa)}</b>
        </div>
        <div className="divisao-barra">
          {saidas.map((f, i) => (
            <Segmento key={i} fatia={f} />
          ))}
        </div>
      </div>
      <Legenda fatias={saidas} total={precisa || 1} />
    </div>
  );
}
