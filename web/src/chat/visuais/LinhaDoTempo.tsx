import type { EventoTempo } from '../../api';
import { diaMesNumerico, dinheiro } from '../../formato';
import './LinhaDoTempo.css';

function textoDoValor({ tipo, valor }: EventoTempo) {
  if (valor === null) return null;
  if (tipo === 'renda') return '+' + dinheiro(Math.abs(valor));
  if (tipo === 'hoje') return dinheiro(valor);
  return '-' + dinheiro(Math.abs(valor));
}

/** Eventos do caixa em ordem de data, numa linha vertical compacta. */
export function LinhaDoTempo({ eventos }: { eventos: EventoTempo[] }) {
  const ordenados = [...eventos].sort((a, b) => a.data.localeCompare(b.data));

  return (
    <ol className="tempo">
      {ordenados.map((e, i) => {
        const valor = textoDoValor(e);
        return (
          <li key={`${e.data}-${i}`} className={`tempo-evento ${e.tipo}`}>
            <time dateTime={e.data.slice(0, 10)}>{diaMesNumerico(e.data)}</time>
            <span className="tempo-marca" aria-hidden="true" />
            <span className="tempo-rotulo">{e.rotulo}</span>
            {valor && <b className="nowrap">{valor}</b>}
          </li>
        );
      })}
    </ol>
  );
}
