import Link from "next/link";

export const metadata = { title: "Regras de Cobrança · AtentBot" };

function H({ children }: { children: React.ReactNode }) {
  return <h2 className="mt-8 text-lg font-semibold text-ink">{children}</h2>;
}

export default function CobrancaPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-14">
      <p className="text-xs font-semibold uppercase tracking-wider text-accent-ink">AtentBot</p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight text-ink">Regras de Cobrança</h1>
      <p className="mt-2 text-sm text-muted">Última atualização: setembro de 2026.</p>

      <div className="mt-3 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
        Documento modelo. Antes de usar comercialmente, valide com seu jurídico e
        preencha os dados da empresa (razão social, CNPJ e contato).
      </div>

      <div className="mt-2 text-sm leading-relaxed text-ink [&_p]:mt-3 [&_p]:text-muted [&_li]:mt-1.5 [&_ul]:mt-2 [&_ul]:list-disc [&_ul]:pl-5 [&_li]:text-muted">
        <H>1. Modelo de preço: mensalidade + consumo</H>
        <p>
          A cobrança do AtentBot tem <strong>duas partes</strong>:
        </p>
        <ul>
          <li>
            <strong>Mensalidade base (plano):</strong> valor fixo do plano
            contratado (Essencial, Profissional ou Escala), cobrado por período
            mensal. Define os limites do plano (números de WhatsApp, agentes,
            usuários, etc.).
          </li>
          <li>
            <strong>Extras por consumo (pay-per-use):</strong> valor variável
            conforme o uso que gera custo de IA, medido em tokens:
            <ul>
              <li><strong>Indexação</strong> — ao enviar/atualizar documentos e reindexar o catálogo (geração de embeddings);</li>
              <li><strong>Conversas</strong> — processamento das mensagens pelo agente de IA.</li>
            </ul>
            Quanto mais documentos e mensagens, maior o consumo. As tarifas
            vigentes por 1.000 tokens ficam visíveis no painel, em Assinatura.
          </li>
        </ul>

        <H>2. Ciclo, forma de pagamento e início</H>
        <p>
          A mensalidade é cobrada de forma recorrente (mensal) via cartão de
          crédito, processada pela Stripe. <strong>Não há período de teste
          gratuito</strong>: a primeira cobrança ocorre na contratação e o acesso
          é liberado em seguida.
        </p>

        <H>3. Como os extras são cobrados</H>
        <p>
          O consumo é medido continuamente e exibido no painel. Enquanto a
          cobrança automática de extras não estiver ativada na sua conta, os
          valores aparecem como <strong>estimativa</strong> (informativos). Quando
          ativada, o consumo do período é somado à fatura da assinatura. O painel
          sempre mostra o consumo acumulado do mês antes do fechamento.
        </p>

        <H>4. Impostos e reajustes</H>
        <p>
          Os valores podem estar sujeitos a tributos aplicáveis. Preços de plano e
          tarifas de consumo podem ser reajustados mediante aviso prévio razoável
          (ex.: 30 dias), passando a valer no ciclo seguinte.
        </p>

        <H>5. Atraso e inadimplência</H>
        <p>
          Em caso de falha no pagamento, a assinatura entra em pendência
          (<em>past_due</em>). Há um período de carência antes da suspensão do
          acesso; regularizado o pagamento, o acesso é restabelecido.
        </p>

        <H>6. Cancelamento e reembolso</H>
        <p>
          O cancelamento pode ser solicitado a qualquer momento pelo painel, em
          Assinatura. O cancelamento é <strong>agendado para o fim do período já
          pago</strong>: você mantém o acesso até lá e não é cobrada nova
          mensalidade. Não há reembolso proporcional do período em curso. Extras
          de consumo já incorridos até a data são devidos. O cancelamento pode ser
          revertido (reativado) enquanto o período não terminar.
        </p>

        <H>7. Contato</H>
        <p>
          Dúvidas sobre cobrança:{" "}
          <a href="mailto:contato@dewconsultoria.com.br" className="font-medium text-accent-ink hover:underline">contato@dewconsultoria.com.br</a>. Regras
          relacionadas ao tratamento de dados estão na{" "}
          <Link href="/confidencialidade" className="font-medium text-accent-ink hover:underline">
            Política de Confidencialidade
          </Link>.
        </p>
      </div>
    </main>
  );
}
