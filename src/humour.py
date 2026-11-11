"""Humour des activités Strava : phrase d'autodérision en tête des descriptions, nom des balades du chien.

À la première personne, comme Tom, sans moquerie hors de lui (le chien a droit à des surnoms flatteurs).
Jamais deux fois la même phrase : `deja` (gardé dans l'état de strava-enrich) associe chaque phrase posée à son activité. Le choix part d'une position
fixée par l'identifiant de l'activité (relancer donne le même texte) et prend la première phrase pas encore utilisée ; quand une liste
est épuisée, la plus anciennement utilisée revient.
"""
import re

TARGET_SEC = 265  # 4'25/km

PILE = [
    "Pile sur le 4'25. Le chrono est content, les jambes ont demandé un avocat.",
    "Du 4'25 au métronome. Qu'on ne me demande pas de refaire ça demain.",
    "Allure respectée à la seconde. Je soupçonne la montre de m'avoir aidé.",
    "Blocs dans la cible : pour une fois, le plan et moi étions d'accord.",
    "Régulier comme une horloge suisse, essoufflé comme une horloge à coucou.",
    "Exactement l'allure prévue. Je vais encadrer ce tour de piste.",
    "Dans la cible du début à la fin. Mes jambes réclament une prime.",
    "Allure tenue, dignité aussi, à peu près.",
    "Le coach avait dit 4'25, j'ai fait 4'25. Je deviens obéissant, c'est inquiétant.",
    "Séance propre. Je ne sais pas qui a couru à ma place, mais merci.",
]
TROP_VITE = [
    "{e} s/km trop vite. Mon plan d'allure me regarde avec déception.",
    "Parti {e} s/km plus vite que prévu, comme d'habitude. Le semi ne pardonnera pas.",
    "{e} s/km sous la cible : l'enthousiasme a encore battu la raison.",
    "Trop rapide de {e} s/km. Mes jambes ont décidé seules, je n'étais que passager.",
    "{e} s/km d'avance sur le plan. Je les rendrai sûrement au km 18.",
    "Plus vite de {e} s/km : la patience, ce sera pour une autre vie.",
    "{e} s/km trop vite. Le chrono dit bravo, le coach dit non.",
    "Avance de {e} s/km : j'ai confondu séance de seuil et course poursuite.",
]
TROP_LENT = [
    "{e} s/km trop lent. Je dirai que le vent était contre, même sans vent.",
    "{e} s/km de retard sur le plan. Les jambes avaient d'autres projets.",
    "En retard de {e} s/km : le moteur a démarré au diesel.",
    "{e} s/km plus lent que prévu. On appellera ça une séance de sagesse.",
    "{e} s/km de retard. Les blocs étaient longs, ma motivation un peu moins.",
    "Plus lent de {e} s/km. Officiellement, je gérais l'effort.",
    "{e} s/km sous l'objectif : la forme est restée au lit.",
    "Retard de {e} s/km. Le seuil, aujourd'hui, c'était plutôt un palier.",
]
FC_HAUTE = [
    "Endurance fondamentale à {fc} bpm : mon coeur n'a pas lu le plan.",
    "Footing tranquille, qu'ils disaient. {fc} bpm de moyenne, mon coeur a une autre version.",
    "{fc} bpm en footing facile : la définition de facile reste à négocier.",
    "Moyenne à {fc} bpm. J'ai couru en endurance, mon coeur en compétition.",
    "Footing à {fc} bpm : la prochaine fois, je ralentis. Promis. Peut-être.",
    "{fc} bpm pour une sortie cool : le mot cool était de trop.",
    "Endurance à {fc} bpm. Il paraît qu'on peut courir en parlant, pas aujourd'hui.",
]
EF_REUSSIE = [
    "Endurance à {fc} bpm : pour une fois, j'ai écouté mon coeur plutôt que mon ego.",
    "FC sage à {fc} bpm. Lent mais discipliné, le combo gagnant.",
    "{fc} bpm de moyenne : le footing facile, le vrai, celui qui construit.",
    "J'ai couru lentement exprès. Mon coeur a apprécié, mon orgueil un peu moins.",
    "Endurance respectée à {fc} bpm. Les escargots m'ont doublé, mais avec respect.",
    "Footing à {fc} bpm : la patience d'aujourd'hui, c'est le chrono du 29.",
    "{fc} bpm, allure tranquille, sourire inclus. C'est ça, l'endurance fondamentale.",
    "Lent en apparence, efficace en vrai : {fc} bpm, mission endurance accomplie.",
]
LONGUE = [
    "{km} km, histoire de pouvoir dire au prochain apéro que j'ai déjà couru.",
    "{km} km : à ce stade ce n'est plus un footing, c'est un trait de caractère.",
    "{km} km au compteur. Le canapé m'attend, il a bien mérité de me revoir.",
    "{km} km : mes chaussures ont demandé des congés.",
    "Sortie de {km} km. J'ai eu le temps de refaire le monde deux fois.",
    "{km} km dans les jambes, et les jambes s'en souviendront demain.",
    "{km} km : assez pour mériter une deuxième assiette de pâtes.",
]
COURTE = [
    "Sortie courte : le canapé n'a pas tout à fait gagné.",
    "Peu de kilomètres, beaucoup de bonne volonté.",
    "Court mais intense. Surtout le moment où j'ai lacé mes chaussures.",
    "Petite sortie : la régularité, c'est aussi se contenter de peu.",
    "Quelques kilomètres pour dire bonjour au quartier.",
    "Sortie express : à peine le temps de transpirer.",
    "Format court : l'important, c'est d'être sorti.",
]
DEFAUT = [
    "Une sortie de plus dans la boîte. Les genoux ne sont pas d'accord, mais ils ne votent pas.",
    "Mission accomplie, douche méritée, crédibilité intacte (ou presque).",
    "Sortie faite. Le plan avance, moi aussi, plus lentement que le plan.",
    "Encore une. Mes chaussures connaissent le chemin mieux que moi.",
    "Sortie validée. Le coach est satisfait, mes mollets un peu moins.",
    "Une de plus au compteur. La régularité, c'est mon seul talent.",
    "Bouclé. Je n'ai croisé aucun record, mais j'ai croisé un chat.",
    "Sortie terminée sans incident, sauf ma foulée en montée.",
    "Coché. Le futur moi du semi me remercie, le moi actuel cherche le canapé.",
]
BALADE = [
    "Promenade du tigre",
    "Patrouille canine du quartier",
    "Sortie officielle du chef de meute",
    "Tournée d'inspection des odeurs",
    "Expédition truffe au vent",
    "Safari urbain avec le fauve",
    "Ronde de surveillance des poteaux",
    "Mission reniflage",
    "Balade du loup domestique",
    "Tour de garde avec mon garde du corps",
    "Récupération active, tenue en laisse",
    "Inspection du territoire",
    "Le chien m'a sorti",
    "Randonnée du molosse",
    "Défilé de la truffe",
    "Escorte royale du quartier",
    "Marche diplomatique avec les voisins à quatre pattes",
    "Grande traversée du lotissement",
    "Sortie du fauve, maître en laisse",
    "Circuit des meilleures odeurs du quartier",
]


