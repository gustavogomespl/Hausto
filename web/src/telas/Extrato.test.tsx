import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Transacao } from '../api';
import { Extrato } from './Extrato';

const t = (data: string, tipo: 'E' | 'S', descr: string, vlr: number): Transacao => ({
  data,
  tipo,
  descr,
  vlr,
  categoria: tipo === 'E' ? 'Salário' : 'Mercado',
  subcategoria: '',
  saldo_apos: 0,
});

const TRANSACOES = [
  t('2025-10-07T09:00:00', 'E', 'Salário ACME', 2500),
  t('2025-10-07T12:00:00', 'S', 'Supermercado Dia', 180),
  t('2025-10-05T18:00:00', 'S', 'Farmácia Pague Menos', 45),
];

afterEach(() => vi.unstubAllGlobals());

async function renderizar() {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => TRANSACOES }));
  render(<Extrato idUsuario="u-1" hoje="2025-10-07" />);
  await screen.findByText('Salário ACME');
}

const itensDoDia = (titulo: string) =>
  within(screen.getByText(titulo).closest('section')!)
    .getAllByRole('listitem')
    .map((li) => li.querySelector('strong')!.textContent);

describe('<Extrato>', () => {
  it('agrupa as transações por dia, mais recentes primeiro', async () => {
    await renderizar();

    const titulos = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(titulos).toEqual(['Hoje · 07/10', '5 de outubro']);
    expect(itensDoDia('Hoje · 07/10')).toEqual(['Salário ACME', 'Supermercado Dia']);
    expect(itensDoDia('5 de outubro')).toEqual(['Farmácia Pague Menos']);
  });

  it('filtra entradas e saídas', async () => {
    await renderizar();

    fireEvent.click(screen.getByRole('tab', { name: 'Entradas' }));
    expect(screen.getByText('Salário ACME')).toBeTruthy();
    expect(screen.queryByText('Supermercado Dia')).toBeNull();
    expect(screen.queryByText('5 de outubro')).toBeNull();

    fireEvent.click(screen.getByRole('tab', { name: 'Saídas' }));
    expect(screen.queryByText('Salário ACME')).toBeNull();
    expect(itensDoDia('Hoje · 07/10')).toEqual(['Supermercado Dia']);
    expect(itensDoDia('5 de outubro')).toEqual(['Farmácia Pague Menos']);
  });
});
