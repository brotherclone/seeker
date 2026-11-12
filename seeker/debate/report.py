"""The survivors report: a finished run rendered as Markdown for Gabe to review. No API calls."""

from __future__ import annotations

from pathlib import Path

from seeker.config import PriceTable
from seeker.ontology import Critique, Debate, DebateRun, DeckSet, Generation, Idea, ScoreAxis


class SurvivorReport:
    """A DebateRun with the generation it debated, as one Markdown document."""

    def __init__(self, run: DebateRun, generation: Generation, deck_set: DeckSet, prices: PriceTable) -> None:
        self.run = run
        self.ideas = {idea.position: idea for idea in generation.ideas}
        self.draws = {draw.position: draw for draw in generation.draw_batch.draws}
        self.deck_set = deck_set
        self.prices = prices

    def write(self, folder: Path, stem: str) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{stem}.md"
        path.write_text(self.render(), encoding="utf-8")
        return path

    def render(self) -> str:
        lines = [f"# Debate report: {Path(self.run.generation_path).stem}", ""]
        lines += self._survivors()
        lines += self._others()
        lines += self._unranked()
        lines += self._provenance()
        return "\n".join(lines).rstrip() + "\n"

    # -- sections --------------------------------------------------------------------

    def _survivors(self) -> list[str]:
        tournament = self.run.tournament
        if tournament is None or not tournament.survivors:
            reason = "the tournament was skipped" if tournament is not None and tournament.skipped else "no tournament yet"
            return ["## Survivors", "", f"None: {reason}.", ""]
        lines = ["## Survivors", ""]
        for rank, position in enumerate(tournament.survivors, start=1):
            debate = self.run.debate_at(position)
            idea = self.ideas[position]
            lines += [f"### {rank}. #{position}: {debate.final_statement}", ""]
            lines.append(f"- **Ratings:** {self._ratings(position)}")
            lines.append(f"- **Cards:** {self._cards(position)}")
            if debate.defense.revision is not None:
                lines.append(f"- **Original:** {idea.statement}")
            if debate.short_a_critique:
                lines.append("- **Note:** a critic failed, so this idea faced fewer than three critiques.")
            lines.append("")
            lines += self._debate(debate)
        return lines

    def _debate(self, debate: Debate) -> list[str]:
        lines: list[str] = []
        for critique in debate.critiques:
            lines += self._critique(critique, debate)
        return lines

    def _critique(self, critique: Critique, debate: Debate) -> list[str]:
        target = critique.target.value + (f" `{critique.target_card}`" if critique.target_card else "")
        lines = [
            f"**{critique.role_name.value}** ({critique.severity.value}, {target}): {critique.failure}",
            "",
            f"> {critique.argument}",
            "",
        ]
        if critique.none_found:
            lines += ["- No prior art found.", ""]
        if critique.citations:
            for citation in critique.citations:
                link = f"[{citation.title}]({citation.url})" if citation.url else f"[[{citation.cited_work}]] ({citation.title})"
                lines.append(f"- {link}: {citation.relevance}")
            lines.append("")
        reply = debate.defense.reply_to(critique.role_name)
        if reply is not None:
            lines += [f"*Advocate {reply.move.value}s:* {reply.argument}", ""]
        return lines

    def _others(self) -> list[str]:
        tournament = self.run.tournament
        if tournament is None or tournament.skipped:
            return []
        others = [p for p in tournament.entrants if p not in tournament.survivors]
        if not others:
            return []
        ranked = sorted(others, key=lambda p: -tournament.rating_of(p, ScoreAxis.PROMISE).rating)
        lines = ["## The rest, by promise", "", "| # | Idea | Novelty | Feasibility | Promise | Outcome |", "|---|---|---|---|---|---|"]
        for position in ranked:
            debate = self.run.debate_at(position)
            cells = [f"{tournament.rating_of(position, axis).rating:.0f}" for axis in ScoreAxis]
            statement = debate.final_statement.replace("|", "\\|")
            lines.append(f"| {position} | {statement} | {' | '.join(cells)} | {debate.defense.outcome.value} |")
        return [*lines, ""]

    def _unranked(self) -> list[str]:
        withdrawn = [d for d in self.run.debates if not d.competes]
        debated = {d.position for d in self.run.debates}
        failed = sorted({f.position for f in self.run.debate_failures} - debated)
        if not withdrawn and not failed:
            return []
        lines = ["## Not ranked", ""]
        lines += [f"- #{d.position} withdrawn: {self.ideas[d.position].statement}" for d in withdrawn]
        for position in failed:
            reasons = "; ".join(
                f"{f.role_name.value}: {f.failure_reason}" for f in self.run.debate_failures if f.position == position
            )
            lines.append(f"- #{position} not debated ({reasons}): {self.ideas[position].statement}")
        return [*lines, ""]

    def _provenance(self) -> list[str]:
        run = self.run
        usage = run.usage
        lines = [
            "## Provenance",
            "",
            f"- Generation: `{run.generation_path}` (sha256 `{run.generation_digest[:12]}`)",
            f"- Git commit: `{run.git_commit or 'unknown'}`",
            f"- Tournament seed: {run.tournament_seed}",
            f"- Catalog at start: `{run.catalog_digest[:12]}`",
            f"- Started: {run.started_at.isoformat()}",
            f"- Stop reason: {run.stop_reason.value if run.stop_reason else 'running'}",
            f"- Roles: " + ", ".join(f"{d.role_name.value} `{d.role_digest[:12]}`" for d in run.role_digests),
            f"- Usage: {usage.input_tokens:,} in / {usage.output_tokens:,} out tokens, {usage.web_search_requests} searches",
            f"- Estimated cost: ${run.estimated_cost_usd:.2f} of a ${run.budget_usd:.2f} budget",
        ]
        return [*lines, ""]

    # -- helpers ---------------------------------------------------------------------

    def _ratings(self, position: int) -> str:
        tournament = self.run.tournament
        return " · ".join(f"{axis.value} {tournament.rating_of(position, axis).rating:.0f}" for axis in ScoreAxis)

    def _cards(self, position: int) -> str:
        names = []
        for card_id in self.draws[position].drawn_cards:
            card = self.deck_set.card(card_id)
            names.append(card.name if card is not None else card_id)
        return ", ".join(names)

    def idea(self, position: int) -> Idea:
        return self.ideas[position]
