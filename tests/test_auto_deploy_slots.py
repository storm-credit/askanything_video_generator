from datetime import datetime, time

from modules.scheduler.auto_deploy import (
    _find_next_publish_slot,
    _merge_slot_reservations,
    _release_slot_reservation,
)
from modules.scheduler.time_planner import KST


def test_existing_reserved_slot_survives_current_item_release():
    """기존 예약과 새 배포 기본 슬롯이 겹치면 기존 예약을 보존하고 다음날로 민다."""
    current_slot = datetime(2026, 5, 6, 8, 0, tzinfo=KST)
    history_slots = {
        "wonderdrop": [
            current_slot,
            datetime(2026, 5, 6, 9, 15, tzinfo=KST),
            datetime(2026, 5, 6, 10, 30, tzinfo=KST),
        ]
    }
    current_schedule_slots = {"wonderdrop": [current_slot]}

    occupied = _merge_slot_reservations(history_slots, current_schedule_slots)
    _release_slot_reservation(occupied, "wonderdrop", current_slot)

    next_slot = _find_next_publish_slot("wonderdrop", current_slot, occupied)

    assert next_slot.date() == datetime(2026, 5, 7, tzinfo=KST).date()
    assert next_slot.time() == time(8, 0)
