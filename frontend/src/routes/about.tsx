import { DocumentPage, DocumentSection } from "@/components/document/DocumentPage";
import { PRODUCT_NAME } from "@/lib/publicCopy";

const DOCUMENT_META = [
  { label: "Version", value: "0.1 · draft" },
  { label: "Last updated", value: "4 May 2026" },
];

export function AboutRoute() {
  return (
    <DocumentPage
      title="About"
      lead={`${PRODUCT_NAME} is a focused past-paper revision tool for searching exam questions and asking grounded study questions against supported collections.`}
      meta={DOCUMENT_META}
    >
      <DocumentSection index={1} title="What it does">
        <p>
          The app searches curated past-paper collections and can assemble study answers with
          sources linked back to the exact questions used.
        </p>
      </DocumentSection>

      <DocumentSection index={2} title="Current scope">
        <p>
          Access is collection-based. Some collections are public, and some are limited to members
          of the relevant university community.
        </p>
      </DocumentSection>

      <DocumentSection index={3} title="Launch status">
        <p>
          This page is intentionally concise for the public-launch polish pass. Final project
          wording can be edited without changing the route structure.
        </p>
      </DocumentSection>
    </DocumentPage>
  );
}
