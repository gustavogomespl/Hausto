import type { ComponentType } from 'react';
import type { Aviso, CampoAncora, Painel } from '../api';
import { CardAviso } from '../componentes/CardAviso';
import { Banco, CartaoVirtual, CodigoBarras, Credito, OlhoFechado, Pix, Seta } from '../componentes/Icones';
import { Valor } from '../componentes/Valor';
import { diaMesCurto } from '../formato';
import './Inicio.css';

const ATALHOS: { rotulo: string; Icone: ComponentType<{ tamanho?: number }> }[] = [
  { rotulo: 'Pix e transferir', Icone: Pix },
  { rotulo: 'Pagar', Icone: CodigoBarras },
  { rotulo: 'Crédito disponível', Icone: Credito },
  { rotulo: 'Cartão virtual', Icone: CartaoVirtual },
];

type Props = {
  painel: Painel;
  aviso: Aviso | undefined;
  aoAbrirAncora: (campo: CampoAncora) => void;
  aoAbrirAviso: (aviso: Aviso) => void;
  aoDispensarAviso: (aviso: Aviso) => void;
};

export function Inicio({ painel, aviso, aoAbrirAncora, aoAbrirAviso, aoDispensarAviso }: Props) {
  const { conta, cartao } = painel;
  return (
    <div className="pagina">
      <div className="inicio-titulo">
        <h1 className="pagina-titulo">Minha conta</h1>
        <OlhoFechado tamanho={28} />
      </div>

      <div className="atalhos">
        {ATALHOS.map(({ rotulo, Icone }) => (
          <div key={rotulo} className="atalho">
            <span className="atalho-icone">
              <Icone tamanho={30} />
            </span>
            <span>{rotulo}</span>
          </div>
        ))}
      </div>

      {aviso && (
        <CardAviso aviso={aviso} aoAbrir={aoAbrirAviso} aoDispensar={() => aoDispensarAviso(aviso)} />
      )}

      <section className="card conta">
        <div className="conta-cabeca">
          <span className="conta-icone banco">
            <Banco tamanho={18} />
          </span>
          <span>Conta corrente</span>
          <Seta tamanho={22} />
        </div>
        <span className="conta-rotulo">Saldo</span>
        <Valor className="conta-valor" valor={conta.saldo} campo="saldo" aoTocar={aoAbrirAncora} />
      </section>

      <section className="card conta">
        <div className="conta-cabeca">
          <span className="conta-icone cartao">
            <span />
            <span />
          </span>
          <span>Cartão de crédito</span>
          <Seta tamanho={22} />
        </div>
        <span className="conta-rotulo">Fatura aberta</span>
        {cartao.fatura === null ? (
          <p className="conta-vazio">Fatura ainda não fechou</p>
        ) : (
          <Valor className="conta-valor" valor={cartao.fatura} campo="fatura" aoTocar={aoAbrirAncora} />
        )}
        {cartao.vencimento && <span className="conta-rodape">Vence em {diaMesCurto(cartao.vencimento)}</span>}
      </section>
    </div>
  );
}
