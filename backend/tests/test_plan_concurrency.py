"""Гонки: одновременные запросы должны соблюдать правила плана.

Данные коммитятся в настоящую тестовую БД (а не откатываются), поэтому пользователь
удаляется в конце каждого теста.
"""

import asyncio
import datetime as dt
import uuid

from app.models.plan import PlannedWorkout
from app.models.user import User
from app.services import plan as plan_service
from app.services.plan import PlanConflictError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

DAY = dt.date(2026, 11, 20)


async def _create_user(maker: async_sessionmaker) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with maker() as session:
        session.add(User(id=user_id, email=f"race-{user_id}@example.com", password_hash="x"))
        await session.commit()
    return user_id


async def _remove_user(maker: async_sessionmaker, user_id: uuid.UUID) -> None:
    async with maker() as session:
        await session.execute(delete(PlannedWorkout).where(PlannedWorkout.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def _count_on_day(maker: async_sessionmaker, user_id: uuid.UUID) -> int:
    async with maker() as session:
        return await session.scalar(
            select(func.count())
            .select_from(PlannedWorkout)
            .where(PlannedWorkout.user_id == user_id, PlannedWorkout.date == DAY)
        )


async def test_concurrent_rest_and_workout_on_same_day(test_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    user_id = await _create_user(maker)

    async def add_rest() -> str:
        async with maker() as session:
            try:
                await plan_service.create_rest(session, user_id, DAY)
                await session.commit()
                return "ok"
            except PlanConflictError:
                await session.rollback()
                return "conflict"

    async def add_workout() -> str:
        async with maker() as session:
            try:
                await plan_service.create_entry(session, user_id, DAY, name="День A")
                await session.commit()
                return "ok"
            except PlanConflictError:
                await session.rollback()
                return "conflict"

    try:
        results = await asyncio.gather(add_rest(), add_workout())
        # Ровно одна запись попадает в день; вторая получает понятный конфликт, а не дубль.
        assert sorted(results) == ["conflict", "ok"]
        assert await _count_on_day(maker, user_id) == 1
    finally:
        await _remove_user(maker, user_id)


async def test_concurrent_workouts_get_distinct_positions(test_engine: AsyncEngine) -> None:
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    user_id = await _create_user(maker)

    async def add_workout(name: str) -> int:
        async with maker() as session:
            entry = await plan_service.create_entry(session, user_id, DAY, name=name)
            await session.commit()
            return entry.position

    try:
        positions = await asyncio.gather(add_workout("A"), add_workout("B"), add_workout("C"))
        # Блокировка плана не даёт двум запросам прочитать одну и ту же «следующую» позицию.
        assert sorted(positions) == [0, 1, 2]
        assert await _count_on_day(maker, user_id) == 3
    finally:
        await _remove_user(maker, user_id)
