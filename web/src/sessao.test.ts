import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { comDataRef, iniciaisDe, lerSessao, salvarSessao, type SessaoSalva } from './sessao';

const CHAVE = 'hausto.cliente';
const quebrado = () => {
  throw new Error('storage bloqueado');
};

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe('sessao', () => {
  it('salva e lê de volta a sessão', () => {
    const sessao: SessaoSalva = { id_usuario: 'abc-123', persona: null };
    salvarSessao(sessao);
    expect(lerSessao()).toEqual(sessao);
  });

  it('devolve null com JSON corrompido ou sem id_usuario', () => {
    localStorage.setItem(CHAVE, '{não é json');
    expect(lerSessao()).toBeNull();

    localStorage.setItem(CHAVE, JSON.stringify({ persona: null }));
    expect(lerSessao()).toBeNull();
  });

  it('não quebra quando o storage lança exceção', () => {
    vi.stubGlobal('localStorage', { getItem: quebrado, setItem: quebrado });

    expect(lerSessao()).toBeNull();
    expect(() => salvarSessao({ id_usuario: 'abc', persona: null })).not.toThrow();
  });

  it('guarda a data da simulação junto da sessão e a limpa com null', () => {
    const sessao: SessaoSalva = { id_usuario: 'abc', persona: null };
    salvarSessao(comDataRef(sessao, '2025-12-25'));
    expect(lerSessao()).toEqual({ id_usuario: 'abc', persona: null, data_ref: '2025-12-25' });

    salvarSessao(comDataRef(lerSessao()!, null));
    expect(lerSessao()).toEqual(sessao);
  });

  it('usa as iniciais da persona ou as duas primeiras letras do id', () => {
    expect(iniciaisDe({ id_usuario: 'abc', persona: { iniciais: 'CS' } as SessaoSalva['persona'] })).toBe('CS');
    expect(iniciaisDe({ id_usuario: 'x9f-123', persona: null })).toBe('X9');
  });
});
