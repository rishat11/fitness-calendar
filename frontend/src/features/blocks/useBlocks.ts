import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Block, type BlockInput, type BlockPlacement } from "../../api/client";
import { PLAN_QUERY_KEY } from "../plan/usePlan";

export const BLOCKS_QUERY_KEY = ["blocks"] as const;

export function useBlocks() {
  return useQuery<Block[]>({
    queryKey: [...BLOCKS_QUERY_KEY, "list"],
    queryFn: () => api.listBlocks(),
  });
}

export function useBlockPlacements() {
  return useQuery<BlockPlacement[]>({
    queryKey: [...BLOCKS_QUERY_KEY, "placements"],
    queryFn: () => api.listBlockPlacements(),
  });
}

function useInvalidateBlocks() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: BLOCKS_QUERY_KEY });
}

export function useCreateBlock() {
  const invalidate = useInvalidateBlocks();
  return useMutation({
    mutationFn: (body: BlockInput) => api.createBlock(body),
    onSuccess: invalidate,
  });
}

export function useUpdateBlock() {
  const invalidate = useInvalidateBlocks();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: BlockInput }) => api.updateBlock(id, body),
    onSuccess: invalidate,
  });
}

export function useCopyBlock() {
  const invalidate = useInvalidateBlocks();
  return useMutation({
    mutationFn: (id: string) => api.copyBlock(id),
    onSuccess: invalidate,
  });
}

export function useDeleteBlock() {
  const invalidate = useInvalidateBlocks();
  return useMutation({
    mutationFn: (id: string) => api.deleteBlock(id),
    onSuccess: invalidate,
  });
}

/** Применение создаёт тренировки в календаре, поэтому сбрасываем и план. */
export function useApplyBlock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      startDate,
      repeats,
    }: {
      id: string;
      startDate: string;
      repeats: boolean;
    }) => api.applyBlock(id, startDate, repeats),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BLOCKS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: PLAN_QUERY_KEY });
    },
  });
}

export function useRepeatPlacement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.repeatBlockPlacement(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BLOCKS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: PLAN_QUERY_KEY });
    },
  });
}

export function useRemoveBlockPlacement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.removeBlockPlacement(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BLOCKS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: PLAN_QUERY_KEY });
    },
  });
}

export function useDeloadSuggestion(placementId: string) {
  return useQuery({
    queryKey: [...BLOCKS_QUERY_KEY, "deload", placementId],
    queryFn: () => api.deloadSuggestion(placementId),
  });
}

/** Принятие меняет неделю в календаре, поэтому сбрасываем и план. */
export function useAcceptDeload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (placementId: string) => api.acceptDeload(placementId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BLOCKS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: PLAN_QUERY_KEY });
    },
  });
}
