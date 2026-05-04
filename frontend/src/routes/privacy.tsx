import {
  DocumentCallout,
  DocumentExternalLink,
  DocumentPage,
  DocumentSection,
} from "@/components/document/DocumentPage";

const DOCUMENT_META = [
  { label: "Version", value: "0.1 · draft" },
  { label: "Last updated", value: "4 May 2026" },
];

const ICO_COMPLAINT_URL =
  "https://ico.org.uk/make-a-complaint/data-protection-complaints/data-protection-complaints/";

export function PrivacyRoute() {
  return (
    <DocumentPage
      title="Privacy notice"
      lead="A concise UK privacy notice for the current service. The contact details and final wording should be reviewed before public launch."
      meta={DOCUMENT_META}
    >
      <DocumentSection index={1} title="Controller and contact">
        <p>
          Controller and contact details will be finalized before public launch. Until then, this
          notice records the data categories and providers used by the current service.
        </p>
      </DocumentSection>

      <DocumentSection index={2} title="Personal data collected">
        <p>
          Sign-in identity and email, university or community affiliation, access-control records,
          search and study requests, and operational request logs.
        </p>
      </DocumentSection>

      <DocumentSection index={3} title="Purposes and lawful bases">
        <p>
          Authentication, access control, answering user requests, service security, debugging, rate
          limiting, and operating-cost control. Final lawful-basis wording should be reviewed before
          public launch.
        </p>
      </DocumentSection>

      <DocumentSection index={4} title="Retention">
        <p>
          Account and access records are kept while needed for access control. Operational logs are
          kept only while needed for security, debugging, and service operation. Final retention
          criteria should be reviewed before public launch.
        </p>
      </DocumentSection>

      <DocumentSection index={5} title="Recipients and providers">
        <p>
          Personal data may be processed by provider categories used for authentication, hosting,
          database or storage, rate limiting, AI or retrieval APIs, and operational infrastructure.
        </p>
      </DocumentSection>

      <DocumentSection index={6} title="Your rights">
        <p>
          You may ask for access, correction, deletion, restriction, objection, or portability where
          those rights apply.
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>Access: request a copy of the personal data held about you.</li>
          <li>Correction: ask for inaccurate or incomplete data to be corrected.</li>
          <li>Deletion: ask for data to be removed where the legal basis allows.</li>
          <li>Restriction or objection: limit how your data is processed.</li>
          <li>Portability: receive your data in a portable format where this applies.</li>
        </ul>
      </DocumentSection>

      <DocumentSection index={7} title="ICO complaint route">
        <p>
          You can complain to the UK Information Commissioner's Office if you are unhappy with how
          your personal data is handled.
        </p>
        <DocumentCallout label="Independent route">
          <p>
            The ICO is the UK's independent data-protection regulator. You may contact them at any
            time without first contacting us.
          </p>
        </DocumentCallout>
        <div className="mt-5">
          <DocumentExternalLink href={ICO_COMPLAINT_URL}>Contact the ICO ↗</DocumentExternalLink>
        </div>
      </DocumentSection>
    </DocumentPage>
  );
}
