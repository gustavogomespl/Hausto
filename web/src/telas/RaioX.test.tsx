import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Painel, Plano } from '../api';
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

  it('mostra "Posso comprar?" e a meta que faz sentido com o saldo do cliente', () => {
    const { rerender } = render(<RaioX plano={null} aviso={undefined} aoAbrirAncora={() => {}} aoAbrirAviso={() => {}} painel={painel({ meta: { tipo: 'sair_do_vermelho', falta: 1234.5 } })} />);
    expect(screen.getByText('Posso comprar?')).toBeTruthy();
    expect(screen.getByText('Meta: sair do vermelho')).toBeTruthy();
    expect(screen.getByText(/Faltam R\$ 1\.234/)).toBeTruthy();

    rerender(<RaioX plano={null} aviso={undefined} aoAbrirAncora={() => {}} aoAbrirAviso={() => {}} painel={painel({ meta: { tipo: 'reserva', alvo: 3000, guardado: 1050, pct: 0.35 } })} />);
    expect(screen.getByText('Meta: reserva')).toBeTruthy();
    expect(screen.getByText('35% guardado')).toBeTruthy();
  });

  it('o cliente toca na meta e define a dele', async () => {
    const aoSalvarMeta = vi.fn().mockResolvedValue(undefined);
    render(
      <RaioX plano={null} aviso={undefined} aoAbrirAncora={() => {}} aoAbrirAviso={() => {}} aoSalvarMeta={aoSalvarMeta}
        painel={painel({ meta: { tipo: 'sair_do_vermelho', falta: 500 } })} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /configurar meta/i }));
    fireEvent.change(screen.getByLabelText('Nome da meta'), { target: { value: 'Casa' } });
    fireEvent.change(screen.getByLabelText('Quanto quer juntar (R$)'), { target: { value: '8000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar meta' }));
    await waitFor(() => expect(aoSalvarMeta).toHaveBeenCalledWith({ nome: 'Casa', valor: 8000 }));
  });

  it('mostra a meta que o cliente definiu', () => {
    render(
      <RaioX plano={null} aviso={undefined} aoAbrirAncora={() => {}} aoAbrirAviso={() => {}}
        painel={painel({ meta: { tipo: 'personalizada', nome: 'Casa', alvo: 8000, guardado: 2000, pct: 0.25 } })} />,
    );
    expect(screen.getByText('Meta: Casa')).toBeTruthy();
    expect(screen.getByText('25% guardado')).toBeTruthy();
  });

  it('se salvar falhar, avisa no formulário; Esc fecha', async () => {
    const aoSalvarMeta = vi.fn().mockRejectedValue(new Error('rede'));
    render(
      <RaioX plano={null} aviso={undefined} aoAbrirAncora={() => {}} aoAbrirAviso={() => {}} aoSalvarMeta={aoSalvarMeta}
        painel={painel({ meta: { tipo: 'sair_do_vermelho', falta: 500 } })} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /configurar meta/i }));
    fireEvent.change(screen.getByLabelText('Nome da meta'), { target: { value: 'Casa' } });
    fireEvent.change(screen.getByLabelText('Quanto quer juntar (R$)'), { target: { value: '8000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar meta' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
