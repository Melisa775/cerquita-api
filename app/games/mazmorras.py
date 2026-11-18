"""Mazmorras: a cooperative fantasy dungeon crawl with a d20.

The party (1 to 5 heroes) explores an adventure room by room. Rooms can
hold monsters (a turn-based fight), something to try (a check against a
difficulty), or both. Clearing the last room wins; if every hero falls in a
fight, the party loses.

The Dungeon Master is either the system ("auto": it narrates and plays the
monsters by itself) or one of the people in the room, who doesn't play a
hero and instead narrates, asks for checks, adds monsters, heals or hurts,
moves the party and chooses what each monster does.

Rolls: d20 + modifier (+2 if the class is good at it) against a number.
Attacks beat the target's armor (AC); checks and saves beat a difficulty
(CD). A natural 20 on an attack is a critical hit (double dice); a 1 misses.
"""

import random

from app.games.mazmorras_data import ADVENTURES, CLASSES, LEVEL_HP, LEVELS, MONSTERS, NARRATION, POWERS, PROFICIENCY

COMPANION_NAMES = ["Brama 🤖", "Lince 🤖", "Ortiga 🤖", "Sauce 🤖"]
MAX_HEROES = 5
REST_COUNT = 2
START_POTIONS = 2
LOG_SIZE = 40
# monster hit points by party size: a lone hero shouldn't face a full dragon
HP_SCALE = {1: 0.5, 2: 0.7, 3: 0.9, 4: 1.0, 5: 1.15}
DAMAGE_SCALE = {1: 0.5, 2: 0.75, 3: 0.9, 4: 1.0, 5: 1.0}


def d(rng, n, sides):
    return sum(rng.randint(1, sides) for _ in range(n))


