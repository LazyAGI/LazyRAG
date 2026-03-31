import useElapsedTime from "@/modules/knowledge/hooks/useElapsedTime";
import TimeUtils from "@/modules/knowledge/utils/time";

interface IProps {
  startTime?: number | string;
  endTime?: number | string; // No endTime means the task is not completed yet.
}

const ElapsedTime = (props: IProps) => {
  const { startTime, endTime } = props;
  const result = useElapsedTime({ startTime, endTime });

  return (
    <>
      {[
        TimeUtils.padZero(result.days * 24 + result.hours),
        TimeUtils.padZero(result.minutes),
        TimeUtils.padZero(result.seconds),
      ].join(":")}
    </>
  );
};

export default ElapsedTime;
