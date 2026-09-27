import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { EventoTempo } from '../../api';
import { LinhaDoTempo } from './LinhaDoTempo';

describe('<LinhaDoTempo>', () => {
  it('ordena por data e mostra dd/mm', () => {
    const eventos: EventoTempo[] = [
      { data: '2025-12-25', rotulo: 'Vence a fatura', valor: 1980, tipo: 'fatura' },
      { data: '2026-01-07', rotulo: 'Salário', valor: 2500, tipo: 'renda' },
      { data: '2025-12-10', rotulo: 'Hoje', valor: null, tipo: 'hoje' },
      { data: '2025-12-15', rotulo: 'Aluguel', valor: 900, tipo: 'despesa' },
    ];
    const { container } = render(<LinhaDoTempo eventos={eventos} />);

    const datas = [...container.querySelectorAll('time')].map((t) => t.textContent);
    expect(datas).toEqual(['10/12', '15/12', '25/12', '07/01']);
    expect(screen.getByText('+R$ 2.500,00')).toBeTruthy();
    expect(screen.getByText('-R$ 1.980,00')).toBeTruthy();
    expect(container.querySelectorAll('li')[0].querySelector('b')).toBeNull();
  });
});
