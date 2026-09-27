import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { Aviso, Painel } from '../api';
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

const semAviso = { aviso: undefined, aoAbrirAviso: () => {}, aoDispensarAviso: () => {} };

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
      const [aviso, setAviso] = useState<Aviso | undefined>(AVISO);
      return (
        <Inicio
          painel={PAINEL}
          aviso={aviso}
          aoAbrirAncora={() => {}}
          aoAbrirAviso={() => {}}
          aoDispensarAviso={(a) => {
            aoDispensar(a);
            setAviso(undefined);
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
});
