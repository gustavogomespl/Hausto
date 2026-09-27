import { afterEach, describe, expect, it, vi } from 'vitest';
import { conversar, ErroApi, listarPersonas, mensagemDeErro } from './api';

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

describe('mensagemDeErro', () => {
  it('explica 404, outros status e falha de rede', () => {
    expect(mensagemDeErro(new ErroApi(404, 'Not Found'))).toBe('Não encontramos esse cliente.');
    expect(mensagemDeErro(new ErroApi(503, 'x'))).toContain('erro 503');
    expect(mensagemDeErro(new TypeError('Failed to fetch'))).toContain('Não consegui falar com o servidor');
  });
});
