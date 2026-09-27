// Ícone ilustrativo por categoria (a API manda só o nome). Busca por trecho, sem acento.
const ICONES: [string[], string][] = [
  [['salario', 'renda', 'adiantamento', 'credito em conta', 'inss', 'beneficio', 'receita', 'entrada'], '💼'],
  [['fatura', 'cartao'], '💳'],
  [['mercado', 'supermercado', 'alimenta'], '🛒'],
  [['delivery', 'ifood', 'restaurante', 'lanche'], '🛵'],
  [['transporte', 'uber', 'combustivel', 'gasolina', 'onibus'], '🚗'],
  [['farmacia', 'saude', 'medic'], '💊'],
  [['streaming', 'assinatura', 'tv'], '📺'],
  [['aluguel', 'moradia', 'casa', 'condominio'], '🏠'],
  [['luz', 'energia', 'agua', 'gas'], '💡'],
  [['celular', 'internet', 'telefone'], '📱'],
  [['roupa', 'vestuario'], '👕'],
  [['escola', 'educacao', 'curso', 'material'], '🎒'],
  [['lazer', 'viagem', 'ferias'], '🎉'],
  [['pix', 'transferencia'], '🔁'],
  [['juros', 'tarifa', 'encargo', 'iof'], '📈'],
];

const normalizar = (texto: string) => texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

export function iconeDaCategoria(...textos: string[]) {
  const alvo = normalizar(textos.join(' '));
  return ICONES.find(([chaves]) => chaves.some((c) => alvo.includes(c)))?.[1] ?? '🧾';
}
