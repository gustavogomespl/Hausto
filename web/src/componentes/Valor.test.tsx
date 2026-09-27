import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Valor } from './Valor';

describe('<Valor>', () => {
  it('mostra o valor formatado e chama o callback com o campo da âncora', () => {
    const aoTocar = vi.fn();
    render(<Valor valor={1980} campo="fatura" aoTocar={aoTocar} />);

    fireEvent.click(screen.getByText('R$ 1.980,00'));

    expect(aoTocar).toHaveBeenCalledOnce();
    expect(aoTocar).toHaveBeenCalledWith('fatura');
  });
});
