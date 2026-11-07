import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Workout, type WorkoutInput } from "../../api/client";

export const WORKOUTS_QUERY_KEY = ["workouts"] as const;

export function useWorkouts() {
  return useQuery<Workout[]>({
    queryKey: [...WORKOUTS_QUERY_KEY, "list"],
    queryFn: () => api.listWorkouts(),
  });
}

export function useWorkout(id: string) {
  return useQuery<Workout>({
    queryKey: [...WORKOUTS_QUERY_KEY, "detail", id],
    queryFn: () => api.getWorkout(id),
  });
}

/** Любая запись меняет и список, и карточку, поэтому сбрасываем весь раздел. */
function useInvalidateWorkouts() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: WORKOUTS_QUERY_KEY });
}

export function useCreateWorkout() {
  const invalidate = useInvalidateWorkouts();
  return useMutation({
    mutationFn: (body: WorkoutInput) => api.createWorkout(body),
    onSuccess: invalidate,
  });
}

export function useUpdateWorkout() {
  const invalidate = useInvalidateWorkouts();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: WorkoutInput }) => api.updateWorkout(id, body),
    onSuccess: invalidate,
  });
}

export function useRenameWorkout() {
  const invalidate = useInvalidateWorkouts();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => api.renameWorkout(id, name),
    onSuccess: invalidate,
  });
}

export function useCopyWorkout() {
  const invalidate = useInvalidateWorkouts();
  return useMutation({
    mutationFn: (id: string) => api.copyWorkout(id),
    onSuccess: invalidate,
  });
}

export function useDeleteWorkout() {
  const invalidate = useInvalidateWorkouts();
  return useMutation({
    mutationFn: (id: string) => api.deleteWorkout(id),
    onSuccess: invalidate,
  });
}
