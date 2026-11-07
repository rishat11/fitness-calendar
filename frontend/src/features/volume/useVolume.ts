import { useQuery } from "@tanstack/react-query";
import { api, type MuscleVolume } from "../../api/client";

export const VOLUME_QUERY_KEY = ["volume"] as const;

/** Неделя по понедельнику: API принимает любую дату недели, ключ кэша — одну на неделю. */
export function useMuscleVolume(weekStart: string) {
  return useQuery<MuscleVolume>({
    queryKey: [...VOLUME_QUERY_KEY, "muscles", weekStart],
    queryFn: () => api.muscleVolume(weekStart),
  });
}
