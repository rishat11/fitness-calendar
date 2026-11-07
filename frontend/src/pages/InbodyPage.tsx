import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { api, type InbodyScan, type InbodyScanInput } from "../api/client";
import { todayIso } from "../features/calendar/dates";
import {
  applyParsed,
  buildScanInput,
  draftFromScan,
  emptyDraft,
  missingFieldLabel,
  type ScanDraft,
} from "../features/inbody/form";
import { deltaLabel, formatDelta } from "../features/inbody/deltas";
import { ScanChart } from "../features/inbody/ScanChart";
import { useCreateInbody, useDeleteInbody, useInbodyScans, useUpdateInbody } from "../features/inbody/useInbody";

const inputClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const labelClass = "flex flex-col gap-1 text-sm font-medium";
const secondaryClass = "text-slate-600 dark:text-slate-300";

const MEMO =
  "Утром или в одно и то же время, натощак или через 2–3 часа после еды, после туалета, без тяжёлой тренировки за 12 часов, без алкоголя накануне, без сауны и обезвоживания, лёгкая одежда без металла, чистые сухие ладони и стопы, спокойная поза, один и тот же прибор.";

/** Ждём паузу в наборе, чтобы не отправлять незаконченное число вроде «8» при вводе «84,7». */
const TEXT_SAVE_DELAY_MS = 400;

function sameScan(a: InbodyScanInput, b: InbodyScanInput): boolean {
  return (
    a.measured_on === b.measured_on &&
    a.measured_time === b.measured_time &&
    a.weight_kg === b.weight_kg &&
    a.smm_kg === b.smm_kg &&
    a.bfm_kg === b.bfm_kg &&
    a.pbf_percent === b.pbf_percent &&
    a.tbw_l === b.tbw_l &&
    a.visceral_fat_level === b.visceral_fat_level &&
    a.bmr_kcal === b.bmr_kcal
  );
}

