import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ProgressoPlano as Progresso } from '../../api';
import { ProgressoPlano } from './ProgressoPlano';

const dados = (extra: Partial<Progresso> = {}): Progresso => ({
  limite_diario: 90,
  dias_decorridos: 5,
  dias_totais: 20,
  gasto_real: 640,
  gasto_previsto: 450,
  status: 'acima',
  ...extra,
});

describe('<ProgressoPlano>', () => {
  it('acima do plano: diz com texto, não só com cor, e mostra "Dia X de Y"', () => {
    const { container } = render(<ProgressoPlano dados={dados()} />);

    expect(screen.getByText('acima do plano')).toBeTruthy();
    expect(screen.queryByText('dentro do plano')).toBeNull();
    expect(screen.getByText('Dia 5 de 20')).toBeTruthy();
    expect(screen.getByText('R$ 640,00')).toBeTruthy();
    expect(screen.getByText('R$ 450,00')).toBeTruthy();
    expect(screen.getByText('R$ 90,00')).toBeTruthy();
    // Régua = plano inteiro (90 × 20 = 1.800): previsto em 25%.
    expect(container.querySelector<HTMLElement>('.progresso-marcador')!.style.left).toBe('25%');
  });

  it('dentro do plano mostra o texto verde de "dentro do plano"', () => {
    const { container } = render(<ProgressoPlano dados={dados({ gasto_real: 300, status: 'dentro' })} />);

    expect(screen.getByText('dentro do plano')).toBeTruthy();
    expect(screen.queryByText('acima do plano')).toBeNull();
    expect(container.querySelector('.progresso-plano')?.classList.contains('dentro')).toBe(true);
  });

  it('versão compacta esconde a linha do limite diário', () => {
    render(<ProgressoPlano dados={dados()} compacto />);

    expect(screen.getByText('Dia 5 de 20')).toBeTruthy();
    expect(screen.queryByText(/por dia no dia a dia/)).toBeNull();
  });
});
