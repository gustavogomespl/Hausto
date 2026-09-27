import { useState } from 'react';
import type { Aviso, CampoAncora, MetaDoCliente, Painel, Plano } from '../api';
import { iconeDaCategoria } from '../categorias';
import { CardAviso } from '../componentes/CardAviso';
import { Cofre, Sacola, Seta } from '../componentes/Icones';
import { Valor } from '../componentes/Valor';
import { ProgressoPlano } from '../chat/visuais/ProgressoPlano';
import { diaMesNumerico, dinheiroCurto, inicialDoMes, nomeDoMes } from '../formato';
import './RaioX.css';

type Props = {
  painel: Painel;
  plano: Plano | null;
  aviso: Aviso | undefined;
  aoAbrirAncora: (campo: CampoAncora) => void;
  aoAbrirAviso: (aviso: Aviso) => void;
  aoSalvarMeta?: (meta: MetaDoCliente) => Promise<void>;
};

export function RaioX({ painel, plano, aviso, aoAbrirAncora, aoAbrirAviso, aoSalvarMeta }: Props) {
  const { raio_x: rx, cartao } = painel;
  // A fatura leva o nome do mês em que vence (vence 25/12 -> fatura de dezembro).
  const mesFatura = nomeDoMes(cartao.vencimento);

  return (
    <div className="pagina raiox">
      <div className="raiox-titulo">
        <h1 className="pagina-titulo">Raio-X</h1>
        {mesFatura && <span>Fatura de {mesFatura}</span>}
      </div>

      {plano && <SeuPlano plano={plano} />}

      {aviso && <CardAviso aviso={aviso} aoAbrir={aoAbrirAviso} />}

      <Baloes meta={rx.meta} aoSalvarMeta={aoSalvarMeta} />

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
            <b>{dinheiroCurto(rx.gasto_por_dia.valor)}</b> × {rx.gasto_por_dia.dias} dias ≈{' '}
            <b>{dinheiroCurto(rx.gasto_por_dia.total)}</b> em compras
          </p>
          {cartao.fatura !== null && (
            <div className="rx-linha-total">
              <span>Fatura aberta</span>
              <span>{dinheiroCurto(cartao.fatura)}</span>
            </div>
          )}
        </section>
      )}

      {rx.juros_por_dia && (
        <section className="card rx-mini">
          <Cabeca titulo="Juros por dia" />
          <Valor
            className="rx-valor"
            valor={rx.juros_por_dia.valor}
            texto={dinheiroCurto(rx.juros_por_dia.valor)}
            campo="juros_por_dia"
            aoTocar={aoAbrirAncora}
          />
          <p className="rx-detalhe">
            Uns <b>{dinheiroCurto(rx.juros_por_dia.custo_30_dias)}</b> no mês, pagando{' '}
            <b>{dinheiroCurto(rx.juros_por_dia.pagando)}</b>
          </p>
        </section>
      )}

      <section className="card rx-mini">
        <Cabeca titulo="Parcelas deste mês" />
        <Valor
          className="rx-valor"
          valor={rx.parcelas.total_mes}
          texto={dinheiroCurto(rx.parcelas.total_mes)}
          campo="parcelas"
          aoTocar={aoAbrirAncora}
        />
        <p className="rx-detalhe">{resumoParcelas(rx.parcelas.itens, mesFatura)}</p>
      </section>

      {(rx.categorias.length > 0 || rx.parcelas.itens.length > 0) && (
        <h2 className="secao-titulo">Detalhes da fatura</h2>
      )}

      {rx.categorias.length > 0 && <Categorias categorias={rx.categorias} />}

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
                  <b>{dinheiroCurto(p.valor)}</b> por mês
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {rx.faturas.length > 0 && <Faturas faturas={rx.faturas} />}
    </div>
  );
}

