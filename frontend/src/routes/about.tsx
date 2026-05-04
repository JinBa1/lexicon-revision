import {
  DocumentExternalLink,
  DocumentPage,
  DocumentSection,
} from "@/components/document/DocumentPage";
import {
  PRODUCT_NAME,
  PROJECT_DISCUSSIONS_URL,
  PROJECT_ISSUES_URL,
  PROJECT_REPOSITORY_URL,
} from "@/lib/publicCopy";

const DOCUMENT_META = [
  { label: "Version", value: "0.1 · draft" },
  { label: "Last updated", value: "4 May 2026" },
];

export function AboutRoute() {
  return (
    <DocumentPage
      title="About"
      lead={`${PRODUCT_NAME} is an independent study tool for supported university student communities. It helps students search past-paper collections, ask grounded study questions, and understand how topics appear across years, while keeping sources, access boundaries, and community ownership visible.`}
      meta={DOCUMENT_META}
    >
      <DocumentSection index={1} title="What it is">
        <p>
          Lexicon Revision is built for student communities working with course-relevant past-paper
          collections.
        </p>
        <p>
          It is not an official university service, a public past-paper archive, or a content
          redistribution platform. It is a study layer for supported collections: a way to search
          questions, ask about topics, compare patterns, and trace answers back to the source
          material.
        </p>
      </DocumentSection>

      <DocumentSection index={2} title="Access and communities">
        <p>Collections are community-managed and access-controlled where required.</p>
        <p>
          Course materials remain available only to eligible students within the relevant university
          community. Lexicon Revision is designed around that reality, with authentication and
          access controls that limit each collection to its intended audience.
        </p>
      </DocumentSection>

      <DocumentSection index={3} title="For students">
        <p>Lexicon Revision makes past-paper revision easier to navigate.</p>
        <p>
          Students can ask about topics, patterns, or specific questions across supported
          collections. The platform helps them find related examples across years, compare how ideas
          are tested, and move faster from scattered PDFs to source-backed understanding.
        </p>
        <p>
          The goal is not to predict exams. The goal is to help students spend less time searching
          manually and more time understanding what past papers are really testing.
        </p>
      </DocumentSection>

      <DocumentSection index={4} title="Revision with sources">
        <p>When generative AI is used, it works as a source-grounded assistance layer.</p>
        <p>
          Generated notes should help students orient themselves: where a topic appears, how
          questions are phrased, what related examples exist, and which source material supports the
          explanation. They are revision support, not official answers, mark schemes, or a
          replacement for lecture notes and course guidance.
        </p>
        <p>Students should always check the original questions and cited material.</p>
      </DocumentSection>

      <DocumentSection index={5} title="More than just another RAG chatbot">
        <p>
          Lexicon Revision treats past papers as a structured study corpus, not just a folder of
          PDFs.
        </p>
        <p>
          Behind the interface is a collection intelligence layer that turns static documents into
          searchable, traceable revision workflows. Questions can be indexed by topic and meaning,
          answers can be linked back to sources, collections can follow community access rules, and
          recurring patterns can be surfaced as the collection grows.
        </p>
        <p>
          This is what makes Lexicon different from a simple RAG chatbot: the answer layer is only
          one part of the product. The broader system is built around source traceability,
          collection governance, and helping students understand course material through the
          structure of past papers.
        </p>
      </DocumentSection>

      <DocumentSection index={6} title="Project direction">
        <p>
          Lexicon Revision is designed to grow collection by collection, community by community.
        </p>
        <p>
          The long-term aim is to provide responsible study infrastructure for student groups:
          searchable course collections, source-grounded explanations, recurring-topic discovery,
          access-aware deployment, and clearer workflows for maintaining revision material over
          time.
        </p>
        <p>
          Lexicon Revision should become more than a search layer over past papers. It should become
          a shared revision workspace where supported communities can build context around course
          material, connect different study resources, and help future students understand not just
          where a question appeared, but how people learned from it.
        </p>
        <p>
          The software can be open and inspectable while supported collections and restricted source
          materials remain controlled by the communities that use them.
        </p>
      </DocumentSection>

      <DocumentSection index={7} title="Independent and unofficial">
        <p>
          Lexicon Revision is open source, independent, and unofficial unless explicitly stated for
          a specific collection or deployment.
        </p>
        <p>
          For questions about a collection, access, source material, or takedown concerns, get in
          touch:
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <DocumentExternalLink href={PROJECT_REPOSITORY_URL}>
            GitHub Repository ↗
          </DocumentExternalLink>
          <DocumentExternalLink href={PROJECT_ISSUES_URL}>GitHub Issues ↗</DocumentExternalLink>
          <DocumentExternalLink href={PROJECT_DISCUSSIONS_URL}>
            GitHub Discussions ↗
          </DocumentExternalLink>
        </div>
      </DocumentSection>
    </DocumentPage>
  );
}
