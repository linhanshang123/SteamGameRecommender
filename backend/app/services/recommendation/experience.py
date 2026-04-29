from __future__ import annotations

from dataclasses import dataclass

from app.schemas.recommendation import (
    ExperienceAxes,
    GameRow,
    ParsedUserIntent,
    ReferenceAnchorProfile,
    SoftAvoids,
)
from app.services.recommendation.all_tags import extract_known_tags_from_text


PACE_FAST_MARKERS = {
    "fast-paced",
    "fast",
    "quick",
    "snappy",
    "responsive",
    "fluid",
    "frantic",
    "rapid",
    "arcade",
}
PACE_SLOW_MARKERS = {
    "slow",
    "slow-paced",
    "methodical",
    "deliberate",
    "turn-based",
    "relaxing",
}

COMBAT_FEEL_MARKERS: dict[str, set[str]] = {
    "action-driven": {"action roguelike", "action", "combat", "hack and slash", "brawler"},
    "fluid": {"fluid", "smooth", "responsive", "fast-paced", "satisfying"},
    "dash-heavy": {"dash", "dodge", "mobility", "agile"},
    "melee-focused": {"hack and slash", "swordplay", "melee", "brawler", "beat em up"},
    "spell-driven": {"magic", "wizard", "mage", "spells", "sorcery"},
    "run-based": {"rogue-like", "rogue-lite", "roguelike", "action roguelike", "perma death"},
}

PRESENTATION_MARKERS: dict[str, set[str]] = {
    "stylized": {"stylized", "stylish", "comic book", "distinctive"},
    "polished": {"polished", "slick", "premium"},
    "dark-fantasy": {"dark fantasy", "mythology", "gothic", "grim"},
    "pixel-art": {"pixel graphics", "pixel art", "retro"},
    "beautiful": {"beautiful", "hand-drawn", "lush", "ornate"},
    "atmospheric": {"atmospheric", "moody"},
    "cartoony": {"cartoony", "colorful", "cute"},
}

LOOP_SHAPE_MARKERS: dict[str, set[str]] = {
    "run-based": {"rogue-like", "rogue-lite", "roguelike", "action roguelike", "perma death"},
    "room-based": {"dungeon crawler", "room", "chambers", "arena"},
    "build-variety": {"replay value", "procedural generation", "build", "synergy"},
    "top-down": {"top-down", "isometric"},
    "platforming": {"platformer", "roguevania"},
    "co-op-friendly": {"co-op", "online co-op", "local co-op"},
}

STRATEGY_MARKERS = {
    "strategy",
    "tactical",
    "tactics",
    "turn-based",
    "turn-based strategy",
    "tower defense",
    "resource management",
    "management",
    "grand strategy",
    "4x",
    "deckbuilder",
    "card battler",
}
SHOOTER_MARKERS = {
    "fps",
    "shooter",
    "arena shooter",
    "top-down shooter",
    "twin stick shooter",
    "looter shooter",
    "first-person",
    "guns",
}
CLUNKY_MARKERS = {
    "deliberate",
    "heavy",
    "slow",
    "methodical",
    "tank controls",
}


@dataclass
class GameExperienceProfile:
    combat_pace: str | None
    combat_feel: list[str]
    presentation_style: list[str]
    loop_shape: list[str]
    strategy_heavy: bool
    slow_combat: bool
    clunky_feel: bool
    shooter_dominant: bool


def _contains_any(blob: str, markers: set[str]) -> bool:
    return any(marker in blob for marker in markers)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(value)
    return ordered


def _extract_axis_labels(blob: str, mapping: dict[str, set[str]]) -> list[str]:
    labels = [label for label, markers in mapping.items() if _contains_any(blob, markers)]
    return _dedupe(labels)


def _pace_from_blob(blob: str) -> str | None:
    if _contains_any(blob, PACE_FAST_MARKERS):
        return "fast"
    if _contains_any(blob, PACE_SLOW_MARKERS):
        return "slow"
    return None


