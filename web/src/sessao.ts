import type { Persona } from './api';

/**
 * Cliente escolhido no onboarding/admin, lembrado entre visitas.
 * `data_ref` é a "data da simulação" escolhida no admin (o "hoje" do app); ausente = data padrão do cliente.
 */
export type SessaoSalva = { id_usuario: string; persona: Persona | null; data_ref?: string };

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

/** Mesma sessão com outra data da simulação; `null` volta à data original do cliente. */
export function comDataRef({ id_usuario, persona }: SessaoSalva, data: string | null): SessaoSalva {
  return data ? { id_usuario, persona, data_ref: data } : { id_usuario, persona };
}

export function iniciaisDe(sessao: SessaoSalva) {
  return sessao.persona?.iniciais ?? sessao.id_usuario.slice(0, 2).toUpperCase();
}
