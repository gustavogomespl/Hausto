import { useEffect, useRef, useState } from 'react';
import { buscarAvisos, buscarPainel, mensagemDeErro, type Aviso, type Origem, type Painel } from './api';
import { Chat, type PedidoAbertura } from './chat/Chat';
import { Carregando, Falha } from './componentes/Estados';
import { TabBar, type Aba } from './componentes/TabBar';
import { Topo } from './componentes/Topo';
import { iniciaisDe, lerSessao, salvarSessao, type SessaoSalva } from './sessao';
import { Admin } from './telas/Admin';
import { Extrato } from './telas/Extrato';
import { Inicio } from './telas/Inicio';
import { Menu } from './telas/Menu';
import { Onboarding } from './telas/Onboarding';
import { Pagamentos } from './telas/Pagamentos';
import { RaioX } from './telas/RaioX';

type Tela = Aba | 'admin';

export default function App() {
  const [sessao, setSessao] = useState<SessaoSalva | null>(lerSessao);
  const [tela, setTela] = useState<Tela>(() => (location.pathname === '/admin' ? 'admin' : 'inicio'));
  // Muda a cada troca de cliente para remontar o app (e zerar a sessão do chat).
  const [versao, setVersao] = useState(0);

  useEffect(() => {
    const aoVoltarNoNavegador = () => setTela(location.pathname === '/admin' ? 'admin' : 'inicio');
    window.addEventListener('popstate', aoVoltarNoNavegador);
    return () => window.removeEventListener('popstate', aoVoltarNoNavegador);
  }, []);

  function irPara(destino: Tela) {
    if (destino === 'admin' && location.pathname !== '/admin') history.pushState(null, '', '/admin');
    if (destino !== 'admin' && location.pathname === '/admin') history.replaceState(null, '', '/');
    setTela(destino);
  }

  function escolher(nova: SessaoSalva) {
    salvarSessao(nova);
    setSessao(nova);
    setVersao((v) => v + 1);
    irPara('inicio');
  }

  let conteudo;
  if (tela === 'admin') {
    conteudo = <Admin atual={sessao} aoEscolher={escolher} aoVoltar={sessao ? () => irPara('menu') : undefined} />;
  } else if (!sessao) {
    conteudo = <Onboarding aoEscolher={(p) => escolher({ id_usuario: p.id_usuario, persona: p })} />;
  } else {
    conteudo = <AppCliente key={`${sessao.id_usuario}#${versao}`} sessao={sessao} aba={tela} aoMudarAba={irPara} />;
  }

  return <main className="moldura">{conteudo}</main>;
}

type PropsCliente = { sessao: SessaoSalva; aba: Aba; aoMudarAba: (aba: Tela) => void };

function AppCliente({ sessao, aba, aoMudarAba }: PropsCliente) {
  const id = sessao.id_usuario;
  const [dados, setDados] = useState<{ painel: Painel; avisos: Aviso[] } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const [dispensados, setDispensados] = useState<string[]>([]);
  const [chatAberto, setChatAberto] = useState(false);
  const [pedido, setPedido] = useState<PedidoAbertura | null>(null);
  const contador = useRef(0);
  const rolagem = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let vivo = true;
    setErro(null);
    Promise.all([buscarPainel(id), buscarAvisos(id).catch(() => [] as Aviso[])])
      .then(([painel, avisos]) => vivo && setDados({ painel, avisos }))
      .catch((e) => vivo && setErro(mensagemDeErro(e)));
    return () => {
      vivo = false;
    };
  }, [id, tentativa]);

  useEffect(() => {
    rolagem.current?.scrollTo?.({ top: 0 });
  }, [aba]);

  function abrirChat(origem?: Origem) {
    setPedido({ id: ++contador.current, origem });
    setChatAberto(true);
  }

  const abrirAncora = (campo: Extract<Origem, { tipo: 'ancora' }>['campo']) => abrirChat({ tipo: 'ancora', campo });
  const abrirAviso = (aviso: Aviso) => abrirChat({ tipo: 'aviso', id: aviso.id });
  const avisoDa = (tela: Aviso['tela']) =>
    dados?.avisos.find((a) => a.tela === tela && !dispensados.includes(a.id));

  function renderizarAba() {
    if (aba === 'pagamentos') return <Pagamentos />;
    if (aba === 'menu') return <Menu aoAbrirDemo={() => aoMudarAba('admin')} />;
    if (erro) return <Falha mensagem={erro} aoTentar={() => setTentativa((n) => n + 1)} />;
    if (!dados) return <Carregando />;
    const { painel } = dados;
    switch (aba) {
      case 'inicio':
        return (
          <Inicio
            painel={painel}
            aviso={avisoDa('home')}
            aoAbrirAncora={abrirAncora}
            aoAbrirAviso={abrirAviso}
            aoDispensarAviso={(a) => setDispensados((d) => [...d, a.id])}
          />
        );
      case 'raiox':
        return <RaioX painel={painel} aviso={avisoDa('raiox')} aoAbrirAncora={abrirAncora} aoAbrirAviso={abrirAviso} />;
      case 'extrato':
        return <Extrato idUsuario={id} hoje={painel.data_ref} />;
    }
  }

  const precisaPagina = erro || !dados ? aba !== 'pagamentos' && aba !== 'menu' : false;

  return (
    <>
      <div className="rolagem" ref={rolagem}>
        <Topo iniciais={iniciaisDe(sessao)} aoAbrirChat={() => abrirChat()} />
        <div className="folha">{precisaPagina ? <div className="pagina">{renderizarAba()}</div> : renderizarAba()}</div>
      </div>
      <TabBar ativa={aba} aoMudar={aoMudarAba} />
      <Chat idUsuario={id} aberto={chatAberto} pedido={pedido} aoFechar={() => setChatAberto(false)} />
    </>
  );
}
