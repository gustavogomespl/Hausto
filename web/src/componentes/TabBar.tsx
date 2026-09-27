import type { ComponentType } from 'react';
import { Casa, Grade, Lista, Raio, Setas } from './Icones';
import './TabBar.css';

export type Aba = 'inicio' | 'raiox' | 'extrato' | 'pagamentos' | 'menu';

const ABAS: { id: Aba; rotulo: string; Icone: ComponentType<{ tamanho?: number }> }[] = [
  { id: 'inicio', rotulo: 'Início', Icone: Casa },
  { id: 'raiox', rotulo: 'Raio-X', Icone: Raio },
  { id: 'extrato', rotulo: 'Extrato', Icone: Lista },
  { id: 'pagamentos', rotulo: 'Pagamentos', Icone: Setas },
  { id: 'menu', rotulo: 'Menu', Icone: Grade },
];

type Props = { ativa: Aba; aoMudar: (aba: Aba) => void };

export function TabBar({ ativa, aoMudar }: Props) {
  return (
    <nav className="tabbar">
      {ABAS.map(({ id, rotulo, Icone }) => (
        <button
          key={id}
          type="button"
          className={`tabbar-item${id === ativa ? ' ativa' : ''}`}
          aria-current={id === ativa ? 'page' : undefined}
          aria-label={rotulo}
          onClick={() => aoMudar(id)}
        >
          <span className="tabbar-icone">
            <Icone tamanho={24} />
          </span>
          <span className="tabbar-rotulo" aria-hidden="true">
            {rotulo}
          </span>
        </button>
      ))}
    </nav>
  );
}
