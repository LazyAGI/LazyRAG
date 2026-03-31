class TimeUtils {
  
  public static padZero = (num: number, digit = 2) => {
    if (!Number(num) || num < 0) {
      return "0".repeat(digit);
    }

    const numStr = num.toString();
    if (numStr.length < digit) {
      return "0".repeat(digit - numStr.length) + numStr;
    }

    return numStr;
  };
}

export default TimeUtils;
