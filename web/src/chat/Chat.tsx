import { useEffect, useRef, useState, type FormEvent } from 'react';
import { conversar, ErroApi, type Origem } from '../api';
import { Brilho, Enviar, Expandir, Fechar, Recolher } from '../componentes/Icones';
import { dinheiro } from '../formato';
import { MensagemHausto, Pensando } from './Mensagem';
import './Chat.css';

/** Pedido de abertura vindo do app; `id` muda a cada toque para disparar de novo. */
export type PedidoAbertura = { id: number; origem?: Origem };

type Acao = { rotulo: string; origem?: Origem };
type Mensagem =
  | { tipo: 'contexto'; rotulo: string; valor: number }
  | { tipo: 'cliente'; texto: string }
  | { tipo: 'hausto'; texto: string; acoes: Acao[] }
  | { tipo: 'erro'; texto: string };

const BOAS_VINDAS: Mensagem = {
  tipo: 'hausto',
  texto: 'Toque em qualquer valor com ✦ no app e eu explico de onde ele vem.\n\nOu escolha aqui:',
  acoes: [
    { rotulo: 'Minha fatura', origem: { tipo: 'ancora', campo: 'fatura' } },
    { rotulo: 'Meu saldo', origem: { tipo: 'ancora', campo: 'saldo' } },
  ],
};

type Props = {
  idUsuario: string;
  aberto: boolean;
  pedido: PedidoAbertura | null;
  aoFechar: () => void;
};

export function Chat({ idUsuario, aberto, pedido, aoFechar }: Props) {
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [sessaoId, setSessaoId] = useState<string | undefined>();
  const [pensando, setPensando] = useState(false);
  const [expandido, setExpandido] = useState(false);
  const [texto, setTexto] = useState('');
  const atendido = useRef<number | null>(null);
  const corpo = useRef<HTMLDivElement>(null);

  async function enviar({ mensagem, origem }: { mensagem?: string; origem?: Origem }) {
    if (mensagem) setMensagens((m) => [...m, { tipo: 'cliente', texto: mensagem }]);
    setPensando(true);
    try {
      const r = await conversar({ id_usuario: idUsuario, mensagem, origem, sessao_id: sessaoId });
      setSessaoId(r.sessao_id);
      const novas: Mensagem[] = [];
      if (r.ancora) novas.push({ tipo: 'contexto', ...r.ancora });
      // A pergunta só vira balão quando o turno foi aberto por origem; se o cliente escreveu, o balão já existe.
      if (r.pergunta && !mensagem) novas.push({ tipo: 'cliente', texto: r.pergunta });
      novas.push({ tipo: 'hausto', texto: r.resposta, acoes: r.sugestoes.map((s) => ({ rotulo: s })) });
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

  // Cada abertura pelo app é atendida uma vez; se chegar durante um turno, espera ele acabar.
  useEffect(() => {
    if (!pedido || pedido.id === atendido.current || pensando) return;
    atendido.current = pedido.id;
    if (pedido.origem) void enviar({ origem: pedido.origem });
    else setMensagens((m) => (m.length ? m : [BOAS_VINDAS]));
  }, [pedido, pensando]);

  useEffect(() => {
    corpo.current?.scrollTo?.({ top: corpo.current.scrollHeight, behavior: 'smooth' });
  }, [mensagens, pensando]);

  function aoEnviar(e: FormEvent) {
    e.preventDefault();
    const mensagem = texto.trim();
    if (!mensagem || pensando) return;
    setTexto('');
    void enviar({ mensagem });
  }

  const ultima = mensagens.at(-1);
  const acoes = !pensando && ultima?.tipo === 'hausto' ? ultima.acoes : [];

  return (
    <>
      <div className={`chat-fundo${aberto ? ' aberto' : ''}`} onClick={aoFechar} aria-hidden="true" />
      <section
        className={`chat${aberto ? ' aberto' : ''}${expandido ? ' expandido' : ''}`}
        role="dialog"
        aria-label="Conversa com o Hausto"
        aria-hidden={!aberto}
        inert={!aberto}
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

        <div className="chat-corpo" ref={corpo}>
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
                return <MensagemHausto key={i} texto={m.texto} />;
              case 'erro':
                return (
                  <div key={i} className="msg-erro" role="alert">
                    {m.texto}
                  </div>
                );
            }
          })}
          {pensando && <Pensando />}
          {acoes.length > 0 && (
            <div className="chat-sugestoes">
              {acoes.map((a) => (
                <button
                  key={a.rotulo}
                  type="button"
                  onClick={() => void enviar(a.origem ? { origem: a.origem } : { mensagem: a.rotulo })}
                >
                  {a.rotulo}
                </button>
              ))}
            </div>
          )}
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