def infer_game_experience_profile(game: GameRow) -> GameExperienceProfile:
    text_blob = " ".join(
        [
            game.name,
            *(game.tags or []),
            *(game.genres or []),
            *(game.categories or []),
            game.llm_context or "",
        ]
    ).lower()

    combat_pace = _pace_from_blob(text_blob)
    combat_feel = _extract_axis_labels(text_blob, COMBAT_FEEL_MARKERS)
    presentation_style = _extract_axis_labels(text_blob, PRESENTATION_MARKERS)
    loop_shape = _extract_axis_labels(text_blob, LOOP_SHAPE_MARKERS)

    strategy_heavy = _contains_any(text_blob, STRATEGY_MARKERS)
    shooter_dominant = _contains_any(text_blob, SHOOTER_MARKERS)
    slow_combat = combat_pace == "slow" or strategy_heavy
    clunky_feel = _contains_any(text_blob, CLUNKY_MARKERS)

    return GameExperienceProfile(
        combat_pace=combat_pace,
        combat_feel=combat_feel,
        presentation_style=presentation_style,
        loop_shape=loop_shape,
        strategy_heavy=strategy_heavy,
        slow_combat=slow_combat,
        clunky_feel=clunky_feel,
        shooter_dominant=shooter_dominant,
    )


def _prompt_contains(prompt: str, *markers: str) -> bool:
    lowered = prompt.lower()
    return any(marker in lowered for marker in markers)


def infer_prompt_axes(prompt: str, preferred_tags: list[str], reference_games: list[str]) -> ExperienceAxes:
    combat_pace = None
    if _prompt_contains(prompt, "fast", "fast-paced", "fastpaced", "quick", "snappy", "fluid", "satisfying"):
        combat_pace = "fast"
    elif _prompt_contains(prompt, "slow", "deliberate", "methodical", "relaxing"):
        combat_pace = "slow"

    combat_feel: list[str] = []
    if preferred_tags or _prompt_contains(prompt, "combat", "action", "fight", "battle"):
        combat_feel.append("action-driven")
    if _prompt_contains(prompt, "fluid", "smooth", "satisfying", "crisp", "snappy"):
        combat_feel.extend(["fluid", "satisfying"])
    if _prompt_contains(prompt, "dash", "mobility", "agile", "dodge"):
        combat_feel.append("dash-heavy")
    if _prompt_contains(prompt, "melee", "slash", "sword"):
        combat_feel.append("melee-focused")

    presentation_style: list[str] = []
    if _prompt_contains(prompt, "stylized", "stylish", "distinctive"):
        presentation_style.append("stylized")
    if _prompt_contains(prompt, "beautiful", "pretty", "gorgeous", "polished", "art style", "visual style"):
        presentation_style.extend(["beautiful", "polished"])
    if _prompt_contains(prompt, "pixel"):
        presentation_style.append("pixel-art")

    loop_shape: list[str] = []
    if _prompt_contains(prompt, "roguelike", "roguelite", "rougelike") or "action roguelike" in preferred_tags:
        loop_shape.append("run-based")
    if reference_games:
        loop_shape.append("room-based")
    if _prompt_contains(prompt, "co-op", "multiplayer", "friends"):
        loop_shape.append("co-op-friendly")

    difficulty_tolerance = None
    if _prompt_contains(prompt, "hard", "difficult", "punishing"):
        difficulty_tolerance = "high"
    elif _prompt_contains(prompt, "casual", "relaxed", "easy", "accessible"):
        difficulty_tolerance = "low"

    return ExperienceAxes(
        combat_pace=combat_pace,
        combat_feel=_dedupe(combat_feel),
        presentation_style=_dedupe(presentation_style),
        loop_shape=_dedupe(loop_shape),
        difficulty_tolerance=difficulty_tolerance,
    )


def infer_soft_avoids(
    prompt: str,
    axes: ExperienceAxes,
    preferred_tags: list[str],
    reference_games: list[str],
) -> SoftAvoids:
    strategy_requested = _prompt_contains(prompt, "strategy", "tactical", "deckbuilder", "turn-based")
    shooter_requested = _prompt_contains(prompt, "shooter", "fps", "guns", "gunplay")

    return SoftAvoids(
        strategy_heavy=not strategy_requested
        and ("action roguelike" in preferred_tags or "run-based" in axes.loop_shape or bool(reference_games)),
        slow_combat=axes.combat_pace == "fast",
        clunky_feel=bool({"fluid", "satisfying", "dash-heavy"} & set(axes.combat_feel)),
        shooter_dominant=not shooter_requested and bool(reference_games),
    )


def _compose_summary(profile: ReferenceAnchorProfile) -> str:
    summary_parts: list[str] = []
    if profile.combat_pace:
        summary_parts.append(f"{profile.combat_pace} combat pace")
    if profile.combat_feel:
        summary_parts.append(f"combat feel: {', '.join(profile.combat_feel[:3])}")
    if profile.loop_shape:
        summary_parts.append(f"loop: {', '.join(profile.loop_shape[:3])}")
    if profile.presentation_style:
        summary_parts.append(f"presentation: {', '.join(profile.presentation_style[:3])}")
    return "; ".join(summary_parts)


