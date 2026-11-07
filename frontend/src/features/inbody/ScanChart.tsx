const WIDTH = 640;
const HEIGHT = 180;
const LEFT = 48;
const RIGHT = 16;
const TOP = 16;
const BOTTOM = 36;
const PLOT_W = WIDTH - LEFT - RIGHT;
const PLOT_H = HEIGHT - TOP - BOTTOM;

type Point = { date: string; value: number };

function xAt(index: number, count: number): number {
  if (count <= 1) return LEFT + PLOT_W / 2;
  return LEFT + (index * PLOT_W) / (count - 1);
}

function yAt(value: number, min: number, max: number): number {
  const span = max - min || 1;
  return TOP + (1 - (value - min) / span) * PLOT_H;
}

function formatTick(value: number): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(value);
}

function shortDate(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${day}.${month}`;
}

function showDate(index: number, count: number): boolean {
  if (count <= 8) return true;
  return index === 0 || index === count - 1 || index % Math.ceil(count / 6) === 0;
}

/** Одна линия по датам замера. */
export function ScanChart({ title, points }: { title: string; points: Point[] }) {
  if (points.length === 0) return null;
  let min = Math.min(...points.map((point) => point.value));
  let max = Math.max(...points.map((point) => point.value));
  if (min === max) {
    const pad = min === 0 ? 1 : Math.abs(min) * 0.05;
    min -= pad;
    max += pad;
  }
  const placed = points.map((point, index) => ({
    ...point,
    x: xAt(index, points.length),
    y: yAt(point.value, min, max),
  }));
  const path = placed
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`)
    .join("");

  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="text-sm font-medium">{title}</figcaption>
      <svg
        role="img"
        aria-label={`${title}: ${points.length} замеров`}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full"
      >
        <text
          x={LEFT - 8}
          y={yAt(max, min, max)}
          textAnchor="end"
          dominantBaseline="middle"
          className="fill-slate-600 text-[11px] dark:fill-slate-300"
        >
          {formatTick(max)}
        </text>
        <text
          x={LEFT - 8}
          y={yAt(min, min, max)}
          textAnchor="end"
          dominantBaseline="middle"
          className="fill-slate-600 text-[11px] dark:fill-slate-300"
        >
          {formatTick(min)}
        </text>
        <path d={path} fill="none" strokeWidth={2} className="stroke-emerald-700 dark:stroke-emerald-400" />
        {placed.map((point, index) => (
          <circle
            key={`${point.date}-${index}`}
            cx={point.x}
            cy={point.y}
            r={3.5}
            className="fill-emerald-700 dark:fill-emerald-400"
          >
            <title>{`${point.date}: ${formatTick(point.value)}`}</title>
          </circle>
        ))}
        {placed.map((point, index) =>
          showDate(index, placed.length) ? (
            <text
              key={`date-${point.date}-${index}`}
              x={point.x}
              y={HEIGHT - 8}
              textAnchor="middle"
              className="fill-slate-600 text-[11px] dark:fill-slate-300"
            >
              {shortDate(point.date)}
            </text>
          ) : null,
        )}
      </svg>
    </figure>
  );
}
