import {
  DocumentCallout,
  DocumentExternalLink,
  DocumentPage,
  DocumentSection,
} from "@/components/document/DocumentPage";
import { PROJECT_DISCUSSIONS_URL, PROJECT_ISSUES_URL } from "@/lib/publicCopy";

const DOCUMENT_META = [
  { label: "Version", value: "0.2" },
  { label: "Last updated", value: "4 May 2026" },
];

const ICO_COMPLAINT_URL =
  "https://ico.org.uk/make-a-complaint/data-protection-complaints/data-protection-complaints/";
const PRIVACY_EMAIL = "jin.bai@outlook.com";

const DATA_CATEGORIES = [
  {
    label: "Account and access data",
    text: "Email address, email verification status, Clerk user identifier, university or community affiliation, collection access status, and access-control records.",
  },
  {
    label: "Study and search data",
    text: "Collections you select, search or study questions you submit, filters, retrieved source references, and generated responses. Lexicon Revision does not currently provide a user-facing study history and does not intentionally store raw search or study questions in normal usage logs.",
  },
  {
    label: "Operational and security data",
    text: "Request identifiers, endpoint, collection name, user identifier where signed in, outcome, latency, provider telemetry, rate-limit metadata, timestamps, and security or error events. Anonymous rate limiting may process IP address-derived identifiers.",
  },
  {
    label: "Contact and request data",
    text: "Messages you send for support, privacy requests, or collection suggestions, including public GitHub issue or discussion content if you choose to use those channels.",
  },
];

const PURPOSES = [
  {
    purpose: "Accounts, sign-in, collection access, search, and source-grounded revision features",
    basis: "Contract, or legitimate interests in providing the requested service",
  },
  {
    purpose: "Security, abuse prevention, rate limiting, debugging, and reliability",
    basis: "Legitimate interests",
  },
  {
    purpose: "Support, privacy requests, and collection suggestions",
    basis: "Legitimate interests, or legal obligation where applicable",
  },
  {
    purpose: "Legal compliance and handling formal requests",
    basis: "Legal obligation",
  },
];

const PROVIDERS = [
  ["Clerk", "Sign-in and account authentication"],
  ["Cloudflare Pages", "Frontend hosting"],
  ["Fly.io", "Backend API hosting"],
  ["Neon", "Postgres database and retrieval store"],
  ["Cloudflare R2", "Object and media storage"],
  ["Upstash Redis", "Rate limiting and abuse prevention"],
  ["Voyage", "Embeddings and reranking"],
  ["OpenAI-compatible provider", "Planning and answer generation"],
  ["GitHub", "Public issue and discussion based support or collection requests"],
] as const;

const RETENTION_ITEMS = [
  "Account and access records are kept while the account or collection access remains active, then deleted or anonymised when they are no longer needed.",
  "Manual access overrides are kept while the override is active or needed for access administration.",
  "Operational usage logs are kept only for security, debugging, reliability, rate limiting, and service operation.",
  "Rate-limit counters are temporary and follow the configured rate-limit windows.",
  "Public GitHub issues or discussions remain public until edited or removed through GitHub.",
  "Deleted records may remain in provider backups for a limited period until those backups expire under the provider's normal backup cycle.",
];

