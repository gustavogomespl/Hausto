import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ClienteResumo, Persona } from '../api';
import { Admin } from './Admin';

const CARLA: Persona = {
  id: 'carla',
  nome: 'Carla Souza Lima',
  iniciais: 'CL',
  idade: 34,
  cidade: 'Recife',
  frase: 'Quero entender minha fatura.',
  renda: 'CLT',
  cor: '#f60',
  id_usuario: 'id-carla-0001',
};

function mockApi(clientes: ClienteResumo[] = []) {
  const respostas: Record<string, unknown> = {
    '/v1/personas': [CARLA],
    '/v1/clientes?limite=50': clientes,
    '/v1/clientes/id-carla-0001/painel': { data_ref: '2025-12-18' },
  };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => ({ ok: true, status: 200, json: async () => respostas[url] })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('<Admin>', () => {
  it('escolhe uma persona', async () => {
    mockApi();
    const aoEscolher = vi.fn();
    render(<Admin atual={null} aoEscolher={aoEscolher} />);

    fireEvent.click(await screen.findByRole('button', { name: /Souza Lima/ }));

    expect(aoEscolher).toHaveBeenCalledWith({ id_usuario: 'id-carla-0001', persona: CARLA });
  });

  it('usa o id digitado sem os espaços das pontas', async () => {
    mockApi();
    const aoEscolher = vi.fn();
    render(<Admin atual={null} aoEscolher={aoEscolher} />);

    fireEvent.change(screen.getByLabelText('id_usuario'), { target: { value: '  abc-123  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Usar' }));

    expect(aoEscolher).toHaveBeenCalledWith({ id_usuario: 'abc-123', persona: null });
  });

  it('cliente da base com o id de uma persona herda a persona', async () => {
    mockApi([{ id_usuario: 'id-carla-0001', persona: 'P2', gatilho: true }]);
    const aoEscolher = vi.fn();
    render(<Admin atual={null} aoEscolher={aoEscolher} />);
    await screen.findByRole('button', { name: /Souza Lima/ });

    fireEvent.click(await screen.findByTitle('id-carla-0001'));

    expect(aoEscolher).toHaveBeenCalledWith({ id_usuario: 'id-carla-0001', persona: CARLA });
  });

  it('"+7 dias" avança a partir da data original do cliente', async () => {
    mockApi();
    const aoMudarData = vi.fn();
    render(<Admin atual={{ id_usuario: 'id-carla-0001', persona: CARLA }} aoEscolher={() => {}} aoMudarData={aoMudarData} />);

    expect(await screen.findByText('18/12/2025')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Voltar à data original' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '+7 dias' }));

    expect(aoMudarData).toHaveBeenCalledWith('2025-12-25');
  });

  it('avança a partir da data já escolhida e "Voltar à data original" limpa', async () => {
    mockApi();
    const aoMudarData = vi.fn();
    render(
      <Admin
        atual={{ id_usuario: 'id-carla-0001', persona: CARLA, data_ref: '2025-12-30' }}
        aoEscolher={() => {}}
        aoMudarData={aoMudarData}
      />,
    );

    expect(screen.getByText('30/12/2025')).toBeTruthy();
    expect(await screen.findByText('Data original: 18/12/2025')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '+3 dias' }));
    fireEvent.click(screen.getByRole('button', { name: 'Voltar à data original' }));

    expect(aoMudarData.mock.calls).toEqual([['2026-01-02'], [null]]);
  });
});
