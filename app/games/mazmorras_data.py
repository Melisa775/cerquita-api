"""Content for Mazmorras: classes, monsters and the adventures.

The rules are an original, simplified take on classic d20 fantasy role-play
(roll a d20, add a modifier, beat a number). Everything here is written for
Cerquita; no text is taken from any published game.
"""

ABILITIES = {
    "fue": "Fuerza",
    "des": "Destreza",
    "con": "Constitución",
    "int": "Inteligencia",
    "sab": "Sabiduría",
    "car": "Carisma",
}

PROFICIENCY = 2  # added to attacks and to the checks a class is good at

# Each class: hit points, armor, ability modifiers, its weapon and its powers.
CLASSES = {
    "guerrero": {
        "label": "Guerrero",
        "hp": 14,
        "ac": 16,
        "mods": {"fue": 3, "des": 1, "con": 2, "int": -1, "sab": 0, "car": 0},
        "skills": ["fue", "con"],
        "weapon": {"name": "Espada larga", "ability": "fue", "dice": [1, 8]},
        "powers": ["segundo_aliento"],
        "blurb": "Aguanta golpes y los devuelve con fuerza. Puede recuperarse en medio de la pelea.",
    },
    "mago": {
        "label": "Mago",
        "hp": 9,
        "ac": 12,
        "mods": {"fue": -1, "des": 2, "con": 1, "int": 3, "sab": 1, "car": 0},
        "skills": ["int", "sab"],
        "weapon": {"name": "Rayo de fuego", "ability": "int", "dice": [1, 10]},
        "powers": ["proyectil_magico", "ola_de_trueno"],
        "slots": 2,
        "blurb": "Poca vida y mucho poder: proyectiles que nunca fallan y una ola de trueno contra grupos.",
    },
    "picaro": {
        "label": "Pícaro",
        "hp": 10,
        "ac": 14,
        "mods": {"fue": 0, "des": 3, "con": 1, "int": 1, "sab": 0, "car": 2},
        "skills": ["des", "int", "car"],
        "weapon": {"name": "Daga", "ability": "des", "dice": [1, 6]},
        "powers": ["ataque_furtivo"],
        "blurb": "Rápido y certero: hace daño extra cuando alguien más distrae al enemigo, y es experto en trampas y cerraduras.",
    },
    "clerigo": {
        "label": "Clérigo",
        "hp": 11,
        "ac": 16,
        "mods": {"fue": 1, "des": 0, "con": 2, "int": 0, "sab": 3, "car": 1},
        "skills": ["sab", "car"],
        "weapon": {"name": "Maza", "ability": "fue", "dice": [1, 6]},
        "powers": ["curar_heridas", "llama_sagrada"],
        "slots": 2,
        "blurb": "Cura a sus compañeros (incluso si cayeron) y castiga con luz sagrada.",
    },
}

POWERS = {
    "segundo_aliento": {"label": "Segundo aliento", "uses": "rest", "text": "Recuperas 1d10 + tu nivel de vida. Una vez por descanso."},
    "proyectil_magico": {"label": "Proyectil mágico", "uses": "slot", "text": "Tres dardos de luz que nunca fallan: 3 × (1d4 + 1) de daño a un enemigo."},
    "ola_de_trueno": {"label": "Ola de trueno", "uses": "slot", "text": "Un estallido que golpea a todos los enemigos: 2d8 de daño (la mitad si superan una salvación de Constitución)."},
    "ataque_furtivo": {"label": "Ataque furtivo", "uses": "passive", "text": "Si hay otro héroe en pie en la pelea, tus ataques hacen 1d6 extra (2d6 desde el nivel 3)."},
    "curar_heridas": {"label": "Curar heridas", "uses": "slot", "text": "Tocas a un aliado (o a ti) y recupera 1d8 + 3. Levanta a quien haya caído."},
    "llama_sagrada": {"label": "Llama sagrada", "uses": "free", "text": "Luz que baja del cielo: el enemigo hace una salvación de Destreza (CD 13) o recibe 1d8. No necesita tirada de ataque."},
}

