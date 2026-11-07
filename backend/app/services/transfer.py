import csv
import datetime as dt
import io
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.block import BlockPlacement
from app.models.exercise import Exercise
from app.models.log import PerformedItem, PerformedWorkout, SetLog
from app.models.plan import PlanChangeLog, PlannedWorkout
from app.models.profile import Profile
from app.models.progression import ProgressionDecision
from app.models.user import User
from app.models.workout import WorkoutTemplate, WorkoutTemplateItem, WorkoutTemplateSet
from app.schemas.plan import PlanItemSnapshot
from app.schemas.profile import ProfileUpdate
from app.schemas.transfer import (
    FORMAT_VERSION,
    ExerciseExport,
    ExportDocument,
    ImportResult,
    PerformedItemExport,
    PerformedWorkoutExport,
    PlanChangeLogExport,
    PlanChangePayloadExport,
    PlannedWorkoutExport,
    ProgressionDecisionExport,
    SetLogExport,
    TemplateItemExport,
    TemplateSetExport,
    WorkoutTemplateExport,
)
from app.services.profile import get_or_create_profile, get_profile_or_default
from app.services.progression import decision_fingerprint

REMINDER_INTERVAL = dt.timedelta(days=30)


class TransferError(Exception):
    """Файл не сходится внутри себя: ссылки, повторы идентификаторов или позиций."""


def export_is_due(
    created_at: dt.datetime,
    last_exported_at: dt.datetime | None,
    now: dt.datetime | None = None,
) -> bool:
    """Напоминание включается через месяц после регистрации и затем через месяц после экспорта."""
    current = now or dt.datetime.now(dt.UTC)
    if current - created_at < REMINDER_INTERVAL:
        return False
    if last_exported_at is None:
        return True
    return current - last_exported_at >= REMINDER_INTERVAL


def _require_unique(ids: Iterable[uuid.UUID], label: str) -> None:
    seen: set[uuid.UUID] = set()
    for item_id in ids:
        if item_id in seen:
            raise TransferError(f"В разделе «{label}» повторяется идентификатор")
        seen.add(item_id)


def _require_positions(positions: Sequence[int], label: str) -> None:
    if len(set(positions)) != len(positions):
        raise TransferError(f"В разделе «{label}» повторяется позиция")