class MazmorrasGame:
    name = "mazmorras"
    max_players = 6  # up to 5 heroes plus a person as Dungeon Master
    actions = {
        "mz_pick", "mz_move", "mz_feature", "mz_rest", "mz_potion",
        "mz_attack", "mz_power", "mz_defend", "mz_roll", "mz_skip",
        "mz_narrate", "mz_check", "mz_spawn", "mz_hp", "mz_give", "mz_monster",
    }

    def __init__(self, players, adventure="cripta", dm="auto", companions=0, rng=None, timings=None):
        if adventure not in ADVENTURES:
            raise ValueError("Esa aventura no existe")
        self.rng = rng or random.Random()
        self.adventure_key = adventure
        self.adventure = ADVENTURES[adventure]
        self.dm = dm  # "auto" or the name of the person who is the DM
        self.people = list(players)
        hero_people = [p for p in players if p != dm]
        taken = set(players)
        self.companions = [n for n in COMPANION_NAMES if n not in taken][:companions]
        self.hero_order = hero_people + self.companions
        if not self.hero_order:
            raise ValueError("Hace falta al menos un héroe")
        if len(self.hero_order) > MAX_HEROES:
            raise ValueError(f"Pueden jugar máximo {MAX_HEROES} héroes")
        self.heroes: dict[str, dict] = {}
        self.picks: dict[str, str | None] = {p: None for p in self.hero_order}
        self.phase = "idle"
        self.result: str | None = None  # "victory" or "defeat" once finished
        self.room = self.adventure["start"]
        self.visited = {self.room}
        self.cleared: set[str] = set()
        self.features_done: set[str] = set()
        self.potions = START_POTIONS
        self.items: list[str] = []
        self.rests = REST_COUNT
        self.monsters: list[dict] = []
        self.order: list[str] = []  # initiative: hero names and monster ids
        self.turn: str | None = None
        self.round = 0
        self.pending_check: dict | None = None
        self.log: list[dict] = []
        self.log_id = 0
        self.last_roll: dict | None = None
        self.roll_id = 0
        self._monster_seq = 0

    @classmethod
    def from_options(cls, players, options, rng, timings=None):
        adventure = options.get("adventure", "cripta")
        dm = options.get("dm", "auto") or "auto"
        if dm != "auto" and dm not in players:
            raise ValueError("El Dungeon Master tiene que estar en la sala")
        try:
            companions = int(options.get("companions", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Opciones no válidas") from exc
        if not 0 <= companions <= 4:
            raise ValueError("Pueden ser de 0 a 4 compañeros bot")
        return cls(players, adventure=adventure, dm=dm, companions=companions, rng=rng, timings=timings)

    # --- room interface -------------------------------------------------
    @property
    def in_progress(self):
        return self.phase not in ("idle", "finished")

    @property
    def timer_key(self):
        return None

    @property
    def timer_seconds(self):
        return None

    def on_timeout(self):
        pass

    def remove_player(self, player):
        pass

    def start(self):
        self.phase = "creating"
        # companions take the classes nobody else is likely to pick first
        for bot in self.companions:
            self._pick(bot, self._free_class())
        self._say("narr", self.adventure["intro"], sound="door")
        self._maybe_begin()

    # --- helpers --------------------------------------------------------
    def _say(self, kind, text, **extra):
        self.log_id += 1
        self.log.append({"id": self.log_id, "kind": kind, "text": text, **extra})
        del self.log[:-LOG_SIZE]

    def _line(self, key, **fields):
        return self.rng.choice(NARRATION[key]).format(**fields)

    def _roll(self, who, label, mod, target=None, kind="check", advantage=False):
        """A d20 roll that the clients animate. Returns (natural, total)."""
        nat = self.rng.randint(1, 20)
        if advantage:
            nat = max(nat, self.rng.randint(1, 20))
        total = nat + mod
        self.roll_id += 1
        ok = None if target is None else (nat != 1 and (nat == 20 or total >= target))
        self.last_roll = {"id": self.roll_id, "who": who, "label": label, "natural": nat, "mod": mod, "total": total, "target": target, "ok": ok, "kind": kind}
        return nat, total

    def _free_class(self):
        used = [c for c in self.picks.values() if c]
        return min(CLASSES, key=lambda c: (used.count(c), list(CLASSES).index(c)))

    def is_bot(self, name):
        return name in self.companions

    def hero_mod(self, hero, ability):
        cls = CLASSES[hero["cls"]]
        return cls["mods"][ability] + (PROFICIENCY if ability in cls["skills"] else 0)

    def attack_bonus(self, hero):
        cls = CLASSES[hero["cls"]]
        return cls["mods"][cls["weapon"]["ability"]] + PROFICIENCY + (1 if hero["level"] >= 3 else 0)

    def standing(self):
        return [h for h in self.heroes.values() if h["hp"] > 0]

    def alive_monsters(self):
        return [m for m in self.monsters if m["hp"] > 0]

    def monster(self, mid):
        m = next((m for m in self.monsters if m["id"] == mid), None)
        if not m or m["hp"] <= 0:
            raise ValueError("Ese enemigo ya no está")
        return m

    def hero(self, name):
        h = self.heroes.get(name)
        if not h:
            raise ValueError("Ese héroe no existe")
        return h

    # --- creating the party ---------------------------------------------
    def _pick(self, player, cls_key):
        if cls_key not in CLASSES:
            raise ValueError("Esa clase no existe")
        cls = CLASSES[cls_key]
        self.picks[player] = cls_key
        self.heroes[player] = {
            "name": player, "cls": cls_key, "hp": cls["hp"], "max_hp": cls["hp"], "ac": cls["ac"],
            "level": 1, "xp": 0, "slots": cls.get("slots", 0), "max_slots": cls.get("slots", 0),
            "aliento": True, "defending": False,
        }

    def _maybe_begin(self):
        if self.phase != "creating" or any(c is None for c in self.picks.values()):
            return
        self.heroes = {p: self.heroes[p] for p in self.hero_order}
        self.phase = "explore"
        self._enter(self.room, first=True)

    # --- exploring ------------------------------------------------------
    def _enter(self, room_id, first=False):
        room = self.adventure["rooms"][room_id]
        self.room = room_id
        self.visited.add(room_id)
        self._say("room", f"{room['name']}. {room['text']}", sound=None if first else "door", room=room_id)
        if room_id not in self.cleared:
            kinds = list(room["monsters"])
            if kinds:
                n = len(self.heroes)
                if n >= 4 and len(kinds) >= 2:
                    kinds.append(next(k for k in kinds if not MONSTERS[k].get("boss")))
                self._start_combat(kinds)
            else:
                self.cleared.add(room_id)

    def move(self, room_id):
        if self.phase != "explore":
            raise ValueError("Ahora no se pueden mover")
        room = self.adventure["rooms"][self.room]
        if room_id not in room["exits"]:
            raise ValueError("Por ahí no se puede ir")
        self.pending_check = None
        self._enter(room_id)

    def try_feature(self, player):
        if self.phase != "explore":
            raise ValueError("Primero terminen la pelea")
        feat = self.adventure["rooms"][self.room].get("feature")
        if not feat or self.room in self.features_done:
            raise ValueError("Aquí no queda nada por intentar")
        hero = self.hero(player)
        if hero["hp"] <= 0:
            raise ValueError("Estás sin fuerzas: alguien tiene que curarte")
        self.features_done.add(self.room)
        mod = self.hero_mod(hero, feat["ability"])
        nat, total = self._roll(player, feat["label"], mod, feat["dc"], kind=feat["ability"])
        ok = self.last_roll["ok"]
        self._say("roll", f"{player} intenta: {feat['label'].lower()} (CD {feat['dc']}). Saca {nat} {'+' if mod >= 0 else '-'} {abs(mod)} = {total}.", roll=self.roll_id, ok=ok)
        if ok:
            self._say("good", feat["success"], sound="good")
            reward = feat.get("reward", {})
            if reward.get("potion"):
                self.potions += reward["potion"]
            if reward.get("key"):
                self.items.append(reward["key"])
            if feat.get("heal_all"):
                for h in self.heroes.values():
                    self._heal(h, d(self.rng, *feat["heal_all"]))
        else:
            self._say("bad", feat["failure"], sound="bad")
            if feat.get("damage"):
                victims = self.standing() if feat.get("all") else [hero]
                for h in victims:
                    self._hurt(h, d(self.rng, *feat["damage"]))
                if not self.standing():
                    # a trap alone never ends the adventure: everyone gets up hurt
                    for h in self.heroes.values():
                        h["hp"] = 1

    def rest(self):
        if self.phase != "explore":
            raise ValueError("No pueden descansar en medio de una pelea")
        if self.rests <= 0:
            raise ValueError("Ya no les quedan descansos")
        self.rests -= 1
        for h in self.heroes.values():
            h["hp"] = min(h["max_hp"], max(h["hp"], 0) + (h["max_hp"] + 1) // 2)
            h["slots"] = min(h["max_slots"], h["slots"] + 1)
            h["aliento"] = True
        self._say("heal", f"Se sientan a descansar un rato. Recuperan vida y fuerzas. (Quedan {self.rests} descansos.)", sound="heal")

    # --- life -----------------------------------------------------------
    def _heal(self, hero, amount):
        was_down = hero["hp"] <= 0
        hero["hp"] = min(hero["max_hp"], max(hero["hp"], 0) + amount)
        if was_down and hero["hp"] > 0:
            self._say("heal", f"¡{hero['name']} se levanta!", sound="heal")
        return amount

    def _hurt(self, hero, amount):
        if hero["hp"] <= 0:
            return
        hero["hp"] = max(0, hero["hp"] - amount)
        if hero["hp"] == 0:
            hero["defending"] = False
            self._say("down", self._line("down", target=hero["name"]), sound="down")

    def use_potion(self, player, target):
        if self.potions <= 0:
            raise ValueError("No les quedan pociones")
        if self.phase == "combat" and self.turn != player:
            raise ValueError("Espera tu turno")
        hero = self.hero(player)
        if hero["hp"] <= 0:
            raise ValueError("Estás sin fuerzas")
        other = self.hero(target or player)
        if other["hp"] >= other["max_hp"]:
            raise ValueError(f"{other['name']} ya tiene la vida completa")
        self.potions -= 1
        amount = d(self.rng, 2, 4) + 2
        self._heal(other, amount)
        who = "se toma" if other is hero else f"le da a {other['name']}"
        self._say("heal", f"{player} {who} una poción: +{amount} de vida.", sound="heal")
        if self.phase == "combat":
            self._next_turn()

    # --- combat ---------------------------------------------------------
    def _new_monster(self, kind):
        data = MONSTERS[kind]
        n = len(self.heroes)
        self._monster_seq += 1
        hp = max(3, round(data["hp"] * HP_SCALE[n]))
        return {
            "id": f"m{self._monster_seq}", "kind": kind, "label": data["label"], "hp": hp, "max_hp": hp,
            "ac": data["ac"], "boss": bool(data.get("boss")), "look": data["look"], "turns": 0,
            "special": data.get("special") if data.get("weak_to") not in self.items else None,
        }

    def _name_monsters(self, monsters):
        counts = {}
        for m in self.monsters + monsters:
            counts[m["kind"]] = counts.get(m["kind"], 0) + 1
        seen = {}
        for m in self.monsters + monsters:
            data = MONSTERS[m["kind"]]
            if data.get("short"):
                m["name"] = data["short"]
            elif counts[m["kind"]] > 1:
                seen[m["kind"]] = seen.get(m["kind"], 0) + 1
                m["name"] = f"{data['label']} {seen[m['kind']]}"
            else:
                m["name"] = data["label"]

    def _start_combat(self, kinds):
        new = [self._new_monster(k) for k in kinds]
        self.monsters = new
        self._name_monsters([])
        if any(MONSTERS[m["kind"]].get("weak_to") in self.items for m in new):
            self._say("good", "La llave de hueso brilla: la corona se apaga y el Rey ya no puede usar su grito helado.", sound="good")
        inits = []
        for name, h in self.heroes.items():
            inits.append((self.rng.randint(1, 20) + CLASSES[h["cls"]]["mods"]["des"], 1, name))
        for m in new:
            inits.append((self.rng.randint(1, 20) + MONSTERS[m["kind"]]["dex"], 0, m["id"]))
        inits.sort(key=lambda x: (-x[0], -x[1]))
        self.order = [x[2] for x in inits]
        self.phase = "combat"
        self.round = 1
        for h in self.heroes.values():
            h["defending"] = False
        names = ", ".join(m["name"] for m in new)
        self._say("fight", f"¡A pelear! Aparecen: {names}. Tiran iniciativa…", sound="growl")
        self.turn = self.order[0]
        self._skip_downed()

    def spawn(self, kind):
        if kind not in MONSTERS:
            raise ValueError("Ese monstruo no existe")
        if self.phase == "explore":
            self.cleared.discard(self.room)
            self._start_combat([kind])
            return
        if self.phase != "combat":
            raise ValueError("Ahora no se pueden agregar monstruos")
        m = self._new_monster(kind)
        self._name_monsters([m])
        self.monsters.append(m)
        self.order.append(m["id"])
        self._say("fight", f"¡{m['name']} se une a la pelea!", sound="growl")

    def _is_monster(self, ident):
        return ident.startswith("m") and ident not in self.heroes

    def _skip_downed(self):
        """Moves past downed heroes and dead monsters."""
        for _ in range(len(self.order) + 1):
            t = self.turn
            if t in self.heroes and self.heroes[t]["hp"] <= 0:
                self._advance()
                continue
            if self._is_monster(t) and all(m["id"] != t or m["hp"] <= 0 for m in self.monsters):
                self._advance()
                continue
            break
        cur = self.heroes.get(self.turn)
        if cur:
            cur["defending"] = False

    def _advance(self):
        i = self.order.index(self.turn)
        if i + 1 >= len(self.order):
            self.round += 1
        self.turn = self.order[(i + 1) % len(self.order)]

    def _next_turn(self):
        if self._check_end():
            return
        # drop the dead from the order (but keep the current position)
        self._advance()
        alive = {m["id"] for m in self.alive_monsters()}
        keep = [x for x in self.order if x in self.heroes or x in alive or x == self.turn]
        self.order = keep
        self._skip_downed()

    def _check_end(self):
        if self.phase != "combat":
            return True
        if not self.alive_monsters():
            self._win_fight()
            return True
        if not self.standing():
            self._finish("defeat")
            self.turn = None
            self._say("end", "Todos los héroes cayeron. La oscuridad se los traga… Fin de la aventura.", sound="defeat")
            return True
        return False

    def _win_fight(self):
        xp = sum(MONSTERS[m["kind"]]["xp"] for m in self.monsters)
        share = xp  # every hero gets the whole fight's experience: it's a team effort
        self._say("good", self._line("victory") + f" Cada héroe gana {share} de experiencia.", sound="good")
        for h in self.heroes.values():
            h["defending"] = False
            if h["hp"] <= 0:
                h["hp"] = 1
                self._say("heal", f"{h['name']} se levanta, malherido.")
            h["xp"] += share
            while h["level"] < len(LEVELS) and h["xp"] >= LEVELS[h["level"]]:
                self._level_up(h)
        self.cleared.add(self.room)
        self.monsters = []
        self.order = []
        self.turn = None
        if self.adventure["rooms"][self.room].get("final"):
            self._finish("victory")
            self._say("end", "¡Lo lograron! La aventura terminó y el pueblo celebrará su nombre por años.", sound="victory")
        else:
            self.phase = "explore"

    def _finish(self, result):
        self.phase = "finished"
        self.result = result
        self.turn = None

    def _level_up(self, h):
        h["level"] += 1
        gain = LEVEL_HP[h["cls"]]
        h["max_hp"] += gain
        h["hp"] = h["max_hp"]  # leveling up feels great: back to full health
        if h["max_slots"]:
            h["max_slots"] += 1
            h["slots"] += 1
        extra = " Ahora pega más fuerte." if h["level"] == 3 else ""
        self._say("level", f"⭐ ¡{h['name']} sube a nivel {h['level']}! +{gain} de vida máxima y se recupera por completo.{extra}", sound="levelup")

    def _need_turn(self, player):
        if self.phase != "combat":
            raise ValueError("No hay pelea")
        if self.turn != player:
            raise ValueError("Espera tu turno")
        hero = self.hero(player)
        if hero["hp"] <= 0:
            raise ValueError("Estás sin fuerzas")
        return hero

    def _weapon_damage(self, hero, crit):
        cls = CLASSES[hero["cls"]]
        n, sides = cls["weapon"]["dice"]
        dmg = d(self.rng, n * (2 if crit else 1), sides) + cls["mods"][cls["weapon"]["ability"]] + (1 if hero["level"] >= 3 else 0)
        if hero["cls"] == "picaro" and len(self.standing()) > 1:
            dmg += d(self.rng, (2 if hero["level"] >= 3 else 1) * (2 if crit else 1), 6)
        return max(1, dmg)

    def _damage_monster(self, m, dmg):
        m["hp"] = max(0, m["hp"] - dmg)
        if m["hp"] == 0:
            self._say("kill", self._line("kill", target=m["name"]), sound="kill")

    def attack(self, player, target):
        hero = self._need_turn(player)
        m = self.monster(target)
        weapon = CLASSES[hero["cls"]]["weapon"]["name"].lower()
        bonus = self.attack_bonus(hero)
        nat, total = self._roll(player, f"Ataque a {m['name']}", bonus, m["ac"], kind="attack")
        sound = "spell" if hero["cls"] == "mago" else "sword"
        if self.last_roll["ok"]:
            crit = nat == 20
            dmg = self._weapon_damage(hero, crit)
            self._say("hit", self._line("crit" if crit else "hit", who=player, target=m["name"], weapon=weapon, dmg=dmg), sound=sound, roll=self.roll_id)
            self._damage_monster(m, dmg)
        else:
            self._say("miss", self._line("miss", who=player, target=m["name"], weapon=weapon), sound="miss", roll=self.roll_id)
        self._next_turn()

    def power(self, player, power, target):
        hero = self._need_turn(player)
        cls = CLASSES[hero["cls"]]
        if power not in cls["powers"] or POWERS[power]["uses"] == "passive":
            raise ValueError("Tu clase no tiene ese poder")
        info = POWERS[power]
        if info["uses"] == "slot" and hero["slots"] <= 0:
            raise ValueError("No te quedan usos de magia: descansen para recuperarlos")
        if info["uses"] == "rest" and not hero["aliento"]:
            raise ValueError("Ya lo usaste: descansen para recuperarlo")
        label = info["label"]
        if power == "segundo_aliento":
            hero["aliento"] = False
            amount = d(self.rng, 1, 10) + hero["level"]
            self._heal(hero, amount)
            self._say("heal", f"{player} respira hondo y recupera {amount} de vida.", sound="heal")
        elif power == "proyectil_magico":
            m = self.monster(target)
            hero["slots"] -= 1
            dmg = sum(d(self.rng, 1, 4) + 1 for _ in range(3))
            self._say("hit", f"Tres dardos de luz salen de las manos de {player} y golpean a {m['name']}: {dmg} de daño.", sound="spell")
            self._damage_monster(m, dmg)
        elif power == "ola_de_trueno":
            hero["slots"] -= 1
            self._say("hit", f"¡BUUUM! {player} libera una ola de trueno.", sound="thunder")
            for m in self.alive_monsters():
                dmg = d(self.rng, 2, 8)
                saved = self.rng.randint(1, 20) >= 13
                dmg = dmg // 2 if saved else dmg
                self._say("hit", f"{m['name']} recibe {dmg} de daño{' (resiste a medias)' if saved else ''}.")
                self._damage_monster(m, dmg)
        elif power == "llama_sagrada":
            m = self.monster(target)
            nat, total = self._roll(m["name"], "Salvación de Destreza", MONSTERS[m["kind"]]["dex"], 13, kind="save")
            if self.last_roll["ok"]:
                self._say("miss", f"La llama sagrada de {player} baja del cielo, pero {m['name']} la esquiva.", sound="spell", roll=self.roll_id)
            else:
                dmg = d(self.rng, 2 if hero["level"] >= 3 else 1, 8)
                self._say("hit", f"Una columna de luz cae sobre {m['name']}: {dmg} de daño.", sound="spell", roll=self.roll_id)
                self._damage_monster(m, dmg)
        elif power == "curar_heridas":
            other = self.hero(target or player)
            if other["hp"] >= other["max_hp"]:
                raise ValueError(f"{other['name']} ya tiene la vida completa")
            hero["slots"] -= 1
            amount = d(self.rng, 1, 8) + 3
            self._heal(other, amount)
            whom = "se cura" if other is hero else f"cura a {other['name']}"
            self._say("heal", f"{player} {whom}: +{amount} de vida.", sound="heal")
        self._next_turn()

    def defend(self, player):
        hero = self._need_turn(player)
        hero["defending"] = True
        self._say("info", f"{player} se pone en guardia (+3 de armadura hasta su próximo turno).", sound="shield")
        self._next_turn()

    def monster_turn(self, target=None):
        if self.phase != "combat" or not self.turn or not self._is_monster(self.turn):
            raise ValueError("No es el turno de un monstruo")
        m = self.monster(self.turn)
        data = MONSTERS[m["kind"]]
        m["turns"] += 1
        heroes = self.standing()
        scale = DAMAGE_SCALE[len(self.heroes)]
        special = m.get("special")
        if special and m["turns"] % special["every"] == 0:
            self._say("fight", f"¡{m['name']} usa {special['name']}!", sound="roar")
            for h in heroes:
                save = self.hero_mod(h, special["save"])
                nat, total = self._roll(h["name"], f"Salvación ({special['save'].upper()})", save, special["dc"], kind="save")
                dmg = max(1, round(d(self.rng, *special["dice"]) * scale))
                if self.last_roll["ok"]:
                    dmg //= 2
                self._say("hurt", f"{h['name']} recibe {dmg} de daño{' (se cubre a tiempo: la mitad)' if self.last_roll['ok'] else ''}.", roll=self.roll_id)
                self._hurt(h, dmg)
            self._next_turn()
            return
        if target:
            h = self.hero(target)
            if h["hp"] <= 0:
                raise ValueError(f"{h['name']} ya está en el suelo")
        else:
            # the weakest-looking hero draws most attacks, but not always
            h = min(heroes, key=lambda x: x["hp"] / x["max_hp"] + self.rng.random() * 0.8)
        ac = h["ac"] + (3 if h["defending"] else 0)
        nat, total = self._roll(m["name"], f"Ataque a {h['name']}", data["attack"], ac, kind="attack")
        if self.last_roll["ok"]:
            n, sides = data["dice"]
            dmg = max(1, round((d(self.rng, n * (2 if nat == 20 else 1), sides) + data["bonus"]) * scale))
            self._say("hurt", self._line("monster_hit", who=m["name"], target=h["name"], dmg=dmg), sound="hurt", roll=self.roll_id)
            self._hurt(h, dmg)
        else:
            self._say("miss", self._line("monster_miss", who=m["name"], target=h["name"]), sound="shield" if h["defending"] else "miss", roll=self.roll_id)
        self._next_turn()

    def skip(self, player):
        if self.phase != "combat" or not self.turn:
            raise ValueError("No hay turno que saltar")
        if self.turn in self.heroes:
            self._say("info", f"{self.turn} deja pasar su turno.")
        self._next_turn()

    # --- checks asked by a person DM --------------------------------------
    def ask_check(self, hero_name, ability, dc, reason):
        h = self.hero(hero_name)
        if ability not in CLASSES[h["cls"]]["mods"]:
            raise ValueError("Esa habilidad no existe")
        try:
            dc = int(dc)
        except (TypeError, ValueError) as exc:
            raise ValueError("La dificultad es un número") from exc
        if not 5 <= dc <= 25:
            raise ValueError("La dificultad va de 5 a 25")
        reason = str(reason or "").strip()[:80]
        self.pending_check = {"hero": hero_name, "ability": ability, "dc": dc, "reason": reason}
        self._say("dm", f"El DM le pide a {hero_name} una tirada de {ability.upper()} (CD {dc}){': ' + reason if reason else ''}.")

    def roll_check(self, player):
        c = self.pending_check
        if not c or c["hero"] != player:
            raise ValueError("No tienes ninguna tirada pendiente")
        h = self.hero(player)
        mod = self.hero_mod(h, c["ability"])
        nat, total = self._roll(player, c["reason"] or f"Tirada de {c['ability'].upper()}", mod, c["dc"], kind=c["ability"])
        ok = self.last_roll["ok"]
        self.pending_check = None
        self._say("roll", f"{player} tira {c['ability'].upper()}: {nat} {'+' if mod >= 0 else '-'} {abs(mod)} = {total} contra CD {c['dc']}. {'¡Lo logra!' if ok else 'No lo logra.'}", roll=self.roll_id, ok=ok, sound="good" if ok else "bad")

    # --- messages -------------------------------------------------------
    def handle(self, player, msg):
        kind = msg.get("type")
        if self.phase == "finished":
            raise ValueError("La aventura ya terminó")
        if kind in {"mz_narrate", "mz_check", "mz_spawn", "mz_hp", "mz_give", "mz_monster"}:
            if player != self.dm:
                raise ValueError("Eso solo lo puede hacer el Dungeon Master")
            self._dm_action(kind, msg)
            return
        if kind == "mz_move" and player == self.dm:
            self.move(msg.get("room"))
            return
        if kind == "mz_skip" and (player == self.dm or self.dm == "auto"):
            self.skip(player)
            return
        if player not in self.heroes and player not in self.picks:
            raise ValueError("No tienes héroe en esta aventura")
        if kind == "mz_pick":
            if self.phase != "creating":
                raise ValueError("Los héroes ya están listos")
            self._pick(player, msg.get("cls"))
            self._maybe_begin()
            return
        if self.phase == "creating":
            raise ValueError("Primero elijan sus héroes")
        if kind == "mz_move":
            self.move(msg.get("room"))
        elif kind == "mz_feature":
            self.try_feature(player)
        elif kind == "mz_rest":
            self.rest()
        elif kind == "mz_potion":
            self.use_potion(player, msg.get("target"))
        elif kind == "mz_attack":
            self.attack(player, msg.get("target"))
        elif kind == "mz_power":
            self.power(player, msg.get("power"), msg.get("target"))
        elif kind == "mz_defend":
            self.defend(player)
        elif kind == "mz_roll":
            self.roll_check(player)
        else:
            raise ValueError("Acción desconocida")

    def _dm_action(self, kind, msg):
        if self.phase == "creating" and kind != "mz_narrate":
            raise ValueError("Esperen a que todos elijan su héroe")
        if kind == "mz_narrate":
            text = str(msg.get("text") or "").strip()[:300]
            if not text:
                raise ValueError("Escribe qué pasa")
            self._say("dm", text, sound="page")
        elif kind == "mz_check":
            self.ask_check(msg.get("hero"), msg.get("ability"), msg.get("dc"), msg.get("reason"))
        elif kind == "mz_spawn":
            self.spawn(msg.get("monster"))
        elif kind == "mz_hp":
            h = self.hero(msg.get("hero"))
            try:
                amount = int(msg.get("amount"))
            except (TypeError, ValueError) as exc:
                raise ValueError("La cantidad es un número") from exc
            if not -30 <= amount <= 30 or amount == 0:
                raise ValueError("Entre -30 y 30")
            if amount > 0:
                self._heal(h, amount)
                self._say("heal", f"El DM cura a {h['name']}: +{amount} de vida.", sound="heal")
            else:
                self._say("hurt", f"{h['name']} recibe {-amount} de daño.", sound="hurt")
                self._hurt(h, -amount)
                if self.phase == "combat":
                    self._check_end()
                elif not self.standing():
                    self._finish("defeat")
                    self._say("end", "Todos los héroes cayeron. Fin de la aventura.", sound="defeat")
        elif kind == "mz_give":
            self.potions += 1
            self._say("good", "El DM les da una poción de curación.", sound="good")
        elif kind == "mz_monster":
            target = msg.get("target")
            self.monster_turn(None if target in (None, "", "auto") else target)

    # --- the automatic DM and the companions --------------------------------
    def bot_move(self):
        """(actor, message) for the next automatic action, or None."""
        from app.games.mazmorras_bot import next_move

        return next_move(self)

    def play_bot(self) -> bool:
        move = self.bot_move()
        if not move:
            return False
        actor, msg = move
        try:
            if actor == "auto":
                self._dm_action(msg["type"], msg)
            else:
                self.handle(actor, msg)
        except ValueError:
            # never get stuck: a refused move becomes a skipped turn
            if self.phase == "combat":
                self._next_turn()
            elif self.pending_check and self.pending_check["hero"] == actor:
                self.pending_check = None
            else:
                return False
        return True

    # --- state ----------------------------------------------------------
    def snapshot(self, viewer=None):
        rooms = []
        for rid, r in self.adventure["rooms"].items():
            seen = rid in self.visited
            feat = r.get("feature")
            rooms.append({
                "id": rid, "pos": r["pos"], "size": r["size"], "exits": r["exits"], "final": bool(r.get("final")),
                "visited": seen, "cleared": rid in self.cleared,
                "name": r["name"] if seen else None,
                "feature": {"label": feat["label"], "kind": feat["kind"], "ability": feat["ability"], "dc": feat["dc"], "done": rid in self.features_done} if feat and seen else None,
            })
        heroes = []
        for name in self.hero_order:
            h = self.heroes.get(name)
            if not h:
                heroes.append({"name": name, "cls": None, "bot": self.is_bot(name)})
                continue
            cls = CLASSES[h["cls"]]
            nxt = LEVELS[h["level"]] if h["level"] < len(LEVELS) else None
            heroes.append({
                "name": name, "cls": h["cls"], "label": cls["label"], "hp": h["hp"], "maxHp": h["max_hp"], "ac": h["ac"] + (3 if h["defending"] else 0),
                "level": h["level"], "xp": h["xp"], "nextXp": nxt, "slots": h["slots"], "maxSlots": h["max_slots"],
                "aliento": h["aliento"], "defending": h["defending"], "down": h["hp"] <= 0, "bot": self.is_bot(name),
                "attack": self.attack_bonus(h), "weapon": cls["weapon"]["name"],
                "mods": {a: self.hero_mod(h, a) for a in cls["mods"]},
                "powers": [p for p in cls["powers"]],
            })
        return {
            "name": self.name,
            "phase": self.phase,
            "result": self.result,
            "players": self.hero_order,
            "options": {"adventure": self.adventure_key, "dm": self.dm, "companions": len(self.companions)},
            "adventure": {"key": self.adventure_key, "title": self.adventure["title"], "intro": self.adventure["intro"]},
            "dm": self.dm,
            "isDm": viewer is not None and viewer == self.dm,
            "me": viewer if viewer in self.picks else None,
            "picks": self.picks,
            "rooms": rooms,
            "room": self.room,
            "roomText": self.adventure["rooms"][self.room]["text"],
            "heroes": heroes,
            "monsters": [{"id": m["id"], "name": m["name"], "kind": m["kind"], "hp": m["hp"], "maxHp": m["max_hp"], "ac": m["ac"], "look": m["look"], "boss": m["boss"]} for m in self.monsters],
            "order": self.order,
            "turn": self.turn,
            "round": self.round,
            "potions": self.potions,
            "items": self.items,
            "rests": self.rests,
            "pendingCheck": self.pending_check,
            "log": self.log[-30:],
            "lastRoll": self.last_roll,
        }
