import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { NAV_ITEMS } from "./navigation";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { TodayPage } from "./pages/TodayPage";
import { ComingSoonPage } from "./pages/ComingSoonPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ExerciseCardPage } from "./pages/ExerciseCardPage";
import { ExercisesPage } from "./pages/ExercisesPage";
import { WorkoutsPage } from "./pages/WorkoutsPage";
import { WorkoutEditorPage } from "./pages/WorkoutEditorPage";
import { CalendarPage } from "./pages/CalendarPage";
import { WorkoutLogPage } from "./pages/WorkoutLogPage";
import { VolumePage } from "./pages/VolumePage";
import { BlocksPage } from "./pages/BlocksPage";
import { NutritionPage } from "./pages/NutritionPage";

/** Разделы с реальными экранами; остальные пункты меню пока показывают «Скоро». */
const IMPLEMENTED_ROUTES = new Set([
  "/",
  "/calendar",
  "/exercises",
  "/workouts",
  "/blocks",
  "/volume",
  "/nutrition",
]);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          <Route element={<ProtectedRoute />}>
            <Route element={<AppLayout />}>
              <Route index element={<TodayPage />} />
              {NAV_ITEMS.filter((item) => !IMPLEMENTED_ROUTES.has(item.to)).map((item) => (
                <Route
                  key={item.to}
                  path={item.to.slice(1)}
                  element={<ComingSoonPage title={item.label} />}
                />
              ))}
              <Route path="calendar" element={<CalendarPage />} />
              <Route path="log/:plannedId" element={<WorkoutLogPage />} />
              <Route path="exercises" element={<ExercisesPage />} />
              <Route path="exercises/:exerciseId" element={<ExerciseCardPage />} />
              <Route path="workouts" element={<WorkoutsPage />} />
              <Route path="workouts/:workoutId" element={<WorkoutEditorPage />} />
              <Route path="blocks" element={<BlocksPage />} />
              <Route path="volume" element={<VolumePage />} />
              <Route path="nutrition" element={<NutritionPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
