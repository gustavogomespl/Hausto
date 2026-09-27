import { useState } from 'react';
import type { Aviso, CampoAncora, Meta, Painel, Plano } from '../api';
import { iconeDaCategoria } from '../categorias';
import { CardAviso } from '../componentes/CardAviso';
import { Brilho, Carro, CasaMeta, Escudo, Sacola, Seta } from '../componentes/Icones';
import { Oculto } from '../componentes/Oculto';
import { Valor } from '../componentes/Valor';
import { ProgressoPlano } from '../chat/visuais/ProgressoPlano';
import { diaMesNumerico, dinheiroCurto, inicialDoMes, mesPorExtenso, nomeDoMes } from '../formato';
import './RaioX.css';

type Props = {
  painel: Painel;
  plano: Plano | null;
  aviso: Aviso | undefined;
  aoAbrirAncora: (campo: CampoAncora) => void;
  aoAbrirAviso: (aviso: Aviso) => void;
  /** "Posso comprar?": abre o chat perguntando o que a pessoa quer comprar. */
  aoSimularCompra?: () => void;
};

type Parcela = Painel['raio_x']['parcelas']['itens'][number];

export function RaioX({ painel, plano, aviso, aoAbrirAncora, aoAbrirAviso, aoSimularCompra }: Props) {
  const { raio_x: rx, cartao } = painel;
  // A fatura leva o nome do mês em que vence (vence 25/12 -> fatura de dezembro).
  const mesFatura = nomeDoMes(cartao.vencimento);
  // Índice (0 = janeiro) do mês da fatura, para saber quando cada parcela acaba.
  const indiceFatura = cartao.vencimento ? Number(cartao.vencimento.slice(5, 7)) - 1 : null;

  return (
    <div className="pagina raiox">
      <div className="raiox-titulo">
        <h1 className="pagina-titulo">Raio-X</h1>
        {mesFatura && <span>Fatura de {mesFatura}</span>}
      </div>

      {plano && <SeuPlano plano={plano} />}

      {aviso && <CardAviso aviso={aviso} aoAbrir={aoAbrirAviso} />}

      {(aoSimularCompra || painel.meta) && (
        <div className="rx-simulacoes">
          {aoSimularCompra && (
            <button type="button" className={`rx-tile${painel.meta ? '' : ' inteira'}`} onClick={aoSimularCompra}>
              <span className="rx-tile-cabeca">
                <span className="rx-tile-icone">
                  <Sacola tamanho={16} strokeWidth={2.2} />
                </span>
                <Seta tamanho={22} />
              </span>
              <span className="rx-tile-rotulo">Simular compra</span>
              <b className="rx-tile-titulo">Posso comprar?</b>
            </button>
          )}
          {painel.meta && <TileMeta meta={painel.meta} aoAbrir={() => aoAbrirAncora('meta')} />}
        </div>
      )}

      <h2 className="secao-titulo">Seu cartão</h2>

      {rx.gasto_por_dia && (
        <section className="card">
          <div className="rx-cabeca-cartao">
            <span className="rx-bandeira">
              <span />
              <span />
            </span>
            Gasto no cartão por dia
          </div>
          <div className="rx-destaque">
            <Valor
              valor={rx.gasto_por_dia.valor}
              texto={dinheiroCurto(rx.gasto_por_dia.valor)}
              campo="gasto_por_dia"
              aoTocar={aoAbrirAncora}
            />
            <span>por dia</span>
          </div>
          <p className="rx-detalhe">
            <b>
              <Oculto>{dinheiroCurto(rx.gasto_por_dia.valor)}</Oculto>
            </b>{' '}
            × {rx.gasto_por_dia.dias} dias ≈{' '}
            <b>
              <Oculto>{dinheiroCurto(rx.gasto_por_dia.total)}</Oculto>
            </b>{' '}
            em compras
          </p>
          {cartao.fatura !== null && (
            <div className="rx-linha-total">
              <span>Fatura aberta</span>
              <span>
                <Oculto>{dinheiroCurto(cartao.fatura)}</Oculto>
              </span>
            </div>
          )}
        </section>
      )}

      {/* Números rápidos: dois por linha; sem juros, as parcelas ocupam a linha inteira. */}
      <div className="rx-numeros">
        {rx.juros_por_dia && (
          <section className="card rx-mini">
            <Cabeca titulo="Juros por dia" pequena />
            <Valor
              className="rx-valor"
              valor={rx.juros_por_dia.valor}
              texto={dinheiroCurto(rx.juros_por_dia.valor)}
              campo="juros_por_dia"
              aoTocar={aoAbrirAncora}
            />
            <p className="rx-detalhe">
              Uns{' '}
              <b>
                <Oculto>{dinheiroCurto(rx.juros_por_dia.custo_30_dias)}</Oculto>
              </b>{' '}
              no mês, pagando{' '}
              <b>
                <Oculto>{dinheiroCurto(rx.juros_por_dia.pagando)}</Oculto>
              </b>
            </p>
          </section>
        )}

        <section className={`card rx-mini${rx.juros_por_dia ? '' : ' inteira'}`}>
          <Cabeca titulo="Parcelas" pequena />
          <Valor
            className="rx-valor"
            valor={rx.parcelas.total_mes}
            texto={dinheiroCurto(rx.parcelas.total_mes)}
            campo="parcelas"
            aoTocar={aoAbrirAncora}
          />
          <p className="rx-detalhe">{resumoParcelas(rx.parcelas.itens, mesFatura)}</p>
        </section>
      </div>

      {(rx.categorias.length > 0 || rx.parcelas.itens.length > 0) && (
        <h2 className="secao-titulo">Detalhes da fatura</h2>
      )}

      {rx.categorias.length > 0 && (
        <Categorias categorias={rx.categorias} aoAbrirDica={() => aoAbrirAncora('gasto_por_dia')} />
      )}

      {rx.parcelas.itens.length > 0 && (
        <section className="card">
          <Cabeca titulo="Compras parceladas" sub="Parcelas já cobradas, contando a deste mês" />
          <ul className="rx-parcelas">
            {rx.parcelas.itens.map((p, i) => (
              <li key={`${i}-${p.descricao}`}>
                <div className="rx-parcela-topo">
                  <span>{p.descricao}</span>
                  <b>
                    {p.atual} de {p.total}
                  </b>
                </div>
                <div className="rx-segmentos" aria-hidden="true">
                  {Array.from({ length: p.total }, (_, i) => (
                    <span key={i} className={i < p.atual ? 'pago' : ''} />
                  ))}
                </div>
                <p className="rx-detalhe">
                  <b>
                    <Oculto>{dinheiroCurto(p.valor)}</Oculto>
                  </b>{' '}
                  por mês
                  {indiceFatura !== null && <> · a última vem em {mesPorExtenso(indiceFatura + p.total - p.atual)}</>}
                </p>
              </li>
            ))}
          </ul>
          {indiceFatura !== null && (
            <DicaCard texto={alivioDasParcelas(rx.parcelas.itens, indiceFatura)} aoAbrir={() => aoAbrirAncora('parcelas')} />
          )}
        </section>
      )}

      {rx.faturas.length > 0 && <Faturas faturas={rx.faturas} />}
    </div>
  );
}

