import { useRecommendations } from "../features/recommendations/useRecommendations";

const secondaryClass = "text-slate-600 dark:text-slate-300";

export function RecommendationsPage() {
  const query = useRecommendations();

  return (
    <div className="flex max-w-xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">Рекомендации</h1>
        <p className={secondaryClass}>
          Осторожные выводы по текущему БЖУ и замерам. Калории здесь — сохранённый уровень, не среднее за недели.
        </p>
      </div>
      <p className={secondaryClass}>Приложение не заменяет консультацию врача или диетолога.</p>
      {query.isPending && <p className={secondaryClass}>Загрузка…</p>}
      {query.isError && (
        <p className="text-red-600">Не удалось загрузить рекомендации. Обновите страницу.</p>
      )}
      {query.data && query.data.items.length === 0 && (
        <p className={secondaryClass}>Сейчас нет советов по этим данным.</p>
      )}
      {query.data && query.data.items.length > 0 && (
        <ul className="flex flex-col gap-4">
          {query.data.items.map((item) => (
            <li
              key={item.code}
              className="flex flex-col gap-2 rounded-xl border border-slate-200 p-4 dark:border-slate-800"
            >
              <p>{item.text}</p>
              {item.basis.length > 0 && (
                <ul className={`flex flex-col gap-1 text-sm ${secondaryClass}`}>
                  {item.basis.map((row) => (
                    <li key={`${item.code}-${row.label}`}>
                      {row.label}: {row.value}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
