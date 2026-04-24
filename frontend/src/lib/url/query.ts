export function truncateExcerpt(text: string, max = 160): string {
  if (text.length <= max) {
    return text;
  }

  return `${text.slice(0, max - 1).trimEnd()}…`;
}
