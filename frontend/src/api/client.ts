import type { components } from "./schema";

export type User = {
  id: string;
  email: string;
  created_at: string;
};

export type Profile = components["schemas"]["ProfileResponse"];
export type ProfileUpdate = components["schemas"]["ProfileUpdate"];
export type Exercise = components["schemas"]["ExerciseResponse"];
export type ExerciseInput = components["schemas"]["ExerciseInput"];
export type ExerciseHistory = components["schemas"]["ExerciseHistory"];
export type ExerciseHistorySession = components["schemas"]["ExerciseHistorySession"];
export type ExerciseHistorySet = components["schemas"]["ExerciseHistorySet"];
export type ExerciseHistoryBest = components["schemas"]["ExerciseHistoryBest"];

export type MuscleVolume = components["schemas"]["VolumeWeekResponse"];
export type MuscleVolumeGroup = components["schemas"]["MuscleVolumeGroup"];

export type Workout = components["schemas"]["WorkoutTemplateResponse"];
export type WorkoutInput = components["schemas"]["WorkoutTemplateInput"];
export type WorkoutItemInput = components["schemas"]["WorkoutItemInput"];
export type WorkoutSetInput = components["schemas"]["WorkoutSetInput"];

export type PlanEntry = components["schemas"]["PlanEntryResponse"];
export type PlanEntryCreate = components["schemas"]["PlanEntryCreate"];
export type PlanEntryUpdate = components["schemas"]["PlanEntryUpdate"];
export type PlanCycleCreate = components["schemas"]["PlanCycleCreate"];
export type PlanShiftRequest = components["schemas"]["PlanShiftRequest"];
export type PlanShiftPreview = components["schemas"]["PlanShiftPreview"];
export type PlanShiftResult = components["schemas"]["PlanShiftResult"];
export type PlanShiftChange = components["schemas"]["PlanShiftChange"];
export type PlanChangeLogItem = components["schemas"]["PlanChangeLogItem"];
export type TodayView = components["schemas"]["TodayResponse"];
export type TodayEntry = components["schemas"]["TodayEntryResponse"];

export type Block = components["schemas"]["BlockResponse"];
export type BlockInput = components["schemas"]["BlockInput"];
export type BlockWeekInput = components["schemas"]["BlockWeekInput"];
export type BlockScheduleInput = components["schemas"]["BlockScheduleInput"];
export type BlockPlacement = components["schemas"]["PlacementResponse"];
export type DeloadSuggestion = components["schemas"]["DeloadSuggestionResponse"];
export type DeloadAccept = components["schemas"]["DeloadAcceptResponse"];

export type PerformedWorkout = components["schemas"]["PerformedWorkoutResponse"];
export type PerformedItem = components["schemas"]["PerformedItemResponse"];
export type SetLog = components["schemas"]["SetLogResponse"];
export type SetWrite = components["schemas"]["SetWrite"];
export type SetCreate = components["schemas"]["SetCreate"];
export type PreviousSets = components["schemas"]["PreviousSets"];
export type ProgressionHint = components["schemas"]["ProgressionHintResponse"];
export type ProgressionDecisionResult = components["schemas"]["ProgressionDecisionResult"];
export type ExportDocument = components["schemas"]["ExportDocument"];
export type ImportResult = components["schemas"]["ImportResult"];

export type ExerciseListParams = {
  includeArchived?: boolean;
  q?: string;
};

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const DEFAULT_ERROR = "Не удалось выполнить запрос. Попробуйте ещё раз.";
const VALIDATION_ERROR = "Проверьте правильность введённых данных";

export function sendJson(path: string, method: string, body: unknown): Promise<unknown> {
  return request(path, {
    method,
    body: body == null ? undefined : JSON.stringify(body),
  });
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, { ...init, headers, credentials: "include" });

  if (response.status === 204) {
    return undefined as T;
  }

  const data: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const detail =
      typeof data === "object" && data !== null && "detail" in data ? data.detail : null;
    let message = DEFAULT_ERROR;
    if (typeof detail === "string") {
      message = detail;
    } else if (response.status === 422) {
      message = VALIDATION_ERROR;
    }
    throw new ApiError(response.status, message);
  }

  return data as T;
}

