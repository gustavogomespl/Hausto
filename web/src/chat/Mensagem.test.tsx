import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TextoHausto } from './Mensagem';
import { paraFala } from './voz';

describe('<TextoHausto>', () => {
  it('com limite, mostra só as primeiras letras sem quebrar o negrito e põe o cursor', () => {
    const { container } = render(<TextoHausto texto={'Sua fatura é **R$ 1.980**.\n- Vence dia 12'} limite={17} />);

    expect(container.textContent).toBe('Sua fatura é R$ 1');
    expect(container.querySelector('strong')?.textContent).toBe('R$ 1');
    expect(container.querySelector('.msg-cursor')).toBeTruthy();
    expect(container.querySelector('.msg-item')).toBeNull();
  });

  it('sem limite, mostra tudo e sem cursor', () => {
    const { container } = render(<TextoHausto texto={'Sua fatura é **R$ 1.980**.\n- Vence dia 12'} />);

    expect(container.querySelectorAll('p')).toHaveLength(2);
    expect(container.querySelector('.msg-item')?.textContent).toBe('Vence dia 12');
    expect(container.querySelector('.msg-cursor')).toBeNull();
  });
});

describe('paraFala', () => {
  it('lê valores como se fala e tira marcações', () => {
    expect(paraFala('Pague **R$ 370,00** hoje ✦\n- Resto: R$ 1.610,50')).toBe(
      'Pague 370 reais hoje. Resto: 1.610 reais e 50 centavos',
    );
  });
});
