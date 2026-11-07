import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";

export const RECOMMENDATIONS_QUERY_KEY = ["recommendations"] as const;

export function useRecommendations() {
  return useQuery({
    queryKey: RECOMMENDATIONS_QUERY_KEY,
    queryFn: () => api.getRecommendations(),
  });
}
