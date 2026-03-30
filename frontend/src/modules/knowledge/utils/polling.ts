import { v4 as uuidV4 } from "uuid";

class Polling {
  private timeoutId: any = null; // setTimeout id

  private loopIds: string[] = [];

  
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

  public cancel = () => {
    clearTimeout(this.timeoutId);
    this.loopIds = [];
    this.timeoutId = null;
  };
}

export default Polling;
