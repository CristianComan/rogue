/**
 * ISO8601 duration <-> seconds. Pydantic's model_dump(mode="json") emits
 * timedelta as strings like "PT5S", "PT1H30M", "P2DT3H" — this only needs
 * to round-trip what Python's timedelta can actually produce (days, hours,
 * minutes, seconds, no months/years), never negative in this domain.
 */

const DURATION_PATTERN =
  /^P(?:(\d+)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$/;

export function durationToSeconds(duration: string): number {
  const match = DURATION_PATTERN.exec(duration);
  if (!match) {
    throw new Error(`Invalid ISO8601 duration: ${duration}`);
  }
  const [, days, hours, minutes, seconds] = match;
  return (
    Number(days ?? 0) * 86400 +
    Number(hours ?? 0) * 3600 +
    Number(minutes ?? 0) * 60 +
    Number(seconds ?? 0)
  );
}

export function secondsToDuration(totalSeconds: number): string {
  if (totalSeconds < 0) {
    throw new Error("secondsToDuration does not support negative durations");
  }
  if (totalSeconds === 0) return "PT0S";

  const days = Math.floor(totalSeconds / 86400);
  let remainder = totalSeconds - days * 86400;
  const hours = Math.floor(remainder / 3600);
  remainder -= hours * 3600;
  const minutes = Math.floor(remainder / 60);
  const seconds = remainder - minutes * 60;

  let result = "P";
  if (days > 0) result += `${days}D`;
  const hasTime = hours > 0 || minutes > 0 || seconds > 0;
  if (hasTime) {
    result += "T";
    if (hours > 0) result += `${hours}H`;
    if (minutes > 0) result += `${minutes}M`;
    if (seconds > 0) result += `${trimTrailingZeros(seconds)}S`;
  }
  return result;
}

function trimTrailingZeros(value: number): string {
  return Number(value.toFixed(6)).toString();
}
