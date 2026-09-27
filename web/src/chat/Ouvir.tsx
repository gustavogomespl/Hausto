import { useEffect, useRef, useState } from 'react';
import { Som } from '../componentes/Icones';

/** Texto do chat pronto para a voz: sem marcação, dinheiro por extenso e uma frase por linha. */
export function paraFala(texto: string): string {
  return texto
    .replace(/\*\*/g, '')
    .replace(/✦/g, '')
    .replace(/R\$\s?(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})/g, (_, reais: string, centavos: string) =>
      Number(centavos) ? `${reais} reais e ${Number(centavos)} centavos` : `${reais} reais`,
    )
    .split('\n')
    .map((linha) => linha.trim().replace(/^- /, ''))
    .filter(Boolean)
    .map((linha) => (/[.!?:;]$/.test(linha) ? linha : `${linha}.`))
    .join(' ');
}

function sintese(): SpeechSynthesis | undefined {
  return typeof window === 'undefined' ? undefined : window.speechSynthesis;
}

/** Acessibilidade: lê a mensagem em voz alta com a voz do próprio navegador (pt-BR). Sem voz, não aparece. */
export function BotaoOuvir({ texto }: { texto: string }) {
  const [falando, setFalando] = useState(false);
  const falandoRef = useRef(false);
  falandoRef.current = falando;
  useEffect(() => () => {
    if (falandoRef.current) sintese()?.cancel(); // saiu da tela: não continua falando
  }, []);

  const voz = sintese();
  if (!voz || typeof SpeechSynthesisUtterance === 'undefined') return null;

  function alternar() {
    if (!voz) return;
    voz.cancel(); // para esta ou outra mensagem que esteja falando
    if (falando) {
      setFalando(false);
      return;
    }
    const fala = new SpeechSynthesisUtterance(paraFala(texto));
    fala.lang = 'pt-BR';
    const portugues = voz.getVoices?.().find((v) => v.lang?.toLowerCase().startsWith('pt'));
    if (portugues) fala.voice = portugues;
    fala.onend = () => setFalando(false);
    fala.onerror = () => setFalando(false);
    voz.speak(fala);
    setFalando(true);
  }

  return (
    <button
      type="button"
      className="msg-ouvir"
      onClick={alternar}
      aria-pressed={falando}
      aria-label={falando ? 'Parar leitura' : 'Ouvir mensagem'}
      title={falando ? 'Parar leitura' : 'Ouvir mensagem'}
    >
      <Som tamanho={22} />
    </button>
  );
}
