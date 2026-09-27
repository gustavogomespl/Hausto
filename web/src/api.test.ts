import { afterEach, describe, expect, it, vi } from 'vitest';
import { buscarPainel, buscarTransacoes, conversar, ErroApi, listarPersonas, mensagemDeErro } from './api';
import { lerSessao, salvarSessao } from './sessao';

const respostaHttp = (status: number, json: () => Promise<unknown>) => ({ ok: status < 400, status, json });

afterEach(() => vi.unstubAllGlobals());

describe('api', () => {
  it('devolve o JSON quando a resposta é ok', async () => {
    const fetchMock = vi.fn().mockResolvedValue(respostaHttp(200, async () => [{ id: 'carla' }]));
    vi.stubGlobal('fetch', fetchMock);

    expect(await listarPersonas()).toEqual([{ id: 'carla' }]);
    expect(fetchMock.mock.calls[0][0]).toBe('/v1/personas');
  });

  it('lê o detail da resposta de erro e lança ErroApi com o status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respostaHttp(422, async () => ({ detail: 'mensagem vazia' }))));

    const erro = await conversar({ id_usuario: 'u-1' }).catch((e: unknown) => e);

    expect(erro).toBeInstanceOf(ErroApi);
    expect((erro as ErroApi).status).toBe(422);
    expect((erro as ErroApi).message).toBe('mensagem vazia');
  });

  it('usa "Erro <status>" quando o corpo do erro não é JSON', async () => {
    const semJson = async () => {
      throw new SyntaxError('não é JSON');
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respostaHttp(502, semJson)));

    await expect(listarPersonas()).rejects.toMatchObject({ status: 502, message: 'Erro 502' });
  });
});

describe('data da simulação', () => {
  const okVazio = () => vi.fn().mockResolvedValue(respostaHttp(200, async () => ({})));

  it('com data salva, manda data_ref na query do painel e no corpo do chat', async () => {
    localStorage.clear();
    salvarSessao({ id_usuario: 'u-1', persona: null, data_ref: '2025-12-25' });
    const dataRef = lerSessao()?.data_ref;
    const fetchMock = okVazio();
    vi.stubGlobal('fetch', fetchMock);

    await buscarPainel('u-1', dataRef);
    await buscarTransacoes('u-1', dataRef);
    await conversar({ id_usuario: 'u-1', mensagem: 'oi', data_ref: dataRef });

    expect(fetchMock.mock.calls[0][0]).toBe('/v1/clientes/u-1/painel?data_ref=2025-12-25');
    expect(fetchMock.mock.calls[1][0]).toBe('/v1/clientes/u-1/transacoes?limite=200&data_ref=2025-12-25');
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ id_usuario: 'u-1', mensagem: 'oi', data_ref: '2025-12-25' });
  });

  it('sem data escolhida, não manda o parâmetro', async () => {
    localStorage.clear();
    salvarSessao({ id_usuario: 'u-1', persona: null });
    const dataRef = lerSessao()?.data_ref;
    const fetchMock = okVazio();
    vi.stubGlobal('fetch', fetchMock);

    await buscarPainel('u-1', dataRef);
    await buscarTransacoes('u-1', dataRef);
    await conversar({ id_usuario: 'u-1', mensagem: 'oi', data_ref: dataRef });

    expect(fetchMock.mock.calls[0][0]).toBe('/v1/clientes/u-1/painel');
    expect(fetchMock.mock.calls[1][0]).toBe('/v1/clientes/u-1/transacoes?limite=200');
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).not.toHaveProperty('data_ref');
  });
});

describe('mensagemDeErro', () => {
  it('explica 404, outros status e falha de rede', () => {
    expect(mensagemDeErro(new ErroApi(404, 'Not Found'))).toBe('Não encontramos esse cliente.');
    expect(mensagemDeErro(new ErroApi(503, 'x'))).toContain('erro 503');
    expect(mensagemDeErro(new TypeError('Failed to fetch'))).toContain('Não consegui falar com o servidor');
  });
});
