import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, type ProgressionDecisionResult, type ProgressionHint } from "../../api/client";
import { WEEK_TYPE_LABELS } from "../blocks/draft";

const buttonClass =
  "min-h-11 rounded-lg px-4 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800";
const primaryButtonClass =
  "min-h-11 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300";

function formatWeight(value: number, unit: ProgressionHint["weight_unit"]): string {
  const number = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value);
  if (unit === "kg") return `${number} кг`;
  if (unit === "lb") return `${number} lb`;
  return number;
}

export function ProgressionHintCard({
  exerciseId,
  performedId,
  onApplied,
}: {
  exerciseId: string | null;
  performedId?: string;
  onApplied?: (result: ProgressionDecisionResult) => void;
}) {
  const queryClient = useQueryClient();
  const hint = useQuery({
    queryKey: ["progression", exerciseId],
    queryFn: () => api.progressionHint(exerciseId ?? ""),
    enabled: exerciseId != null,
    retry: (count, error) => error instanceof ApiError && error.status >= 500 && count < 2,
  });
  const decision = useMutation({
    mutationFn: (action: "accept" | "reject") =>
      api.decideProgression(exerciseId ?? "", action, performedId),
    onSuccess: async (result) => {
      if (result.action === "accept") onApplied?.(result);
      await queryClient.invalidateQueries({ queryKey: ["progression", exerciseId] });
    },
  });

  if (!hint.data) return null;

  const weekType = hint.data.week_type ? WEEK_TYPE_LABELS[hint.data.week_type] : null;

  return (
    <aside
      role="region"
      aria-label="Подсказка по прогрессии"
      className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900"
    >
      {weekType && (
        <p className="text-sm text-slate-600 dark:text-slate-300">Тип недели: {weekType}</p>
      )}
      <p>{hint.data.message}</p>
      {hint.data.suggested_weight != null && (
        <p>Предлагаемый вес: {formatWeight(hint.data.suggested_weight, hint.data.weight_unit)}</p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={primaryButtonClass}
          disabled={decision.isPending}
          onClick={() => decision.mutate("accept")}
        >
          Принять
        </button>
        <button
          type="button"
          className={buttonClass}
          disabled={decision.isPending}
          onClick={() => decision.mutate("reject")}
        >
          Отклонить
        </button>
      </div>
      {decision.isError && (
        <p role="alert" className="text-sm text-red-600">
          {decision.error.message}
        </p>
      )}
    </aside>
  );
}