LEVELS = [0, 100, 250]  # XP to reach levels 1, 2 and 3
LEVEL_HP = {"guerrero": 8, "mago": 5, "picaro": 6, "clerigo": 7}

# Monsters: hit points, armor, attack bonus, damage dice + bonus, XP, look.
MONSTERS = {
    "rata": {"label": "Rata gigante", "hp": 7, "ac": 12, "attack": 4, "dice": [1, 4], "bonus": 2, "xp": 25, "dex": 2, "look": "rat"},
    "goblin": {"label": "Goblin", "hp": 7, "ac": 13, "attack": 4, "dice": [1, 6], "bonus": 2, "xp": 50, "dex": 2, "look": "goblin"},
    "lobo": {"label": "Lobo", "hp": 11, "ac": 13, "attack": 4, "dice": [2, 4], "bonus": 2, "xp": 50, "dex": 2, "look": "wolf"},
    "esqueleto": {"label": "Esqueleto", "hp": 13, "ac": 13, "attack": 4, "dice": [1, 6], "bonus": 2, "xp": 50, "dex": 2, "look": "skeleton"},
    "cultista": {"label": "Cultista", "hp": 9, "ac": 12, "attack": 3, "dice": [1, 6], "bonus": 1, "xp": 25, "dex": 1, "look": "cultist"},
    "limo": {"label": "Limo ácido", "hp": 22, "ac": 8, "attack": 3, "dice": [2, 6], "bonus": 0, "xp": 100, "dex": -2, "look": "slime"},
    "arana": {"label": "Araña gigante", "hp": 26, "ac": 14, "attack": 5, "dice": [1, 8], "bonus": 3, "xp": 200, "dex": 3, "look": "spider"},
    "ogro": {"label": "Ogro", "hp": 45, "ac": 11, "attack": 6, "dice": [2, 8], "bonus": 4, "xp": 450, "dex": -1, "look": "ogre"},
    "rey_esqueleto": {"label": "El Rey Olvidado", "hp": 75, "ac": 15, "attack": 5, "dice": [2, 6], "bonus": 3, "xp": 700, "dex": 1, "look": "lich", "boss": True, "short": "El Rey Olvidado", "weak_to": "llave_hueso",
                      "special": {"name": "Grito helado", "every": 3, "dice": [3, 6], "save": "con", "dc": 13}},
    "dragon": {"label": "Escamarroja, el dragón joven", "hp": 80, "ac": 16, "attack": 6, "dice": [2, 8], "bonus": 3, "xp": 1100, "dex": 0, "look": "dragon", "boss": True, "short": "Escamarroja",
               "special": {"name": "Aliento de fuego", "every": 3, "dice": [5, 6], "save": "des", "dc": 13}},
}