def build_reference_anchor_profile(
    intent: ParsedUserIntent,
    resolved_reference_games: list[GameRow],
) -> ReferenceAnchorProfile | None:
    if not resolved_reference_games and not intent.reference_games:
        return None

    aggregate_parts: list[str] = []
    for reference_game in resolved_reference_games:
        aggregate_parts.extend(reference_game.tags or [])
        aggregate_parts.extend(reference_game.genres or [])
        aggregate_parts.append(reference_game.llm_context or "")

    aggregate_blob = " ".join([*aggregate_parts, intent.free_text_intent]).lower()
    derived_tags = _dedupe([*extract_known_tags_from_text(aggregate_blob), *intent.preferred_tags])[:8]
    prompt_axes = infer_prompt_axes(intent.free_text_intent, intent.preferred_tags, intent.reference_games)

    profile = ReferenceAnchorProfile(
        anchor_names=[reference_game.name for reference_game in resolved_reference_games] or intent.reference_games,
        derived_tags=derived_tags,
        combat_pace=_pace_from_blob(aggregate_blob) or prompt_axes.combat_pace,
        combat_feel=_dedupe(_extract_axis_labels(aggregate_blob, COMBAT_FEEL_MARKERS) + prompt_axes.combat_feel),
        presentation_style=_dedupe(
            _extract_axis_labels(aggregate_blob, PRESENTATION_MARKERS) + prompt_axes.presentation_style
        ),
        loop_shape=_dedupe(_extract_axis_labels(aggregate_blob, LOOP_SHAPE_MARKERS) + prompt_axes.loop_shape),
    )
    profile.summary = _compose_summary(profile)
    return profile


def enrich_intent(intent: ParsedUserIntent, resolved_reference_games: list[GameRow]) -> ParsedUserIntent:
    prompt_axes = infer_prompt_axes(intent.free_text_intent, intent.preferred_tags, intent.reference_games)
    merged_axes = ExperienceAxes(
        combat_pace=intent.experience_axes.combat_pace or prompt_axes.combat_pace,
        combat_feel=_dedupe([*intent.experience_axes.combat_feel, *prompt_axes.combat_feel]),
        presentation_style=_dedupe([*intent.experience_axes.presentation_style, *prompt_axes.presentation_style]),
        loop_shape=_dedupe([*intent.experience_axes.loop_shape, *prompt_axes.loop_shape]),
        difficulty_tolerance=intent.experience_axes.difficulty_tolerance or prompt_axes.difficulty_tolerance,
    )

    soft_avoids = intent.implicit_soft_avoids
    inferred_soft_avoids = infer_soft_avoids(
        intent.free_text_intent,
        merged_axes,
        intent.preferred_tags,
        intent.reference_games,
    )
    merged_soft_avoids = SoftAvoids(
        strategy_heavy=soft_avoids.strategy_heavy or inferred_soft_avoids.strategy_heavy,
        slow_combat=soft_avoids.slow_combat or inferred_soft_avoids.slow_combat,
        clunky_feel=soft_avoids.clunky_feel or inferred_soft_avoids.clunky_feel,
        shooter_dominant=soft_avoids.shooter_dominant or inferred_soft_avoids.shooter_dominant,
    )

    anchor_profile = build_reference_anchor_profile(intent, resolved_reference_games)
    if anchor_profile:
        merged_axes = ExperienceAxes(
            combat_pace=merged_axes.combat_pace or anchor_profile.combat_pace,
            combat_feel=_dedupe([*merged_axes.combat_feel, *anchor_profile.combat_feel]),
            presentation_style=_dedupe([*merged_axes.presentation_style, *anchor_profile.presentation_style]),
            loop_shape=_dedupe([*merged_axes.loop_shape, *anchor_profile.loop_shape]),
            difficulty_tolerance=merged_axes.difficulty_tolerance,
        )

    must_have = _dedupe(
        [
            *intent.must_have,
            *intent.preferred_tags,
            *(["fast combat"] if merged_axes.combat_pace == "fast" else []),
            *([f"reference:{name}" for name in intent.reference_games]),
        ]
    )
    nice_to_have = _dedupe([*intent.nice_to_have, *merged_axes.presentation_style, *merged_axes.combat_feel])

    return intent.model_copy(
        update={
            "experience_axes": merged_axes,
            "implicit_soft_avoids": merged_soft_avoids,
            "must_have": must_have,
            "nice_to_have": nice_to_have,
            "reference_anchor_profile": anchor_profile,
        }
    )
