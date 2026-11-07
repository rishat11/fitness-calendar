import { useEffect } from "react";

/** Не даёт экрану погаснуть, пока открыт лог. Повторный запрос нужен: блокировка снимается, когда вкладку скрыли. */
export function useWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !("wakeLock" in navigator)) return;
    let released = false;
    let sentinel: WakeLockSentinel | null = null;

    const request = () => {
      if (released || document.visibilityState !== "visible") return;
      navigator.wakeLock
        .request("screen")
        .then((lock) => {
          if (released) {
            void lock.release();
            return;
          }
          sentinel = lock;
        })
        .catch(() => {
          // Отказ браузера не мешает записи: часть устройств Wake Lock не даёт.
        });
    };

    request();
    const onVisible = () => {
      if (document.visibilityState === "visible") request();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      released = true;
      document.removeEventListener("visibilitychange", onVisible);
      void sentinel?.release();
    };
  }, [active]);
}
