import { useEffect, useRef, useState, type FormEvent, type PointerEvent } from 'react';
import { conversar, ErroApi, type Origem, type Visual } from '../api';
import { useArrastarRolagem } from '../componentes/arrastar';
import { Brilho, Enviar, Expandir, Fechar, Recolher } from '../componentes/Icones';
import { dinheiro } from '../formato';
import { animarDigitacao, MensagemHausto, Pensando } from './Mensagem';
import { falar, pararDeFalar, podeFalar } from './voz';
import './Chat.css';

/** Pedido de abertura vindo do app; `id` muda a cada toque para disparar de novo. */
export type PedidoAbertura = { id: number; origem?: Origem };

type Acao = { rotulo: string; origem?: Origem; ouvir?: boolean };
type Mensagem =
  | { tipo: 'contexto'; rotulo: string; valor: number }
  | { tipo: 'cliente'; texto: string }
  | { tipo: 'hausto'; id: string; texto: string; acoes: Acao[]; visuais?: Visual[] }
  | { tipo: 'erro'; texto: string };

const BOAS_VINDAS: Omit<Extract<Mensagem, { tipo: 'hausto' }>, 'id'> = {
  tipo: 'hausto',
  texto: 'Toque em qualquer valor com ✦ no app e eu explico de onde ele vem.\n\nOu escolha aqui:',
  acoes: [
    { rotulo: 'Minha fatura', origem: { tipo: 'ancora', campo: 'fatura' } },
    { rotulo: 'Meu saldo', origem: { tipo: 'ancora', campo: 'saldo' } },
  ],
};

const OUVIR: Acao = { rotulo: 'Ouvir em áudio', ouvir: true };

type Props = {
  idUsuario: string;
  /** Data da simulação escolhida no admin; ausente = data padrão do cliente. */
  dataRef?: string;
  aberto: boolean;
  pedido: PedidoAbertura | null;
  /** Persona que prefere ouvir (Dona Maria): toda resposta ganha a opção "Ouvir em áudio". */
  ouvirEmAudio?: boolean;
  aoFechar: () => void;
};

