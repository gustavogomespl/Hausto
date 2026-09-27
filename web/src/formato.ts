const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const moedaInteira = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

// Intl usa espaço não separável entre "R$" e o número; trocamos por espaço comum
// e evitamos a quebra de linha via CSS (white-space: nowrap).
const limpar = (texto: string) => texto.replace(/ /g, ' ');

/** R$ 1.980,00 */
export const dinheiro = (valor: number) => limpar(moeda.format(valor));

/** R$ 1.980 quando o valor é redondo; senão mantém os centavos (R$ 2,35). Usado no Raio-X. */
export const dinheiroCurto = (valor: number) =>
  Number.isInteger(valor) ? limpar(moedaInteira.format(valor)) : dinheiro(valor);

/** +R$ 1.500,00 / -R$ 900,00 */
export const dinheiroComSinal = (valor: number, tipo: 'E' | 'S') =>
  (tipo === 'E' ? '+' : '-') + dinheiro(Math.abs(valor));

const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];

/** Lê "YYYY-MM-DD" (ou ISO com hora) sem passar por fuso horário. */
function partes(data: string) {
  const [ano, mes, dia] = data.slice(0, 10).split('-').map(Number);
  return { ano, mes, dia };
}

/** "2025-10-12" -> "12/out" */
export function diaMesCurto(data: string) {
  const { mes, dia } = partes(data);
  return `${dia}/${MESES[mes - 1]?.slice(0, 3) ?? '?'}`;
}

/** "2025-12-05" -> "05/12" */
export function diaMesNumerico(data: string) {
  const { mes, dia } = partes(data);
  return `${String(dia).padStart(2, '0')}/${String(mes).padStart(2, '0')}`;
}

/** "2025-12-05" -> "05/12/2025" */
export function dataCompleta(data: string) {
  const { ano } = partes(data);
  return `${diaMesNumerico(data)}/${ano}`;
}

/** "2025-12-18" + 7 -> "2025-12-25", em UTC para não tropeçar em fuso ou horário de verão. */
export function somarDias(data: string, dias: number) {
  const { ano, mes, dia } = partes(data);
  return new Date(Date.UTC(ano, mes - 1, dia + dias)).toISOString().slice(0, 10);
}

/** Título do grupo no extrato: "Hoje · 07/10" ou "20 de setembro". */
export function tituloDoDia(data: string, hoje: string) {
  const { mes, dia } = partes(data);
  if (data.slice(0, 10) === hoje.slice(0, 10)) {
    return `Hoje · ${String(dia).padStart(2, '0')}/${String(mes).padStart(2, '0')}`;
  }
  return `${dia} de ${MESES[mes - 1] ?? '?'}`;
}

/** "2025-10" ou "10/2025" -> "outubro" (null se não der para ler). */
export function nomeDoMes(anoMes: string | null | undefined) {
  const achado = anoMes?.match(/^\d{4}-(\d{2})|^(\d{1,2})\/\d{4}/);
  if (!achado) return null;
  return MESES[Number(achado[1] ?? achado[2]) - 1] ?? null;
}

/** "2025-10" -> "O" */
export const inicialDoMes = (anoMes: string) => (nomeDoMes(anoMes) ?? '?').charAt(0).toUpperCase();