def validate_links(document: ExportDocument) -> None:
    """Проверяет, что ссылки ведут на записи этого же файла. Иначе импорт не начнётся."""
    _require_unique((row.id for row in document.exercises), "упражнения")
    _require_unique((row.id for row in document.workout_templates), "тренировки")
    _require_unique((row.id for row in document.planned_workouts), "план")
    _require_unique((row.id for row in document.plan_change_logs), "журнал сдвигов")
    _require_unique((row.id for row in document.performed_workouts), "выполненные тренировки")
    _require_unique((row.id for row in document.progression_decisions), "подсказки прогрессии")

    exercise_ids = {row.id for row in document.exercises}
    template_ids = {row.id for row in document.workout_templates}
    planned_ids = {row.id for row in document.planned_workouts}

    for template in document.workout_templates:
        _require_positions([item.position for item in template.items], template.name)
        _require_unique((item.id for item in template.items), template.name)
        for item in template.items:
            if item.exercise_id not in exercise_ids:
                raise TransferError(
                    f"В тренировке «{template.name}» указано неизвестное упражнение"
                )
            _require_positions([set_.position for set_ in item.sets], template.name)
            _require_unique((set_.id for set_ in item.sets), template.name)

    by_day: dict[dt.date, list[PlannedWorkoutExport]] = defaultdict(list)
    for entry in document.planned_workouts:
        if entry.template_id is not None and entry.template_id not in template_ids:
            raise TransferError("В плане указан неизвестный шаблон тренировки")
        by_day[entry.date].append(entry)
    for day, group in by_day.items():
        kinds = {entry.kind for entry in group}
        rest_count = sum(1 for entry in group if entry.kind == "rest")
        if "rest" in kinds and "workout" in kinds:
            raise TransferError(f"{day.isoformat()} совмещает отдых и тренировку")
        if rest_count > 1:
            raise TransferError(f"На {day.isoformat()} несколько дней отдыха")

    for log in document.plan_change_logs:
        if log.payload.operation != log.operation:
            raise TransferError("Операция в журнале сдвигов не совпадает с записью")
        for change in log.payload.changes:
            if change.id not in planned_ids:
                raise TransferError("Журнал сдвигов ссылается на запись плана, которой нет в файле")

    linked_plans = [
        workout.planned_id for workout in document.performed_workouts if workout.planned_id
    ]
    _require_unique(linked_plans, "факт")

    for workout in document.performed_workouts:
        if workout.planned_id is not None and workout.planned_id not in planned_ids:
            raise TransferError("Факт тренировки ссылается на запись плана, которой нет в файле")
        _require_positions([item.position for item in workout.items], workout.name or "факт")
        _require_unique((item.id for item in workout.items), workout.name or "факт")
        for item in workout.items:
            if item.exercise_id is not None and item.exercise_id not in exercise_ids:
                raise TransferError(f"В факте «{item.name}» указано неизвестное упражнение")
            _require_positions([set_.position for set_ in item.sets], item.name)
            _require_unique((set_.id for set_ in item.sets), item.name)
            for logged in item.sets:
                if logged.exercise_id is not None and logged.exercise_id not in exercise_ids:
                    raise TransferError(f"В подходе «{item.name}» указано неизвестное упражнение")

    performed_ids = {row.id for row in document.performed_workouts}
    seen_hints: set[tuple[uuid.UUID, str, uuid.UUID, float | None]] = set()
    for decision in document.progression_decisions:
        if decision.exercise_id not in exercise_ids:
            raise TransferError("Решение по прогрессии ссылается на неизвестное упражнение")
        if decision.last_session_id not in performed_ids:
            raise TransferError(
                "Решение по прогрессии ссылается на тренировку, которой нет в файле"
            )
        fingerprint = (
            decision.exercise_id,
            decision.status,
            decision.last_session_id,
            decision.suggested_weight,
        )
        if fingerprint in seen_hints:
            raise TransferError("Повторяется решение по одной и той же подсказке")
        seen_hints.add(fingerprint)


def _new_id(mapping: dict[uuid.UUID, uuid.UUID], old: uuid.UUID) -> uuid.UUID:
    mapped = mapping.get(old)
    if mapped is None:
        mapped = uuid.uuid4()
        mapping[old] = mapped
    return mapped


def _remap_snapshot(
    items: Sequence[PlanItemSnapshot], exercises: dict[uuid.UUID, uuid.UUID]
) -> list[dict[str, object]]:
    dumped: list[dict[str, object]] = []
    for item in items:
        payload = item.model_dump(mode="json")
        exercise = payload["exercise"]
        assert isinstance(exercise, dict)
        old = uuid.UUID(str(exercise["exercise_id"]))
        if old in exercises:
            exercise["exercise_id"] = str(exercises[old])
        dumped.append(payload)
    return dumped


