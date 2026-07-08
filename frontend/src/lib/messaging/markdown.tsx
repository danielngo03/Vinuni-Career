import { Fragment, type ReactNode } from "react";

/**
 * Sanitized markdown-lite renderer for message bodies (ADR-0012: "markdown-lite,
 * sanitized on render; no raw HTML"). Output is built entirely from React
 * elements and text nodes — React escapes every text node, so NO raw HTML can
 * ever be injected. We never use `dangerouslySetInnerHTML`.
 *
 * Supported, intentionally minimal:
 * - line breaks (each newline → a real break),
 * - `**bold**`, `*italic*` / `_italic_`, `` `code` ``,
 * - bare `https://` / `http://` autolinks (validated scheme; `rel=noopener`).
 *
 * Anything else renders as literal, escaped text.
 */

const URL_RE = /(https?:\/\/[^\s<>()]+[^\s<>().,!?;:'"])/g;

type Token =
  | { t: "text"; v: string }
  | { t: "bold"; v: string }
  | { t: "italic"; v: string }
  | { t: "code"; v: string };

/** Tokenize one line into emphasis/code/text runs (non-nesting, left-to-right). */
function tokenizeLine(line: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  let buf = "";
  const flush = () => {
    if (buf) {
      tokens.push({ t: "text", v: buf });
      buf = "";
    }
  };
  while (i < line.length) {
    if (line.startsWith("**", i)) {
      const end = line.indexOf("**", i + 2);
      if (end > i + 1) {
        flush();
        tokens.push({ t: "bold", v: line.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }
    const ch = line[i];
    if (ch === "`") {
      const end = line.indexOf("`", i + 1);
      if (end > i) {
        flush();
        tokens.push({ t: "code", v: line.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    if (ch === "*" || ch === "_") {
      const end = line.indexOf(ch, i + 1);
      if (end > i + 1) {
        flush();
        tokens.push({ t: "italic", v: line.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    buf += ch;
    i += 1;
  }
  flush();
  return tokens;
}

/** Split a plain string into literal text + validated autolink anchors. */
function renderTextWithLinks(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = [];
  const parts = text.split(URL_RE);
  parts.forEach((part, idx) => {
    if (!part) return;
    if (URL_RE.test(part)) {
      // Reset lastIndex (URL_RE is global) and re-validate the scheme.
      URL_RE.lastIndex = 0;
      out.push(
        <a
          key={`${keyBase}-l${idx}`}
          href={part}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="break-all underline decoration-[var(--brand-primary)]/40 underline-offset-2 hover:decoration-[var(--brand-primary)]"
        >
          {part}
        </a>,
      );
    } else {
      URL_RE.lastIndex = 0;
      out.push(<Fragment key={`${keyBase}-t${idx}`}>{part}</Fragment>);
    }
  });
  return out;
}

/** Render markdown-lite `body` as safe React nodes (no raw HTML). */
export function renderMessageBody(body: string): ReactNode {
  const lines = body.replace(/\r\n/g, "\n").split("\n");
  return lines.map((line, li) => {
    const tokens = tokenizeLine(line);
    const rendered = tokens.map((tok, ti) => {
      const key = `${li}-${ti}`;
      switch (tok.t) {
        case "bold":
          return (
            <strong key={key} className="font-semibold">
              {renderTextWithLinks(tok.v, key)}
            </strong>
          );
        case "italic":
          return <em key={key}>{renderTextWithLinks(tok.v, key)}</em>;
        case "code":
          return (
            <code
              key={key}
              className="rounded bg-[var(--bg-muted)] px-1 py-0.5 font-mono text-[0.85em]"
            >
              {tok.v}
            </code>
          );
        default:
          return (
            <Fragment key={key}>{renderTextWithLinks(tok.v, key)}</Fragment>
          );
      }
    });
    return (
      <Fragment key={li}>
        {li > 0 && <br />}
        {rendered}
      </Fragment>
    );
  });
}
