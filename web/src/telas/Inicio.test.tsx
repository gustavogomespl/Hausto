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
});
