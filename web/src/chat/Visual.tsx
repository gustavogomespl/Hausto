import { useId } from 'react';
import type { Visual as TipoVisual } from '../api';
import { ComparaOpcoes } from './visuais/ComparaOpcoes';
import { DivisaoDinheiro } from './visuais/DivisaoDinheiro';
import { LinhaDoTempo } from './visuais/LinhaDoTempo';
import { ProgressoPlano } from './visuais/ProgressoPlano';
import './Visual.css';

function grafico(visual: TipoVisual) {
  switch (visual.tipo) {
    case 'caixa_ate_renda':
      return <DivisaoDinheiro etapas={visual.dados.etapas} resumo={visual.resumo} />;
    case 'comparar_opcoes':
      return <ComparaOpcoes opcoes={visual.dados.opcoes} />;
    case 'linha_do_tempo':
      return <LinhaDoTempo eventos={visual.dados.eventos} />;
    case 'progresso_plano':
      return <ProgressoPlano dados={visual.dados} />;
    default:
      return null; // tipo novo que esta versão do app ainda não conhece
  }
}

/** Card de um gráfico explicativo que acompanha a resposta do Hausto. */
export function Visual({ visual }: { visual: TipoVisual }) {
  const id = useId();
  const conteudo = grafico(visual);
  if (!conteudo) return null;
  return (
    <figure className="visual" aria-labelledby={`${id}-titulo`} aria-describedby={`${id}-resumo`}>
      <h4 id={`${id}-titulo`}>{visual.titulo}</h4>
      <p id={`${id}-resumo`} className="visual-resumo">
        {visual.resumo}
      </p>
      {conteudo}
    </figure>
  );
}
