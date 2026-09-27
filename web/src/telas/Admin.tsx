import { useEffect, useState, type FormEvent } from 'react';
import { listarClientes, listarPersonas, mensagemDeErro, type ClienteResumo, type Persona } from '../api';
import { Carregando, Falha } from '../componentes/Estados';
import { Voltar } from '../componentes/Icones';
import type { SessaoSalva } from '../sessao';
import './Admin.css';

type Props = {
  atual: SessaoSalva | null;
  aoEscolher: (sessao: SessaoSalva) => void;
  aoVoltar?: () => void;
};

type Carga<T> = { dados: T | null; erro: string | null };

function useCarga<T>(buscar: () => Promise<T>): Carga<T> {
  const [estado, setEstado] = useState<Carga<T>>({ dados: null, erro: null });
  useEffect(() => {
    let vivo = true;
    buscar()
      .then((dados) => vivo && setEstado({ dados, erro: null }))
      .catch((e) => vivo && setEstado({ dados: null, erro: mensagemDeErro(e) }));
    return () => {
      vivo = false;
    };
  }, [buscar]);
  return estado;
}

export function Admin({ atual, aoEscolher, aoVoltar }: Props) {
  const personas = useCarga(listarPersonas);
  const clientes = useCarga(listarClientes);
  const [idDigitado, setIdDigitado] = useState('');

  // Um cliente da base pode ser o mesmo de uma persona; aí herdamos nome e iniciais.
  const personaDe = (c: ClienteResumo) => personas.dados?.find((p) => p.id_usuario === c.id_usuario) ?? null;
  const usarCliente = (c: ClienteResumo) => aoEscolher({ id_usuario: c.id_usuario, persona: personaDe(c) });
  const usarPersona = (p: Persona) => aoEscolher({ id_usuario: p.id_usuario, persona: p });

  function enviar(e: FormEvent) {
    e.preventDefault();
    const id = idDigitado.trim();
    if (id) aoEscolher({ id_usuario: id, persona: null });
  }

  return (
    <div className="rolagem admin">
      <header className="admin-topo">
        {aoVoltar && (
          <button type="button" className="admin-voltar" onClick={aoVoltar} aria-label="Voltar ao app">
            <Voltar />
          </button>
        )}
        <div>
          <h1>Modo demonstração</h1>
          <p>{atual ? `Cliente atual: ${curto(atual.id_usuario)}` : 'Escolha com quem o Hausto vai conversar.'}</p>
        </div>
      </header>

      <div className="pagina">
        <h2 className="secao-titulo">Personas</h2>
        {personas.erro && <Falha mensagem={personas.erro} />}
        {!personas.erro && !personas.dados && <Carregando />}
        <div className="admin-personas">
          {personas.dados?.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`admin-persona${atual?.id_usuario === p.id_usuario ? ' atual' : ''}`}
              onClick={() => usarPersona(p)}
            >
              <span className="admin-avatar" style={{ background: p.cor }}>
                {p.iniciais}
              </span>
              <strong>{p.nome.split(' ').slice(-2).join(' ')}</strong>
              <small>{p.renda}</small>
            </button>
          ))}
        </div>

        <h2 className="secao-titulo">Outro cliente</h2>
        <form className="card admin-form" onSubmit={enviar}>
          <input
            value={idDigitado}
            onChange={(e) => setIdDigitado(e.target.value)}
            placeholder="id_usuario"
            aria-label="id_usuario"
            autoCapitalize="off"
            spellCheck={false}
          />
          <button type="submit" className="botao-laranja" disabled={!idDigitado.trim()}>
            Usar
          </button>
        </form>

        <h2 className="secao-titulo">Clientes da base</h2>
        {clientes.erro && <Falha mensagem={clientes.erro} />}
        {!clientes.erro && !clientes.dados && <Carregando />}
        {clientes.dados && (
          <ul className="card admin-clientes">
            {clientes.dados.length === 0 && <li className="admin-vazio">Nenhum cliente.</li>}
            {clientes.dados.map((c) => (
              <li key={c.id_usuario}>
                <button
                  type="button"
                  className={atual?.id_usuario === c.id_usuario ? 'atual' : ''}
                  onClick={() => usarCliente(c)}
                  title={c.id_usuario}
                >
                  <code>{curto(c.id_usuario)}</code>
                  <span className="admin-persona-nome">
                    {c.persona}
                    {personaDe(c) && ` · ${personaDe(c)!.nome.split(' ').at(-2)}`}
                  </span>
                  {c.gatilho && <span className="admin-gatilho">gatilho D-7</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

const curto = (id: string) => (id.length > 12 ? `${id.slice(0, 8)}…` : id);
