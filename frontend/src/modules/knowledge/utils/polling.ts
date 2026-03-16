import { v4 as uuidV4 } from "uuid";

class Polling {
  private timeoutId: any = null; // setTimeout id

  private loopIds: string[] = []; // 轮询中的任务id，用于判断请求是否已取消

  /**
   * 开始轮询
   * @param request Promise请求
   * @param interval 轮训间隔（毫秒）
   * @param onSuccess 请求成功的回调
   * @param onError 请求失败的回调
   */
  public start = (params: {
    interval: number;
    request: () => Promise<any>;
    onSuccess?: (res: any) => void;
    onError?: (err: any) => void;
  }) => {
    const { request, interval, onSuccess, onError } = params;
    const loop = (loopId: string) => {
      this.loopIds.push(loopId);
      request()
        .then((res) => {
          if (!this.loopIds.includes(loopId)) {
            return;
          }
          this.timeoutId = setTimeout(() => {
            loop(uuidV4());
          }, interval);
          onSuccess?.(res);
        })
        .catch((err) => {
          if (!this.loopIds.includes(loopId)) {
            return;
          }
          this.timeoutId = setTimeout(() => {
            loop(uuidV4());
          }, interval);
          onError?.(err);
        });
    };
    loop(uuidV4());
  };

  // 取消轮询
  public cancel = () => {
    clearTimeout(this.timeoutId);
    this.loopIds = [];
    this.timeoutId = null;
  };
}

export default Polling;
