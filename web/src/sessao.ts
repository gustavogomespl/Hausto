import type { Persona } from './api';

/** Cliente escolhido no onboarding/admin, lembrado entre visitas. */
export type SessaoSalva = { id_usuario: string; persona: Persona | null };

const CHAVE = 'hausto.cliente';

export function lerSessao(): SessaoSalva | null {
  try {
    const bruto = localStorage.getItem(CHAVE);
    const salvo = bruto ? (JSON.parse(bruto) as SessaoSalva) : null;
    return salvo?.id_usuario ? salvo : null;
  } catch {
    return null;
  }
}

export function salvarSessao(sessao: SessaoSalva) {
  try {
    localStorage.setItem(CHAVE, JSON.stringify(sessao));
  } catch {
    /* sem storage (aba anônima, bloqueio): segue só em memória */
  }
}

export function iniciaisDe(sessao: SessaoSalva) {
  return sessao.persona?.iniciais ?? sessao.id_usuario.slice(0, 2).toUpperCase();
}