# Adventures: rooms on a grid (x, z in tiles; w, d size), connected by doors.
# A feature is something to try once: a check (ability + CD) with what
# happens on success and on failure.
ADVENTURES = {
    "cripta": {
        "title": "La cripta del Rey Olvidado",
        "intro": "Hace siglos enterraron a un rey cruel bajo la colina. Desde hace un mes, los muertos del pueblo no descansan. El alcalde les pide bajar a la cripta y terminar con lo que sea que despertó allá abajo.",
        "start": "entrada",
        "rooms": {
            "entrada": {
                "name": "La escalera rota", "pos": [0, 6], "size": [4, 3], "exits": ["sala_ratas", "pasillo"],
                "text": "Los escalones de piedra bajan hacia la oscuridad. Huele a tierra húmeda y a algo más viejo. Sus antorchas iluminan dos caminos: un hueco que se oye lleno de chillidos y un pasillo largo.",
                "monsters": [],
                "feature": {"kind": "sign", "label": "Leer las runas de la pared", "ability": "int", "dc": 10,
                            "success": "Las runas advierten: «Quien toque la corona sin la llave de hueso, despertará la escarcha». Mejor recordarlo.",
                            "failure": "Las runas están demasiado gastadas. Solo entienden la palabra «corona»."},
            },
            "sala_ratas": {
                "name": "El osario", "pos": [-5, 6], "size": [4, 4], "exits": ["entrada", "capilla"],
                "text": "Montañas de huesos cubren el suelo… y algo se mueve debajo de ellos.",
                "monsters": ["rata", "rata"],
                "feature": {"kind": "chest", "label": "Revisar el cofre entre los huesos", "ability": "des", "dc": 12,
                            "success": "El cofre se abre sin ruido: dentro hay una poción de curación.", "reward": {"potion": 1},
                            "failure": "Una aguja salta de la cerradura.", "damage": [1, 6]},
            },
            "pasillo": {
                "name": "El pasillo de las estatuas", "pos": [5, 6], "size": [5, 3], "exits": ["entrada", "guardia"],
                "text": "Estatuas de guerreros sin cara flanquean el pasillo. Una baldosa del centro está un poco más alta que las otras.",
                "monsters": [],
                "feature": {"kind": "trap", "label": "Buscar trampas", "ability": "sab", "dc": 12,
                            "success": "Ven el mecanismo a tiempo y lo traban con una daga. Pasan sin problema.",
                            "failure": "¡Clic! Una lluvia de dardos sale de las estatuas.", "damage": [2, 4], "all": True},
            },
            "capilla": {
                "name": "La capilla profanada", "pos": [-5, 0], "size": [4, 4], "exits": ["sala_ratas", "trono"],
                "text": "Velas negras arden sobre un altar partido. Unos cultistas cantan con los ojos en blanco y se giran hacia ustedes.",
                "monsters": ["cultista", "cultista", "goblin"],
                "feature": {"kind": "altar", "label": "Purificar el altar", "ability": "sab", "dc": 13,
                            "success": "Una luz cálida recorre la capilla: todos recuperan 1d8 de vida.", "heal_all": [1, 8],
                            "failure": "El altar escupe humo negro, pero no pasa nada más."},
            },
            "guardia": {
                "name": "La sala de guardia", "pos": [5, 0], "size": [4, 4], "exits": ["pasillo", "trono"],
                "text": "Esqueletos con armaduras oxidadas siguen haciendo guardia después de siglos. Sus ojos se encienden en azul.",
                "monsters": ["esqueleto", "esqueleto"],
                "feature": {"kind": "chest", "label": "Forzar el armero", "ability": "fue", "dc": 13,
                            "success": "La puerta cede: encuentran la llave de hueso y una poción.", "reward": {"potion": 1, "key": "llave_hueso"},
                            "failure": "La puerta no cede y se lastiman las manos.", "damage": [1, 4]},
            },
            "trono": {
                "name": "La sala del trono", "pos": [0, -6], "size": [6, 5], "exits": ["capilla", "guardia"], "final": True,
                "text": "Un trono de hielo negro. Sobre él, el Rey Olvidado abre los ojos y su corona brilla con un frío que corta la respiración.",
                "monsters": ["rey_esqueleto", "esqueleto"],
                "feature": None,
            },
        },
    },
    "cueva": {
        "title": "La cueva de Escamarroja",
        "intro": "Un dragón joven se instaló en la montaña y quema las granjas del valle. Con su tesoro, el pueblo podría reconstruirlo todo. El camino a su guarida pasa por el bosque de los lobos.",
        "start": "claro",
        "rooms": {
            "claro": {
                "name": "El claro del bosque", "pos": [0, 7], "size": [5, 4], "exits": ["madriguera", "puente"],
                "text": "El bosque se abre en un claro con un campamento abandonado. Hay huellas enormes de lobo… y otras, mucho más grandes, de garras.",
                "monsters": ["lobo"],
                "feature": {"kind": "camp", "label": "Revisar el campamento", "ability": "sab", "dc": 10,
                            "success": "Entre las cenizas encuentran una poción y un mapa: el puente colgante está podrido en el centro.", "reward": {"potion": 1},
                            "failure": "Solo hay cenizas frías."},
            },
            "madriguera": {
                "name": "La madriguera", "pos": [-6, 7], "size": [4, 4], "exits": ["claro", "nido"],
                "text": "Un túnel de tierra bajo las raíces de un roble gigante. Ojos amarillos brillan en la oscuridad.",
                "monsters": ["lobo", "lobo"],
                "feature": None,
            },
            "puente": {
                "name": "El puente colgante", "pos": [6, 7], "size": [5, 3], "exits": ["claro", "galeria"],
                "text": "Un puente de cuerdas sobre un abismo. El viento lo sacude y varias tablas faltan.",
                "monsters": [],
                "feature": {"kind": "bridge", "label": "Cruzar con cuidado", "ability": "des", "dc": 11,
                            "success": "Pasan uno por uno, pisando solo las tablas firmes.",
                            "failure": "¡Una tabla se rompe! Alguien queda colgando y se raspa contra las rocas.", "damage": [1, 8]},
            },
            "nido": {
                "name": "El nido de las arañas", "pos": [-6, 1], "size": [4, 4], "exits": ["madriguera", "guarida"],
                "text": "Telarañas gruesas como sogas cubren las paredes. Algo baja lentamente del techo.",
                "monsters": ["arana"],
                "feature": {"kind": "chest", "label": "Cortar el capullo", "ability": "fue", "dc": 11,
                            "success": "Dentro del capullo hay un aventurero desafortunado… y su bolsa con dos pociones.", "reward": {"potion": 2},
                            "failure": "La seda es demasiado dura."},
            },
            "galeria": {
                "name": "La galería del ogro", "pos": [6, 1], "size": [5, 4], "exits": ["puente", "guarida"],
                "text": "Una cueva llena de huesos de vaca. Un ogro ronca sobre un montón de paja y abre un ojo al oírlos.",
                "monsters": ["ogro"],
                "feature": {"kind": "sneak", "label": "Robar el saco del ogro", "ability": "des", "dc": 14,
                            "success": "Sin despertarlo del todo, sacan del saco una poción y una gema que vale una fortuna.", "reward": {"potion": 1},
                            "failure": "El ogro gruñe y les tira un hueso a la cabeza.", "damage": [1, 6]},
            },
            "guarida": {
                "name": "La guarida de Escamarroja", "pos": [0, -5], "size": [7, 6], "exits": ["nido", "galeria"], "final": True,
                "text": "Montañas de monedas de oro brillan bajo el humo. Escamarroja levanta la cabeza, sonríe con todos sus dientes y el aire se pone a hervir.",
                "monsters": ["dragon"],
                "feature": None,
            },
        },
    },
}

