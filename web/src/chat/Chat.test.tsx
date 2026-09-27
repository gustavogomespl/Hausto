import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { RespostaChat } from '../api';
import { Chat } from './Chat';

const resposta = (extra: Partial<RespostaChat> = {}): RespostaChat => ({
  sessao_id: 'sessao-1',
  resposta: 'Oi, Carla. A fatura de **R$ 1.980** vence dia 12.',
  etapa: 'explicar',
  modo: 'simulado',
  pendente_confirmacao: null,
  tools_chamadas: [],
  numeros_sem_fonte: [],
  sugestoes: ['Quero ver', 'Agora não'],
  ancora: { rotulo: 'Fatura aberta', valor: 1980 },
  pergunta: 'Por que esse valor?',
  visuais: [],
  ...extra,
});

function mockFetch(...respostas: RespostaChat[]) {
  const fetchMock = vi.fn();
  for (const r of respostas) fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => r });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const corpoDa = (fetchMock: ReturnType<typeof vi.fn>, chamada: number) =>
  JSON.parse(fetchMock.mock.calls[chamada][1].body as string);

afterEach(() => vi.unstubAllGlobals());

describe('<Chat>', () => {
  it('envia a origem ao abrir por âncora e mostra contexto, pergunta, resposta e sugestões', async () => {
    const fetchMock = mockFetch(resposta());
    render(
      <Chat
        idUsuario="u-1"
        aberto
        pedido={{ id: 1, origem: { tipo: 'ancora', campo: 'fatura' } }}
        aoFechar={() => {}}
      />,
    );

    expect(await screen.findByRole('button', { name: 'Quero ver' })).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe('/v1/chat');
    expect(corpoDa(fetchMock, 0)).toEqual({ id_usuario: 'u-1', origem: { tipo: 'ancora', campo: 'fatura' } });
    expect(screen.getByText('Fatura aberta')).toBeTruthy();
    expect(screen.getByText('R$ 1.980,00')).toBeTruthy();
    expect(screen.getByText('Por que esse valor?')).toBeTruthy();
    expect(screen.getByText('R$ 1.980').tagName).toBe('STRONG');
  });

  it('manda o texto da sugestão como mensagem reaproveitando a sessão', async () => {
    const fetchMock = mockFetch(resposta(), resposta({ ancora: null, pergunta: null, resposta: 'Certo.', sugestoes: ['Sim', 'Não'] }));
    render(<Chat idUsuario="u-1" aberto pedido={{ id: 1, origem: { tipo: 'ancora', campo: 'fatura' } }} aoFechar={() => {}} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Quero ver' }));

    expect(await screen.findByRole('button', { name: 'Sim' })).toBeTruthy();
    expect(corpoDa(fetchMock, 1)).toEqual({ id_usuario: 'u-1', mensagem: 'Quero ver', sessao_id: 'sessao-1' });
  });

  it('mostra um único balão do cliente quando o chip enviado como mensagem volta com pergunta', async () => {
    // O servidor transforma o chip em origem e devolve a pergunta canônica dele.
    const fetchMock = mockFetch(
      resposta({ sugestoes: ['Quero simular'] }),
      resposta({ ancora: null, pergunta: 'Simular meu imprevisto', resposta: 'Vamos simular.', sugestoes: ['Ok'] }),
    );
    const { container } = render(
      <Chat idUsuario="u-1" aberto pedido={{ id: 1, origem: { tipo: 'ancora', campo: 'fatura' } }} aoFechar={() => {}} />,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Quero simular' }));

    expect(await screen.findByRole('button', { name: 'Ok' })).toBeTruthy();
    expect(corpoDa(fetchMock, 1).mensagem).toBe('Quero simular');
    const baloes = [...container.querySelectorAll('.msg-cliente')].map((b) => b.textContent);
    expect(baloes).toEqual(['Por que esse valor?', 'Quero simular']);
  });

  it.each([
    ['Minha fatura', 'fatura'],
    ['Meu saldo', 'saldo'],
  ])('aberto sem origem mostra as boas-vindas e "%s" manda a âncora %s', async (chip, campo) => {
    const fetchMock = mockFetch(resposta());
    render(<Chat idUsuario="u-1" aberto pedido={{ id: 1 }} aoFechar={() => {}} />);

    expect(screen.getByText(/Toque em qualquer valor com/)).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: chip }));

    expect(await screen.findByRole('button', { name: 'Quero ver' })).toBeTruthy();
    expect(corpoDa(fetchMock, 0)).toEqual({ id_usuario: 'u-1', origem: { tipo: 'ancora', campo } });
  });

  it('mostra o card do visual abaixo do texto do Hausto e acima das sugestões', async () => {
    mockFetch(
      resposta({
        visuais: [
          {
            tipo: 'linha_do_tempo',
            titulo: 'Seu caixa até o salário',
            resumo: 'A fatura vence antes do salário cair.',
            dados: {
              eventos: [
                { data: '2025-12-25', rotulo: 'Vence a fatura', valor: 1980, tipo: 'fatura' },
                { data: '2025-12-10', rotulo: 'Hoje', valor: null, tipo: 'hoje' },
              ],
            },
          },
        ],
      }),
    );
    const { container } = render(
      <Chat idUsuario="u-1" aberto pedido={{ id: 1, origem: { tipo: 'ancora', campo: 'fatura' } }} aoFechar={() => {}} />,
    );

    const card = await screen.findByRole('figure', { name: 'Seu caixa até o salário' });
    const mensagem = container.querySelector('.msg-hausto')!;
    expect(mensagem.contains(card)).toBe(true);
    const segue = (a: Node, b: Node) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(segue(screen.getByText('R$ 1.980'), card)).toBe(true);
    expect(segue(card, screen.getByRole('button', { name: 'Quero ver' }))).toBe(true);
    expect(card.getAttribute('aria-describedby')).toBeTruthy();
    expect(screen.getByText('A fatura vence antes do salário cair.')).toBeTruthy();
  });

  it('sem visuais a mensagem do Hausto fica só com o texto (inclusive se o campo não vier)', async () => {
    const semCampo: Partial<RespostaChat> = resposta({ resposta: 'Segunda resposta.', sugestoes: ['Ok'] });
    delete semCampo.visuais;
    mockFetch(resposta(), semCampo as RespostaChat);
    const { container } = render(
      <Chat idUsuario="u-1" aberto pedido={{ id: 1, origem: { tipo: 'ancora', campo: 'fatura' } }} aoFechar={() => {}} />,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Quero ver' }));

    expect(await screen.findByRole('button', { name: 'Ok' })).toBeTruthy();
    expect(container.querySelectorAll('.msg-hausto')).toHaveLength(2);
    expect(container.querySelector('.visual')).toBeNull();
  });

  it('mostra erro claro quando a API falha', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }));
    render(<Chat idUsuario="u-1" aberto pedido={{ id: 1, origem: { tipo: 'ancora', campo: 'saldo' } }} aoFechar={() => {}} />);

    expect((await screen.findByRole('alert')).textContent).toContain('erro 500');
  });
});
