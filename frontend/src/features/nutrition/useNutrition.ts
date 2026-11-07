import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type NutritionIntakeUpdate } from "../../api/client";

export const NUTRITION_INTAKE_QUERY_KEY = ["nutrition", "intake"] as const;
export const NUTRITION_TARGET_QUERY_KEY = ["nutrition", "target"] as const;

export function useNutritionIntake() {
  return useQuery({
    queryKey: NUTRITION_INTAKE_QUERY_KEY,
    queryFn: () => api.getNutritionIntake(),
  });
}

export function useNutritionTarget() {
  return useQuery({
    queryKey: NUTRITION_TARGET_QUERY_KEY,
    queryFn: () => api.getNutritionTarget(),
  });
}

export function useUpdateNutritionIntake() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: NutritionIntakeUpdate) => api.updateNutritionIntake(body),
    onSuccess: (intake) => {
      queryClient.setQueryData(NUTRITION_INTAKE_QUERY_KEY, intake);
    },
  });
}
