"""Five-minute community votes with durable identities and results."""

import secrets
import time

from storage.fun import load_state, update_state

CHOICES = {"legend": "Гей", "bore": "Негр"}
DURATION = 300


def counts(poll):
    return {choice: sum(vote == choice for vote in poll["votes"].values()) for choice in CHOICES}


def finish(state, poll):
    if poll["closed"]:
        return False
    result = counts(poll)
    poll["closed"] = True
    if result["legend"] == result["bore"]:
        poll["result"] = "tie" if sum(result.values()) else "empty"
    else:
        poll["result"] = max(result, key=result.get)
        person = state["people"].setdefault(poll["target"], {})
        # Later-ending rounds win even if old rounds are recovered after a restart.
        previous = person.get("verdict", {})
        if previous.get("until", 0) <= poll["until"]:
            person["verdict"] = {"choice": poll["result"], "name": poll["name"],
                                 "until": poll["until"], "counts": result}
    return True


def start(chat_id, message_id, identity, name):
    def create(state):
        polls = state["community"].setdefault("title_polls", {})
        for poll in polls.values():
            if poll["chat_id"] == chat_id and poll["target"] == str(identity) and not poll["closed"]:
                return False, poll
        # Completed polls can be discarded; permanent verdicts remain in people.
        completed = [token for token, poll in polls.items() if poll["reported"]]
        for token in completed[:-128]:
            del polls[token]
        token = secrets.token_hex(6)
        poll = {"token": token, "chat_id": chat_id, "source_id": message_id,
                "target": str(identity), "name": " ".join(name.split())[:80] or "Участник",
                "message_id": 0, "until": time.time() + DURATION, "votes": {},
                "closed": False, "reported": False}
        polls[token] = poll
        return True, poll
    return update_state(create)


def attach(token, message_id):
    def change(state):
        poll = state["community"]["title_polls"][token]
        poll["message_id"] = message_id
        return True, poll
    return update_state(change)


def vote(token, chat_id, identity, choice):
    if choice not in CHOICES:
        raise ValueError("Неизвестный вариант")
    def change(state):
        poll = state["community"].get("title_polls", {}).get(token)
        if not poll or poll["chat_id"] != chat_id:
            raise ValueError("Это голосование недоступно в этом чате")
        if poll["closed"] or poll["until"] <= time.time():
            raise ValueError("Голосование завершено. Итоги — /titles.")
        changed = poll["votes"].get(str(identity)) != choice
        poll["votes"][str(identity)] = choice
        return changed, poll
    return update_state(change)


def due(token):
    def change(state):
        poll = state["community"].get("title_polls", {}).get(token)
        if not poll or poll["reported"]:
            return False, None
        changed = finish(state, poll) if poll["until"] <= time.time() else False
        return changed, poll
    return update_state(change)


def mark_reported(token):
    def change(state):
        poll = state["community"]["title_polls"][token]
        if not poll["closed"]:
            finish(state, poll)
        poll["reported"] = True
        return True, None
    update_state(change)


def leaderboard():
    return sorted([(identity, person["verdict"]) for identity, person in load_state()["people"].items()
                   if "verdict" in person], key=lambda row: (row[1]["choice"], row[1]["name"].casefold(), row[0]))


def pending():
    return {token: (poll["until"] if poll["message_id"] and not poll["closed"] else 0)
            for token, poll in load_state()["community"].get("title_polls", {}).items() if not poll["reported"]}