export const api = {
  getMe: () => request<User>("/api/auth/me"),

  login: (email: string, password: string) =>
    request<User>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string) =>
    request<User>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  logout: () => request<void>("/api/auth/logout", { method: "POST" }),

  deleteAccount: (password: string) =>
    request<void>("/api/auth/account", {
      method: "DELETE",
      body: JSON.stringify({ password }),
    }),

  getProfile: () => request<Profile>("/api/profile"),

  updateProfile: (body: ProfileUpdate) =>
    request<Profile>("/api/profile", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  getExercise: (id: string) => request<Exercise>(`/api/exercises/${id}`),

  exerciseHistory: (id: string) => request<ExerciseHistory>(`/api/exercises/${id}/history`),

  listExercises: ({ includeArchived = false, q }: ExerciseListParams = {}) => {
    const search = new URLSearchParams();
    if (includeArchived) search.set("include_archived", "true");
    if (q) search.set("q", q);
    const query = search.toString();
    return request<Exercise[]>(`/api/exercises${query ? `?${query}` : ""}`);
  },

  createExercise: (body: ExerciseInput) =>
    request<Exercise>("/api/exercises", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateExercise: (id: string, body: ExerciseInput) =>
    request<Exercise>(`/api/exercises/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  deleteExercise: (id: string) => request<void>(`/api/exercises/${id}`, { method: "DELETE" }),

  archiveExercise: (id: string) => request<Exercise>(`/api/exercises/${id}/archive`, { method: "POST" }),

  restoreExercise: (id: string) => request<Exercise>(`/api/exercises/${id}/restore`, { method: "POST" }),

  listWorkouts: () => request<Workout[]>("/api/workouts"),

  getWorkout: (id: string) => request<Workout>(`/api/workouts/${id}`),

  createWorkout: (body: WorkoutInput) =>
    request<Workout>("/api/workouts", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateWorkout: (id: string, body: WorkoutInput) =>
    request<Workout>(`/api/workouts/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  renameWorkout: (id: string, name: string) =>
    request<Workout>(`/api/workouts/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),

  copyWorkout: (id: string) => request<Workout>(`/api/workouts/${id}/copy`, { method: "POST" }),

  deleteWorkout: (id: string) => request<void>(`/api/workouts/${id}`, { method: "DELETE" }),

  listPlan: (start: string, end: string) => {
    const search = new URLSearchParams({ start, end });
    return request<PlanEntry[]>(`/api/plan?${search.toString()}`);
  },

  today: (day: string) => {
    const search = new URLSearchParams({ day });
    return request<TodayView>(`/api/today?${search.toString()}`);
  },

  addPlanEntry: (body: PlanEntryCreate) =>
    request<PlanEntry>("/api/plan/entries", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  addPlanCycle: (body: PlanCycleCreate) =>
    request<PlanEntry[]>("/api/plan/cycles", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updatePlanEntry: (id: string, body: PlanEntryUpdate) =>
    request<PlanEntry>(`/api/plan/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deletePlanEntry: (id: string) => request<void>(`/api/plan/${id}`, { method: "DELETE" }),

  previewPlanShift: (body: PlanShiftRequest) =>
    request<PlanShiftPreview>("/api/plan/shift/preview", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  applyPlanShift: (body: PlanShiftRequest) =>
    request<PlanShiftResult>("/api/plan/shift/apply", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  undoPlanShift: () => request<PlanShiftResult>("/api/plan/shift/undo", { method: "POST" }),

  planShiftHistory: () => request<PlanChangeLogItem[]>("/api/plan/shift/history"),

  startPerformed: (plannedId: string) =>
    request<PerformedWorkout>("/api/performed", {
      method: "POST",
      body: JSON.stringify({ planned_id: plannedId }),
    }),

  previousSets: (exerciseId: string, excludeId: string) => {
    const search = new URLSearchParams({ exercise_id: exerciseId, exclude_id: excludeId });
    return request<PreviousSets | null>(`/api/performed/previous?${search.toString()}`);
  },

  progressionHint: (exerciseId: string) =>
    request<ProgressionHint | null>(`/api/progression/${exerciseId}`),

  decideProgression: (exerciseId: string, action: "accept" | "reject", performedId?: string) =>
    request<ProgressionDecisionResult>(`/api/progression/${exerciseId}/decision`, {
      method: "POST",
      body: JSON.stringify({ action, performed_id: performedId ?? null }),
    }),

  muscleVolume: (day: string) => {
    const search = new URLSearchParams({ day });
    return request<MuscleVolume>(`/api/volume/muscles?${search.toString()}`);
  },

  listBlocks: () => request<Block[]>("/api/blocks"),

  createBlock: (body: BlockInput) =>
    request<Block>("/api/blocks", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  copyBlock: (id: string) => request<Block>(`/api/blocks/${id}/copy`, { method: "POST" }),

  deleteBlock: (id: string) => request<void>(`/api/blocks/${id}`, { method: "DELETE" }),

  applyBlock: (id: string, startDate: string) =>
    request<BlockPlacement>(`/api/blocks/${id}/apply`, {
      method: "POST",
      body: JSON.stringify({ start_date: startDate }),
    }),

  listBlockPlacements: () => request<BlockPlacement[]>("/api/blocks/placements"),

  removeBlockPlacement: (id: string) =>
    request<void>(`/api/blocks/placements/${id}`, { method: "DELETE" }),

  deloadSuggestion: (placementId: string) =>
    request<DeloadSuggestion>(`/api/blocks/placements/${placementId}/deload-suggestion`),

  acceptDeload: (placementId: string) =>
    request<DeloadAccept>(`/api/blocks/placements/${placementId}/deload-suggestion/accept`, {
      method: "POST",
    }),

  exportData: () => request<ExportDocument>("/api/export"),

  downloadWorkoutsCsv: async () => {
    const response = await fetch("/api/export/workouts.csv", { credentials: "include" });
    if (!response.ok) {
      const data: unknown = await response.json().catch(() => null);
      const detail =
        typeof data === "object" && data !== null && "detail" in data ? data.detail : null;
      throw new ApiError(response.status, typeof detail === "string" ? detail : DEFAULT_ERROR);
    }
    return response.blob();
  },

  importData: (body: ExportDocument) =>
    request<ImportResult>("/api/import?mode=replace", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
