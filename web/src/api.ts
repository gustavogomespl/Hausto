export type Persona = { id: 'maria' | 'carla' | 'jonas'; nome: string; iniciais: string; idade: number; cidade: string; frase: string; renda: 'INSS' | 'CLT' | 'MEI'; cor: string; id_usuario: string };
// GET /v1/personas -> Persona[]

export type Painel = {
  id_usuario: string; data_ref: string; perfil: 'P1' | 'P2' | 'P3' | 'P4';
  conta: { saldo: number };
  cartao: { fatura: number | null; vencimento: string /* YYYY-MM-DD */; origem: string; mes_ref: string | null };
  raio_x: {
    gasto_por_dia: { valor: number; dias: number; total: number; mes_ref: string } | null;
    juros_por_dia: { valor: number; pagando: number; custo_30_dias: number } | null;
    parcelas: { total_mes: number; itens: { descricao: string; valor: number; atual: number; total: number }[] };
    categorias: { categoria: string; valor: number }[];
    faturas: { mes: string /* YYYY-MM */; modo: 'integral' | 'parcial' | 'minimo' }[];
  };
};
// GET /v1/clientes/{id}/painel -> Painel

export type IdAviso = 'fatura_vence' | 'sem_folga' | 'imprevisto';
export type Aviso = { id: IdAviso; tela: 'home' | 'raiox'; rotulo: string; titulo: string; texto: string; cta: string };
// GET /v1/clientes/{id}/avisos -> Aviso[]

export type Transacao = { data: string; tipo: 'E' | 'S'; descr: string; vlr: number; categoria: string; subcategoria: string; saldo_apos: number };
// GET /v1/clientes/{id}/transacoes?limite=200 -> Transacao[]  (mais recentes primeiro)

export type ClienteResumo = { id_usuario: string; persona: string; gatilho: boolean };
// GET /v1/clientes?limite=50 -> ClienteResumo[]

export type Origem = { tipo: 'aviso'; id: IdAviso } | { tipo: 'ancora'; campo: 'saldo' | 'fatura' | 'gasto_por_dia' | 'juros_por_dia' | 'parcelas' };
export type PedidoChat = { id_usuario: string; mensagem?: string; sessao_id?: string; origem?: Origem };
export type RespostaChat = {
  sessao_id: string; resposta: string; etapa: string; modo: string;
  pendente_confirmacao: Record<string, unknown> | null; tools_chamadas: string[]; numeros_sem_fonte: string[];
  sugestoes: string[]; ancora: { rotulo: string; valor: number } | null; pergunta: string | null;
};
// POST /v1/chat PedidoChat -> RespostaChat

export type CampoAncora = Extract<Origem, { tipo: 'ancora' }>['campo'];

export class ErroApi extends Error {
  status: number;
  constructor(status: number, mensagem: string) {
    super(mensagem);
    this.status = status;
  }
}

const BASE = import.meta.env.VITE_API_URL ?? '';

async function pedir<T>(caminho: string, init?: RequestInit): Promise<T> {
  const resposta = await fetch(BASE + caminho, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!resposta.ok) {
    let detalhe = '';
    try {
      const corpo = await resposta.json();
      if (typeof corpo?.detail === 'string') detalhe = corpo.detail;
    } catch {
      /* corpo sem JSON */
    }
    throw new ErroApi(resposta.status, detalhe || `Erro ${resposta.status}`);
  }
  return resposta.json() as Promise<T>;
}

const cliente = (id: string) => `/v1/clientes/${encodeURIComponent(id)}`;

export const listarPersonas = () => pedir<Persona[]>('/v1/personas');
export const buscarPainel = (id: string) => pedir<Painel>(`${cliente(id)}/painel`);
export const buscarAvisos = (id: string) => pedir<Aviso[]>(`${cliente(id)}/avisos`);
export const buscarTransacoes = (id: string) => pedir<Transacao[]>(`${cliente(id)}/transacoes?limite=200`);
export const listarClientes = () => pedir<ClienteResumo[]>('/v1/clientes?limite=50');
export const conversar = (pedido: PedidoChat) =>
  pedir<RespostaChat>('/v1/chat', { method: 'POST', body: JSON.stringify(pedido) });

/** Texto amigável para mostrar ao usuário quando uma chamada falha. */
export function mensagemDeErro(erro: unknown): string {
  if (erro instanceof ErroApi) {
    if (erro.status === 404) return 'Não encontramos esse cliente.';
    return `O servidor respondeu com erro ${erro.status}. Tente de novo em instantes.`;
  }
  return 'Não consegui falar com o servidor. Confira se a API está no ar e tente de novo.';
}
