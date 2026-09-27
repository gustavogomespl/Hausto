import { createContext, useContext, type ReactNode } from 'react';

/** O "olho" da Home: quando ligado, todo valor em dinheiro do app vira ••••. */
export const ValoresOcultos = createContext<{ ocultos: boolean; alternar: () => void }>({
  ocultos: false,
  alternar: () => {},
});

export const useValoresOcultos = () => useContext(ValoresOcultos);

export const MASCARA = '••••';

/** Um valor em dinheiro que respeita o "ocultar valores". */
export function Oculto({ children }: { children: ReactNode }) {
  const { ocultos } = useValoresOcultos();
  return ocultos ? <span className="oculto">{MASCARA}</span> : <>{children}</>;
}
