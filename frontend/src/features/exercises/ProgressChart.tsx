import type { ExerciseHistoryBest } from "../../api/client";

export type ChartPoint = ExerciseHistoryBest & {
  date: string;
  startedAt: string;
};

const WIDTH = 640;
const HEIGHT = 220;
const LEFT = 52;
const RIGHT = 44;
const TOP = 16;
const BOTTOM = 32;
const PLOT_W = WIDTH - LEFT - RIGHT;
const PLOT_H = HEIGHT - TOP - BOTTOM;

type Scale = { min: number; max: number };

function range(values: number[]): Scale | null {
  if (values.length === 0) return null;
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    const pad = min === 0 ? 1 : Math.abs(min) * 0.15;
    min -= pad;
    max += pad;
  }
  return { min, max };
}

function xAt(index: number, count: number): number {
  if (count <= 1) return LEFT + PLOT_W / 2;
  return LEFT + (index * PLOT_W) / (count - 1);
}

function yAt(value: number, scale: Scale): number {
  const span = scale.max - scale.min;
  return TOP + (1 - (value - scale.min) / span) * PLOT_H;
}

function shortDate(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${day}.${month}`;
}

function formatTick(value: number): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(value);
}

/** Подписи — реальные значения, а не запас шкалы: у одной точки не появляется «13,8 повт.». */
function tickValues(values: number[]): number[] {
  const unique = [...new Set(values.map((value) => Math.round(value * 10) / 10))];
  unique.sort((a, b) => b - a);
  if (unique.length <= 3) return unique;
  return [unique[0], unique[Math.floor(unique.length / 2)], unique[unique.length - 1]];
}

function showDate(index: number, count: number): boolean {
  if (count <= 6) return true;
  if (index === 0 || index === count - 1) return true;
  return index % Math.ceil(count / 5) === 0;
}

function pathOf(points: { x: number; y: number | null }[]): string[] {
  const paths: string[] = [];
  let current = "";
  for (const point of points) {
    if (point.y == null) {
      if (current) paths.push(current);
      current = "";
      continue;
    }
    current += `${current ? "L" : "M"}${point.x.toFixed(1)},${point.y.toFixed(1)}`;
  }
  if (current) paths.push(current);
  return paths;
}

/** Один график по завершённым сессиям. Линия 1ПМ рисуется только там, где она посчитана. */
export function ProgressChart({ points }: { points: ChartPoint[] }) {
  const loads = points.flatMap((point) => (point.load == null ? [] : [point.load]));
  const epleys = points.flatMap((point) => (point.epley_1rm == null ? [] : [point.epley_1rm]));
  const weightScale = range([...loads, ...epleys]);
  const repsScale = range(points.map((point) => point.reps));
  if (!repsScale || points.length === 0) return null;

  const weightTicks = weightScale ? tickValues([...loads, ...epleys]) : [];
  const repsTicks = tickValues(points.map((point) => point.reps));
  const placed = points.map((point, index) => ({
    ...point,
    x: xAt(index, points.length),
    loadY: point.load == null || !weightScale ? null : yAt(point.load, weightScale),
    epleyY: point.epley_1rm == null || !weightScale ? null : yAt(point.epley_1rm, weightScale),
    repsY: yAt(point.reps, repsScale),
  }));
  const series = [
    loads.length > 0 ? "нагрузка" : null,
    "повторы",
    epleys.length > 0 ? "расчётный 1ПМ" : null,
  ].filter((name) => name != null);

  return (
    <figure className="flex flex-col gap-3">
      <svg
        role="img"
        aria-label={`График прогрессии: ${series.join(", ")}`}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full"
      >
        {weightTicks.map((tick) => (
          <text
            key={`w-${tick}`}
            x={LEFT - 8}
            y={yAt(tick, weightScale as Scale)}
            textAnchor="end"
            dominantBaseline="middle"
            className="fill-slate-600 text-[11px] dark:fill-slate-300"
          >
            {formatTick(tick)}
          </text>
        ))}
        {repsTicks.map((tick) => (
          <text
            key={`r-${tick}`}
            x={LEFT + PLOT_W + 8}
            y={yAt(tick, repsScale)}
            textAnchor="start"
            dominantBaseline="middle"
            className="fill-slate-600 text-[11px] dark:fill-slate-300"
          >
            {formatTick(tick)}
          </text>
        ))}
        {pathOf(placed.map((point) => ({ x: point.x, y: point.loadY }))).map((d) => (
          <path
            key={d}
            d={d}
            fill="none"
            strokeWidth={2}
            className="stroke-slate-800 dark:stroke-slate-100"
          />
        ))}
        {pathOf(placed.map((point) => ({ x: point.x, y: point.repsY }))).map((d) => (
          <path key={d} d={d} fill="none" strokeWidth={2} className="stroke-sky-700 dark:stroke-sky-300" />
        ))}
        {pathOf(placed.map((point) => ({ x: point.x, y: point.epleyY }))).map((d) => (
          <path
            key={`e-${d}`}
            d={d}
            fill="none"
            strokeWidth={2}
            strokeDasharray="5 4"
            className="stroke-amber-700 dark:stroke-amber-300"
          />
        ))}
        {placed.map((point, index) => (
          <g key={`${point.date}-${point.startedAt}-${index}`}>
            {point.loadY != null && (
              <circle cx={point.x} cy={point.loadY} r={3.5} className="fill-slate-800 dark:fill-slate-100" />
            )}
            <circle cx={point.x} cy={point.repsY} r={3.5} className="fill-sky-700 dark:fill-sky-300" />
            {point.epleyY != null && (
              <circle cx={point.x} cy={point.epleyY} r={3.5} className="fill-amber-700 dark:fill-amber-300" />
            )}
            {showDate(index, placed.length) && (
              <text
                x={point.x}
                y={TOP + PLOT_H + 18}
                textAnchor="middle"
                className="fill-slate-600 text-[11px] dark:fill-slate-300"
              >
                {shortDate(point.date)}
              </text>
            )}
          </g>
        ))}
      </svg>
      <ul className="flex flex-wrap gap-x-4 gap-y-2 text-sm text-slate-600 dark:text-slate-300">
        {loads.length > 0 && (
          <li className="flex items-center gap-2">
            <span className="inline-block h-0.5 w-6 bg-slate-800 dark:bg-slate-100" />
            Нагрузка
          </li>
        )}
        <li className="flex items-center gap-2">
          <span className="inline-block h-0.5 w-6 bg-sky-700 dark:bg-sky-300" />
          Повторы
        </li>
        {epleys.length > 0 && (
          <li className="flex items-center gap-2">
            <span className="inline-block h-0.5 w-6 border-b-2 border-dashed border-amber-700 dark:border-amber-300" />
            Расчётный 1ПМ
          </li>
        )}
      </ul>
      {epleys.length > 0 && (
        <figcaption className="text-sm text-slate-600 dark:text-slate-300">
          Расчётный 1ПМ по формуле Эпли. Это не цель.
        </figcaption>
      )}
    </figure>
  );
}
