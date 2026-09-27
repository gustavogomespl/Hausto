import { describe, expect, it } from 'vitest';
import { iconeDaCategoria } from './categorias';

describe('iconeDaCategoria', () => {
  it('ignora acentos e maiúsculas', () => {
    expect(iconeDaCategoria('Farmácia')).toBe('💊');
    expect(iconeDaCategoria('SUPERMERCADO')).toBe('🛒');
    expect(iconeDaCategoria('Educação')).toBe('🎒');
  });

  it('procura em todos os textos e cai no ícone padrão', () => {
    expect(iconeDaCategoria('Outros', 'PIX ENVIADO')).toBe('🔁');
    expect(iconeDaCategoria('Outros')).toBe('🧾');
  });
});
