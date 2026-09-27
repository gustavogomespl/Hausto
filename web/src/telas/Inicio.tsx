import { useRef, type ComponentType } from 'react';
import type { Aviso, CampoAncora, Painel, Simulacao } from '../api';
import { useArrastarRolagem } from '../componentes/arrastar';
import { CardAviso } from '../componentes/CardAviso';
import { DicaFatura } from '../componentes/DicaFatura';
import { Banco, CartaoVirtual, Celular, CodigoBarras, Cofrinho, Credito, Olho, OlhoFechado, Pix, Seta } from '../componentes/Icones';
import { useValoresOcultos } from '../componentes/Oculto';
import { OpenFinance } from '../componentes/OpenFinance';
import { Valor } from '../componentes/Valor';
import { diaMesCurto } from '../formato';
import './Inicio.css';

const ATALHOS: { rotulo: string; Icone: ComponentType<{ tamanho?: number }>; selo?: string }[] = [
  { rotulo: 'Pix e transferir', Icone: Pix },
  { rotulo: 'Pagar', Icone: CodigoBarras },
  { rotulo: 'Crédito disponível', Icone: Credito, selo: 'Oferta' },
  { rotulo: 'Cartão virtual', Icone: CartaoVirtual },
  { rotulo: 'Cofrinho', Icone: Cofrinho },
  { rotulo: 'Recarga de celular', Icone: Celular },
];

type Props = {
  painel: Painel;
  avisos: Aviso[];
  /** Contas do backend para a dica do card da fatura; ausente enquanto carrega ou se falhar. */
  simulacao?: Simulacao | null;
  aoAbrirAncora: (campo: CampoAncora) => void;
  aoAbrirAviso: (aviso: Aviso) => void;
  aoDispensarAviso: (aviso: Aviso) => void;
};

export function Inicio({ painel, avisos, simulacao = null, aoAbrirAncora, aoAbrirAviso, aoDispensarAviso }: Props) {
  const { conta, cartao } = painel;
  const { ocultos, alternar } = useValoresOcultos();
  const atalhos = useRef<HTMLDivElement>(null);
  useArrastarRolagem(atalhos);
  // O acompanhamento do plano combinado vem antes dos demais avisos.
  const emOrdem = [...avisos].sort((a, b) => Number(b.id === 'plano') - Number(a.id === 'plano'));
  return (
    <div className="pagina">
      <div className="inicio-titulo">
        <h1 className="pagina-titulo">Minha conta</h1>
        <button
          type="button"
          className="inicio-olho"
          onClick={alternar}
          aria-pressed={ocultos}
          aria-label={ocultos ? 'Mostrar valores' : 'Ocultar valores'}
        >
          {ocultos ? <Olho tamanho={28} /> : <OlhoFechado tamanho={28} />}
        </button>
      </div>

      <div className="atalhos" ref={atalhos}>
        {ATALHOS.map(({ rotulo, Icone, selo }) => (
          <div key={rotulo} className="atalho">
            {selo && <span className="atalho-selo">{selo}</span>}
            <span className="atalho-icone">
              <Icone tamanho={30} />
            </span>
            <span>{rotulo}</span>
          </div>
        ))}
      </div>

      {emOrdem.map((aviso) => (
        <CardAviso key={aviso.id} aviso={aviso} aoAbrir={aoAbrirAviso} aoDispensar={() => aoDispensarAviso(aviso)} />
      ))}

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
        <OpenFinance />
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
        {cartao.fatura !== null && <DicaFatura simulacao={simulacao} aoAbrir={() => aoAbrirAncora('fatura')} />}
      </section>
    </div>
  );
}
