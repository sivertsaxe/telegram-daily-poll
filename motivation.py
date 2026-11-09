"""Approved original German lines; not quotations attributed to David Goggins."""
import random
from datetime import date

QUOTE_DAYS = (1, 4)  # Tuesday and Friday, Europe/Berlin.
QUOTES = [
    'Motivation kommt und geht. Die {target} bleiben.',
    'Du musst nicht alle auf einmal schaffen. Aber anfangen musst du.',
    'Deine Ausrede hat heute schon mehr Wiederholungen als du.',
    'Der schwierigste Liegestütz ist der erste. Also bring ihn hinter dich.',
    'Heute durchziehen. Morgen froh sein, dass du es gemacht hast.',
    '{target} Liegestütze werden vom Nachdenken nicht weniger.',
    'Disziplin heißt: auch dann anfangen, wenn das Sofa gute Argumente hat.',
    'Die Liegestütze von heute kannst du morgen nicht mehr gestern machen.',
    'Du wartest auf Motivation? Mach schon mal zehn, solange du wartest.',
    'Der Boden ist da. Du bist da. Beste Voraussetzungen.',
    'Ein schlechter Tag kann trotzdem ein guter Trainingstag werden.',
    'Du musst heute keinen Rekord brechen. Nur dein Versprechen halten.',
    'Kleine Sätze. Kurze Pausen. Keine große Diskussion.',
    'Dein zukünftiges Ich wird dir danken. Dein Sofa wird es verkraften.',
    'Es wird nicht jeden Tag leichter. Aber du wirst stärker.',
    'Erst die Wiederholungen. Dann die Erfolgsgeschichte.',
    'Gemeinsam angefangen. Gemeinsam durchziehen. Bis zur JuWeiFei.',
    'Die Weihnachtsfeier kommt näher. Die Liegestütze machen sich nicht von allein.',
    'Auch zehn auf einmal bringen dich ans Ziel. Null auf einmal eher nicht.',
    'Motivation ist gut. Gemachte Liegestütze sind besser.',
]


def daily_target(day):
    # Only the confirmed increase; no unapproved monthly increases after December.
    return 130 if day >= date(2026, 12, 1) else 125


def choose_quote(state, day):
    """Persist the choice before sending, and exhaust a shuffled bag before repeats."""
    choices = state.setdefault('quote_choices', {})
    key = day.isoformat()
    if key not in choices:
        bag = state.setdefault('quote_bag', [])
        if not bag:
            bag.extend(range(len(QUOTES)))
            random.shuffle(bag)
            if bag[-1] == state.get('last_quote'):
                bag[0], bag[-1] = bag[-1], bag[0]
        choices[key] = bag.pop()
        state['last_quote'] = choices[key]
    return QUOTES[choices[key]].format(target=daily_target(day))
