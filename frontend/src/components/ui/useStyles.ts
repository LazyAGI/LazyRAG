import { useEffect, useState } from "react";

const styleRegistry = new Set<string>();

export const injectStyles = (styleId: string, css: string) => {
  const existingStyle = document.getElementById(styleId) as
    | HTMLStyleElement
    | null;

  if (existingStyle) {
    if (existingStyle.textContent !== css) {
      existingStyle.textContent = css;
    }
    styleRegistry.add(styleId);
    return;
  }

  const style = document.createElement("style");
  style.id = styleId;
  style.textContent = css;
  document.head.appendChild(style);
  styleRegistry.add(styleId);
};

export const useStyles = (styleId: string, css: string) => {
  const [, setInjected] = useState(false);
  useEffect(() => {
    injectStyles(styleId, css);
    setInjected(true);
  }, [styleId, css]);
};
