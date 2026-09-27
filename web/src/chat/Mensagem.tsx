import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { Visual as TipoVisual } from '../api';
import { Brilho, Joinha, Som } from '../componentes/Icones';
import { falar, pararDeFalar, podeFalar, useFalando } from './voz';
import { Visual } from './Visual';

type Parte = { tipo: 'texto' | 'forte'; texto: string } | { tipo: 'brilho' };
type Linha = { item: boolean; partes: Parte[] };

/** Quebra o texto em linhas ("- " vira item) e cada linha em texto, **negrito** e ✦. */
function analisar(texto: string): Linha[] {
  return texto
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((linha) => {
      const item = linha.startsWith('- ');
      const partes = (item ? linha.slice(2) : linha)
        .split(/(\*\*[^*]+\*\*|✦)/)
        .filter(Boolean)
        .map((p): Parte => {
          if (p === '✦') return { tipo: 'brilho' };
          if (p.startsWith('**') && p.endsWith('**') && p.length > 4) return { tipo: 'forte', texto: p.slice(2, -2) };
          return { tipo: 'texto', texto: p };
        });
      return { item, partes };
    });
}

const tamanho = (p: Parte) => (p.tipo === 'brilho' ? 1 : p.texto.length);
const totalDeLetras = (linhas: Linha[]) => linhas.reduce((s, l) => s + l.partes.reduce((t, p) => t + tamanho(p), 0), 0);

/**
 * Texto do Hausto: cada linha vira um parágrafo; "- " vira item; **negrito** e ✦ em laranja.
 * Com `limite`, mostra só as primeiras letras (efeito de digitação) e o cursor no fim.
 */
export function TextoHausto({ texto, limite }: { texto: string; limite?: number }) {
  const linhas = analisar(texto);
  let resta = limite ?? Infinity;
  const saida: ReactNode[] = [];
  for (const [i, linha] of linhas.entries()) {
    if (resta <= 0) break;
    const conteudo: ReactNode[] = [];
    for (const [j, parte] of linha.partes.entries()) {
      if (resta <= 0) break;
      const n = Math.min(resta, tamanho(parte));
      resta -= n;
      if (parte.tipo === 'brilho') conteudo.push(<Brilho key={j} tamanho={14} className="msg-brilho" />);
      else if (parte.tipo === 'forte') conteudo.push(<strong key={j}>{parte.texto.slice(0, n)}</strong>);
      else conteudo.push(parte.texto.slice(0, n));
    }
    const digitando = limite !== undefined && resta <= 0 && limite < totalDeLetras(linhas);
    if (digitando) conteudo.push(<span key="cursor" className="msg-cursor" aria-hidden="true" />);
    saida.push(
      <p key={i} className={linha.item ? 'msg-item' : undefined}>
        {conteudo}
      </p>,
    );
  }
  return <>{saida}</>;
}

/** Digitação letra por letra só quando o aparelho aceita animação (e nunca nos testes, sem matchMedia). */
export const animarDigitacao = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const MS_POR_LETRA = 22;

type Props = {
  id: string;
  texto: string;
  visuais?: TipoVisual[];
  /** Digita a resposta; ao terminar chama `aoTerminar`. Sem isso, aparece inteira. */
  digitar?: boolean;
  aoAvancar?: () => void;
  aoTerminar?: () => void;
};

export function MensagemHausto({ id, texto, visuais = [], digitar = false, aoAvancar, aoTerminar }: Props) {
  const total = totalDeLetras(analisar(texto));
  const [letras, setLetras] = useState(digitar ? 0 : total);
  const avisos = useRef({ aoAvancar, aoTerminar });
  avisos.current = { aoAvancar, aoTerminar };

  useEffect(() => {
    if (!digitar) return;
    const relogio = setInterval(() => {
      setLetras((n) => Math.min(total, n + 1));
    }, MS_POR_LETRA);
    return () => clearInterval(relogio);
  }, [digitar, total]);

  const pronto = letras >= total;
  useEffect(() => {
    if (!digitar) return;
    avisos.current.aoAvancar?.();
    if (pronto) avisos.current.aoTerminar?.();
  }, [digitar, letras, pronto]);

  return (
    <div className="msg-hausto">
      <TextoHausto texto={texto} limite={pronto ? undefined : letras} />
      {pronto && visuais.map((v, i) => <Visual key={i} visual={v} />)}
      {pronto && <Reacoes id={id} texto={texto} />}
    </div>
  );
}

/** Curtir / não curtir / ouvir em cada resposta do Hausto. */
function Reacoes({ id, texto }: { id: string; texto: string }) {
  const [voto, setVoto] = useState<'sim' | 'nao' | null>(null);
  const tocando = useFalando(id);
  const votar = (v: 'sim' | 'nao') => setVoto((atual) => (atual === v ? null : v));
  return (
    <div className="msg-reacoes">
      <button type="button" aria-pressed={voto === 'sim'} aria-label="Gostei da resposta" title="Gostei" onClick={() => votar('sim')}>
        <Joinha tamanho={20} />
      </button>
      <button
        type="button"
        aria-pressed={voto === 'nao'}
        aria-label="Não gostei da resposta"
        title="Não gostei"
        onClick={() => votar('nao')}
      >
        <Joinha tamanho={20} style={{ transform: 'rotate(180deg)' }} />
      </button>
      {podeFalar() && (
        <button
          type="button"
          className="msg-ouvir"
          aria-pressed={tocando}
          aria-label={tocando ? 'Parar leitura' : 'Ouvir esta resposta'}
          title="Ouvir"
          onClick={() => (tocando ? pararDeFalar() : falar(texto, id))}
        >
          <Som tamanho={20} />
        </button>
      )}
      <span className="msg-obrigado" role="status">
        {voto ? 'Obrigado pelo retorno!' : ''}
      </span>
    </div>
  );
}

export function Pensando() {
  return (
    <div className="msg-pensando" role="status" aria-label="Hausto está pensando">
      <span />
      <span />
      <span />
    </div>
  );
}
