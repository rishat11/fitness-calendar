import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type PlanCycleCreate,
  type PlanEntry,
  type PlanEntryCreate,
  type PlanEntryUpdate,
  type PlanShiftRequest,
  type TodayView,
} from "../../api/client";

export const PLAN_QUERY_KEY = ["plan"] as const;

/** План на календарный день вместе с состоянием лога: не начат, открыт, завершён. */
export function useToday(day: string) {
  return useQuery<TodayView>({
    queryKey: [...PLAN_QUERY_KEY, "today", day],
    queryFn: () => api.today(day),
  });
}

/** Записи плана за диапазон дат (включительно). Предыдущий месяц остаётся на экране при переключении. */
export function usePlanRange(start: string, end: string) {
  return useQuery<PlanEntry[]>({
    queryKey: [...PLAN_QUERY_KEY, "range", start, end],
    queryFn: () => api.listPlan(start, end),
    placeholderData: keepPreviousData,
  });
}

/** Любая запись меняет все загруженные диапазоны, поэтому сбрасываем весь раздел плана. */
function useInvalidatePlan() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: PLAN_QUERY_KEY });
}

export function useAddPlanEntry() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: (body: PlanEntryCreate) => api.addPlanEntry(body),
    onSuccess: invalidate,
  });
}

export function useAddPlanCycle() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: (body: PlanCycleCreate) => api.addPlanCycle(body),
    onSuccess: invalidate,
  });
}

export function useUpdatePlanEntry() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: PlanEntryUpdate }) =>
      api.updatePlanEntry(id, body),
    onSuccess: invalidate,
  });
}

export function useDeletePlanEntry() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: (id: string) => api.deletePlanEntry(id),
    onSuccess: invalidate,
  });
}

export function usePlanShiftHistory() {
  return useQuery({
    queryKey: [...PLAN_QUERY_KEY, "history"],
    queryFn: () => api.planShiftHistory(),
  });
}

export function usePreviewPlanShift() {
  return useMutation({
    mutationFn: (body: PlanShiftRequest) => api.previewPlanShift(body),
  });
}

export function useApplyPlanShift() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    // Ключ нужен родителю: карточка записи размонтируется сразу после сдвига,
    // и её собственный onSuccess может не успеть показать тост.
    mutationKey: ["plan", "shift", "apply"],
    mutationFn: (body: PlanShiftRequest) => api.applyPlanShift(body),
    onSuccess: invalidate,
  });
}

export function useUndoPlanShift() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: () => api.undoPlanShift(),
    onSuccess: invalidate,
  });
}
