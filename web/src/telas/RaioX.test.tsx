import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Painel, Plano } from '../api';
import { alivioDasParcelas, dicaDasCategorias, RaioX } from './RaioX';

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

const PLANO: Plano = {
  pagamento_fatura: 920,
  reserva: 150,
  limite_diario: 90,
  inicio: '2025-12-10',
  fim: '2026-01-07',
  progresso: { limite_diario: 90, dias_decorridos: 5, dias_totais: 28, gasto_real: 640, gasto_previsto: 450, status: 'acima' },
};

const renderizar = (p: Painel, plano: Plano | null = null) =>
  render(<RaioX painel={p} plano={plano} aviso={undefined} aoAbrirAncora={() => {}} aoAbrirAviso={() => {}} />);

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
    expect(screen.getByText('Parcelas')).toBeTruthy();
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

  it('com plano aceito mostra o card "Seu plano" no topo', () => {
    renderizar(painel(), PLANO);

    expect(screen.getByText('Seu plano até 07/01')).toBeTruthy();
    expect(screen.getByText('R$ 90')).toBeTruthy();
    expect(screen.getByText('Dia 5 de 28')).toBeTruthy();
    expect(screen.getByText('acima do plano')).toBeTruthy();
    expect(screen.getByText('R$ 920')).toBeTruthy();
    expect(screen.getByText('R$ 150')).toBeTruthy();
  });

  it('sem plano não mostra o card', () => {
    renderizar(painel());

    expect(screen.queryByText(/Seu plano/)).toBeNull();
    expect(screen.queryByText(/do plano/)).toBeNull();
  });

  it('mostra quando vem a última parcela e a dica de quando a fatura fica mais leve', () => {
    renderizar(painel());

    // Fatura de dezembro, parcela 3 de 10: a última vem em julho; agosto já vem sem ela.
    expect(screen.getByText(/a última vem em julho/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Em agosto, a fatura fica R$ 250 mais leve.' })).toBeTruthy();
  });

  it('põe em negrito os valores em reais e as porcentagens das dicas', () => {
    renderizar(painel({ categorias: [{ categoria: 'Mercado', valor: 400 }, { categoria: 'Posto', valor: 200 }] }));

    const negritos = [...document.querySelectorAll('.rx-dica b')].map((b) => b.textContent);
    expect(negritos).toEqual(['R$ 400', '67%', 'R$ 250']);
  });

  it('tocar num mês do histórico lê como a fatura foi paga', () => {
    renderizar(painel());

    expect(screen.getByText('Toque num mês para ver como pagou.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Novembro: pagou só o mínimo' }));
    expect(screen.getByText('Novembro: pagou só o mínimo.')).toBeTruthy();
  });
});

describe('simulações do Raio-X', () => {
  const META = { rotulo: 'Casa', nome: 'entrada da casa própria', icone: 'casa' as const, alvo: 10000, guardado: 3200, falta: 6800, pct: 32 };

  it('mostra "Posso comprar?" e a meta; cada um abre o chat do seu jeito', () => {
    const aoSimularCompra = vi.fn();
    const aoAbrirAncora = vi.fn();
    render(
      <RaioX
        painel={{ ...painel(), meta: META }}
        plano={null}
        aviso={undefined}
        aoAbrirAncora={aoAbrirAncora}
        aoAbrirAviso={() => {}}
        aoSimularCompra={aoSimularCompra}
      />,
    );

    expect(screen.getByText('Meta: casa')).toBeTruthy();
    expect(screen.getByText('32% guardado')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /Posso comprar\?/ }));
    fireEvent.click(screen.getByRole('button', { name: /Meta: casa, 32% guardado/ }));

    expect(aoSimularCompra).toHaveBeenCalledOnce();
    expect(aoAbrirAncora).toHaveBeenCalledWith('meta');
  });

  it('sem meta, "Posso comprar?" ocupa a linha inteira', () => {
    const { container } = render(
      <RaioX painel={painel()} plano={null} aviso={undefined} aoAbrirAncora={() => {}} aoAbrirAviso={() => {}} aoSimularCompra={() => {}} />,
    );

    expect(screen.queryByText(/guardado/)).toBeNull();
    expect(container.querySelector('.rx-tile.inteira')).toBeTruthy();
  });
});

describe('dicas do Raio-X', () => {
  it('soma no mesmo mês as parcelas que acabam juntas', () => {
    const itens = [
      { descricao: 'Geladeira', valor: 210, atual: 3, total: 6 },
      { descricao: 'Celular', valor: 120, atual: 5, total: 10 },
      { descricao: 'TV', valor: 90, atual: 8, total: 11 },
    ];
    // Fatura de outubro (índice 9).
    expect(alivioDasParcelas(itens, 9)).toBe('Em fevereiro, a fatura fica R$ 300 mais leve. Em abril, mais R$ 120.');
  });

  it('aponta a categoria que mais pesou', () => {
    expect(
      dicaDasCategorias([
        { categoria: 'Posto', valor: 200 },
        { categoria: 'Mercado', valor: 400 },
      ]),
    ).toBe('Mercado pesou mais: R$ 400, 67% das compras desta fatura.');
    expect(dicaDasCategorias([{ categoria: 'Mercado', valor: 400 }])).toBe(
      'Todas as compras desta fatura foram em Mercado: R$ 400.',
    );
  });
});
