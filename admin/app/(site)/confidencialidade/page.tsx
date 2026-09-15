import Link from "next/link";

export const metadata = { title: "Termos de Confidencialidade · AtentBot" };

function H({ children }: { children: React.ReactNode }) {
  return <h2 className="mt-8 text-lg font-semibold text-ink">{children}</h2>;
}

export default function ConfidencialidadePage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-14">
      <p className="text-xs font-semibold uppercase tracking-wider text-accent-ink">AtentBot</p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight text-ink">Termos de Confidencialidade</h1>
      <p className="mt-2 text-sm text-muted">Última atualização: setembro de 2026.</p>

      <div className="mt-3 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
        Documento modelo. Antes de usar comercialmente, valide com seu jurídico e
        preencha os dados da empresa (razão social, CNPJ, encarregado/DPO e contato).
      </div>

      <div className="mt-2 text-sm leading-relaxed text-ink [&_p]:mt-3 [&_p]:text-muted [&_li]:mt-1.5 [&_ul]:mt-2 [&_ul]:list-disc [&_ul]:pl-5 [&_li]:text-muted">
        <H>1. O que é confidencial</H>
        <p>
          Consideram-se confidenciais todas as informações do cliente às quais o
          AtentBot tem acesso para operar o serviço, incluindo: catálogo de
          produtos, cadastros e dados dos clientes finais, o conteúdo das conversas
          de WhatsApp, documentos enviados à base de conhecimento, credenciais e
          configurações. Também é confidencial qualquer informação da AtentBot
          compartilhada com o cliente.
        </p>

        <H>2. Isolamento entre clientes (multi-tenant)</H>
        <p>
          Cada cliente é um ambiente isolado (tenant). Os dados de um cliente —
          conversas, catálogo, base de conhecimento, clientes finais e métricas —
          <strong> não são acessíveis por outro cliente</strong>. Cada agente de IA
          responde apenas com base no conhecimento do próprio cliente.
        </p>

        <H>3. Uso das informações</H>
        <p>
          As informações são usadas exclusivamente para operar e melhorar o serviço
          contratado. <strong>Não vendemos</strong> dados e não os usamos para fins
          alheios à prestação do serviço. O acesso interno é restrito ao necessário.
        </p>

        <H>4. Subprocessadores</H>
        <p>
          Para funcionar, o serviço trafega dados por terceiros essenciais, cada um
          com suas próprias políticas:
        </p>
        <ul>
          <li><strong>Google (Gemini)</strong> — modelo de IA e geração de embeddings;</li>
          <li><strong>Stripe</strong> — processamento de pagamentos;</li>
          <li><strong>WhatsApp / Meta</strong> — canal de mensagens;</li>
          <li><strong>Provedor de infraestrutura</strong> — hospedagem e banco de dados.</li>
        </ul>

        <H>5. LGPD e papéis</H>
        <p>
          Em relação aos dados dos clientes finais tratados na plataforma, o cliente
          contratante atua como <strong>controlador</strong> e o AtentBot como
          <strong> operador</strong>, tratando os dados conforme as instruções do
          cliente e a legislação (Lei nº 13.709/2018 – LGPD). O cliente é
          responsável por ter base legal para o tratamento e por atender às
          solicitações dos titulares; o AtentBot dá o suporte técnico razoável.
          Encarregado/DPO (contato): <a href="mailto:contato@dewconsultoria.com.br" className="font-medium text-accent-ink hover:underline">contato@dewconsultoria.com.br</a>.
        </p>

        <H>6. Segurança</H>
        <p>
          Adotamos medidas técnicas e organizacionais razoáveis: senhas com hash,
          sessões autenticadas, isolamento por tenant, e restrição de acesso. Nenhum
          sistema é 100% imune; incidentes relevantes serão comunicados conforme a lei.
        </p>

        <H>7. Retenção e exclusão</H>
        <p>
          Os dados são mantidos enquanto durar a assinatura. Encerrado o contrato, o
          cliente pode solicitar a exportação e/ou exclusão dos seus dados, ressalvadas
          as obrigações legais de guarda.
        </p>

        <H>8. Vigência</H>
        <p>
          As obrigações de confidencialidade permanecem durante a vigência do contrato
          e por período razoável após o seu término.
        </p>

        <H>9. Contato</H>
        <p>
          Para assuntos de privacidade e confidencialidade:{" "}
          <a href="mailto:contato@dewconsultoria.com.br" className="font-medium text-accent-ink hover:underline">contato@dewconsultoria.com.br</a>. Sobre
          valores, veja as{" "}
          <Link href="/cobranca" className="font-medium text-accent-ink hover:underline">
            Regras de Cobrança
          </Link>.
        </p>
      </div>
    </main>
  );
}