/** "Posso comprar?" (informativo) e a meta, que o cliente toca para definir a dele. */
function Baloes({ meta, aoSalvarMeta }: { meta: Painel['raio_x']['meta']; aoSalvarMeta?: (m: MetaDoCliente) => Promise<void> }) {
  const [editando, setEditando] = useState(false);
  return (
    <>
      <div className="rx-baloes">
        <section className="card rx-balao">
          <span className="rx-balao-icone"><Sacola tamanho={18} /></span>
          <p>Simular compra</p>
          <strong>Posso comprar?</strong>
        </section>
        {meta && (
          <button type="button" className="card rx-balao rx-balao-acao" onClick={() => setEditando(true)}
            aria-label={`${tituloDaMeta(meta)}. Configurar meta`}>
            <span className="rx-balao-topo">
              <span className="rx-balao-icone"><Cofre tamanho={18} /></span>
              <Seta tamanho={20} />
            </span>
            <span className="rx-balao-rotulo">{tituloDaMeta(meta)}</span>
            {meta.tipo === 'sair_do_vermelho' ? (
              <strong>Faltam {dinheiroCurto(meta.falta)}</strong>
            ) : (
              <>
                <strong>{Math.round(meta.pct * 100)}% guardado</strong>
                <span className="rx-balao-barra" aria-hidden="true">
                  <span style={{ width: `${Math.max(3, meta.pct * 100)}%` }} />
                </span>
              </>
            )}
          </button>
        )}
      </div>
      {editando && (
        <EditarMeta
          inicial={meta?.tipo === 'personalizada' ? { nome: meta.nome, valor: meta.alvo } : undefined}
          aoFechar={() => setEditando(false)}
          aoSalvar={async (m) => {
            await aoSalvarMeta?.(m);
            setEditando(false);
          }}
        />
      )}
    </>
  );
}

function tituloDaMeta(meta: NonNullable<Painel['raio_x']['meta']>) {
  if (meta.tipo === 'sair_do_vermelho') return 'Meta: sair do vermelho';
  return meta.tipo === 'personalizada' ? `Meta: ${meta.nome}` : 'Meta: reserva';
}

function EditarMeta({ inicial, aoFechar, aoSalvar }: {
  inicial?: MetaDoCliente; aoFechar: () => void; aoSalvar: (m: MetaDoCliente) => Promise<void>;
}) {
  const [nome, setNome] = useState(inicial?.nome ?? '');
  const [valor, setValor] = useState(inicial ? String(inicial.valor) : '');
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(false);
  const numero = Number(valor.replace(/\./g, '').replace(',', '.'));
  const valido = nome.trim().length > 0 && numero > 0;
  return (
    <div
      className="rx-meta-fundo"
      role="dialog"
      aria-modal="true"
      aria-label="Configurar meta"
      onKeyDown={(e) => e.key === 'Escape' && aoFechar()}
      onClick={(e) => e.target === e.currentTarget && aoFechar()}
    >
      <form
        className="card rx-meta-form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!valido) return;
          setSalvando(true);
          setErro(false);
          try {
            await aoSalvar({ nome: nome.trim(), valor: numero });
          } catch {
            setErro(true);
          } finally {
            setSalvando(false);
          }
        }}
      >
        <h3>Sua meta</h3>
        <label>
          Nome da meta
          <input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: casa, carro, reserva" maxLength={40} autoFocus />
        </label>
        <label>
          Quanto quer juntar (R$)
          <input value={valor} onChange={(e) => setValor(e.target.value)} inputMode="decimal" placeholder="Ex.: 5.000" />
        </label>
        {erro && (
          <p className="rx-meta-erro" role="alert">
            Não deu para salvar agora. Tente de novo.
          </p>
        )}
        <div className="rx-meta-botoes">
          <button type="button" className="rx-meta-cancelar" onClick={aoFechar}>Cancelar</button>
          <button type="submit" className="botao-laranja" disabled={!valido || salvando}>Salvar meta</button>
        </div>
      </form>
    </div>
  );
}