async def _clear_user_data(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Удаляет данные пользователя в порядке, который допускают внешние ключи."""
    await db.execute(delete(ProgressionDecision).where(ProgressionDecision.user_id == user_id))
    performed_ids = select(PerformedWorkout.id).where(PerformedWorkout.user_id == user_id)
    await db.execute(delete(SetLog).where(SetLog.performed_id.in_(performed_ids)))
    await db.execute(delete(PerformedItem).where(PerformedItem.performed_id.in_(performed_ids)))
    await db.execute(delete(PerformedWorkout).where(PerformedWorkout.user_id == user_id))
    await db.execute(delete(PlanChangeLog).where(PlanChangeLog.user_id == user_id))
    await db.execute(delete(PlannedWorkout).where(PlannedWorkout.user_id == user_id))
    # Размещения блоков дают тренировки в календаре: без них они не должны остаться.
    await db.execute(delete(BlockPlacement).where(BlockPlacement.user_id == user_id))
    await db.execute(delete(WorkoutTemplate).where(WorkoutTemplate.user_id == user_id))
    await db.execute(delete(Exercise).where(Exercise.user_id == user_id))


async def build_export(db: AsyncSession, user_id: uuid.UUID) -> ExportDocument:
    profile = await get_profile_or_default(db, user_id)
    exercises = list(
        await db.scalars(
            select(Exercise).where(Exercise.user_id == user_id).order_by(Exercise.name, Exercise.id)
        )
    )
    templates = list(
        await db.scalars(
            select(WorkoutTemplate)
            .where(WorkoutTemplate.user_id == user_id)
            .order_by(WorkoutTemplate.created_at, WorkoutTemplate.id)
        )
    )
    planned = list(
        await db.scalars(
            select(PlannedWorkout)
            .where(PlannedWorkout.user_id == user_id)
            .order_by(PlannedWorkout.date, PlannedWorkout.position, PlannedWorkout.id)
        )
    )
    logs = list(
        await db.scalars(
            select(PlanChangeLog)
            .where(PlanChangeLog.user_id == user_id)
            .order_by(PlanChangeLog.seq)
        )
    )
    performed = list(
        await db.scalars(
            select(PerformedWorkout)
            .where(PerformedWorkout.user_id == user_id)
            .order_by(PerformedWorkout.date, PerformedWorkout.started_at, PerformedWorkout.id)
        )
    )
    decisions = list(
        await db.scalars(
            select(ProgressionDecision)
            .where(ProgressionDecision.user_id == user_id)
            .order_by(ProgressionDecision.created_at, ProgressionDecision.id)
        )
    )
    return ExportDocument(
        format_version=FORMAT_VERSION,
        exported_at=dt.datetime.now(dt.UTC),
        profile=ProfileUpdate.model_validate(profile, from_attributes=True),
        exercises=[ExerciseExport.model_validate(row, from_attributes=True) for row in exercises],
        workout_templates=[
            WorkoutTemplateExport(
                id=template.id,
                name=template.name,
                created_at=template.created_at,
                items=[
                    TemplateItemExport(
                        id=item.id,
                        exercise_id=item.exercise_id,
                        position=item.position,
                        sets=[
                            TemplateSetExport.model_validate(set_, from_attributes=True)
                            for set_ in item.sets
                        ],
                    )
                    for item in template.items
                ],
            )
            for template in templates
        ],
        planned_workouts=[
            PlannedWorkoutExport(
                id=entry.id,
                date=entry.date,
                kind=entry.kind,  # type: ignore[arg-type]
                template_id=entry.template_id,
                name=entry.name,
                snapshot=[PlanItemSnapshot.model_validate(item) for item in entry.snapshot],
                status=entry.status,  # type: ignore[arg-type]
                is_fixed=entry.is_fixed,
                position=entry.position,
                created_at=entry.created_at,
            )
            for entry in planned
        ],
        plan_change_logs=[
            PlanChangeLogExport(
                id=log.id,
                operation=log.operation,  # type: ignore[arg-type]
                payload=PlanChangePayloadExport.model_validate(log.payload),
                created_at=log.created_at,
            )
            for log in logs
        ],
        performed_workouts=[
            PerformedWorkoutExport(
                id=workout.id,
                planned_id=workout.planned_id,
                date=workout.date,
                name=workout.name,
                note=workout.note,
                started_at=workout.started_at,
                finished_at=workout.finished_at,
                items=[
                    PerformedItemExport(
                        id=item.id,
                        position=item.position,
                        exercise_id=item.exercise_id,
                        name=item.name,
                        equipment=item.equipment,  # type: ignore[arg-type]
                        weight_type=item.weight_type,  # type: ignore[arg-type]
                        weight_unit=item.weight_unit,  # type: ignore[arg-type]
                        weight_step=item.weight_step,
                        note=item.note,
                        targets=item.targets,
                        sets=[
                            SetLogExport.model_validate(logged, from_attributes=True)
                            for logged in item.sets
                        ],
                    )
                    for item in workout.items
                ],
            )
            for workout in performed
        ],
        progression_decisions=[
            ProgressionDecisionExport(
                id=row.id,
                exercise_id=row.exercise_id,
                status=row.status,  # type: ignore[arg-type]
                last_session_id=row.last_session_id,
                suggested_weight=row.suggested_weight,
                action=row.action,  # type: ignore[arg-type]
                created_at=row.created_at,
            )
            for row in decisions
        ],
    )


async def mark_exported(db: AsyncSession, user_id: uuid.UUID, when: dt.datetime) -> None:
    profile = await get_or_create_profile(db, user_id)
    profile.last_exported_at = when


async def export_reminder_due(db: AsyncSession, user: User, now: dt.datetime | None = None) -> bool:
    profile = await db.get(Profile, user.id)
    last_exported = None if profile is None else profile.last_exported_at
    return export_is_due(user.created_at, last_exported, now)


async def import_replace(
    db: AsyncSession, user_id: uuid.UUID, document: ExportDocument
) -> ImportResult:
    """Заменяет данные пользователя содержимым файла. Идентификаторы получают новые значения."""
    validate_links(document)
    await _clear_user_data(db, user_id)

    exercises: dict[uuid.UUID, uuid.UUID] = {}
    for row in document.exercises:
        new_id = _new_id(exercises, row.id)
        db.add(
            Exercise(
                id=new_id,
                user_id=user_id,
                name=row.name,
                primary_muscle=row.primary_muscle,
                secondary_muscles=list(row.secondary_muscles),
                equipment=row.equipment,
                weight_type=row.weight_type,
                weight_unit=row.weight_unit,
                weight_step=row.weight_step,
                rep_min=row.rep_min,
                rep_max=row.rep_max,
                archived=row.archived,
            )
        )
    await db.flush()

    templates: dict[uuid.UUID, uuid.UUID] = {}
    for row in document.workout_templates:
        template_id = _new_id(templates, row.id)
        db.add(
            WorkoutTemplate(
                id=template_id,
                user_id=user_id,
                name=row.name,
                created_at=row.created_at,
            )
        )
        for item in row.items:
            item_id = uuid.uuid4()
            db.add(
                WorkoutTemplateItem(
                    id=item_id,
                    template_id=template_id,
                    exercise_id=exercises[item.exercise_id],
                    position=item.position,
                )
            )
            for set_ in item.sets:
                db.add(
                    WorkoutTemplateSet(
                        id=uuid.uuid4(),
                        item_id=item_id,
                        position=set_.position,
                        rep_min=set_.rep_min,
                        rep_max=set_.rep_max,
                        target_rir=set_.target_rir,
                        rest_seconds=set_.rest_seconds,
                    )
                )
    await db.flush()

    planned: dict[uuid.UUID, uuid.UUID] = {}
    for row in document.planned_workouts:
        new_id = _new_id(planned, row.id)
        template_id = None if row.template_id is None else templates[row.template_id]
        db.add(
            PlannedWorkout(
                id=new_id,
                user_id=user_id,
                date=row.date,
                kind=row.kind,
                template_id=template_id,
                name=row.name,
                snapshot=_remap_snapshot(row.snapshot, exercises),
                status=row.status,
                is_fixed=row.is_fixed,
                position=row.position,
                created_at=row.created_at,
            )
        )
    await db.flush()

    for row in sorted(document.plan_change_logs, key=lambda log: log.created_at):
        payload = row.payload.model_dump(mode="json")
        changes = payload["changes"]
        assert isinstance(changes, list)
        for change in changes:
            assert isinstance(change, dict)
            change["id"] = str(planned[uuid.UUID(str(change["id"]))])
        db.add(
            PlanChangeLog(
                id=uuid.uuid4(),
                user_id=user_id,
                operation=row.operation,
                payload=payload,
                created_at=row.created_at,
            )
        )
    await db.flush()

    performed_ids: dict[uuid.UUID, uuid.UUID] = {}
    for row in document.performed_workouts:
        performed_id = _new_id(performed_ids, row.id)
        planned_id = None if row.planned_id is None else planned[row.planned_id]
        db.add(
            PerformedWorkout(
                id=performed_id,
                user_id=user_id,
                planned_id=planned_id,
                date=row.date,
                name=row.name,
                note=row.note,
                started_at=row.started_at,
                finished_at=row.finished_at,
            )
        )
        for item in row.items:
            item_id = uuid.uuid4()
            exercise_id = None if item.exercise_id is None else exercises[item.exercise_id]
            db.add(
                PerformedItem(
                    id=item_id,
                    performed_id=performed_id,
                    position=item.position,
                    exercise_id=exercise_id,
                    name=item.name,
                    equipment=item.equipment,
                    weight_type=item.weight_type,
                    weight_unit=item.weight_unit,
                    weight_step=item.weight_step,
                    note=item.note,
                    targets=[target.model_dump(mode="json") for target in item.targets],
                )
            )
            for logged in item.sets:
                set_exercise = None if logged.exercise_id is None else exercises[logged.exercise_id]
                db.add(
                    SetLog(
                        id=uuid.uuid4(),
                        item_id=item_id,
                        performed_id=performed_id,
                        exercise_id=set_exercise,
                        position=logged.position,
                        weight=logged.weight,
                        extra_weight=logged.extra_weight,
                        reps=logged.reps,
                        rir=logged.rir,
                        is_warmup=logged.is_warmup,
                        is_assisted=logged.is_assisted,
                        is_negative=logged.is_negative,
                        note=logged.note,
                    )
                )
    await db.flush()

    for row in document.progression_decisions:
        exercise_id = exercises[row.exercise_id]
        session_id = performed_ids[row.last_session_id]
        db.add(
            ProgressionDecision(
                id=uuid.uuid4(),
                user_id=user_id,
                exercise_id=exercise_id,
                status=row.status,
                last_session_id=session_id,
                suggested_weight=row.suggested_weight,
                fingerprint=decision_fingerprint(row.status, session_id, row.suggested_weight),
                action=row.action,
                created_at=row.created_at,
            )
        )
    await db.flush()

    profile = await get_or_create_profile(db, user_id)
    imported = document.profile
    profile.goal = imported.goal
    profile.height_cm = imported.height_cm
    profile.age = imported.age
    profile.sex = imported.sex
    profile.weight_unit = imported.weight_unit
    profile.theme = imported.theme
    await db.flush()

    return ImportResult(
        exercises=len(document.exercises),
        workout_templates=len(document.workout_templates),
        planned_workouts=len(document.planned_workouts),
        performed_workouts=len(document.performed_workouts),
    )


def _csv_cell(value: object) -> object:
    return "" if value is None else value


def _csv_row(
    day: dt.date,
    workout_name: str | None,
    exercise_name: str,
    set_number: object,
    logged: SetLogExport | None,
    note: str | None,
) -> list[object]:
    return [
        day.isoformat(),
        workout_name or "",
        exercise_name,
        set_number,
        _csv_cell(None if logged is None else logged.weight),
        _csv_cell(None if logged is None else logged.extra_weight),
        _csv_cell(None if logged is None else logged.reps),
        _csv_cell(None if logged is None else logged.rir),
        "" if logged is None else ("да" if logged.is_warmup else "нет"),
        "" if logged is None else ("да" if logged.is_assisted else "нет"),
        "" if logged is None else ("да" if logged.is_negative else "нет"),
        note or "",
    ]


def workouts_csv(document: ExportDocument) -> str:
    """Одна строка на подход. Пустая тренировка всё равно попадает в файл одной строкой."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Дата",
            "Тренировка",
            "Упражнение",
            "Подход",
            "Вес",
            "Доп. вес",
            "Повторы",
            "RIR",
            "Разминка",
            "С помощью",
            "Негативы",
            "Заметка",
        ]
    )
    for workout in document.performed_workouts:
        if not workout.items:
            writer.writerow(_csv_row(workout.date, workout.name, "", "", None, workout.note))
            continue
        for item in workout.items:
            if not item.sets:
                writer.writerow(
                    _csv_row(workout.date, workout.name, item.name, "", None, item.note)
                )
                continue
            for logged in item.sets:
                writer.writerow(
                    _csv_row(
                        workout.date,
                        workout.name,
                        item.name,
                        logged.position + 1,
                        logged,
                        logged.note,
                    )
                )
    return "\ufeff" + buffer.getvalue()
