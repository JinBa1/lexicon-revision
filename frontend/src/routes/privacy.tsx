const sections = [
  {
    heading: "Controller and contact",
    body: "Controller/contact placeholder. Replace this with the public project identity and contact address before launch.",
  },
  {
    heading: "Personal data collected",
    body: "Sign-in identity and email, university/community affiliation, access-control records, search and study requests, and operational request logs.",
  },
  {
    heading: "Purposes and lawful bases",
    body: "Authentication, access control, answering user requests, service security, debugging, rate limiting, and operating-cost control. Replace this scaffold with the final lawful-basis wording before launch.",
  },
  {
    heading: "Retention",
    body: "Account and access records are kept while needed for access control. Operational logs are kept only while needed for security, debugging, and service operation. Replace with final retention criteria before launch.",
  },
  {
    heading: "Recipients and providers",
    body: "Personal data may be processed by provider categories used for authentication, hosting, database/storage, rate limiting, AI/retrieval APIs, and operational infrastructure.",
  },
  {
    heading: "Your rights",
    body: "You may ask for access, correction, deletion, restriction, objection, or portability where those rights apply.",
  },
];

export function PrivacyRoute() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16 font-body text-ink">
      <div className="section-eyebrow">Launch scaffold</div>
      <h1 className="mt-2 font-display text-3xl font-semibold">Privacy notice</h1>
      <p className="mt-4 max-w-2xl text-sm leading-6 text-ink-muted">
        This page is a minimum UK privacy-notice scaffold for the current service. Edit the
        placeholders before public launch.
      </p>

      <div className="mt-10 space-y-7">
        {sections.map((section) => (
          <section key={section.heading}>
            <h2 className="font-display text-xl font-semibold">{section.heading}</h2>
            <p className="mt-2 text-sm leading-6 text-ink-muted">{section.body}</p>
          </section>
        ))}

        <section>
          <h2 className="font-display text-xl font-semibold">ICO complaint route</h2>
          <p className="mt-2 text-sm leading-6 text-ink-muted">
            You can complain to the UK Information Commissioner's Office if you are unhappy with how
            your personal data is handled.
          </p>
          <a
            href="https://ico.org.uk/make-a-complaint/data-protection-complaints/data-protection-complaints/"
            className="mt-3 inline-block font-display text-sm text-claret hover:underline"
            rel="noreferrer"
            target="_blank"
          >
            Contact the ICO
          </a>
        </section>
      </div>
    </main>
  );
}