export function PrivacyRoute() {
  return (
    <DocumentPage
      title="Privacy notice"
      lead="This notice explains how Lexicon Revision collects and uses personal data when you sign in, access a collection, search past-paper material, ask a revision question, or contact us."
      meta={DOCUMENT_META}
    >
      <DocumentSection index={1} title="Controller and contact">
        <p>
          Lexicon Revision is operated by <strong>Jin Bai</strong>. Jin Bai is the controller for
          the personal data described in this notice.
        </p>
        <p>
          For privacy questions or requests, contact{" "}
          <a className="font-semibold text-claret hover:underline" href={`mailto:${PRIVACY_EMAIL}`}>
            {PRIVACY_EMAIL}
          </a>
          .
        </p>
      </DocumentSection>

      <DocumentSection index={2} title="Personal data collected">
        <p>
          We collect and process the categories of personal data below. Please do not include
          personal data, sensitive personal data, or private information about other people in study
          questions or search prompts.
        </p>
        <DefinitionList items={DATA_CATEGORIES} />
      </DocumentSection>

      <DocumentSection index={3} title="Purposes and lawful bases">
        <p>
          We process personal data only where we have a lawful basis. Where we rely on legitimate
          interests, those interests are running a secure, reliable, access-controlled revision
          service and protecting it from misuse.
        </p>
        <PurposeList items={PURPOSES} />
        <p>
          You can object to processing based on legitimate interests. We will consider the objection
          and stop processing unless there is a compelling reason to continue or the data is needed
          for legal claims.
        </p>
      </DocumentSection>

      <DocumentSection index={4} title="AI and source-grounded answers">
        <p>
          When you ask for an answer with sources, Lexicon Revision may process your question, the
          selected collection, filters, retrieved source snippets, and the generated response.
          Queries and retrieved source text may be sent to third-party AI or retrieval providers
          where needed to provide the feature.
        </p>
        <p>
          Voyage is used for embeddings and reranking. An OpenAI-compatible provider may be used for
          planning and answer generation. Generated answers are revision support, not official
          teaching material or guaranteed solutions; check the cited source material.
        </p>
      </DocumentSection>

      <DocumentSection index={5} title="Recipients and providers">
        <p>We do not sell personal data. We use service providers to operate Lexicon Revision:</p>
        <ProviderList items={PROVIDERS} />
      </DocumentSection>

      <DocumentSection index={6} title="International transfers">
        <p>
          Some providers may process personal data outside the UK. Where this happens, we rely on
          the provider's applicable transfer safeguards, such as adequacy arrangements, standard
          contractual clauses, the UK International Data Transfer Agreement, the UK Addendum, or
          equivalent safeguards where applicable.
        </p>
      </DocumentSection>

      <DocumentSection index={7} title="Retention">
        <p>We keep personal data only for as long as needed for the purposes in this notice.</p>
        <ul className="list-disc space-y-2 pl-5">
          {RETENTION_ITEMS.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <DocumentCallout label="No study history">
          <p>
            Lexicon Revision does not currently keep a user-facing study history. Normal usage logs
            are operational records and are not intended to store raw search or study questions.
          </p>
        </DocumentCallout>
      </DocumentSection>

      <DocumentSection index={8} title="Cookies and local storage">
        <p>
          Lexicon Revision uses essential cookies or browser storage for sign-in, session security,
          access control, and basic service operation. Production authentication is provided by
          Clerk.
        </p>
        <p>
          Local development and test builds may use stub authentication that stores an email address
          in session storage. That mode is not intended for production.
        </p>
        <p>
          No non-essential analytics or session-replay tracking is currently used. If that changes,
          this notice will be updated and consent will be requested where required.
        </p>
      </DocumentSection>

      <DocumentSection index={9} title="Collection requests and support">
        <p>
          Collection suggestions and general support may be handled through GitHub Issues or GitHub
          Discussions. Those channels are public. Do not post private information, sensitive
          personal data, or privacy requests there.
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <DocumentExternalLink href={PROJECT_ISSUES_URL}>GitHub Issues ↗</DocumentExternalLink>
          <DocumentExternalLink href={PROJECT_DISCUSSIONS_URL}>
            GitHub Discussions ↗
          </DocumentExternalLink>
        </div>
      </DocumentSection>

      <DocumentSection index={10} title="Your rights">
        <p>
          You may ask for access, correction, deletion, restriction, objection, or portability where
          those rights apply. You may also withdraw consent where processing is based on consent.
          These rights are not absolute and may depend on the lawful basis and circumstances of the
          processing.
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>Access: request a copy of the personal data held about you.</li>
          <li>Correction: ask for inaccurate or incomplete data to be corrected.</li>
          <li>Deletion: ask for data to be removed where the legal basis allows.</li>
          <li>Restriction or objection: limit how your data is processed.</li>
          <li>Portability: receive your data in a portable format where this applies.</li>
        </ul>
        <p>
          To make a request, contact{" "}
          <a className="font-semibold text-claret hover:underline" href={`mailto:${PRIVACY_EMAIL}`}>
            {PRIVACY_EMAIL}
          </a>
          .
        </p>
      </DocumentSection>

      <DocumentSection index={11} title="Complaints to the ICO">
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

      <DocumentSection index={12} title="Changes to this notice">
        <p>
          We may update this notice as the service changes. If there are significant changes to how
          personal data is used, we will update this page and, where appropriate, notify users
          before the new use begins.
        </p>
      </DocumentSection>
    </DocumentPage>
  );
}

function DefinitionList({ items }: { items: { label: string; text: string }[] }) {
  return (
    <dl className="space-y-3">
      {items.map((item) => (
        <div key={item.label}>
          <dt className="font-ui text-[11px] font-bold uppercase tracking-[0.14em] text-claret">
            {item.label}
          </dt>
          <dd className="mt-1">{item.text}</dd>
        </div>
      ))}
    </dl>
  );
}

function PurposeList({ items }: { items: { purpose: string; basis: string }[] }) {
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.purpose} className="rounded border border-rule bg-paper px-4 py-3">
          <div className="font-display font-semibold text-ink">{item.purpose}</div>
          <div className="mt-1 font-ui text-[12px] uppercase tracking-[0.08em] text-ink-muted">
            Lawful basis: <span className="font-semibold text-ink">{item.basis}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function ProviderList({ items }: { items: readonly (readonly [string, string])[] }) {
  return (
    <dl className="divide-y divide-rule rounded border border-rule bg-paper">
      {items.map(([provider, purpose]) => (
        <div key={provider} className="grid gap-1 px-4 py-3 sm:grid-cols-[180px_1fr]">
          <dt className="font-display font-semibold text-ink">{provider}</dt>
          <dd>{purpose}</dd>
        </div>
      ))}
    </dl>
  );
}
