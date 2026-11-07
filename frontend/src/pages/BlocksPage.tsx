import { useState, type FormEvent } from "react";
import { type Block, type BlockPlacement } from "../api/client";
import { todayIso } from "../features/calendar/dates";
import {
  addWeek,
  DAY_LABELS,
  draftToInput,
  EMPTY_CHOICE,
  emptyBlockDraft,
  MAX_BLOCK_WEEKS,
  REST_CHOICE,
  WEEK_TYPE_LABELS,
  type BlockDraft,
} from "../features/blocks/draft";
import { PeriodizationHelp } from "../features/blocks/PeriodizationHelp";
import {
  useAcceptDeload,
  useApplyBlock,
  useBlockPlacements,
  useBlocks,
  useCopyBlock,
  useCreateBlock,
  useDeleteBlock,
  useDeloadSuggestion,
  useRemoveBlockPlacement,
} from "../features/blocks/useBlocks";
import { useWorkouts } from "../features/workouts/useWorkouts";

const buttonClass =
  "min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800";
const inputClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const primaryButtonClass =
  "min-h-11 rounded-lg bg-slate-900 px-5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300";

function weeksLabel(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} неделя`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} недели`;
  return `${count} недель`;
}

function BlockForm({ onDone }: { onDone?: () => void }) {
  const { data: templates } = useWorkouts();
  const createBlock = useCreateBlock();
  const [draft, setDraft] = useState<BlockDraft>(emptyBlockDraft);
  const [error, setError] = useState<string | null>(null);

  const updateWeek = (index: number, patch: Partial<BlockDraft["weeks"][number]>) => {
    setDraft((current) => ({
      ...current,
      weeks: current.weeks.map((week, position) =>
        position === index ? { ...week, ...patch } : week,
      ),
    }));
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const result = draftToInput(draft);
    if ("error" in result) {
      setError(result.error);
      return;
    }
    setError(null);
    createBlock.mutate(result.input, {
      onSuccess: () => {
        setDraft(emptyBlockDraft());
        onDone?.();
      },
    });
  };

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-label="Новый блок"
      className="flex flex-col gap-4 rounded-xl border border-slate-200 p-4 dark:border-slate-800"
    >
      <label className="flex flex-col gap-1 text-sm font-medium">
        Название блока
        <input
          className={inputClass}
          value={draft.name}
          placeholder="Например, «Силовой блок ноябрь»"
          onChange={(event) => setDraft({ ...draft, name: event.target.value })}
        />
      </label>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 text-sm font-medium">Недели блока</legend>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          В конце блока стоит неделя разгрузки: объём 50%, запас повторов 4. Множитель можно
          изменить. Если убрать эту неделю, при сохранении она добавится снова.
        </p>
        {draft.weeks.map((week, index) => (
          <div
            key={week.key}
            className="grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-3 sm:grid-cols-6 dark:bg-slate-900"
          >
            <label className="col-span-2 flex flex-col gap-1 text-sm sm:col-span-2">
              Тип недели {index + 1}
              <select
                className={inputClass}
                value={week.weekType}
                onChange={(event) =>
                  updateWeek(index, {
                    weekType: event.target.value as BlockDraft["weeks"][number]["weekType"],
                  })
                }
              >
                {Object.entries(WEEK_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Повторы от
              <input
                className={inputClass}
                inputMode="numeric"
                value={week.repMin}
                onChange={(event) => updateWeek(index, { repMin: event.target.value })}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              до
              <input
                className={inputClass}
                inputMode="numeric"
                value={week.repMax}
                onChange={(event) => updateWeek(index, { repMax: event.target.value })}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              RIR
              <input
                className={inputClass}
                inputMode="numeric"
                value={week.targetRir}
                onChange={(event) => updateWeek(index, { targetRir: event.target.value })}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Объём, доля
              <input
                className={inputClass}
                inputMode="decimal"
                value={week.volumeMultiplier}
                onChange={(event) => updateWeek(index, { volumeMultiplier: event.target.value })}
              />
            </label>
            <div className="col-span-2 flex items-end justify-end sm:col-span-6">
              <button
                type="button"
                className={buttonClass}
                disabled={draft.weeks.length <= 1}
                onClick={() =>
                  setDraft({ ...draft, weeks: draft.weeks.filter((_, pos) => pos !== index) })
                }
              >
                Убрать неделю
              </button>
            </div>
          </div>
        ))}
        <div>
          <button
            type="button"
            className={buttonClass}
            disabled={draft.weeks.length >= MAX_BLOCK_WEEKS}
            onClick={() => setDraft({ ...draft, weeks: addWeek(draft.weeks) })}
          >
            Добавить неделю
          </button>
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">
          Расписание недели (отсчёт от даты старта блока)
        </legend>
        {DAY_LABELS.map((label, dayIndex) => (
          <label key={label} className="flex flex-col gap-1 text-sm sm:flex-row sm:items-center">
            <span className="w-24 shrink-0">{label}</span>
            <select
              className={`${inputClass} sm:max-w-md`}
              aria-label={label}
              value={draft.schedule[dayIndex]}
              onChange={(event) => {
                const schedule = [...draft.schedule];
                schedule[dayIndex] = event.target.value;
                setDraft({ ...draft, schedule });
              }}
            >
              <option value={EMPTY_CHOICE}>Без занятия</option>
              <option value={REST_CHOICE}>Отдых</option>
              {(templates ?? []).map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          </label>
        ))}
      </fieldset>

      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" className={primaryButtonClass} disabled={createBlock.isPending}>
          Сохранить блок
        </button>
        {error && (
          <span role="alert" className="text-sm text-red-600">
            {error}
          </span>
        )}
        {createBlock.isError && (
          <span role="alert" className="text-sm text-red-600">
            {createBlock.error.message}
          </span>
        )}
      </div>
    </form>
  );
}

function BlockRow({ block }: { block: Block }) {
  const copy = useCopyBlock();
  const apply = useApplyBlock();
  const remove = useDeleteBlock();
  const [startDate, setStartDate] = useState(todayIso);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const busy = copy.isPending || apply.isPending || remove.isPending;

  const handleApply = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    apply.mutate({ id: block.id, startDate });
  };

  return (
    <li className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <p className="font-medium">{block.name}</p>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {weeksLabel(block.length_weeks)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {confirmingDelete ? (
            <>
              <span className="text-sm">Удалить блок?</span>
              <button
                type="button"
                className={`${buttonClass} text-red-600`}
                disabled={busy}
                onClick={() => remove.mutate(block.id)}
              >
                Удалить
              </button>
              <button type="button" className={buttonClass} onClick={() => setConfirmingDelete(false)}>
                Отмена
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className={buttonClass}
                disabled={busy}
                onClick={() => copy.mutate(block.id)}
              >
                Копировать
              </button>
              <button
                type="button"
                className={buttonClass}
                disabled={busy}
                onClick={() => setConfirmingDelete(true)}
              >
                Удалить
              </button>
            </>
          )}
        </div>
      </div>

      <form
        onSubmit={handleApply}
        aria-label={`Применить блок ${block.name}`}
        className="flex flex-col gap-2 sm:flex-row sm:items-end"
      >
        <label className="flex flex-col gap-1 text-sm font-medium">
          Дата старта
          <input
            type="date"
            className={inputClass}
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
        </label>
        <button type="submit" className={primaryButtonClass} disabled={busy || !startDate}>
          Применить к календарю
        </button>
        {apply.isSuccess && (
          <span role="status" className="text-sm text-slate-600 dark:text-slate-300">
            Блок добавлен в календарь
          </span>
        )}
        {apply.isError && (
          <span role="alert" className="text-sm text-red-600">
            {apply.error.message}
          </span>
        )}
      </form>
    </li>
  );
}

function DeloadOffer({ placementId }: { placementId: string }) {
  const { data } = useDeloadSuggestion(placementId);
  const accept = useAcceptDeload();
  if (!data?.suggest) return null;

  return (
    <section aria-label="Предложение разгрузки" className="flex flex-col gap-2">
      <p className="text-sm">{data.message}</p>
      <ul className="flex flex-col gap-1">
        {(data.reasons ?? []).map((reason) => (
          <li key={reason.code} className="text-sm text-slate-600 dark:text-slate-300">
            {reason.text}
          </li>
        ))}
      </ul>
      <button
        type="button"
        className={`${primaryButtonClass} self-start`}
        disabled={accept.isPending}
        onClick={() => accept.mutate(placementId)}
      >
        Сделать эту неделю разгрузкой
      </button>
      {accept.isError && (
        <span role="alert" className="text-sm text-red-600">
          {accept.error.message}
        </span>
      )}
    </section>
  );
}

function PlacementRow({ placement }: { placement: BlockPlacement }) {
  const remove = useRemoveBlockPlacement();
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800">
      <div className="flex flex-col gap-1">
        <p className="font-medium">{placement.name}</p>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {placement.start_date} — {placement.end_date} ({weeksLabel(placement.length_weeks)})
        </p>
        <DeloadOffer placementId={placement.id} />
      </div>
      <div className="flex flex-col items-start gap-1">
        <button
          type="button"
          className={buttonClass}
          disabled={remove.isPending}
          onClick={() => remove.mutate(placement.id)}
        >
          Убрать из календаря
        </button>
        {remove.isError && (
          <span role="alert" className="text-sm text-red-600">
            {remove.error.message}
          </span>
        )}
      </div>
    </li>
  );
}

export function BlocksPage() {
  const { data: blocks, isPending, isError } = useBlocks();
  const { data: placements } = useBlockPlacements();
  const [showForm, setShowForm] = useState(false);

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <h1 className="text-2xl font-semibold">Блоки периодизации</h1>
      <p className="text-sm text-slate-600 dark:text-slate-300">
        Блок — расписание недель, которое вы применяете к календарю с даты старта. Тренировки
        создаются по неделям, поэтому правка блока не меняет уже применённый план.
      </p>
      <PeriodizationHelp />

      <div>
        <button type="button" className={buttonClass} onClick={() => setShowForm((value) => !value)}>
          {showForm ? "Скрыть форму" : "Новый блок"}
        </button>
      </div>
      {showForm && <BlockForm onDone={() => setShowForm(false)} />}

      {isPending && <p className="text-slate-600 dark:text-slate-300">Загрузка…</p>}
      {isError && <p className="text-red-600">Не удалось загрузить блоки. Обновите страницу.</p>}
      {blocks && blocks.length === 0 && (
        <p className="text-slate-600 dark:text-slate-300">
          Блоков пока нет. Создайте первый, чтобы применить его к календарю.
        </p>
      )}
      {blocks && blocks.length > 0 && (
        <ul className="flex flex-col gap-3" aria-label="Список блоков">
          {blocks.map((block) => (
            <BlockRow key={block.id} block={block} />
          ))}
        </ul>
      )}

      {placements && placements.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">В календаре</h2>
          <ul className="flex flex-col gap-3" aria-label="Применённые блоки">
            {placements.map((placement) => (
              <PlacementRow key={placement.id} placement={placement} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}