import moment from "moment";
import { useEffect, useRef, useState } from "react";

interface IProps {
  startTime?: number | string;
  endTime?: number | string;
}

interface IResult {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
}

const useElapsedTime = (props: IProps) => {
  const [result, setResult] = useState<IResult>({
    days: 0,
    hours: 0,
    minutes: 0,
    seconds: 0,
  });
  const timeoutRef = useRef<any>(null);
  const { startTime, endTime } = props;
  useEffect(() => {
    updateTime();
    return () => {
      clearTimeout(timeoutRef.current);
    };
  }, [startTime, endTime]);

  const updateTime = () => {
    if (!startTime) {
      return;
    }
    const duration = moment.duration(
      (moment(endTime).unix() - moment(startTime).unix()) * 1000,
    );
    const days = duration.days();
    const hours = duration.hours() + days * 24;
    const minutes = duration.minutes();
    const seconds = duration.seconds();
    setResult(formatTime({ days, hours, minutes, seconds }));

    if (!endTime) {
      timeoutRef.current = setTimeout(() => {
        updateTime();
      }, 1000);
    }
  };

  const formatTime = (obj: IResult) => {
    const newResult = {} as IResult;
    Object.entries(obj).map(([key, value]) => {
      newResult[key as keyof IResult] = value >= 0 ? value : 0;
    });
    return newResult;
  };

  return result;
};

export default useElapsedTime;
