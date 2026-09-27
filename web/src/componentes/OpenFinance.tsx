import { useRef, type ReactNode } from 'react';
import { useArrastarRolagem } from './arrastar';
import './OpenFinance.css';

/** Logos simplificados (ilustrativos) dos bancos, no círculo de 44×44. */
const BANCOS: { nome: string; logo: ReactNode }[] = [
  {
    nome: 'Mercado Pago',
    logo: (
      <>
        <circle cx="22" cy="22" r="22" fill="#00B1EA" />
        <ellipse cx="22" cy="22" rx="15" ry="10" fill="#fff" stroke="#2D3277" strokeWidth="1.8" />
        <path
          d="M11 21.5l4.5-2.5 4 1.5 3-2 3.5.5 5 3M15.5 19l5.5 5.5c.8.8 2 .8 2.6 0M19 22.5l3.5 3.2M21.5 21.5l3.5 3M26.5 21l3 2.5"
          fill="none"
          stroke="#2D3277"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </>
    ),
  },
  {
    nome: 'Nubank',
    logo: (
      <>
        <circle cx="22" cy="22" r="22" fill="#820AD1" />
        <text x="22" y="28" textAnchor="middle" fontFamily="Arial,sans-serif" fontSize="17" fontWeight="700" fill="#fff">
          nu
        </text>
      </>
    ),
  },
  {
    nome: 'Bradesco',
    logo: (
      <>
        <circle cx="22" cy="22" r="22" fill="#CC092F" />
        <path d="M12 25c3-6 17-6 20 0M14 19c2 3 14 3 16 0M22 12v20" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
      </>
    ),
  },
  {
    nome: 'Banco do Brasil',
    logo: (
      <>
        <circle cx="22" cy="22" r="22" fill="#FCFC30" />
        <path d="M13 16l9-5 9 5-9 5zM13 28l9 5 9-5-9-5z" fill="none" stroke="#0038A8" strokeWidth="2.6" strokeLinejoin="round" />
      </>
    ),
  },
  {
    nome: 'Santander',
    logo: (
      <>
        <circle cx="22" cy="22" r="22" fill="#EC0000" />
        <path
          d="M22 10c-3 4 3 7 0 11M17 15c-2 3 2 5 0 8M27 15c-2 3 2 5 0 8M11 27c7-3 15-3 22 0v5H11z"
          fill="#fff"
          stroke="#fff"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </>
    ),
  },
  {
    nome: 'Caixa',
    logo: (
      <>
        <circle cx="22" cy="22" r="22" fill="#005CA9" />
        <path d="M13 13l18 18M31 13L13 31" stroke="#F39200" strokeWidth="5" strokeLinecap="round" />
      </>
    ),
  },
];

/** Atalho visual para conectar outros bancos (Open Finance), dentro do card da conta. */
export function OpenFinance() {
  const linha = useRef<HTMLDivElement>(null);
  useArrastarRolagem(linha);
  return (
    <div className="of-linha" ref={linha} role="group" aria-label="Conectar outros bancos (Open Finance)">
      {BANCOS.map(({ nome, logo }) => (
        <button key={nome} type="button" className="of-banco" aria-label={`Conectar ${nome}`}>
          <svg className="of-logo" viewBox="0 0 44 44" aria-hidden="true">
            {logo}
          </svg>
          {nome}
          <span className="of-mais" aria-hidden="true">
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#858893" strokeWidth="3.2" strokeLinecap="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
          </span>
        </button>
      ))}
    </div>
  );
}
