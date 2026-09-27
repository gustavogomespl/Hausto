import { useEffect, useMemo, useState } from 'react';
import { buscarTransacoes, mensagemDeErro, type Transacao } from '../api';
import { iconeDaCategoria } from '../categorias';
import { Carregando, Falha } from '../componentes/Estados';
import { Oculto } from '../componentes/Oculto';
import { dinheiroComSinal, tituloDoDia } from '../formato';
import './Extrato.css';

type Filtro = 'todos' | 'E' | 'S';
const FILTROS: { id: Filtro; rotulo: string }[] = [
  { id: 'todos', rotulo: 'Todos' },
  { id: 'E', rotulo: 'Entradas' },
  { id: 'S', rotulo: 'Saídas' },
];

type Props = { idUsuario: string; hoje: string; dataRef?: string };

export function Extrato({ idUsuario, hoje, dataRef }: Props) {
  const [transacoes, setTransacoes] = useState<Transacao[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const [filtro, setFiltro] = useState<Filtro>('todos');

  useEffect(() => {
    let vivo = true;
    setErro(null);
    buscarTransacoes(idUsuario, dataRef)
      .then((lista) => vivo && setTransacoes(lista))
      .catch((e) => vivo && setErro(mensagemDeErro(e)));
    return () => {
      vivo = false;
    };
  }, [idUsuario, dataRef, tentativa]);

  // Agrupa por dia mantendo a ordem da API (mais recentes primeiro).
  const dias = useMemo(() => {
    const grupos = new Map<string, Transacao[]>();
    for (const t of transacoes ?? []) {
      if (filtro !== 'todos' && t.tipo !== filtro) continue;
      const dia = t.data.slice(0, 10);
      grupos.set(dia, [...(grupos.get(dia) ?? []), t]);
    }
    return [...grupos];
  }, [transacoes, filtro]);

  return (
    <div className="pagina">
      <h1 className="pagina-titulo">Extrato</h1>
      <div className="filtros" role="tablist">
        {FILTROS.map((f) => (
          <button
            key={f.id}
            type="button"
            role="tab"
            aria-selected={filtro === f.id}
            className={`filtro${filtro === f.id ? ' ativo' : ''}`}
            onClick={() => setFiltro(f.id)}
          >
            {f.rotulo}
          </button>
        ))}
      </div>

      {erro && <Falha mensagem={erro} aoTentar={() => setTentativa((n) => n + 1)} />}
      {!erro && !transacoes && <Carregando />}
      {transacoes && dias.length === 0 && <p className="extrato-vazio">Nenhuma movimentação por aqui.</p>}

      {dias.map(([dia, itens]) => (
        <section key={dia} className="extrato-dia">
          <h2 className="secao-titulo">{tituloDoDia(dia, hoje)}</h2>
          <ul className="card extrato-lista">
            {itens.map((t, i) => (
              <li key={i} className="lancamento">
                <span className="lancamento-icone">{iconeDaCategoria(t.categoria, t.subcategoria, t.descr)}</span>
                <div className="lancamento-texto">
                  <strong>{t.descr}</strong>
                  <span>{t.categoria}</span>
                </div>
                <span className={`lancamento-valor${t.tipo === 'E' ? ' entrada' : ''}`}>
                  <Oculto>{dinheiroComSinal(t.vlr, t.tipo)}</Oculto>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