def _modele(gabarit: str) -> "re.Pattern":
    """« Endurance à {fc} bpm » reconnaît « Endurance à 152 bpm » comme « Endurance à 147 bpm » : c'est la même blague."""
    morceaux = re.split(r"\{\w+\}", gabarit)
    return re.compile("^" + ".+?".join(re.escape(m) for m in morceaux) + "$")


def choisir(options: list[str], cle, deja: dict[str, str] | None = None, **valeurs) -> str:
    """Phrase dont le modèle n'a pas encore servi à une autre activité, en partant de la position donnée par `cle` (l'identifiant).

    `deja` : phrase posée -> identifiant de l'activité, dans l'ordre d'utilisation. La même activité retrouve toujours sa phrase
    (le débrief et la description Strava sont calculés séparément) ; une liste épuisée reprend le modèle le plus anciennement utilisé."""
    deja = deja if deja is not None else {}
    n, cle = len(options), str(cle)
    ordre = [options[(int(cle) + i) % n] for i in range(n)]
    usages = {g: [p for p in deja if _modele(g).match(p)] for g in ordre}
    a_moi = next((p for g in ordre for p in usages[g] if deja[p] == cle), None)
    if a_moi:
        choix = a_moi
    else:
        libres = [g for g in ordre if not usages[g]]
        if libres:
            gabarit = libres[0]
        else:   # tout a servi : le modèle dont le dernier usage est le plus ancien
            rang = {p: i for i, p in enumerate(deja)}
            gabarit = min(ordre, key=lambda g: max(rang[p] for p in usages[g]))
        choix = gabarit.format(**valeurs)
    deja.pop(choix, None)
    deja[choix] = cle
    return choix


