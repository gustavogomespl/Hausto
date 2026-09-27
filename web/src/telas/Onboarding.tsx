import { useEffect, useState } from 'react';
import { listarPersonas, mensagemDeErro, type Persona } from '../api';
import { Brilho } from '../componentes/Icones';
import { Carregando, Falha } from '../componentes/Estados';
import './Onboarding.css';

type Props = { aoEscolher: (persona: Persona) => void };

export function Onboarding({ aoEscolher }: Props) {
  const [personas, setPersonas] = useState<Persona[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const [escolhida, setEscolhida] = useState<Persona | null>(null);

  useEffect(() => {
    let vivo = true;
    setErro(null);
    listarPersonas()
      .then((lista) => vivo && setPersonas(lista))
      .catch((e) => vivo && setErro(mensagemDeErro(e)));
    return () => {
      vivo = false;
    };
  }, [tentativa]);

  return (
    <div className="rolagem onboarding">
      <header className="onb-topo">
        <div className="onb-marca">
          <span className="onb-logo">
            <Brilho tamanho={20} />
          </span>
          Hausto
        </div>
        <span className="onb-selo">Teste prévio</span>
        <h1>Com quem o Hausto vai conversar?</h1>
        <p>Escolha uma persona. Cada persona é um cliente real da base, com o extrato dela.</p>
      </header>

      <div className="onb-lista">
        {erro && <Falha mensagem={erro} aoTentar={() => setTentativa((n) => n + 1)} />}
        {!erro && !personas && <Carregando />}
        {personas?.map((p) => (
          <PersonaCard key={p.id} persona={p} marcada={escolhida?.id === p.id} aoMarcar={() => setEscolhida(p)} />
        ))}
      </div>

      <footer className="onb-rodape">
        <button
          type="button"
          className="onb-botao"
          disabled={!escolhida}
          onClick={() => escolhida && aoEscolher(escolhida)}
        >
          {escolhida ? `Entrar como ${escolhida.nome.split(' ')[0]}` : 'Escolha uma persona'}
        </button>
        <small>Dados fictícios, apenas para teste.</small>
      </footer>
    </div>
  );
}

export function PersonaCard({ persona, marcada, aoMarcar }: { persona: Persona; marcada: boolean; aoMarcar: () => void }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={marcada}
      className={`persona${marcada ? ' marcada' : ''}`}
      onClick={aoMarcar}
    >
      <div className="persona-cabeca">
        <span className="persona-avatar" style={{ background: persona.cor }}>
          {persona.iniciais}
        </span>
        <div className="persona-nome">
          <strong>{persona.nome}</strong>
          <span>
            {persona.idade} anos · {persona.cidade}
          </span>
        </div>
        <span className="persona-radio" />
      </div>
      <p className="persona-frase">"{persona.frase}"</p>
      <div className="persona-tags">
        <span className="tag tag-renda">{persona.renda}</span>
      </div>
    </button>
  );
}
