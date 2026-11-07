import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Profile, type ProfileUpdate } from "../../api/client";

export const PROFILE_QUERY_KEY = ["profile"] as const;

export function useProfile() {
  return useQuery<Profile>({
    queryKey: PROFILE_QUERY_KEY,
    queryFn: () => api.getProfile(),
    staleTime: 5 * 60 * 1000,
  });
}

/** PUT заменяет профиль целиком, поэтому тело собирается из текущих значений с нужными правками. */
export function toProfileUpdate(profile: Profile, changes: Partial<ProfileUpdate> = {}): ProfileUpdate {
  return {
    goal: profile.goal,
    height_cm: profile.height_cm,
    age: profile.age,
    sex: profile.sex,
    weight_unit: profile.weight_unit,
    theme: profile.theme,
    ...changes,
  };
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  const latest = useRef<ProfileUpdate | null>(null);
  return useMutation({
    mutationFn: (body: ProfileUpdate) => {
      latest.current = body;
      return api.updateProfile(body);
    },
    onSuccess: (profile, body) => {
      if (body !== latest.current) {
        return;
      }
      queryClient.setQueryData(PROFILE_QUERY_KEY, profile);
    },
  });
}
