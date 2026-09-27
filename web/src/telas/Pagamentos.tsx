import type { ComponentType } from 'react';
import { Baixar, Calendario, Celular, CodigoBarras, Pix, Setas } from '../componentes/Icones';
import './Grade.css';

const ITENS: { rotulo: string; Icone: ComponentType<{ tamanho?: number }> }[] = [
  { rotulo: 'Pix', Icone: Pix },
  { rotulo: 'Boleto', Icone: CodigoBarras },
  { rotulo: 'Transferir', Icone: Setas },
  { rotulo: 'Agendados', Icone: Calendario },
  { rotulo: 'Débito automático', Icone: Baixar },
  { rotulo: 'Recarga', Icone: Celular },
];

export function Pagamentos() {
  return (
    <div className="pagina">
      <h1 className="pagina-titulo">Pagamentos</h1>
      <div className="grade">
        {ITENS.map(({ rotulo, Icone }) => (
          <div key={rotulo} className="grade-item com-icone">
            <Icone tamanho={30} />
            <span>{rotulo}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
