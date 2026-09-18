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
        <H>1. Modelo de preço: mensalidade com mensagens incluídas</H>
        <p>
          A cobrança do AtentBot tem <strong>duas partes</strong>, e só a primeira é obrigatória:
        </p>
        <ul>
          <li>
            <strong>Mensalidade (plano):</strong> valor fixo do plano contratado
            (Essencial, Profissional ou Escala), cobrado por período mensal. Define
            os limites do plano (números de WhatsApp, agentes, usuários) e a
            <strong> quantidade de mensagens da IA incluídas</strong> por ciclo.
          </li>
          <li>
            <strong>Pacotes extras (opcionais):</strong> se as mensagens do ciclo
            acabarem, o responsável da conta pode comprar um pacote no painel, em
            Assinatura, com pagamento único e antecipado. Nada é cobrado sem que
            você compre.
          </li>
        </ul>
        <p>
          <strong>O que conta como mensagem:</strong> cada resposta enviada pelo
          agente de IA a um cliente. Ler documentos, importar e reindexar o
          catálogo e as mensagens enviadas pela sua equipe não contam.
        </p>

        <H>2. Ciclo, forma de pagamento e início</H>
        <p>
          A mensalidade é cobrada de forma recorrente (mensal) via cartão de
          crédito, processada pela Stripe. Os pacotes extras são pagos na compra,
          pelos meios disponíveis no checkout. <strong>Não há período de teste
          gratuito</strong>: a primeira cobrança ocorre na contratação e o acesso
          é liberado em seguida.
        </p>

        <H>3. Cota do ciclo e pacotes extras</H>
        <ul>
          <li>
            As mensagens incluídas renovam a cada ciclo de cobrança. O que não for
            usado <strong>não acumula</strong> para o ciclo seguinte.
          </li>
          <li>
            O pacote extra entra no saldo quando o pagamento é confirmado e vale
            <strong> até o fim do ciclo em que foi pago</strong>. Mensagens de pacote
            não usadas expiram na renovação e não são reembolsadas.
          </li>
          <li>
            Avisamos o responsável da conta por e-mail ao atingir 80% e 100% das
            mensagens do ciclo. O saldo fica sempre visível no painel.
          </li>
          <li>
            Se as mensagens acabarem e nenhum pacote for comprado, a IA para de
            responder até a renovação. Cada cliente que escrever recebe um aviso de
            que um atendente vai continuar, e a conversa vai para a fila humana do
            painel. Nenhum valor adicional é cobrado. Se um pacote for comprado
            depois, as conversas em que sua equipe ainda não respondeu voltam
            para a IA.
          </li>
        </ul>

        <H>4. Impostos e reajustes</H>
        <p>
          Os valores podem estar sujeitos a tributos aplicáveis. Preços de plano,
          quantidade de mensagens incluídas e preços de pacote podem ser reajustados mediante aviso prévio razoável
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
          mensalidade. Não há reembolso proporcional do período em curso nem dos
          pacotes extras já comprados. O cancelamento pode ser
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
