import { describe, expect, it } from 'vitest';
import { diaMesCurto, dinheiro, dinheiroComSinal, dinheiroCurto, nomeDoMes, tituloDoDia } from './formato';

describe('formato', () => {
  it('formata dinheiro em pt-BR', () => {
    expect(dinheiro(1980)).toBe('R$ 1.980,00');
    expect(dinheiro(0.5)).toBe('R$ 0,50');
    expect(dinheiroCurto(1180)).toBe('R$ 1.180');
    expect(dinheiroCurto(2.35)).toBe('R$ 2,35');
  });

  it('põe sinal pelo tipo da transação', () => {
    expect(dinheiroComSinal(1500, 'E')).toBe('+R$ 1.500,00');
    expect(dinheiroComSinal(-900, 'S')).toBe('-R$ 900,00');
  });

  it('formata datas sem depender do fuso', () => {
    expect(diaMesCurto('2025-10-12')).toBe('12/out');
    expect(tituloDoDia('2025-10-07', '2025-10-07')).toBe('Hoje · 07/10');
    expect(tituloDoDia('2025-09-20T10:00:00', '2025-10-07')).toBe('20 de setembro');
    expect(nomeDoMes('2025-10')).toBe('outubro');
    expect(nomeDoMes('11/2025')).toBe('novembro');
    expect(nomeDoMes(null)).toBeNull();
  });
});
