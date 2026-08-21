"""Tests unitaires du service sync/activities.py (mocks WatchFilesystem + stores).

Voir docs/decisions/adr-002.md (flux Montre → GC) et adr-008.md (stratégie de test).

`list_uploadable_files` (et `push_activities` à l'étape suivante) sont testés
avec des doublures : aucune montre réelle, aucun appel réseau.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openrunner55.sync.activities import (
    UPLOADABLE_CATEGORIES,
    list_uploadable_files,
)


# --- Doublures ---------------------------------------------------------------


class FakeWatch:
    """Doublure de WatchFilesystem : list_fit_files et file_size pilotables."""

    def __init__(
        self,
        files: dict[str, list[Path]] | None = None,
        sizes: dict[Path, int] | None = None,
    ):
        self._files = files or {}
        self._sizes = sizes or {}
        self.queried_categories: list[str] = []

    def list_fit_files(self, category: str) -> list[Path]:
        self.queried_categories.append(category)
        return self._files.get(category, [])

    def file_size(self, path: Path) -> int:
        return self._sizes.get(path, 0)


class FakeTransfers:
    """Doublure de TransferredFilesStore : dédup `(file_name, source)` en mémoire."""

    def __init__(self, transferred: set[tuple[str, str]] | None = None):
        self._transferred = transferred or set()
        self.queried: list[tuple[str, str, str | None]] = []

    def is_transferred(self, file_name: str, direction: str, source: str | None = None) -> bool:
        self.queried.append((file_name, direction, source))
        return (file_name, source) in self._transferred


# --- list_uploadable_files ---------------------------------------------------


@pytest.mark.unit
class TestListUploadableFiles:
    def test_empty_watch_returns_empty_list(self) -> None:
        assert list_uploadable_files(FakeWatch(), FakeTransfers()) == []

    def test_lists_all_four_categories_in_order(self) -> None:
        watch = FakeWatch(
            files={
                "Activity": [Path("Activity/2026-08-07-08-29-33.fit")],
                "Monitor": [Path("Monitor/M85K3715.FIT")],
                "Sleep": [Path("Sleep/S7O00000.FIT")],
                "Metrics": [Path("Metrics/G8400529.fit")],
            }
        )
        result = list_uploadable_files(watch, FakeTransfers())

        assert [f.path for f in result] == [
            Path("Activity/2026-08-07-08-29-33.fit"),
            Path("Monitor/M85K3715.FIT"),
            Path("Sleep/S7O00000.FIT"),
            Path("Metrics/G8400529.fit"),
        ]
        # category portée en minuscules (convention brief), ordre UPLOADABLE_CATEGORIES
        assert [f.category for f in result] == ["activity", "monitor", "sleep", "metrics"]

    def test_excludes_summary(self) -> None:
        watch = FakeWatch(
            files={
                "Activity": [Path("Activity/a.fit")],
                "SUMMARY": [Path("SUMMARY/abc.FIT")],
            }
        )
        result = list_uploadable_files(watch, FakeTransfers())

        assert [f.path for f in result] == [Path("Activity/a.fit")]
        # SUMMARY n'est jamais interrogé (pas dans UPLOADABLE_CATEGORIES)
        assert "SUMMARY" not in watch.queried_categories
        assert watch.queried_categories == list(UPLOADABLE_CATEGORIES)

    def test_marks_already_transferred(self) -> None:
        watch = FakeWatch(
            files={
                "Activity": [Path("Activity/a.fit"), Path("Activity/b.fit")],
            }
        )
        transfers = FakeTransfers(transferred={("a.fit", "activity")})
        result = list_uploadable_files(watch, transfers)

        by_name = {f.path.name: f for f in result}
        assert by_name["a.fit"].already_transferred is True
        assert by_name["b.fit"].already_transferred is False

    def test_dedup_uses_basename_and_lowercase_source(self) -> None:
        watch = FakeWatch(
            files={"Activity": [Path("Activity/2026-08-07-08-29-33.fit")]}
        )
        transfers = FakeTransfers()
        list_uploadable_files(watch, transfers)

        # D1 : file_name = basename (path.name), source = catégorie minuscule
        assert transfers.queried == [
            ("2026-08-07-08-29-33.fit", "up", "activity")
        ]

    def test_records_file_size(self) -> None:
        watch = FakeWatch(
            files={"Activity": [Path("Activity/a.fit")]},
            sizes={Path("Activity/a.fit"): 1234},
        )
        result = list_uploadable_files(watch, FakeTransfers())
        assert result[0].size == 1234

    def test_name_order_preserved_within_category(self) -> None:
        # Le tri par nom est délégué à list_fit_files ; le service préserve
        # l'ordre retourné (chronologique pour Activity/).
        watch = FakeWatch(
            files={
                "Activity": [
                    Path("Activity/2026-08-01-08-00-00.fit"),
                    Path("Activity/2026-08-02-08-00-00.fit"),
                ],
                "Monitor": [Path("Monitor/b.FIT"), Path("Monitor/a.FIT")],
            }
        )
        result = list_uploadable_files(watch, FakeTransfers())
        assert [f.path for f in result] == [
            Path("Activity/2026-08-01-08-00-00.fit"),
            Path("Activity/2026-08-02-08-00-00.fit"),
            Path("Monitor/b.FIT"),
            Path("Monitor/a.FIT"),
        ]