/** O plano que o cliente aceitou no chat, acompanhado dia a dia até a próxima renda. */
function SeuPlano({ plano }: { plano: Plano }) {
  return (
    <section className="card rx-plano">
      <Cabeca titulo={`Seu plano até ${diaMesNumerico(plano.fim)}`} sub="Combinado com o Hausto" />
      <div className="rx-destaque">
        <strong className="rx-plano-limite">{dinheiroCurto(plano.limite_diario)}</strong>
        <span>por dia no dia a dia</span>
      </div>
      <ProgressoPlano dados={plano.progresso} compacto />
      <dl className="rx-plano-combinado">
        <div>
          <dt>Pagar da fatura</dt>
          <dd>{dinheiroCurto(plano.pagamento_fatura)}</dd>
        </div>
        <div>
          <dt>Guardar de reserva</dt>
          <dd>{dinheiroCurto(plano.reserva)}</dd>
        </div>
      </dl>
    </section>
  );
}

function Cabeca({ titulo, sub }: { titulo: string; sub?: string }) {
  return (
    <div className="card-cabeca">
      <div>
        <h3>{titulo}</h3>
        {sub && <p>{sub}</p>}
      </div>
      <Seta tamanho={22} />
    </div>
  );
}

function resumoParcelas(itens: Painel['raio_x']['parcelas']['itens'], mes: string | null) {
  if (itens.length === 0) return 'Nenhuma parcela nesta fatura.';
  const nomes = itens.map((p) => `${p.descricao} (${p.atual} de ${p.total})`);
  const lista = nomes.length > 1 ? `${nomes.slice(0, -1).join(', ')} e ${nomes.at(-1)}` : nomes[0];
  return `${mes ? `Na fatura de ${mes}` : 'Nesta fatura'}: ${lista}`;
}

function Categorias({ categorias }: { categorias: Painel['raio_x']['categorias'] }) {
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
              <b>{dinheiroCurto(c.valor)}</b>
            </div>
            <div className="rx-barra" style={{ width: `${Math.max(4, (c.valor / maior) * 100)}%` }} />
          </li>
        ))}
      </ul>
    </section>
  );
}

const MODOS = {
  integral: { rotulo: 'Tudo', altura: 100 },
  parcial: { rotulo: 'Uma parte', altura: 52 },
  minimo: { rotulo: 'Só o mínimo', altura: 18 },
} as const;

function Faturas({ faturas }: { faturas: Painel['raio_x']['faturas'] }) {
  const periodo = `em ${faturas[0].mes.slice(0, 4)}`;
  const conta = (modo: keyof typeof MODOS) => faturas.filter((f) => f.modo === modo).length;
  const incompletas = faturas.length - conta('integral');
  return (
    <section className="card">
      <Cabeca
        titulo={`Como pagou as faturas ${periodo}`}
        sub={`Parcial ou mínimo em ${incompletas} de ${faturas.length} faturas`}
      />
      <div className="rx-grafico" role="img" aria-label={`Como pagou as faturas ${periodo}`}>
        {faturas.map((f) => (
          <div key={f.mes} className="rx-coluna">
            <div className="rx-coluna-area">
              <span
                className={`rx-coluna-barra ${f.modo}`}
                style={{ height: `${MODOS[f.modo].altura}%` }}
                title={`${nomeDoMes(f.mes)}: ${MODOS[f.modo].rotulo}`}
              />
            </div>
            <span className="rx-coluna-mes">{inicialDoMes(f.mes)}</span>
          </div>
        ))}
      </div>
      <div className="rx-legenda">
        {(Object.keys(MODOS) as (keyof typeof MODOS)[]).map((modo) => (
          <span key={modo}>
            <i className={modo} />
            {MODOS[modo].rotulo} <b>{conta(modo)}</b>
          </span>
        ))}
      </div>
    </section>
  );
}
