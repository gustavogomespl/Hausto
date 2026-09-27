import type { ReactNode } from 'react';
import type { Visual as TipoVisual } from '../api';
import { Brilho, Joinha } from '../componentes/Icones';
import { BotaoOuvir } from './Ouvir';
import { Visual } from './Visual';

/** Texto do Hausto: cada linha vira um parágrafo; "- " vira item; **negrito** e ✦ em laranja. */
export function TextoHausto({ texto }: { texto: string }) {
  const linhas = texto.split('\n').map((l) => l.trim()).filter(Boolean);
  return (
    <>
      {linhas.map((linha, i) =>
        linha.startsWith('- ') ? (
          <p key={i} className="msg-item">
            {enfeitar(linha.slice(2))}
          </p>
        ) : (
          <p key={i}>{enfeitar(linha)}</p>
        ),
      )}
    </>
  );
}

function enfeitar(linha: string): ReactNode[] {
  return linha.split(/(\*\*[^*]+\*\*|✦)/).map((parte, i) => {
    if (parte === '✦') return <Brilho key={i} tamanho={14} className="msg-brilho" />;
    if (parte.startsWith('**') && parte.endsWith('**') && parte.length > 4) return <strong key={i}>{parte.slice(2, -2)}</strong>;
    return parte;
  });
}

export function MensagemHausto({ texto, visuais = [] }: { texto: string; visuais?: TipoVisual[] }) {
  return (
    <div className="msg-hausto">
      <TextoHausto texto={texto} />
      {visuais.map((v, i) => (
        <Visual key={i} visual={v} />
      ))}
      <div className="msg-reacoes">
        <Joinha tamanho={22} />
        <Joinha tamanho={22} style={{ transform: 'rotate(180deg)' }} />
        <BotaoOuvir texto={[texto, ...visuais.map((v) => `Gráfico: ${v.titulo}. ${v.resumo}`)].join('\n')} />
      </div>
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
