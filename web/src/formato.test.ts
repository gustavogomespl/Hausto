import { describe, expect, it } from 'vitest';
import { dataCompleta, diaMesCurto, diaMesNumerico, dinheiro, dinheiroComSinal, dinheiroCurto, nomeDoMes, somarDias, tituloDoDia } from './formato';

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
    expect(diaMesNumerico('2025-12-05')).toBe('05/12');
    expect(tituloDoDia('2025-10-07', '2025-10-07')).toBe('Hoje · 07/10');
    expect(tituloDoDia('2025-09-20T10:00:00', '2025-10-07')).toBe('20 de setembro');
    expect(nomeDoMes('2025-10')).toBe('outubro');
    expect(nomeDoMes('11/2025')).toBe('novembro');
    expect(nomeDoMes(null)).toBeNull();
  });

  it('soma dias virando mês e ano', () => {
    expect(somarDias('2025-12-18', 7)).toBe('2025-12-25');
    expect(somarDias('2025-12-30', 3)).toBe('2026-01-02');
    expect(somarDias('2024-02-28', 1)).toBe('2024-02-29');
    expect(dataCompleta('2025-12-05')).toBe('05/12/2025');
  });
});
