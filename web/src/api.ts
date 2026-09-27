export type Persona = { id: 'maria' | 'carla' | 'jonas'; nome: string; iniciais: string; idade: number; cidade: string; frase: string; renda: 'INSS' | 'CLT' | 'MEI'; cor: string; id_usuario: string };
// GET /v1/personas -> Persona[]

/** Meta de poupança da persona (a base não tem metas; vem da história da persona no backend). */
export type Meta = {
  rotulo: string; nome: string; icone: 'casa' | 'carro' | 'reserva';
  alvo: number; guardado: number; falta: number; pct: number;
};

export type Painel = {
  id_usuario: string; data_ref: string; perfil: 'P1' | 'P2' | 'P3' | 'P4';
  meta?: Meta | null;
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
// GET /v1/clientes/{id}/painel?data_ref=YYYY-MM-DD -> Painel
// Toda chamada por cliente aceita `data_ref` opcional (a "data da simulação"); sem ela, o backend usa a data padrão do cliente.

export type IdAviso = 'fatura_vence' | 'sem_folga' | 'imprevisto' | 'plano';
export type Aviso = { id: IdAviso; tela: 'home' | 'raiox'; rotulo: string; titulo: string; texto: string; cta: string };
// GET /v1/clientes/{id}/avisos?data_ref= -> Aviso[]

export type Transacao = { data: string; tipo: 'E' | 'S'; descr: string; vlr: number; categoria: string; subcategoria: string; saldo_apos: number };
// GET /v1/clientes/{id}/transacoes?limite=200&data_ref= -> Transacao[]  (mais recentes primeiro)

/** Andamento do plano combinado: previsto = limite diário × dias decorridos. */
export type ProgressoPlano = {
  limite_diario: number; dias_decorridos: number; dias_totais: number;
  gasto_real: number; gasto_previsto: number; status: 'dentro' | 'acima';
};
export type Plano = {
  pagamento_fatura: number; reserva: number; limite_diario: number;
  inicio: string /* YYYY-MM-DD */; fim: string /* YYYY-MM-DD */; progresso: ProgressoPlano;
};
// GET /v1/clientes/{id}/plano?data_ref= -> Plano | null  (null enquanto o cliente não aceitou um plano)

/** Uma das formas de pagar a fatura, já com as restrições de caixa conferidas pelo backend. */
export type OpcaoPagamento = { valor_pago?: number; valor_fatura?: number; atende_restricoes: boolean };
export type Simulacao =
  | { erro: string }
  | {
      valor_fatura: number; disponivel_para_fatura: number; proxima_renda: string /* YYYY-MM-DD */;
      opcoes: { integral: OpcaoPagamento; parcial_viavel: OpcaoPagamento; minimo: OpcaoPagamento };
      status: 'ok' | 'insuficiente'; recomendada?: 'integral' | 'parcial_viavel' | 'minimo';
    };
// GET /v1/clientes/{id}/simulacao?data_ref= -> Simulacao  (as mesmas contas que o chat usa, sem LLM)

export type ClienteResumo ={ id_usuario: string; persona: string; gatilho: boolean };
// GET /v1/clientes?limite=50 -> ClienteResumo[]

// `compra` não é um card de aviso: é o "Posso comprar?" do Raio-X, que abre o chat pelo mesmo caminho.
export type Origem =
  | { tipo: 'aviso'; id: IdAviso | 'compra' }
  | { tipo: 'ancora'; campo: 'saldo' | 'fatura' | 'gasto_por_dia' | 'juros_por_dia' | 'parcelas' | 'meta' };
// Gráficos que acompanham a resposta do chat (0..n por mensagem).
export type EtapaCaixa = { rotulo: string; valor: number; tipo: 'inicio' | 'entrada' | 'saida' | 'resultado' };
export type OpcaoVisual = {
  rotulo: string; pago: number; custo: number; juros_cartao?: number; juros_conta?: number;
  divida_restante: number; cabe: boolean; destaque: boolean;
};
export type EventoTempo = { data: string /* YYYY-MM-DD */; rotulo: string; valor: number | null; tipo: 'hoje' | 'fatura' | 'despesa' | 'renda' };
export type Visual =
  | { tipo: 'caixa_ate_renda'; titulo: string; resumo: string; dados: { etapas: EtapaCaixa[] } }
  | { tipo: 'comparar_opcoes'; titulo: string; resumo: string; dados: { opcoes: OpcaoVisual[] } }
  | { tipo: 'linha_do_tempo'; titulo: string; resumo: string; dados: { eventos: EventoTempo[] } }
  | { tipo: 'progresso_plano'; titulo: string; resumo: string; dados: ProgressoPlano };

export type PedidoChat = { id_usuario: string; mensagem?: string; sessao_id?: string; origem?: Origem; data_ref?: string };
export type RespostaChat = {
  sessao_id: string; resposta: string; etapa: string; modo: string;
  pendente_confirmacao: Record<string, unknown> | null; tools_chamadas: string[]; numeros_sem_fonte: string[];
  sugestoes: string[]; ancora: { rotulo: string; valor: number } | null; pergunta: string | null;
  visuais: Visual[];
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

/** "?limite=200&data_ref=2025-12-25", pulando os parâmetros ausentes. */
function consulta(parametros: Record<string, string | number | undefined>) {
  const presentes = Object.entries(parametros).flatMap(([chave, valor]) =>
    valor === undefined ? [] : [[chave, String(valor)]],
  );
  const texto = new URLSearchParams(presentes).toString();
  return texto ? `?${texto}` : '';
}

export const listarPersonas = () => pedir<Persona[]>('/v1/personas');
export const buscarPainel = (id: string, dataRef?: string) =>
  pedir<Painel>(`${cliente(id)}/painel${consulta({ data_ref: dataRef })}`);
export const buscarAvisos = (id: string, dataRef?: string) =>
  pedir<Aviso[]>(`${cliente(id)}/avisos${consulta({ data_ref: dataRef })}`);
export const buscarTransacoes = (id: string, dataRef?: string) =>
  pedir<Transacao[]>(`${cliente(id)}/transacoes${consulta({ limite: 200, data_ref: dataRef })}`);
export const buscarPlano = (id: string, dataRef?: string) =>
  pedir<Plano | null>(`${cliente(id)}/plano${consulta({ data_ref: dataRef })}`);
export const buscarSimulacao = (id: string, dataRef?: string) =>
  pedir<Simulacao>(`${cliente(id)}/simulacao${consulta({ data_ref: dataRef })}`);
export const listarClientes =() => pedir<ClienteResumo[]>('/v1/clientes?limite=50');
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
