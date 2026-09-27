import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BotaoOuvir, paraFala } from './Ouvir';

class Fala {
  text: string;
  lang = '';
  voice: unknown = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(texto: string) {
    this.text = texto;
  }
}

describe('paraFala', () => {
  it('lê reais e centavos por extenso e tira a marcação', () => {
    expect(paraFala('**Pague** R$ 1.234,56 ✦')).toBe('Pague 1.234 reais e 56 centavos.');
    expect(paraFala('Custa R$ 0,00 de juros')).toBe('Custa 0 reais de juros.');
  });

  it('cada linha vira uma frase e o item de lista perde o traço', () => {
    expect(paraFala('Opções:\n- Pagar tudo\n- Pagar o mínimo')).toBe('Opções: Pagar tudo. Pagar o mínimo.');
  });
});

describe('<BotaoOuvir>', () => {
  const sintese = { speak: vi.fn(), cancel: vi.fn(), getVoices: () => [{ lang: 'pt-BR', name: 'Luciana' }] };

  beforeEach(() => {
    vi.stubGlobal('speechSynthesis', sintese);
    vi.stubGlobal('SpeechSynthesisUtterance', Fala);
    sintese.speak.mockClear();
    sintese.cancel.mockClear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it('lê a mensagem em português e para no segundo clique', () => {
    render(<BotaoOuvir texto="Sua fatura é R$ 900,00." />);
    fireEvent.click(screen.getByRole('button', { name: 'Ouvir mensagem' }));

    const fala = sintese.speak.mock.calls[0][0] as Fala;
    expect(fala.text).toBe('Sua fatura é 900 reais.');
    expect(fala.lang).toBe('pt-BR');
    expect(screen.getByRole('button', { name: 'Parar leitura' }).getAttribute('aria-pressed')).toBe('true');

    fireEvent.click(screen.getByRole('button', { name: 'Parar leitura' }));
    expect(sintese.cancel).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Ouvir mensagem' })).toBeTruthy();
  });

  it('volta ao estado inicial quando a leitura termina', () => {
    render(<BotaoOuvir texto="Oi" />);
    fireEvent.click(screen.getByRole('button', { name: 'Ouvir mensagem' }));
    act(() => (sintese.speak.mock.calls[0][0] as Fala).onend?.());
    expect(screen.getByRole('button', { name: 'Ouvir mensagem' }).getAttribute('aria-pressed')).toBe('false');
  });

  it('sem voz no navegador, não mostra o botão', () => {
    vi.stubGlobal('speechSynthesis', undefined);
    const { container } = render(<BotaoOuvir texto="Oi" />);
    expect(container.querySelector('button')).toBeNull();
  });
});

describe('<MensagemHausto> com o botão de ouvir', () => {
  it('lê também o título e o resumo dos gráficos da mensagem', async () => {
    const { MensagemHausto } = await import('./Mensagem');
    const speak = vi.fn();
    vi.stubGlobal('speechSynthesis', { speak, cancel: vi.fn(), getVoices: () => [] });
    vi.stubGlobal('SpeechSynthesisUtterance', Fala);
    render(
      <MensagemHausto
        texto="Veja no gráfico."
        visuais={[{ tipo: 'comparar_opcoes', titulo: 'Quanto custa cada forma de pagar', resumo: 'Cabem no caixa: pagar tudo.', dados: { opcoes: [] } }]}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Ouvir mensagem' }));
    expect((speak.mock.calls[0][0] as Fala).text).toBe('Veja no gráfico. Gráfico: Quanto custa cada forma de pagar. Cabem no caixa: pagar tudo.');
    vi.unstubAllGlobals();
  });
});
