import { describe, expect, it } from 'vitest';
import type { Simulacao } from '../api';
import { dicaDaFatura } from './DicaFatura';

const simulacao = (extra: Partial<Extract<Simulacao, { status: string }>>): Simulacao => ({
  valor_fatura: 1980,
  disponivel_para_fatura: 370,
  proxima_renda: '2026-01-05',
  opcoes: {
    integral: { valor_fatura: 1980, atende_restricoes: false },
    parcial_viavel: { valor_pago: 370, atende_restricoes: true },
    minimo: { valor_pago: 297, atende_restricoes: true },
  },
  status: 'ok',
  recomendada: 'parcial_viavel',
  ...extra,
});

describe('dicaDaFatura', () => {
  it('quando cabe pagar tudo, sugere o valor da fatura em tom positivo', () => {
    expect(dicaDaFatura(simulacao({ recomendada: 'integral' }))).toEqual({
      tom: 'bom',
      rotulo: 'Dá pra pagar tudo',
      acao: 'Pague',
      valor: 1980,
    });
  });

  it('quando não cabe, sugere o valor da opção recomendada pelo backend', () => {
    expect(dicaDaFatura(simulacao({}))).toEqual({ tom: 'alerta', rotulo: 'Não pague tudo agora', acao: 'Pague', valor: 370 });
    expect(dicaDaFatura(simulacao({ recomendada: 'minimo' }))?.valor).toBe(297);
  });

  it('quando nem o mínimo cabe, não mostra valor e oferece pagar menos juros', () => {
    expect(dicaDaFatura(simulacao({ status: 'insuficiente', recomendada: undefined }))).toEqual({
      tom: 'alerta',
      rotulo: 'Dá pra pagar menos juros',
      acao: 'Ver como',
    });
  });

  it('sem simulação ou com fatura desconhecida, não há dica', () => {
    expect(dicaDaFatura(null)).toBeNull();
    expect(dicaDaFatura({ erro: 'fatura_desconhecida' })).toBeNull();
  });
});
