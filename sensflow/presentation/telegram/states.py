"""FSM state groups for multi-step Telegram conversations."""

from aiogram.fsm.state import State, StatesGroup


class CreateOrderStates(StatesGroup):
    username = State()
    requested_robux = State()
    place_selection = State()
    manual_place_id = State()
    duplicate_confirmation = State()


class OrderSearchStates(StatesGroup):
    query = State()


class DraftEditStates(StatesGroup):
    requested_robux = State()
    place_id = State()


class CustomerSearchStates(StatesGroup):
    query = State()


class CustomerPlaceIDStates(StatesGroup):
    place_id = State()


class SettingsEditStates(StatesGroup):
    value = State()
