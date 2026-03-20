from dataclasses import dataclass

from helius_agent.tools.notes import load_all_notes


@dataclass
class NotesSystemPromptMiddleware:
    enabled: bool = True
    header: str = "Project Notes"

    def apply_to_system_prompt(self, system_prompt: str) -> str:
        if not self.enabled:
            return system_prompt

        notes = load_all_notes()
        if not notes:
            return system_prompt

        notes_block = "\n\n".join(notes).strip()
        if not notes_block:
            return system_prompt

        return (
            f"{system_prompt}\n\n"
            f"[{self.header}]\n"
            f"{notes_block}"
        )


__all__ = ["NotesSystemPromptMiddleware"]
