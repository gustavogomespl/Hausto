import type { ReactNode, SVGProps } from 'react';

type Props = SVGProps<SVGSVGElement> & { tamanho?: number };

function svg(conteudo: ReactNode) {
  return function Icone({ tamanho = 24, ...resto }: Props) {
    return (
      <svg
        width={tamanho}
        height={tamanho}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.9}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        {...resto}
      >
        {conteudo}
      </svg>
    );
  };
}

/** A estrela de quatro pontas (✦) do Hausto. */
export function Brilho({ tamanho = 12, ...resto }: Props) {
  return (
    <svg width={tamanho} height={tamanho} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...resto}>
      <path d="M12 1.5c.7 5.8 4.7 9.8 10.5 10.5-5.8.7-9.8 4.7-10.5 10.5C11.3 16.7 7.3 12.7 1.5 12 7.3 11.3 11.3 7.3 12 1.5z" />
    </svg>
  );
}

export const Casa = svg(<path d="M4 10.5 12 4l8 6.5V19a1.5 1.5 0 0 1-1.5 1.5H15v-5.5H9v5.5H5.5A1.5 1.5 0 0 1 4 19z" />);
export const Raio = svg(<path d="M13 2.5 4.5 13.5h6.5l-1 8 8.5-11h-6.5z" />);
export const Lista = svg(<path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01" />);
export const Setas = svg(<path d="M4 8.5h15.5l-3.5-3.5M20 15.5H4.5L8 19" />);
export const Grade = svg(
  <>
    <rect x="4" y="4" width="6.5" height="6.5" rx="1.8" />
    <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.8" />
    <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.8" />
    <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.8" />
  </>,
);
export const Busca = svg(<path d="M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4" />);
export const Sino = svg(<path d="M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 1.5h-15zM10 20.5a2.2 2.2 0 0 0 4 0" />);
export const Balao = svg(<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v10a1.5 1.5 0 0 1-1.5 1.5H9l-5 4z" />);
export const OlhoFechado = svg(<path d="M3 9.5c4.5 5 13.5 5 18 0M6.5 12.5 5 14.5M12 14v2.5M17.5 12.5l1.5 2" />);
export const Pix = svg(<path d="M12 2.8 21.2 12 12 21.2 2.8 12zM12 7.8 7.8 12l4.2 4.2 4.2-4.2zM7.4 7.4l4.6 4.6 4.6-4.6" />);
export const CodigoBarras = svg(<path d="M4.5 5v14M8 5v14M11.5 5v14M14.5 5v10M17.5 5v14M20 5v10" />);
export const Credito = svg(
  <>
    <rect x="3.5" y="7" width="13" height="13" rx="2.2" />
    <path d="M12 10.5H9.3a1.3 1.3 0 0 0 0 2.6h1.4a1.3 1.3 0 0 1 0 2.6H8M10 9.3v1.2M10 15.7v1.2M19.5 3v6M16.5 6h6" />
  </>,
);
export const CartaoVirtual = svg(<rect x="3" y="6.5" width="18" height="11" rx="2" strokeDasharray="3 2.6" />);
export const Calendario = svg(
  <>
    <rect x="4" y="5.5" width="16" height="15" rx="2.2" />
    <path d="M4 10h16M8.5 3.5v4M15.5 3.5v4" />
  </>,
);
export const Baixar = svg(<path d="M12 3.5v12M7 10.5l5 5 5-5M5 20.5h14" />);
export const Celular = svg(
  <>
    <rect x="7" y="2.5" width="10" height="19" rx="2.2" />
    <path d="M11 18h2" />
  </>,
);
export const Banco = svg(<path d="M3.5 9.5 12 4.5l8.5 5zM5.5 10v7.5M9.8 10v7.5M14.2 10v7.5M18.5 10v7.5M3.5 20h17" />);
export const Seta = svg(<path d="m9 5.5 6.5 6.5L9 18.5" />);
export const Voltar = svg(<path d="M15 5.5 8.5 12l6.5 6.5" />);
export const Expandir = svg(<path d="M14.5 3.5h6v6M20.5 3.5 14 10M9.5 20.5h-6v-6M3.5 20.5 10 14" />);
export const Recolher = svg(<path d="M20 10h-6V4M14 10l6.5-6.5M4 14h6v6M10 14l-6.5 6.5" />);
export const Fechar = svg(<path d="M6 6l12 12M18 6 6 18" />);
export const Enviar = svg(<path d="M5 12h14M13 6l6 6-6 6" />);
export const Joinha = svg(<path d="M7.5 10.5V20h-3v-9.5zM7.5 10.5 11 3.5a2.3 2.3 0 0 1 2.3 2.3V9h5a2 2 0 0 1 2 2.3l-1.2 6.9a2 2 0 0 1-2 1.8H7.5" />);
export const Som = svg(<path d="M11 5.5 6.5 9H3.5v6h3l4.5 3.5zM15.5 9a4.2 4.2 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11" />);
