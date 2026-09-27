import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { OpcaoVisual } from '../../api';
import { ComparaOpcoes } from './ComparaOpcoes';

describe('<ComparaOpcoes>', () => {
  const opcoes: OpcaoVisual[] = [
    { rotulo: 'Pagar tudo', pago: 1980, custo: 0, divida_restante: 0, cabe: false, destaque: false },
    { rotulo: 'Pagar R$ 920', pago: 920, custo: 95, divida_restante: 1060, cabe: true, destaque: true },
    { rotulo: 'Só o mínimo', pago: 297, custo: 260, divida_restante: 1683, cabe: true, destaque: false },
  ];

  it('marca a opção que não cabe com texto, não só com cor', () => {
    const { container } = render(<ComparaOpcoes opcoes={opcoes} />);
    const itens = container.querySelectorAll('.opcao');

    expect(screen.getAllByText('aperta os essenciais')).toHaveLength(1);
    expect(itens[0].textContent).toContain('aperta os essenciais');
    expect(itens[0].textContent).toContain('Sem juros');
    expect(screen.getByText('R$ 95,00 de juros')).toBeTruthy();
  });

  it('realça só a opção em destaque', () => {
    const { container } = render(<ComparaOpcoes opcoes={opcoes} />);
    const itens = [...container.querySelectorAll('.opcao')];

    expect(itens.map((i) => i.classList.contains('destaque'))).toEqual([false, true, false]);
    expect(itens[1].getAttribute('data-destaque')).toBe('true');
    expect(screen.queryByText(/recomendad/i)).toBeNull();
  });

  it('sem juros mostra só o selo, sem trilha de custo', () => {
    const { container } = render(<ComparaOpcoes opcoes={opcoes} />);
    const itens = container.querySelectorAll('.opcao');

    expect(itens[0].querySelector('.opcao-sem-juros')?.textContent).toBe('Sem juros');
    expect(itens[0].querySelector('.opcao-trilho')).toBeNull();
    expect(itens[1].querySelector('.opcao-trilho span')).toBeTruthy();
    expect(itens[2].querySelector('.opcao-trilho span')).toBeTruthy();
  });

  it('sem folga: um aviso só no resumo, sem repetir em cada opção', () => {
    const semFolga: OpcaoVisual[] = [
      { rotulo: 'Pagar tudo', pago: 1150.91, custo: 143.79, juros_cartao: 0, juros_conta: 143.79, divida_restante: 2163.33, cabe: false, destaque: false },
      { rotulo: 'Pagar o mínimo', pago: 172.64, custo: 221.84, juros_cartao: 143.08, juros_conta: 78.76, divida_restante: 2163.33, cabe: false, destaque: false },
    ];
    render(<ComparaOpcoes opcoes={semFolga} />);

    expect(screen.queryByText('aperta os essenciais')).toBeNull();
    expect(screen.getByText('juros do limite da conta')).toBeTruthy();
    expect(screen.getByText('juros do cartão R$ 143,08 + juros da conta R$ 78,76')).toBeTruthy();
  });
});
