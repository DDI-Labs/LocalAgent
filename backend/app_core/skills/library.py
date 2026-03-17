"""Skill library — loads skills from disk, fuzzy-matches prompts to skills.

Uses ``difflib.SequenceMatcher`` for fuzzy matching plus substring and
token-overlap boosts.  No external dependencies required.
"""

from __future__ import annotations

import difflib
import logging
import re
from pathlib import Path

from app_core.skills.skill import Skill
from app_core.skills.compiler import CompiledSkill, compile_skill

logger = logging.getLogger(__name__)

# Characters stripped during normalisation
_PUNCT_RE = re.compile(r"[^\w\s]")


def _normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return _PUNCT_RE.sub("", text.lower()).strip()


def _token_set(text: str) -> set[str]:
    return set(_normalise(text).split())


class SkillLibrary:
    """Load skills from a directory and match user prompts to them."""

    def __init__(self, skills_dir: Path, match_threshold: float = 0.55):
        self.skills_dir = skills_dir
        self.match_threshold = match_threshold
        self.skills: list[Skill] = []
        self._compiled: dict[str, CompiledSkill] = {}

    def load(self) -> None:
        """Scan ``skills_dir`` for ``*.md`` files and parse each into a Skill."""
        self.skills.clear()
        self._compiled.clear()
        if not self.skills_dir.exists():
            logger.info("Skills directory %s does not exist — library is empty", self.skills_dir)
            return
        for md_path in sorted(self.skills_dir.glob("*.md")):
            try:
                skill = Skill.from_file(md_path)
                self.skills.append(skill)
                self._compiled[skill.name] = compile_skill(skill)
                logger.info("Loaded skill: %s (%d triggers)", skill.name, len(skill.trigger_phrases))
            except Exception as e:
                logger.warning("Failed to load skill from %s: %s", md_path, e)

    def reload(self) -> None:
        """Re-scan the directory (hot-reload after creating new skills)."""
        self.load()

    def get_compiled(self, skill_name: str) -> CompiledSkill | None:
        """Return the compiled version of a skill by name."""
        return self._compiled.get(skill_name)

    def match(self, prompt: str) -> tuple[Skill, float] | None:
        """Find the best matching skill for *prompt*.

        Returns ``(skill, score)`` if a match is found above
        ``match_threshold``, otherwise ``None``.
        """
        if not self.skills:
            return None

        norm_prompt = _normalise(prompt)
        prompt_tokens = _token_set(prompt)
        best_skill: Skill | None = None
        best_score: float = 0.0

        for skill in self.skills:
            for phrase in skill.trigger_phrases:
                score = _score_match(norm_prompt, prompt_tokens, phrase)
                if score > best_score:
                    best_score = score
                    best_skill = skill

        if best_skill is not None and best_score >= self.match_threshold:
            return best_skill, best_score
        return None


def _score_match(
    norm_prompt: str,
    prompt_tokens: set[str],
    trigger_phrase: str,
) -> float:
    """Compute a composite match score between a normalised prompt and a
    trigger phrase.

    Combines:
    1. ``SequenceMatcher.ratio()`` — character-level similarity
    2. Substring bonus — if either contains the other
    3. Token overlap — shared words / union of words
    """
    norm_trigger = _normalise(trigger_phrase)

    # 1. Character-level similarity
    seq_score = difflib.SequenceMatcher(None, norm_prompt, norm_trigger).ratio()

    # 2. Substring bonus
    substring_bonus = 0.0
    if norm_trigger in norm_prompt or norm_prompt in norm_trigger:
        substring_bonus = 0.25

    # 3. Token overlap (Jaccard-ish)
    trigger_tokens = _token_set(trigger_phrase)
    if prompt_tokens and trigger_tokens:
        overlap = len(prompt_tokens & trigger_tokens)
        union = len(prompt_tokens | trigger_tokens)
        token_score = overlap / union
    else:
        token_score = 0.0

    # Weighted composite — sequence matcher is primary, the others boost
    return 0.50 * seq_score + 0.25 * token_score + substring_bonus
