import { cn } from "@/lib/cn";

/**
 * Marca AtentBot: símbolo turquesa (PNG com transparência) + logotipo "ATENTBOT".
 * O logotipo é aplicado como máscara, então herda a cor do texto e funciona
 * nos temas claro e escuro sem precisar de duas versões do arquivo.
 */
export function Marca({
  tamanho = "md",
  nomeClassName,
  className,
}: {
  tamanho?: "md" | "lg";
  /** Classes extras do logotipo (ex.: escondê-lo em telas muito estreitas). */
  nomeClassName?: string;
  className?: string;
}) {
  const lg = tamanho === "lg";
  return (
    <span className={cn("inline-flex items-center", lg ? "gap-3" : "gap-2.5", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/brand/simbolo.png"
        alt=""
        width={256}
        height={220}
        className={lg ? "h-10 w-auto" : "h-8 w-auto"}
      />
      <span
        role="img"
        aria-label="AtentBot"
        className={cn("block bg-ink", nomeClassName, lg ? "h-[22px] w-[140px]" : "h-[17px] w-[108px]")}
        style={{
          WebkitMaskImage: "url(/brand/wordmark.png)",
          maskImage: "url(/brand/wordmark.png)",
          WebkitMaskSize: "contain",
          maskSize: "contain",
          WebkitMaskRepeat: "no-repeat",
          maskRepeat: "no-repeat",
        }}
      />
    </span>
  );
}
