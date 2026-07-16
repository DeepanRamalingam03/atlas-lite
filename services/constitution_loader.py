from pathlib import Path


class ConstitutionLoader:
    """
    Loads the Atlas Constitution documents.
    """

    def __init__(self, base_dir: str = "atlas_core/constitution"):
        self.base_path = Path(base_dir)

    def read_document(self, filename: str) -> str:
        path = self.base_path / filename

        if not path.exists():
            return ""

        return path.read_text(encoding="utf-8")

    def load_all(self) -> str:
        documents = []

        for file in sorted(self.base_path.glob("*.md")):
            text = self.read_document(file.name).strip()

            if text:
                documents.append(
                    f"# {file.stem}\n\n{text}"
                )

        return "\n\n" + ("\n\n" + ("-" * 80) + "\n\n").join(documents)