function ScanForm({
  editing,
  onCancel,
}: {
  editing: InbodyScan | null;
  onCancel: () => void;
}) {
  const create = useCreateInbody();
  const update = useUpdateInbody();
  const [draft, setDraft] = useState<ScanDraft>(() =>
    editing ? draftFromScan(editing) : emptyDraft(todayIso()),
  );
  const [pdfMessage, setPdfMessage] = useState<string | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [readingPdf, setReadingPdf] = useState(false);
  const [saved, setSaved] = useState(false);
  const formRef = useRef(draft);
  const saveTimer = useRef<number | null>(null);
  const saveGeneration = useRef(0);
  const savedId = useRef<string | null>(editing?.id ?? null);
  const lastSaved = useRef<InbodyScanInput | null>(
    editing ? buildScanInput(draftFromScan(editing)) : null,
  );
  const createInFlight = useRef(false);

  useEffect(() => {
    return () => {
      if (saveTimer.current !== null) {
        window.clearTimeout(saveTimer.current);
      }
    };
  }, []);

  const clearSaveTimer = () => {
    if (saveTimer.current !== null) {
      window.clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
  };

  const persist = (next: ScanDraft) => {
    const generation = ++saveGeneration.current;
    const body = buildScanInput(next);
    if (body == null) {
      setSaved(false);
      return;
    }
    const id = savedId.current;
    if (id) {
      if (lastSaved.current && sameScan(lastSaved.current, body)) {
        setSaved(true);
        return;
      }
      update.mutate(
        { id, body },
        {
          onSuccess: () => {
            if (generation !== saveGeneration.current) return;
            lastSaved.current = body;
            setSaved(true);
          },
        },
      );
      return;
    }
    // Повторный вызов, пока первый замер ещё создаётся, допишет правку в тот же id.
    if (createInFlight.current) return;
    createInFlight.current = true;
    create.mutate(body, {
      onSuccess: (scan) => {
        createInFlight.current = false;
        savedId.current = scan.id;
        lastSaved.current = body;
        if (generation !== saveGeneration.current) {
          persist(formRef.current);
          return;
        }
        savedId.current = null;
        lastSaved.current = null;
        const empty = emptyDraft(todayIso());
        formRef.current = empty;
        setDraft(empty);
        setPdfMessage(null);
        setPdfError(null);
        setSaved(true);
      },
      onError: () => {
        createInFlight.current = false;
      },
    });
  };

  const schedulePersist = (next: ScanDraft, immediate: boolean) => {
    setSaved(false);
    create.reset();
    update.reset();
    clearSaveTimer();
    if (immediate) {
      persist(next);
      return;
    }
    saveTimer.current = window.setTimeout(() => {
      saveTimer.current = null;
      persist(formRef.current);
    }, TEXT_SAVE_DELAY_MS);
  };

  const updateField = (patch: Partial<ScanDraft>, immediate: boolean) => {
    const next = { ...formRef.current, ...patch };
    formRef.current = next;
    setDraft(next);
    schedulePersist(next, immediate);
  };

  const flushTextSave = () => {
    if (saveTimer.current === null) return;
    clearSaveTimer();
    persist(formRef.current);
  };

  const onPdf = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setReadingPdf(true);
    setPdfError(null);
    setPdfMessage(null);
    try {
      const parsed = await api.parseInbodyPdf(file);
      const next = applyParsed(formRef.current, parsed);
      formRef.current = next;
      setDraft(next);
      setPdfMessage(
        parsed.missing.length === 0
          ? "Цифры с листа подставлены."
          : `Не найдено: ${parsed.missing.map(missingFieldLabel).join(", ")}. Допишите вручную.`,
      );
      schedulePersist(next, false);
    } catch (caught) {
      setPdfError(caught instanceof Error ? caught.message : "Не удалось прочитать PDF");
    } finally {
      setReadingPdf(false);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    flushTextSave();
  };

  const saving = create.isPending || update.isPending;

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">{editing ? "Правка замера" : "Новый замер"}</h2>
      <label className={labelClass}>
        PDF-лист InBody
        <input
          type="file"
          accept="application/pdf,.pdf"
          className={inputClass}
          disabled={readingPdf || saving}
          onChange={(event) => void onPdf(event)}
        />
      </label>
      {readingPdf && <p className={secondaryClass}>Чтение файла…</p>}
      {pdfMessage && (
        <p role="status" className={secondaryClass}>
          {pdfMessage}
        </p>
      )}
      {pdfError && (
        <p role="alert" className="text-sm text-red-600">
          {pdfError}
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={labelClass}>
          Дата
          <input
            type="date"
            className={inputClass}
            value={draft.measured_on}
            onChange={(event) => updateField({ measured_on: event.target.value }, true)}
            onBlur={flushTextSave}
            required
          />
        </label>
        <label className={labelClass}>
          Время
          <input
            type="time"
            className={inputClass}
            value={draft.measured_time}
            onChange={(event) => updateField({ measured_time: event.target.value }, true)}
            onBlur={flushTextSave}
          />
        </label>
        <TextField
          label="Вес, кг"
          value={draft.weight_kg}
          onChange={(weight_kg) => updateField({ weight_kg }, false)}
          onBlur={flushTextSave}
        />
        <TextField
          label="Мышцы, кг"
          value={draft.smm_kg}
          onChange={(smm_kg) => updateField({ smm_kg }, false)}
          onBlur={flushTextSave}
        />
        <TextField
          label="Содержание жира, кг"
          value={draft.bfm_kg}
          onChange={(bfm_kg) => updateField({ bfm_kg }, false)}
          onBlur={flushTextSave}
        />
        <TextField
          label="Жир, %"
          value={draft.pbf_percent}
          onChange={(pbf_percent) => updateField({ pbf_percent }, false)}
          onBlur={flushTextSave}
        />
        <TextField
          label="Вода, л"
          value={draft.tbw_l}
          onChange={(tbw_l) => updateField({ tbw_l }, false)}
          onBlur={flushTextSave}
        />
        <TextField
          label="Висцеральный жир, уровень"
          value={draft.visceral_fat_level}
          onChange={(visceral_fat_level) => updateField({ visceral_fat_level }, false)}
          onBlur={flushTextSave}
        />
        <TextField
          label="Обмен веществ, ккал"
          value={draft.bmr_kcal}
          onChange={(bmr_kcal) => updateField({ bmr_kcal }, false)}
          onBlur={flushTextSave}
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {saving && (
          <span role="status" className="text-sm text-slate-600 dark:text-slate-300">
            Сохраняем…
          </span>
        )}
        {saved && !saving && (
          <span role="status" className="text-sm text-green-700 dark:text-green-400">
            Сохранено
          </span>
        )}
        {editing && (
          <button type="button" className="min-h-11 rounded-xl px-3 text-sm" onClick={onCancel}>
            Отмена
          </button>
        )}
      </div>
      {(create.isError || update.isError) && (
        <p role="alert" className="text-sm text-red-600">
          Не удалось сохранить замер.
        </p>
      )}
    </form>
  );
}

function TextField({
  label,
  value,
  onChange,
  onBlur,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
}) {
  return (
    <label className={labelClass}>
      {label}
      <input
        className={inputClass}
        inputMode="decimal"
        autoComplete="off"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
      />
    </label>
  );
}

export function InbodyPage() {
  const scans = useInbodyScans();
  const remove = useDeleteInbody();
  const [editingId, setEditingId] = useState<string | null>(null);
  const rows = scans.data ?? [];
  const editing = rows.find((scan) => scan.id === editingId) ?? null;
  const latest = rows.at(-1);

  return (
    <div className="flex max-w-3xl flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">InBody</h1>
        <p className={secondaryClass}>
          Загрузите PDF с прибора или введите цифры с листа. Каждый замер остаётся в истории, графики
          строятся по датам. Норма калорий прибора сюда не переносится.
        </p>
      </div>

      <section className="flex flex-col gap-2" aria-labelledby="inbody-memo">
        <h2 id="inbody-memo" className="text-lg font-semibold">
          Как правильно делать замер InBody
        </h2>
        <p className={secondaryClass}>{MEMO}</p>
        <p className={secondaryClass}>Вывод строится по нескольким замерам, а не по одному.</p>
      </section>

      {scans.isPending && <p className={secondaryClass}>Загрузка…</p>}
      {scans.isError && <p className="text-red-600">Не удалось загрузить замеры. Обновите страницу.</p>}

      {scans.data && (
        <>
          <ScanForm key={editing?.id ?? "new"} editing={editing} onCancel={() => setEditingId(null)} />

          {latest && latest.deltas.length > 0 && (
            <section className="flex flex-col gap-2" aria-label="Дельты последнего замера">
              <h2 className="text-lg font-semibold">К предыдущему замеру</h2>
              <ul className="flex flex-col gap-1 text-sm">
                {latest.deltas.map((delta) => (
                  <li key={delta.code}>
                    {deltaLabel(delta.code)}: {formatDelta(delta)}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="grid gap-6 lg:grid-cols-2" aria-label="Графики">
            <ScanChart title="Вес, кг" points={rows.map((row) => ({ date: row.measured_on, value: row.weight_kg }))} />
            <ScanChart title="Мышцы, кг" points={rows.map((row) => ({ date: row.measured_on, value: row.smm_kg }))} />
            <ScanChart title="Жир, кг" points={rows.map((row) => ({ date: row.measured_on, value: row.bfm_kg }))} />
            <ScanChart title="Жир, %" points={rows.map((row) => ({ date: row.measured_on, value: row.pbf_percent }))} />
          </section>

          <section className="flex flex-col gap-3" aria-label="Список замеров">
            <h2 className="text-lg font-semibold">Замеры</h2>
            {rows.length === 0 && <p className={secondaryClass}>Замеров пока нет.</p>}
            <ul className="flex flex-col gap-2">
              {[...rows].reverse().map((scan) => (
                <li
                  key={scan.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 px-3 py-2 dark:border-slate-800"
                >
                  <span>
                    {scan.measured_on}
                    {scan.measured_time ? ` ${scan.measured_time.slice(0, 5)}` : ""} · {scan.weight_kg} кг
                  </span>
                  <span className="flex gap-2">
                    <button type="button" className="min-h-11 px-2 text-sm" onClick={() => setEditingId(scan.id)}>
                      Изменить
                    </button>
                    <button
                      type="button"
                      className="min-h-11 px-2 text-sm text-red-700 dark:text-red-300"
                      onClick={() => {
                        if (window.confirm("Удалить этот замер?")) {
                          remove.mutate(scan.id, {
                            onSuccess: () => {
                              if (editingId === scan.id) setEditingId(null);
                            },
                          });
                        }
                      }}
                    >
                      Удалить
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
