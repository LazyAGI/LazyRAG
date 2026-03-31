import { isObject } from "lodash";

class UIUtils {
  public static jsonParser = (content: unknown, defaultValue = {}) => {
    try {
      if (typeof content === "string") {
        return JSON.parse(content);
      }
      return isObject(content) ? content : defaultValue;
    } catch {
      return defaultValue;
    }
  };

  // Determines whether to scroll to the bottom, compatible with some browsers where scrollTop is a decimal.
  public static isReachBottom = (element: HTMLElement) => {
    if (!element) {
      return false;
    }
    const { scrollTop, clientHeight, scrollHeight } = element;
    return scrollTop > 0 && scrollTop + clientHeight + 2 > scrollHeight;
  };
}
export default UIUtils;
