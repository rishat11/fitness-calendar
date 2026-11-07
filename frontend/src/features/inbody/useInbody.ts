import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type InbodyScanInput } from "../../api/client";

export const INBODY_QUERY_KEY = ["inbody"] as const;

export function useInbodyScans() {
  return useQuery({
    queryKey: INBODY_QUERY_KEY,
    queryFn: () => api.listInbody(),
  });
}

export function useCreateInbody() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: InbodyScanInput) => api.createInbody(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: INBODY_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: ["nutrition", "target"] });
      void queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}

export function useUpdateInbody() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: InbodyScanInput }) => api.updateInbody(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: INBODY_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: ["nutrition", "target"] });
      void queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}

export function useDeleteInbody() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteInbody(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: INBODY_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: ["nutrition", "target"] });
      void queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}
