import { useState, type FormEvent } from "react";
import { type Block, type BlockPlacement } from "../api/client";
import { todayIso } from "../features/calendar/dates";
import {
  addWeek,
  dayLabel,
  draftFromBlock,
  draftToInput,
  EMPTY_CHOICE,
  emptyBlockDraft,
  MAX_BLOCK_WEEKS,
  MAX_CYCLE_DAYS,
  resizeBlockWeeks,
  resizeCycleDays,
  REST_CHOICE,
  WEEK_TYPE_LABELS,
  type BlockDraft,
} from "../features/blocks/draft";
import { PeriodizationHelp } from "../features/blocks/PeriodizationHelp";
import {
  useAcceptDeload,
  useApplyBlock,
  useBlockPlacements,
  useRepeatPlacement,
  useBlocks,
  useCopyBlock,
  useCreateBlock,
  useDeleteBlock,
  useDeloadSuggestion,
  useRemoveBlockPlacement,
  useUpdateBlock,
} from "../features/blocks/useBlocks";
import { useWorkouts } from "../features/workouts/useWorkouts";

const buttonClass =
  "min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800";
const inputClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const primaryButtonClass =
  "min-h-11 rounded-lg bg-slate-900 px-5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300";

function countLabel(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} ${one}`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} ${few}`;
  return `${count} ${many}`;
}

function blockSpanLabel(cycles: number, cycleDays: number): string {
  return `${countLabel(cycles, "цикл", "цикла", "циклов")} по ${countLabel(cycleDays, "дню", "дня", "дней")}`;
}

function BlockForm({
  block,
  onDone,
  onCancel,
}: {
  block?: Block;
  onDone?: () => void;
  onCancel?: () => void;
}) {
  const { data: templates } = useWorkouts();
  const createBlock = useCreateBlock();
  const updateBlock = useUpdateBlock();
  const [draft, setDraft] = useState<BlockDraft>(() => (block ? draftFromBlock(block) : emptyBlockDraft()));
  const [error, setError] = useState<string | null>(null);
  const saving = block ? updateBlock : createBlock;
  const knownTemplates = new Set((templates ?? []).map((template) => template.id));
  const missingTemplates = (block?.schedule ?? []).flatMap((item) => {
    if (item.kind !== "workout" || !item.template_id || knownTemplates.has(item.template_id)) return [];
    return [{ id: item.template_id, name: item.name ?? "Тренировка" }];
  });
  const extraTemplates = missingTemplates.filter(
    (template, index) => missingTemplates.findIndex((item) => item.id === template.id) === index,
  );

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
    const onSuccess = () => {
      if (!block) setDraft(emptyBlockDraft());
      onDone?.();
    };
    if (block) {
      updateBlock.mutate({ id: block.id, body: result.input }, { onSuccess });
      return;
    }
    createBlock.mutate(result.input, { onSuccess });
  };

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-label={block ? "Редактирование блока" : "Новый блок"}
      className="flex flex-col gap-4 rounded-xl border border-slate-200 p-4 dark:border-slate-800"
    >
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_9rem_9rem]">
        <label className="flex flex-col gap-1 text-sm font-medium">
          Название блока
          <input
            className={inputClass}
            value={draft.name}
            placeholder="Например, «Силовой блок ноябрь»"
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Длина цикла, дней
          <select
            className={inputClass}
            value={draft.cycleDays}
            onChange={(event) =>
              setDraft((current) => {
                const cycleDays = Number(event.target.value);
                return {
                  ...current,
                  cycleDays,
                  schedule: resizeCycleDays(current.schedule, cycleDays),
                };
              })
            }
          >
            {Array.from({ length: MAX_CYCLE_DAYS }, (_, index) => (
              <option key={index + 1} value={index + 1}>
                {index + 1}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Число циклов
          <select
            className={inputClass}
            value={draft.weeks.length}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                weeks: resizeBlockWeeks(current.weeks, Number(event.target.value)),
              }))
            }
          >
            {Array.from({ length: MAX_BLOCK_WEEKS }, (_, index) => (
              <option key={index + 1} value={index + 1}>
                {index + 1}
              </option>
            ))}
          </select>
        </label>
      </div>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 text-sm font-medium">Циклы</legend>
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
              Тип цикла {index + 1}
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
                Убрать цикл
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
            Добавить цикл
          </button>
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">
          Дни цикла. Следующий цикл повторяет их с параметрами своего типа.
        </legend>
        {draft.schedule.map((choice, dayIndex) => (
          <label key={dayLabel(dayIndex)} className="flex flex-col gap-1 text-sm sm:flex-row sm:items-center">
            <span className="w-24 shrink-0">{dayLabel(dayIndex)}</span>
            <select
              className={`${inputClass} sm:max-w-md`}
              aria-label={dayLabel(dayIndex)}
              value={choice}
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
              {extraTemplates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          </label>
        ))}
      </fieldset>

      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" className={primaryButtonClass} disabled={saving.isPending}>
          Сохранить блок
        </button>
        {onCancel && (
          <button type="button" className={buttonClass} disabled={saving.isPending} onClick={onCancel}>
            Отмена
          </button>
        )}
        {error && (
          <span role="alert" className="text-sm text-red-600">
            {error}
          </span>
        )}
        {saving.isError && (
          <span role="alert" className="text-sm text-red-600">
            {saving.error.message}
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
  const [repeats, setRepeats] = useState(true);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [editing, setEditing] = useState(false);
  const busy = copy.isPending || apply.isPending || remove.isPending;

  const handleApply = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    apply.mutate({ id: block.id, startDate, repeats });
  };

  if (editing) {
    return (
      <li>
        <BlockForm block={block} onDone={() => setEditing(false)} onCancel={() => setEditing(false)} />
      </li>
    );
  }

  return (
    <li className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <p className="font-medium">{block.name}</p>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {blockSpanLabel(block.length_weeks, block.cycle_days || 7)}
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
              <button type="button" className={buttonClass} disabled={busy} onClick={() => setEditing(true)}>
                Редактировать
              </button>
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
        <label className="flex min-h-11 items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            className="size-5"
            checked={repeats}
            onChange={(event) => setRepeats(event.target.checked)}
          />
          Повторять без конца
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

function placementWhen(placement: BlockPlacement): string {
  const span = blockSpanLabel(placement.length_weeks, placement.cycle_days || 7);
  if (placement.repeats || placement.end_date == null) {
    return `с ${placement.start_date}, без конца (${span})`;
  }
  return `${placement.start_date} — ${placement.end_date} (${span})`;
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
  const repeat = useRepeatPlacement();
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800">
      <div className="flex flex-col gap-1">
        <p className="font-medium">{placement.name}</p>
        <p className="text-sm text-slate-600 dark:text-slate-300">{placementWhen(placement)}</p>
        <DeloadOffer placementId={placement.id} />
      </div>
      <div className="flex flex-col items-start gap-1">
        {!placement.repeats && (
          <button
            type="button"
            className={buttonClass}
            disabled={repeat.isPending || remove.isPending}
            onClick={() => repeat.mutate(placement.id)}
          >
            Продлить без конца
          </button>
        )}
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
        Блок — несколько циклов подряд. Длина цикла задаётся в днях, поэтому сплит может быть
        короче недели: следующий цикл повторяет те же дни, но со своим типом, например разгрузкой.
        Правка блока не меняет уже поставленный в календарь план.
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