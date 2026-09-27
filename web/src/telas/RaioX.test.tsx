import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Painel } from '../api';
import { RaioX } from './RaioX';

const painel = (raioX: Partial<Painel['raio_x']> = {}): Painel => ({
  id_usuario: 'u-1',
  data_ref: '2025-12-10',
  perfil: 'P2',
  conta: { saldo: 850 },
  cartao: { fatura: 1980, vencimento: '2025-12-25', origem: 'fatura', mes_ref: '2025-11' },
  raio_x: {
    gasto_por_dia: { valor: 42, dias: 30, total: 1260, mes_ref: '2025-11' },
    juros_por_dia: { valor: 2.35, pagando: 300, custo_30_dias: 70.5 },
    parcelas: { total_mes: 250, itens: [{ descricao: 'Geladeira', valor: 250, atual: 3, total: 10 }] },
    categorias: [{ categoria: 'Mercado', valor: 600 }],
    faturas: [
      { mes: '2025-09', modo: 'integral' },
      { mes: '2025-10', modo: 'parcial' },
      { mes: '2025-11', modo: 'minimo' },
      { mes: '2025-12', modo: 'minimo' },
    ],
    ...raioX,
  },
});

const renderizar = (p: Painel) =>
  render(<RaioX painel={p} aviso={undefined} aoAbrirAncora={() => {}} aoAbrirAviso={() => {}} />);

describe('<RaioX>', () => {
  it('nomeia a fatura pelo mês do vencimento, não pelo mês de consumo', () => {
    renderizar(painel());

    expect(screen.getByText('Fatura de dezembro')).toBeTruthy();
    expect(screen.queryByText('Fatura de novembro')).toBeNull();
    expect(screen.getByText('Na fatura de dezembro: Geladeira (3 de 10)')).toBeTruthy();
    expect(screen.getByText('Compras desta fatura, sem as parcelas')).toBeTruthy();
  });

  it('esconde gasto e juros por dia quando vêm nulos', () => {
    renderizar(painel({ gasto_por_dia: null, juros_por_dia: null }));

    expect(screen.queryByText('Gasto no cartão por dia')).toBeNull();
    expect(screen.queryByText('Juros por dia')).toBeNull();
    expect(screen.getByText('Parcelas deste mês')).toBeTruthy();
  });

  it('avisa quando não há parcelas e some com a lista', () => {
    renderizar(painel({ parcelas: { total_mes: 0, itens: [] } }));

    expect(screen.getByText('Nenhuma parcela nesta fatura.')).toBeTruthy();
    expect(screen.queryByText('Compras parceladas')).toBeNull();
  });

  it('conta as faturas por modo de pagamento na legenda', () => {
    const { container } = renderizar(painel());

    expect(screen.getByText('Como pagou as faturas em 2025')).toBeTruthy();
    expect(screen.getByText('Parcial ou mínimo em 3 de 4 faturas')).toBeTruthy();
    const legenda = [...container.querySelectorAll('.rx-legenda span')].map((s) => s.textContent);
    expect(legenda).toEqual(['Tudo 1', 'Uma parte 1', 'Só o mínimo 2']);
  });
});