# Smileys demandés par Tom pour les descriptions Strava (pas pour les docs ni les commits), un par phrase, selon la situation.
SMILEYS = {
    "pile": ["🎯", "😎", "👌", "🤓", "🧘"],
    "vite": ["🚀", "😅", "💨", "🏎️", "🙈"],
    "lent": ["🐢", "😴", "🥱", "🐌", "🙃"],
    "fc_haute": ["🥵", "😮‍💨", "🫀", "🔥", "😵‍💫"],
    "ef": ["😌", "😛", "🐌", "🧘", "😇"],
    "longue": ["🥵", "🍝", "🦵", "🫠", "🏔️"],
    "courte": ["😜", "🛋️", "⏱️", "🤏", "😁"],
    "defaut": ["😛", "🙃", "😅", "💪", "🤪"],
}


def smiley(categorie: str, cle) -> str:
    s = SMILEYS[categorie]
    return s[(int(cle) // 3) % len(s)]   # change d'une activité à l'autre, stable pour une même activité


def sans_smiley(texte: str) -> str:
    """Phrase sans son smiley final : la mémoire anti-répétition compare les blagues, pas les smileys."""
    import re as _re
    return _re.sub(r"[\s\U0001F000-\U0001FAFF\u2600-\u27BF\u200D\uFE0F]+$", "", texte)


def phrase(act: dict, ecart_blocs: float | None, workout_type: int | None, deja: dict[str, str] | None = None) -> str:
    """ecart_blocs : écart moyen des blocs à la cible en s/km (négatif = trop vite), None si pas de blocs. Phrase suivie d'un smiley."""
    aid = act.get("id", 0)
    km = act["distance"] / 1000
    fc = act.get("average_heartrate")
    if ecart_blocs is not None:
        if abs(ecart_blocs) <= 3:
            base, cat = choisir(PILE, aid, deja), "pile"
        elif ecart_blocs < 0:
            base, cat = choisir(TROP_VITE, aid, deja, e=f"{abs(ecart_blocs):.0f}"), "vite"
        else:
            base, cat = choisir(TROP_LENT, aid, deja, e=f"{abs(ecart_blocs):.0f}"), "lent"
    elif workout_type in (None, 0) and fc and fc >= 145:
        base, cat = choisir(FC_HAUTE, aid, deja, fc=f"{fc:.0f}"), "fc_haute"
    elif workout_type in (None, 0) and fc and km < 18:   # footing réussi : jamais une phrase qui le fait passer pour raté
        base, cat = choisir(EF_REUSSIE, aid, deja, fc=f"{fc:.0f}"), "ef"
    elif km >= 18:
        base, cat = choisir(LONGUE, aid, deja, km=f"{km:.0f}"), "longue"
    elif km < 5:
        base, cat = choisir(COURTE, aid, deja), "courte"
    else:
        base, cat = choisir(DEFAUT, aid, deja), "defaut"
    return f"{base} {smiley(cat, aid)}"


def nom_balade(act: dict, deja: dict[str, str] | None = None) -> str:
    return choisir(BALADE, act.get("id", 0), deja)
