import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { EtapaCaixa } from '../../api';
import { DivisaoDinheiro, dividir } from './DivisaoDinheiro';

const comSobra: EtapaCaixa[] = [
  { rotulo: 'Saldo hoje', valor: 20873.31, tipo: 'inicio' },
  { rotulo: 'Entradas e saídas previstas até 25/12', valor: -886.03, tipo: 'saida' },
  { rotulo: 'Fatura: pagar tudo', valor: -1744.74, tipo: 'saida' },
  { rotulo: 'Essenciais até 07/01', valor: -355.51, tipo: 'saida' },
  { rotulo: 'Até 07/01', valor: 17887.03, tipo: 'resultado' },
];

const comFalta: EtapaCaixa[] = [
  { rotulo: 'Saldo hoje', valor: -8130, tipo: 'inicio' },
  { rotulo: 'Entradas e saídas previstas até 20/12', valor: 921.66, tipo: 'entrada' },
  { rotulo: 'Fatura: pagar o mínimo', valor: -145.52, tipo: 'saida' },
  { rotulo: 'Essenciais até 10/01', valor: -2545.29, tipo: 'saida' },
  { rotulo: 'Até 10/01', valor: -9899.15, tipo: 'resultado' },
];

const itensDaLegenda = (container: HTMLElement) =>
  [...container.querySelectorAll('.divisao-legenda li')].map((li) => li.textContent);

describe('<DivisaoDinheiro>', () => {
  it('com sobra: uma barra, um segmento por saída e a sobra no fim', () => {
    const { container } = render(<DivisaoDinheiro etapas={comSobra} resumo="Sobram R$ 17.887,03." />);

    expect(container.querySelectorAll('.divisao-barra')).toHaveLength(1);
    const segmentos = [...container.querySelectorAll('.divisao-segmento')];
    expect(segmentos.map((s) => s.className.replace('divisao-segmento ', ''))).toEqual([
      'papel-movimento',
      'papel-fatura',
      'papel-essenciais',
      'papel-sobra',
    ]);
    expect(container.querySelector('.divisao-manchete')?.textContent).toBe('Você tem R$ 20.873,31');
    expect(itensDaLegenda(container).at(-1)).toBe('SobraR$ 17.887,0386%');
    expect(itensDaLegenda(container)[1]).toBe('Fatura: pagar tudoR$ 1.744,748%');
    expect(screen.queryByText(/Falta/)).toBeNull();
    expect(screen.getByRole('img').getAttribute('aria-label')).toBe('Sobram R$ 17.887,03.');
  });

  it('com falta: duas barras na mesma escala, o saldo negativo entra no que precisa sair', () => {
    const { container } = render(<DivisaoDinheiro etapas={comFalta} resumo="Faltam R$ 9.899,15." />);

    expect(container.querySelectorAll('.divisao-barra')).toHaveLength(2);
    expect(container.querySelector('.divisao-manchete')?.textContent).toContain('Falta R$ 9.899,15');
    expect(screen.getByText('Falta R$ 9.899,15')).toBeTruthy(); // rótulo do trecho tracejado
    expect(itensDaLegenda(container)).toEqual([
      'Fatura: pagar o mínimoR$ 145,521%',
      'Essenciais até 10/01R$ 2.545,2924%',
      'Saldo negativo hojeR$ 8.130,0075%',
    ]);
    expect(screen.getByText('R$ 921,66')).toBeTruthy(); // o que tem
    expect(screen.getByText('R$ 10.820,81')).toBeTruthy(); // o que precisa sair
    expect(screen.queryByText(/Sobra/)).toBeNull();
  });

  it('o que tem menos o que precisa sair bate com o resultado do backend', () => {
    for (const etapas of [comSobra, comFalta]) {
      const { tem, precisa, resultado } = dividir(etapas);
      expect(tem - precisa).toBeCloseTo(resultado, 2);
    }
    expect(dividir(comSobra)).toMatchObject({ tem: 20873.31, resultado: 17887.03 });
    expect(dividir(comFalta).tem).toBeCloseTo(921.66, 2);
    expect(dividir(comFalta).precisa).toBeCloseTo(10820.81, 2);
  });
});
