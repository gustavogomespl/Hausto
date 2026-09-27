import { useEffect, type RefObject } from 'react';

/**
 * Carrossel horizontal: no toque já rola sozinho; no mouse, arrastar e roda do mouse também rolam.
 * Enquanto arrasta, o clique do item não dispara.
 */
export function useArrastarRolagem(ref: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const linha = ref.current;
    if (!linha) return;
    let x0: number | null = null;
    let esquerda0 = 0;
    let moveu = false;

    const descer = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse' || e.button !== 0) return;
      x0 = e.clientX;
      esquerda0 = linha.scrollLeft;
      moveu = false;
    };
    const mover = (e: PointerEvent) => {
      if (x0 === null) return;
      const dx = e.clientX - x0;
      if (!moveu && Math.abs(dx) > 4) {
        moveu = true;
        linha.classList.add('arrastando');
      }
      if (moveu) linha.scrollLeft = esquerda0 - dx;
    };
    const soltar = () => {
      if (x0 === null) return;
      x0 = null;
      linha.classList.remove('arrastando');
    };
    const clicar = (e: MouseEvent) => {
      if (!moveu) return;
      e.stopPropagation();
      e.preventDefault();
      moveu = false;
    };
    const rodar = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
      const maximo = linha.scrollWidth - linha.clientWidth;
      if ((e.deltaY < 0 && linha.scrollLeft <= 0) || (e.deltaY > 0 && linha.scrollLeft >= maximo)) return;
      e.preventDefault();
      linha.scrollLeft += e.deltaY;
    };

    linha.addEventListener('pointerdown', descer);
    window.addEventListener('pointermove', mover);
    window.addEventListener('pointerup', soltar);
    linha.addEventListener('click', clicar, true);
    linha.addEventListener('wheel', rodar, { passive: false });
    return () => {
      linha.removeEventListener('pointerdown', descer);
      window.removeEventListener('pointermove', mover);
      window.removeEventListener('pointerup', soltar);
      linha.removeEventListener('click', clicar, true);
      linha.removeEventListener('wheel', rodar);
    };
  }, [ref]);
}
