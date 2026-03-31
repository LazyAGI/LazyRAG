import { useEffect, useMemo, useState, useRef } from "react";
import Prism from "prismjs";
import "prismjs/themes/prism.css";
import "prismjs/components/prism-markup";

interface RenderHtmlProps {
  fileData: ArrayBuffer;
  content: string | null;
}

const scheduleIdle = (fn: () => void) => {
  const ric = window as unknown as {
    requestIdleCallback?: (
      cb: IdleRequestCallback,
      opts?: { timeout?: number },
    ) => number;
  };
  if (typeof ric.requestIdleCallback === "function") {
    ric.requestIdleCallback(fn, { timeout: 50 });
  } else {
    setTimeout(fn, 0);
  }
};

const RenderHtml = ({ fileData, content }: RenderHtmlProps) => {
  const contentText = useMemo(() => content || "", [content]);
  const [originalText, setOriginalText] = useState("");
  const codeRef = useRef<HTMLElement | null>(null);
  const runIdRef = useRef(0);
  const baseHtmlRef = useRef("");
  const lastRenderedTextRef = useRef("");
  const debounceRef = useRef<number | null>(null);

  useEffect(() => {
    if (fileData) {
      setOriginalText(new TextDecoder().decode(fileData));
    }
  }, [fileData]);

  useEffect(() => {
    const root = codeRef.current;
    if (!originalText || !root) {
      baseHtmlRef.current = "";
      return;
    }

    if (lastRenderedTextRef.current === originalText && baseHtmlRef.current) {
      if (
        codeRef.current &&
        codeRef.current.innerHTML !== baseHtmlRef.current
      ) {
        codeRef.current.innerHTML = baseHtmlRef.current;
      }
      return;
    }

    runIdRef.current += 1;
    const id = runIdRef.current;
    root.textContent = originalText;

    scheduleIdle(() => {
      if (runIdRef.current !== id) {
        return;
      }

      try {
        const highlighted = Prism.highlight(
          originalText,
          Prism.languages.markup,
          "markup",
        );
        baseHtmlRef.current = highlighted;
        if (codeRef.current && runIdRef.current === id) {
          codeRef.current.innerHTML = highlighted;
        }
        lastRenderedTextRef.current = originalText;
      } catch (err) {
        void err;
        const escaped = originalText
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;");
        baseHtmlRef.current = escaped;
        if (codeRef.current) {
          codeRef.current.textContent = escaped;
        }
        lastRenderedTextRef.current = originalText;
      }
    });

    return () => {
      runIdRef.current += 1;
    };
  }, [originalText]);

  const restoreBase = (root: HTMLElement) => {
    if (!root) {
      return;
    }
    if (baseHtmlRef.current) {
      root.innerHTML = baseHtmlRef.current;
      return;
    }
    const marks = root.querySelectorAll("mark.keyword");
    marks.forEach((m) => {
      const p = m.parentNode;
      if (p) {
        p.replaceChild(document.createTextNode(m.textContent || ""), m);
        p.normalize();
      }
    });
  };

  useEffect(() => {
    if (debounceRef.current !== null) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }

    const delay = 50;
    debounceRef.current = window.setTimeout(() => {
      runIdRef.current += 1;
      const id = runIdRef.current;
      const root = codeRef.current;

      if (!root) {
        return;
      }

      if (!contentText || contentText.length === 0) {
        return;
      }

      restoreBase(root);

      const nodes: { node: Text; start: number; end: number }[] = [];
      let full = "";
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        if (runIdRef.current !== id) {
          return;
        }
        const n = walker.currentNode as Text;
        const s = full.length;
        const t = n.nodeValue || "";
        full += t;
        nodes.push({ node: n, start: s, end: full.length });
      }

      const esc = contentText.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&");
      const re = new RegExp(esc, "gi");
      const matches: { start: number; end: number }[] = [];
      const MAX = 100;
      let m;
      while ((m = re.exec(full)) !== null && matches.length < MAX) {
        matches.push({ start: m.index, end: m.index + m[0].length });
        if (m.index === re.lastIndex) {
          re.lastIndex++;
        }
      }

      for (let i = matches.length - 1; i >= 0; i--) {
        if (runIdRef.current !== id) {
          return;
        }
        const { start: ms, end: me } = matches[i];
        for (const { node, start, end } of nodes) {
          if (runIdRef.current !== id) {
            return;
          }
          if (end <= ms || start >= me) {
            continue;
          }
          const text = node.nodeValue || "";
          const a = Math.max(0, ms - start);
          const b = Math.min(text.length, me - start);
          if (a >= b) {
            continue;
          }
          const before = text.slice(0, a);
          const hit = text.slice(a, b);
          const after = text.slice(b);
          const p = node.parentNode;
          if (!p) {
            continue;
          }
          p.insertBefore(document.createTextNode(before), node);
          const mark = document.createElement("mark");
          mark.className = "keyword";
          mark.style.backgroundColor = "yellow";
          mark.textContent = hit;
          p.insertBefore(mark, node);
          p.insertBefore(document.createTextNode(after), node);
          p.removeChild(node);
        }
      }

      requestAnimationFrame(() => {
        const now = codeRef.current;
        if (!now) {
          return;
        }
        const kws = now.querySelectorAll(".keyword");
        if (kws.length) {
          (kws[0] as HTMLElement).scrollIntoView({
            behavior: "smooth",
            block: "center",
          });
        }
      });
    }, delay);

    return () => {
      runIdRef.current += 1;
      if (debounceRef.current !== null) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    };
  }, [contentText]);

  return (
    <div
      style={{
        padding: "16px",
        overflow: "auto",
        height: "calc(100vh - 220px)",
        border: "1px solid #eee",
      }}
    >
      <pre
        className="!m-0"
        style={{
          whiteSpace: "pre-wrap",
          overflowWrap: "anywhere",
          wordBreak: "break-word",
          overflowX: "auto",
        }}
      >
        <code
          ref={codeRef}
          className="language-markup"
          style={{
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            hyphens: "auto",
            display: "block",
          }}
        />
      </pre>
    </div>
  );
};

export default RenderHtml;