# Lines for the automatic Dungeon Master, so the story doesn't repeat itself.
NARRATION = {
    "hit": [
        "{who} golpea a {target} con su {weapon}: {dmg} de daño.",
        "¡Directo! {who} le hace {dmg} de daño a {target}.",
        "{who} encuentra un hueco en la defensa de {target}: {dmg} de daño.",
    ],
    "crit": [
        "¡GOLPE CRÍTICO! {who} le hace {dmg} de daño a {target}.",
        "¡Un 20 natural! {who} hunde su {weapon} en {target}: {dmg} de daño.",
    ],
    "miss": [
        "{who} ataca a {target}, pero falla.",
        "{target} esquiva el golpe de {who} por un pelo.",
        "El ataque de {who} rebota en la defensa de {target}.",
    ],
    "kill": [
        "{target} cae y no se levanta más.",
        "{target} se desploma con un último quejido.",
        "{target} queda fuera de combate.",
    ],
    "monster_hit": [
        "{who} ataca a {target}: {dmg} de daño.",
        "{who} alcanza a {target} y le hace {dmg} de daño.",
        "¡Ay! {who} hiere a {target}: {dmg} de daño.",
    ],
    "monster_miss": [
        "{who} ataca a {target}, pero no logra atravesar su defensa.",
        "{target} esquiva a {who} en el último momento.",
    ],
    "down": [
        "¡{target} cae al suelo, sin fuerzas! Alguien tiene que curarle.",
        "{target} se desploma. Si nadie le ayuda, no podrá seguir peleando.",
    ],
    "victory": [
        "El último enemigo cae. Por un momento solo se oye su respiración agitada.",
        "Silencio. Lo lograron… por ahora.",
    ],
}
