import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { Aviso, Painel } from '../api';
import { ValoresOcultos } from '../componentes/Oculto';
import { Inicio } from './Inicio';

const PAINEL: Painel = {
  id_usuario: 'u-1',
  data_ref: '2025-12-10',
  perfil: 'P2',
  conta: { saldo: 850 },
  cartao: { fatura: 1980, vencimento: '2025-12-25', origem: 'fatura', mes_ref: '2025-11' },
  raio_x: {
    gasto_por_dia: null,
    juros_por_dia: null,
    parcelas: { total_mes: 0, itens: [] },
    categorias: [],
    faturas: [],
  },
};

const AVISO: Aviso = {
  id: 'fatura_vence',
  tela: 'home',
  rotulo: 'HAUSTO',
  titulo: 'Sua fatura vence em 7 dias',
  texto: 'Vale olhar antes.',
  cta: 'Ver com o Hausto',
};

const PLANO: Aviso = {
  id: 'plano',
  tela: 'home',
  rotulo: 'SEU PLANO',
  titulo: 'Você saiu do plano',
  texto: 'Nos últimos 5 dias foram R$ 640,00 no dia a dia; o plano previa R$ 450,00.',
  cta: 'Ver o que fazer',
};

const semAviso = { avisos: [], aoAbrirAviso: () => {}, aoDispensarAviso: () => {} };

describe('<Inicio>', () => {
  it('mostra "Fatura ainda não fechou" quando a fatura é nula', () => {
    render(<Inicio painel={{ ...PAINEL, cartao: { ...PAINEL.cartao, fatura: null } }} aoAbrirAncora={() => {}} {...semAviso} />);

    expect(screen.getByText('Fatura ainda não fechou')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /R\$ 1\.980/ })).toBeNull();
  });

  it('abre o Hausto pelo ✦ do saldo e da fatura', () => {
    const aoAbrirAncora = vi.fn();
    render(<Inicio painel={PAINEL} aoAbrirAncora={aoAbrirAncora} {...semAviso} />);

    fireEvent.click(screen.getByRole('button', { name: /R\$ 850,00\. Perguntar/ }));
    fireEvent.click(screen.getByRole('button', { name: /R\$ 1\.980,00\. Perguntar/ }));

    expect(aoAbrirAncora.mock.calls).toEqual([['saldo'], ['fatura']]);
  });

  it('"Agora não" dispensa e esconde o aviso', () => {
    const aoDispensar = vi.fn();
    function ComEstado() {
      const [avisos, setAvisos] = useState<Aviso[]>([AVISO]);
      return (
        <Inicio
          painel={PAINEL}
          avisos={avisos}
          aoAbrirAncora={() => {}}
          aoAbrirAviso={() => {}}
          aoDispensarAviso={(a) => {
            aoDispensar(a);
            setAvisos((lista) => lista.filter((x) => x.id !== a.id));
          }}
        />
      );
    }
    render(<ComEstado />);

    expect(screen.getByText('HAUSTO')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Agora não' }));

    expect(aoDispensar).toHaveBeenCalledWith(AVISO);
    expect(screen.queryByText(AVISO.titulo)).toBeNull();
  });

  it('empilha todos os avisos da home, com o do plano primeiro', () => {
    const aoAbrirAviso = vi.fn();
    render(<Inicio painel={PAINEL} avisos={[AVISO, PLANO]} aoAbrirAncora={() => {}} aoAbrirAviso={aoAbrirAviso} aoDispensarAviso={() => {}} />);

    const titulos = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(titulos).toEqual([PLANO.titulo, AVISO.titulo]);

    fireEvent.click(screen.getByRole('button', { name: 'Ver o que fazer' }));
    expect(aoAbrirAviso).toHaveBeenCalledWith(PLANO);
  });

  it('o olho esconde e mostra os valores', () => {
    function ComOlho() {
      const [ocultos, setOcultos] = useState(false);
      return (
        <ValoresOcultos.Provider value={{ ocultos, alternar: () => setOcultos((v) => !v) }}>
          <Inicio painel={PAINEL} aoAbrirAncora={() => {}} {...semAviso} />
        </ValoresOcultos.Provider>
      );
    }
    render(<ComOlho />);

    fireEvent.click(screen.getByRole('button', { name: 'Ocultar valores' }));
    expect(screen.queryByText(/R\$ 850/)).toBeNull();
    expect(screen.getAllByRole('button', { name: /Valor oculto/ })).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: 'Mostrar valores' }));
    expect(screen.getByText('R$ 850,00')).toBeTruthy();
  });

  it('mostra a dica do Hausto no card da fatura e abre a conversa sobre ela', () => {
    const aoAbrirAncora = vi.fn();
    render(
      <Inicio
        painel={PAINEL}
        simulacao={{
          valor_fatura: 1980,
          disponivel_para_fatura: 370,
          proxima_renda: '2026-01-05',
          opcoes: {
            integral: { atende_restricoes: false },
            parcial_viavel: { valor_pago: 370, atende_restricoes: true },
            minimo: { valor_pago: 297, atende_restricoes: true },
          },
          status: 'ok',
          recomendada: 'parcial_viavel',
        }}
        aoAbrirAncora={aoAbrirAncora}
        {...semAviso}
      />,
    );

    expect(screen.getByText('Não pague tudo agora')).toBeTruthy();
    expect(screen.getByText('R$ 370,00')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Não pague tudo agora/ }));
    expect(aoAbrirAncora).toHaveBeenCalledWith('fatura');
  });
});
