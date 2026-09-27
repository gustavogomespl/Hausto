import { useSyncExternalStore } from 'react';

/**
 * Leitura em voz alta das respostas do Hausto. Um único áudio por vez: começar outro para o anterior.
 * `useFalando(id)` diz se a resposta `id` é a que está tocando (para marcar o botão 🔊).
 */

let falando: string | null = null;
let geracao = 0;
const ouvintes = new Set<() => void>();

function mudar(id: string | null) {
  falando = id;
  ouvintes.forEach((avisar) => avisar());
}

const temVoz = () => typeof window !== 'undefined' && 'speechSynthesis' in window;

// Vozes neurais/online soam bem menos robóticas; nomes conhecidos ganham ou perdem pontos.
function melhorVoz(): SpeechSynthesisVoice | null {
  const pontos = (v: SpeechSynthesisVoice) =>
    (/natural|neural/i.test(v.name) ? 8 : 0) +
    (/google/i.test(v.name) ? 5 : 0) +
    (/enhanced|premium|aprimorad/i.test(v.name) ? 4 : 0) +
    (/online/i.test(v.name) ? 3 : 0) +
    (/francisca|thalita|luciana|fernanda/i.test(v.name) ? 1 : 0) +
    (/maria|daniel|compact|espeak/i.test(v.name) ? -4 : 0);
  const vozes = speechSynthesis.getVoices().filter((v) => /^pt[-_]BR/i.test(v.lang));
  return vozes.sort((a, b) => pontos(b) - pontos(a))[0] ?? null;
}

/** Deixa o texto com cara de fala: tira marcações e emojis e escreve valores como se fala. */
export function paraFala(texto: string) {
  return texto
    .replace(/\*\*/g, '')
    .replace(/^\s*-\s+/gm, '')
    .replace(/R\$\s*([\d.]+),00\b/g, '$1 reais')
    .replace(/R\$\s*([\d.]+),(\d{2})\b/g, '$1 reais e $2 centavos')
    .replace(/R\$\s*([\d.]+)/g, '$1 reais')
    .replace(/(\d)\s*x\b/gi, '$1 vezes')
    .replace(/✦/g, '')
    .replace(/[•→←↑↓·|]/g, ', ')
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]|\u{FE0F}|\u{200D}/gu, '')
    .replace(/\s*\n\s*/g, '. ')
    .replace(/([.!?])\s*\./g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

export function pararDeFalar() {
  geracao++;
  if (temVoz()) speechSynthesis.cancel();
  if (falando !== null) mudar(null);
}

/** Lê `texto` e marca a resposta `id` como tocando até terminar (ou até outra leitura começar). */
export function falar(texto: string, id: string) {
  pararDeFalar();
  if (!temVoz()) return;
  const minha = geracao;
  const voz = melhorVoz();
  // Uma frase por vez: pausas mais naturais e evita o corte de falas longas no Chrome.
  const frases = paraFala(texto).match(/[^.!?;:]+[.!?;:]*/g) ?? [];
  const terminar = () => {
    if (minha === geracao) mudar(null);
  };
  const proxima = (i: number) => {
    if (minha !== geracao) return;
    const frase = frases[i]?.trim();
    if (i >= frases.length) return terminar();
    if (!frase) return proxima(i + 1);
    const fala = new SpeechSynthesisUtterance(frase);
    fala.lang = 'pt-BR';
    if (voz) fala.voice = voz;
    fala.rate = voz && /natural|neural|google/i.test(voz.name) ? 1.05 : 1;
    fala.onend = () => proxima(i + 1);
    fala.onerror = terminar;
    speechSynthesis.speak(fala);
  };
  mudar(id);
  proxima(0);
}

const assinar = (avisar: () => void) => {
  ouvintes.add(avisar);
  return () => ouvintes.delete(avisar);
};

export function useFalando(id: string) {
  return useSyncExternalStore(assinar, () => falando === id);
}

export const podeFalar = temVoz;
