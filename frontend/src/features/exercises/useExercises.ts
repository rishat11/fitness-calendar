import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Exercise, type ExerciseInput } from "../../api/client";

export const EXERCISES_QUERY_KEY = ["exercises"] as const;

type ExerciseFilters = { includeArchived: boolean; search: string };

export function useExercises({ includeArchived, search }: ExerciseFilters) {
  const q = search.trim() || undefined;
  return useQuery<Exercise[]>({
    queryKey: [...EXERCISES_QUERY_KEY, { includeArchived, q }],
    queryFn: () => api.listExercises({ includeArchived, q }),
    // При наборе в поиске не мигаем пустым списком между запросами.
    placeholderData: keepPreviousData,
  });
}

/** Любая запись меняет список и поиск, поэтому сбрасываем все варианты ключа. */
function useInvalidateExercises() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: EXERCISES_QUERY_KEY });
}

export function useCreateExercise() {
  const invalidate = useInvalidateExercises();
  return useMutation({
    mutationFn: (body: ExerciseInput) => api.createExercise(body),
    onSuccess: invalidate,
  });
}

export function useUpdateExercise() {
  const invalidate = useInvalidateExercises();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ExerciseInput }) =>
      api.updateExercise(id, body),
    onSuccess: invalidate,
  });
}

export function useArchiveExercise() {
  const invalidate = useInvalidateExercises();
  return useMutation({
    mutationFn: (id: string) => api.archiveExercise(id),
    onSuccess: invalidate,
  });
}

export function useRestoreExercise() {
  const invalidate = useInvalidateExercises();
  return useMutation({
    mutationFn: (id: string) => api.restoreExercise(id),
    onSuccess: invalidate,
  });
}

export function useDeleteExercise() {
  const invalidate = useInvalidateExercises();
  return useMutation({
    mutationFn: (id: string) => api.deleteExercise(id),
    onSuccess: invalidate,
  });
}
