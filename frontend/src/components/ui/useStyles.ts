import { useEffect, useState } from "react";

const styleRegistry = new Set<string>();

export const injectStyles = (styleId: string, css: string) => {
  if (styleRegistry.has(styleId) || document.getElementById(styleId)) return;
  const style = document.createElement("style");
  style.id = styleId;
  style.textContent = css;
  document.head.appendChild(style);
  styleRegistry.add(styleId);
};

export const useStyles = (styleId: string, css: string) => {
  const [, setInjected] = useState(false);
  useEffect(() => {
    if (!styleRegistry.has(styleId) && !document.getElementById(styleId)) {
      injectStyles(styleId, css);
      setInjected(true);
    }
  }, [styleId, css]);
};