export function Chat({ idUsuario, dataRef, aberto, pedido, ouvirEmAudio = false, aoFechar }: Props) {
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [sessaoId, setSessaoId] = useState<string | undefined>();
  const [pensando, setPensando] = useState(false);
  const [expandido, setExpandido] = useState(false);
  const [texto, setTexto] = useState('');
  // Resposta que ainda está sendo "digitada"; as sugestões só aparecem quando ela termina.
  const [digitando, setDigitando] = useState<string | null>(null);
  const atendido = useRef<number | null>(null);
  const contador = useRef(0);
  const corpo = useRef<HTMLDivElement>(null);
  const sugestoes = useRef<HTMLDivElement>(null);
  const folha = useRef<HTMLElement>(null);
  // Só acompanha o fim da conversa se a pessoa já estiver lá embaixo.
  const colado = useRef(true);
  useArrastarRolagem(sugestoes);

  const novaResposta = (m: Omit<Extract<Mensagem, { tipo: 'hausto' }>, 'tipo' | 'id'>): Mensagem => {
    const id = `r${++contador.current}`;
    if (animarDigitacao()) setDigitando(id);
    return { tipo: 'hausto', id, ...m };
  };

  /** `nova`: primeira mensagem de uma conversa nova, sem a sessão anterior no backend. */
  async function enviar({ mensagem, origem, nova = false }: { mensagem?: string; origem?: Origem; nova?: boolean }) {
    colado.current = true;
    if (mensagem) setMensagens((m) => [...m, { tipo: 'cliente', texto: mensagem }]);
    setPensando(true);
    try {
      const r = await conversar({
        id_usuario: idUsuario,
        mensagem,
        origem,
        sessao_id: nova ? undefined : sessaoId,
        data_ref: dataRef,
      });
      setSessaoId(r.sessao_id);
      const novas: Mensagem[] = [];
      if (r.ancora) novas.push({ tipo: 'contexto', ...r.ancora });
      // A pergunta só vira balão quando o turno foi aberto por origem; se o cliente escreveu, o balão já existe.
      if (r.pergunta && !mensagem) novas.push({ tipo: 'cliente', texto: r.pergunta });
      novas.push(novaResposta({ texto: r.resposta, acoes: r.sugestoes.map((s) => ({ rotulo: s })), visuais: r.visuais ?? [] }));
      setMensagens((m) => [...m, ...novas]);
    } catch (e) {
      const texto =
        e instanceof ErroApi
          ? `Não consegui responder agora (erro ${e.status}). Tente de novo em instantes.`
          : 'Não consegui falar com o servidor. Confira sua conexão e tente de novo.';
      setMensagens((m) => [...m, { tipo: 'erro', texto }]);
    } finally {
      setPensando(false);
    }
  }

  // Cada abertura pelo app (✦, card, dica, balão do topo) começa uma conversa nova: tela limpa e sessão nova,
  // para a resposta não herdar o assunto anterior. É atendida uma vez; se chegar durante um turno, espera ele acabar.
  useEffect(() => {
    if (!pedido || pedido.id === atendido.current || pensando) return;
    atendido.current = pedido.id;
    pararDeFalar();
    setSessaoId(undefined);
    setExpandido(false);
    setTexto('');
    colado.current = true;
    if (pedido.origem) {
      setDigitando(null);
      setMensagens([]);
      void enviar({ origem: pedido.origem, nova: true });
    } else {
      const boasVindas = { ...BOAS_VINDAS, id: `b${++contador.current}` };
      setDigitando(animarDigitacao() ? boasVindas.id : null);
      setMensagens([boasVindas]);
    }
  }, [pedido, pensando]);

  function rolarParaOFim(suave = false) {
    const el = corpo.current;
    if (el && colado.current) el.scrollTo?.({ top: el.scrollHeight, behavior: suave ? 'smooth' : 'auto' });
  }

  useEffect(() => {
    rolarParaOFim(true);
  }, [mensagens, pensando, digitando]);

  // Fechar a conversa para a leitura em voz alta.
  useEffect(() => {
    if (!aberto) pararDeFalar();
  }, [aberto]);

  function aoEnviar(e: FormEvent) {
    e.preventDefault();
    const mensagem = texto.trim();
    if (!mensagem || pensando) return;
    setTexto('');
    void enviar({ mensagem });
  }

  // Arrastar pela alça: para cima expande, para baixo recolhe ou fecha.
  const puxao = useRef<{ y0: number; dy: number } | null>(null);
  function aoPuxar(e: PointerEvent<HTMLDivElement>) {
    if ((e.target as HTMLElement).closest('button')) return;
    puxao.current = { y0: e.clientY, dy: 0 };
    folha.current?.classList.add('puxando');
    e.currentTarget.setPointerCapture?.(e.pointerId);
  }
  function aoMoverPuxao(e: PointerEvent<HTMLDivElement>) {
    if (!puxao.current || !folha.current) return;
    puxao.current.dy = e.clientY - puxao.current.y0;
    folha.current.style.transform = puxao.current.dy > 0 ? `translateY(${puxao.current.dy}px)` : '';
  }
  function aoSoltarPuxao() {
    if (!puxao.current) return;
    const { dy } = puxao.current;
    puxao.current = null;
    folha.current?.classList.remove('puxando');
    if (folha.current) folha.current.style.transform = '';
    if (dy < -40 && !expandido) setExpandido(true);
    else if (dy > 60) {
      if (expandido) setExpandido(false);
      else aoFechar();
    }
  }

  const ultima = mensagens.at(-1);
  const respostaPronta = !pensando && ultima?.tipo === 'hausto' && ultima.id !== digitando;
  const acoes = respostaPronta ? [...ultima.acoes, ...(ouvirEmAudio && podeFalar() ? [OUVIR] : [])] : [];

  function aoEscolher(a: Acao) {
    if (a.ouvir) {
      if (ultima?.tipo === 'hausto') falar(ultima.texto, ultima.id);
      return;
    }
    void enviar(a.origem ? { origem: a.origem } : { mensagem: a.rotulo });
  }

  return (
    <>
      <div className={`chat-fundo${aberto ? ' aberto' : ''}`} onClick={aoFechar} aria-hidden="true" />
      <section
        ref={folha}
        className={`chat${aberto ? ' aberto' : ''}${expandido ? ' expandido' : ''}`}
        role="dialog"
        aria-label="Conversa com o Hausto"
        aria-hidden={!aberto}
        inert={!aberto}
      >
        <div
          className="chat-topo"
          onPointerDown={aoPuxar}
          onPointerMove={aoMoverPuxao}
          onPointerUp={aoSoltarPuxao}
          onPointerCancel={aoSoltarPuxao}
        >
          <span className="chat-alca" aria-hidden="true" />
          <header className="chat-cabeca">
            <span className="chat-avatar">
              <Brilho tamanho={18} />
            </span>
            <strong>Hausto</strong>
            <button
              type="button"
              onClick={() => setExpandido((v) => !v)}
              aria-label={expandido ? 'Recolher conversa' : 'Expandir conversa'}
            >
              {expandido ? <Recolher /> : <Expandir />}
            </button>
            <button type="button" onClick={aoFechar} aria-label="Fechar conversa">
              <Fechar tamanho={26} />
            </button>
          </header>
        </div>

        <div
          className="chat-corpo"
          ref={corpo}
          onScroll={(e) => {
            const el = e.currentTarget;
            colado.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
          }}
        >
          {mensagens.map((m, i) => {
            switch (m.tipo) {
              case 'contexto':
                return (
                  <div key={i} className="msg-contexto">
                    <span>{m.rotulo}</span>
                    <strong>{dinheiro(m.valor)}</strong>
                  </div>
                );
              case 'cliente':
                return (
                  <div key={i} className="msg-cliente">
                    {m.texto}
                  </div>
                );
              case 'hausto':
                return (
                  <MensagemHausto
                    key={m.id}
                    id={m.id}
                    texto={m.texto}
                    visuais={m.visuais}
                    digitar={m.id === digitando}
                    aoAvancar={() => rolarParaOFim()}
                    aoTerminar={() => setDigitando((d) => (d === m.id ? null : d))}
                  />
                );
              case 'erro':
                return (
                  <div key={i} className="msg-erro" role="alert">
                    {m.texto}
                  </div>
                );
            }
          })}
          {pensando && <Pensando />}
        </div>

        {/* Sempre no DOM (vazia some pelo CSS) para o arrastar com o mouse ficar ligado. */}
        <div className="chat-sugestoes" ref={sugestoes}>
          {acoes.map((a) => (
            <button key={a.rotulo} type="button" onClick={() => aoEscolher(a)}>
              {a.rotulo}
            </button>
          ))}
        </div>

        <form className="chat-rodape" onSubmit={aoEnviar}>
          <input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Pergunte sobre esse valor..."
            aria-label="Mensagem para o Hausto"
            disabled={pensando}
          />
          <button type="submit" aria-label="Enviar" disabled={pensando || !texto.trim()}>
            <Enviar />
          </button>
        </form>
      </section>
    </>
  );
}
