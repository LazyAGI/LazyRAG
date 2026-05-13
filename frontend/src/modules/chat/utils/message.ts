import type { Query } from "@/api/generated/chatbot-client";

interface ChatUserMessageLike {
  delta?: string;
  inputs?: Query[] | null;
}

export function normalizeMessageInputs(
  inputs?: Query[] | null,
  fallbackText?: string,
): Query[] {
  const normalizedInputs = Array.isArray(inputs)
    ? inputs
        .filter((item): item is Query => !!item)
        .map((item) => ({ ...item }))
    : [];

  const trimmedFallbackText = fallbackText?.trim();
  const hasTextInput = normalizedInputs.some((item) => {
    const inputType = item.input_type || "text";
    return inputType === "text" && !!item.text?.trim();
  });

  if (!hasTextInput && trimmedFallbackText) {
    normalizedInputs.unshift({
      input_type: "text",
      text: fallbackText,
    });
  }

  return normalizedInputs;
}

export function getRegenerationInputs(
  userMessage?: ChatUserMessageLike,
): Query[] {
  if (!userMessage) {
    return [];
  }

  return normalizeMessageInputs(userMessage.inputs, userMessage.delta);
}