const ICONES_META = { casa: CasaMeta, carro: Carro, reserva: Escudo };

/** A meta de poupança da persona: quanto já guardou; tocar abre o Hausto explicando quanto falta. */
function TileMeta({ meta, aoAbrir }: { meta: Meta; aoAbrir: () => void }) {
  const Icone = ICONES_META[meta.icone] ?? Escudo;
  return (
    <button
      type="button"
      className="rx-tile"
      onClick={aoAbrir}
      aria-label={`Meta: ${meta.rotulo.toLowerCase()}, ${meta.pct}% guardado. Perguntar ao Hausto sobre a meta`}
    >
      <span className="rx-tile-cabeca">
        <span className="rx-tile-icone">
          <Icone tamanho={16} strokeWidth={2.2} />
        </span>
        <Seta tamanho={22} />
      </span>
      <span className="rx-tile-rotulo">Meta: {meta.rotulo.toLowerCase()}</span>
      <b className="rx-tile-titulo">{meta.pct}% guardado</b>
      <span className="rx-tile-barra" aria-hidden="true">
        <i style={{ width: `${Math.min(100, meta.pct)}%` }} />
      </span>
    </button>
  );
}

/** O plano que o cliente aceitou no chat, acompanhado dia a dia até a próxima renda. */
function SeuPlano({ plano }: { plano: Plano }) {
  return (
    <section className="card rx-plano">
      <Cabeca titulo={`Seu plano até ${diaMesNumerico(plano.fim)}`} sub="Combinado com o Hausto" />
      <div className="rx-destaque">
        <strong className="rx-plano-limite">
          <Oculto>{dinheiroCurto(plano.limite_diario)}</Oculto>
        </strong>
        <span>por dia no dia a dia</span>
      </div>
      <ProgressoPlano dados={plano.progresso} compacto />
      <dl className="rx-plano-combinado">
        <div>
          <dt>Pagar da fatura</dt>
          <dd>
            <Oculto>{dinheiroCurto(plano.pagamento_fatura)}</Oculto>
          </dd>
        </div>
        <div>
          <dt>Guardar de reserva</dt>
          <dd>
            <Oculto>{dinheiroCurto(plano.reserva)}</Oculto>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function Cabeca({ titulo, sub, pequena = false }: { titulo: string; sub?: string; pequena?: boolean }) {
  return (
    <div className={`card-cabeca${pequena ? ' pequena' : ''}`}>
      <div>
        <h3>{titulo}</h3>
        {sub && <p>{sub}</p>}
      </div>
      <Seta tamanho={pequena ? 18 : 22} />
    </div>
  );
}

// Valores em reais (R$ 400, R$ 1.610,50) e porcentagens (67%) dentro do texto de uma dica.
const NUMERO = /(R\$\s?\d[\d.]*(?:,\d{2})?|\d+(?:,\d+)?%)/;

/** A dica ✦ do Hausto no pé de um card do Raio-X; os números vêm em negrito e tocar abre a conversa. */
function DicaCard({ texto, aoAbrir }: { texto: string; aoAbrir: () => void }) {
  return (
    <button type="button" className="rx-dica" onClick={aoAbrir}>
      <Brilho tamanho={12} />
      <span>
        {texto.split(NUMERO).map((parte, i) => {
          if (i % 2 === 0) return parte;
          // Dinheiro respeita o "ocultar valores"; porcentagem não revela quanto a pessoa tem.
          return <b key={i}>{parte.startsWith('R$') ? <Oculto>{parte}</Oculto> : parte}</b>;
        })}
      </span>
    </button>
  );
}

function resumoParcelas(itens: Parcela[], mes: string | null) {
  if (itens.length === 0) return 'Nenhuma parcela nesta fatura.';
  const nomes = itens.map((p) => `${p.descricao} (${p.atual} de ${p.total})`);
  const lista = nomes.length > 1 ? `${nomes.slice(0, -1).join(', ')} e ${nomes.at(-1)}` : nomes[0];
  return `${mes ? `Na fatura de ${mes}` : 'Nesta fatura'}: ${lista}`;
}

/** "Em fevereiro, a fatura fica R$ 210 mais leve. Em abril, mais R$ 120." */
export function alivioDasParcelas(itens: Parcela[], indiceFatura: number) {
  // A fatura que vem depois da última parcela é a primeira sem ela.
  const porMes = new Map<number, number>();
  for (const p of itens) {
    const livre = indiceFatura + p.total - p.atual + 1;
    porMes.set(livre, (porMes.get(livre) ?? 0) + p.valor);
  }
  return [...porMes]
    .sort(([a], [b]) => a - b)
    .map(([mes, valor], i) =>
      i === 0
        ? `Em ${mesPorExtenso(mes)}, a fatura fica ${dinheiroCurto(valor)} mais leve.`
        : `Em ${mesPorExtenso(mes)}, mais ${dinheiroCurto(valor)}.`,
    )
    .join(' ');
}

/** "Mercado pesou mais: R$ 400, 67% das compras desta fatura." */
export function dicaDasCategorias(categorias: Painel['raio_x']['categorias']) {
  const total = categorias.reduce((soma, c) => soma + c.valor, 0);
  const maior = [...categorias].sort((a, b) => b.valor - a.valor)[0];
  if (categorias.length === 1) return `Todas as compras desta fatura foram em ${maior.categoria}: ${dinheiroCurto(maior.valor)}.`;
  const pct = Math.round((maior.valor / total) * 100);
  return `${maior.categoria} pesou mais: ${dinheiroCurto(maior.valor)}, ${pct}% das compras desta fatura.`;
}

function Categorias({ categorias, aoAbrirDica }: { categorias: Painel['raio_x']['categorias']; aoAbrirDica: () => void }) {
  const ordenadas = [...categorias].sort((a, b) => b.valor - a.valor);
  const maior = Math.max(...ordenadas.map((c) => c.valor), 1);
  return (
    <section className="card">
      <Cabeca titulo="Onde foi o dinheiro do cartão" sub="Compras desta fatura, sem as parcelas" />
      <ul className="rx-categorias">
        {ordenadas.map((c) => (
          <li key={c.categoria}>
            <div className="rx-categoria-topo">
              <span className="rx-categoria-icone">{iconeDaCategoria(c.categoria)}</span>
              <span className="rx-categoria-nome">{c.categoria}</span>
              <b>
                <Oculto>{dinheiroCurto(c.valor)}</Oculto>
              </b>
            </div>
            <div className="rx-barra" style={{ width: `${Math.max(4, (c.valor / maior) * 100)}%` }} />
          </li>
        ))}
      </ul>
      <DicaCard texto={dicaDasCategorias(categorias)} aoAbrir={aoAbrirDica} />
    </section>
  );
}

const MODOS = {
  integral: { rotulo: 'Tudo', frase: 'pagou tudo', altura: 100 },
  parcial: { rotulo: 'Uma parte', frase: 'pagou uma parte', altura: 52 },
  minimo: { rotulo: 'Só o mínimo', frase: 'pagou só o mínimo', altura: 18 },
} as const;

function Faturas({ faturas }: { faturas: Painel['raio_x']['faturas'] }) {
  const [escolhida, setEscolhida] = useState<number | null>(null);
  const periodo = `em ${faturas[0].mes.slice(0, 4)}`;
  const conta = (modo: keyof typeof MODOS) => faturas.filter((f) => f.modo === modo).length;
  const incompletas = faturas.length - conta('integral');
  const nomeMes = (mes: string) => {
    const nome = nomeDoMes(mes) ?? mes;
    return nome.charAt(0).toUpperCase() + nome.slice(1);
  };
  const lida = escolhida === null ? null : faturas[escolhida];
  return (
    <section className="card">
      <Cabeca
        titulo={`Como pagou as faturas ${periodo}`}
        sub={`Parcial ou mínimo em ${incompletas} de ${faturas.length} faturas`}
      />
      <div className={`rx-grafico${lida ? ' escolhendo' : ''}`} role="group" aria-label={`Como pagou as faturas ${periodo}`}>
        {faturas.map((f, i) => {
          const rotulo = `${nomeMes(f.mes)}: ${MODOS[f.modo].frase}`;
          return (
            <button
              key={f.mes}
              type="button"
              className={`rx-coluna${i === escolhida ? ' escolhida' : ''}`}
              aria-label={rotulo}
              aria-pressed={i === escolhida}
              title={rotulo}
              onClick={() => setEscolhida(i)}
              onMouseEnter={() => setEscolhida(i)}
              onFocus={() => setEscolhida(i)}
            >
              <span className="rx-coluna-area">
                <span className={`rx-coluna-barra ${f.modo}`} style={{ height: `${MODOS[f.modo].altura}%` }} />
              </span>
              <span className="rx-coluna-mes" aria-hidden="true">
                {inicialDoMes(f.mes)}
              </span>
            </button>
          );
        })}
      </div>
      <div className="rx-legenda">
        {(Object.keys(MODOS) as (keyof typeof MODOS)[]).map((modo) => (
          <span key={modo}>
            <i className={modo} />
            {MODOS[modo].rotulo} <b>{conta(modo)}</b>
          </span>
        ))}
      </div>
      <p className="rx-leitura" aria-live="polite">
        {lida ? `${nomeMes(lida.mes)}: ${MODOS[lida.modo].frase}.` : 'Toque num mês para ver como pagou.'}
      </p>
    </section>
  );
}
