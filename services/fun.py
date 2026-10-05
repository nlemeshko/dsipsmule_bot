"""Community mechanics, without LLM calls or Telegram delivery."""

import random
import re
import secrets
import time
from datetime import datetime, timezone

from storage.fun import load_state, update_state

MOODS = {
    "angry": ("Злой дед", "Ворчи и отвечай язвительно, с короткими колкими панчами."),
    "tired": ("После репетиции", "Ты устал после репетиции: сухой юмор, ленивое ворчание, без яростных тирад."),
    "lyutik": ("Лютик украл микрофон", "Ты театрально возмущён пропажей микрофона: музыкальные шутки и саркастичные диссы."),
}
PASSPORT_TITLES = ("Баритон местного значения", "Покоритель соседских нервов", "Голос последнего дубля",
                   "Почётный будильник сквада", "Легенда ванной комнаты", "Вокальный ведьмак")
PASSPORT_DETAILS = ("Талант: брать ноты, которые ещё не изобрели.", "Талант: превращать один дубль в семь.",
                    "Талант: держать микрофон увереннее, чем тональность.", "Талант: выходить на бис даже из душа.")
ORDERS = (("Орден героического припева", "За отвагу перед высокой нотой."),
          ("Орден семи дублей", "За упорство, которое не выдержал даже микрофон."),
          ("Орден соседского терпения", "За музыкальные подвиги после десяти вечера."),
          ("Орден золотого дуэта", "За способность вытащить напарника из вокального болота."),
          ("Орден дедовского одобрения", "За редкий случай, когда Ведьмак перестал ворчать."))
RIDDLES = (
    ("🤍🌹🌹", "Белые розы", "Юрий Шатунов"),
    ("⭐📛☀️", "Звезда по имени Солнце", "Группа «Кино»"),
    ("🐦🌲⏳", "Кукушка", "Песня Виктора Цоя, которую также исполняла Полина Гагарина"),
    ("🌾🇷🇺", "Полюшко-поле", "Песня о широком русском поле"),
    ("🌲❄️🎄", "В лесу родилась ёлочка", "Новогодняя песня"),
    ("🐎🐎🐎⚪", "Три белых коня", "Песня из фильма «Чародеи»"),
    ("🌊🚢🌬️", "Ветер с моря дул", "Натали"),
    ("🎸🩸👕", "Группа крови", "Группа «Кино»"),
    ("💃🧊🔥", "Тает лёд", "Группа «Грибы»"),
    ("🧒🌼💔", "Ромашки", "Земфира"),
    ("👑🤡🌲", "Лесник", "Группа «Король и Шут»"),
    ("🌃🐴🌾", "Конь", "Группа «Любэ»"),
)
DED_PATTERN = re.compile(r"\b(?:дед|деда|деду|дедом|деды|дедушка|дедуля|дедули|дедулю)\b", re.IGNORECASE)
_mood_cache = None


def permanent_card(identity, name, kind):
    if kind not in {"passport", "order"}:
        raise ValueError("Unknown card")

    def issue(state):
        person = state["people"].setdefault(str(identity), {})
        if kind in person:
            return False, person[kind]
        title, detail = ((random.choice(PASSPORT_TITLES), random.choice(PASSPORT_DETAILS))
                         if kind == "passport" else random.choice(ORDERS))
        person[kind] = {"number": secrets.token_hex(4).upper(), "name": name[:100], "title": title,
                        "detail": detail, "issued": datetime.now(timezone.utc).strftime("%d.%m.%Y")}
        return True, person[kind]

    return update_state(issue)


def ded_status():
    count = load_state()["community"].get("ded", {}).get("count", 0)
    return {"count": count, "anger": ((count - 1) % 10 + 1) * 10 if count else 0}


def mention_ded(chat_id, message_id):
    def increment(state):
        ded = state["community"].setdefault("ded", {"count": 0, "seen": []})
        key = f"{chat_id}:{message_id}"
        if key in ded["seen"]:
            return False, None
        ded["seen"] = (ded["seen"] + [key])[-256:]
        ded["count"] += 1
        return True, ded["count"]

    return update_state(increment)


def mood_result(mood, now=None):
    now = time.time() if now is None else now
    if not mood or mood["until"] <= now:
        return {"active": False, "mode": "angry", "votes": {}, "until": 0}
    counts = {key: sum(choice == key for choice in mood["votes"].values()) for key in MOODS}
    winner = max(counts, key=lambda key: (counts[key], key == mood.get("mode", "angry")))
    return {**mood, "active": True, "mode": winner, "counts": counts}


def open_mood():
    def open_round(state):
        mood = mood_result(state["community"].get("mood"))
        if mood["active"]:
            return False, mood
        mood = {"token": secrets.token_hex(4), "until": time.time() + 3600, "votes": {}, "mode": "angry"}
        state["community"]["mood"] = mood
        return True, mood_result(mood)

    return update_state(open_round)


def vote_mood(identity, token, mode):
    if mode not in MOODS:
        raise ValueError("Неизвестное настроение")

    def vote(state):
        mood = state["community"].get("mood")
        if not mood or mood["token"] != token or not mood_result(mood)["active"]:
            raise ValueError("Голосование завершено. Открой /mood заново.")
        changed = mood["votes"].get(str(identity)) != mode
        mood["votes"][str(identity)] = mode
        result = mood_result(mood)
        mood["mode"] = result["mode"]
        return changed, result

    result = update_state(vote)
    invalidate_mood()
    return result


def invalidate_mood():
    global _mood_cache
    _mood_cache = None


def mood_instruction():
    global _mood_cache
    if _mood_cache is None or time.monotonic() >= _mood_cache[0]:
        _mood_cache = (time.monotonic() + 15, load_state()["community"].get("mood"))
    result = mood_result(_mood_cache[1])
    return MOODS[result["mode"]][1] if result["active"] else ""


def normalize_answer(text):
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower().replace("ё", "е")).split())


def start_guess(chat_id):
    def start(state):
        game = state["games"].get(str(chat_id))
        if game and game["until"] > time.time() and not game.get("finished"):
            return False, game
        emoji, answer, hint = random.choice(RIDDLES)
        game = {"token": secrets.token_hex(4), "emoji": emoji, "answer": answer, "hint": hint,
                "until": time.time() + 180, "finished": False}
        state["games"][str(chat_id)] = game
        return True, game

    return update_state(start)


def guess_game(chat_id):
    return load_state()["games"].get(str(chat_id))


def solve_guess(chat_id, text, identity, name):
    def solve(state):
        game = state["games"].get(str(chat_id))
        if not game or game.get("finished"):
            return False, {"status": "none"}
        if game["until"] <= time.time():
            return False, {"status": "expired", "answer": game["answer"]}
        if normalize_answer(text) != normalize_answer(game["answer"]):
            return False, {"status": "wrong", "game": game}
        game.update(finished=True, winner=str(identity), winner_name=name[:100])
        person = state["people"].setdefault(str(identity), {})
        person["guess_wins"] = person.get("guess_wins", 0) + 1
        return True, {"status": "won", "answer": game["answer"]}

    return update_state(solve)


def guess_button(chat_id, token, action):
    def apply(state):
        game = state["games"].get(str(chat_id))
        if not game or game["token"] != token or game.get("finished") or game["until"] <= time.time():
            raise ValueError("Раунд завершён. Открой /guess заново.")
        if action == "hint":
            return False, game
        if action == "end":
            game["finished"] = True
            return True, game
        raise ValueError("Неизвестная кнопка")

    return update_state(apply)
