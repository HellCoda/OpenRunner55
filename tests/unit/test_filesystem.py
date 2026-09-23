"""Tests unitaires du WatchFilesystem (watch Core) — arborescence mockée via tmp_path.

Voir docs/decisions/adr-002.md (module watch/) et adr-008.md (stratégie de test).

Aucune montre réelle : le `mount_path` est un `tmp_path` pytest dans lequel on
recrée l'arborescence `GARMIN/{category}/` de la FR55.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openrunner55.watch.filesystem import WatchFilesystem


@pytest.fixture
def fs(tmp_path: Path) -> WatchFilesystem:
    """Filesystem pointant sur un volume simulé (tmp_path)."""
    return WatchFilesystem(mount_path=tmp_path)


def _write(fs: WatchFilesystem, rel: str, content: bytes = b"\x0e.FITtest") -> Path:
    """Écrit un fichier via l'API et retourne son chemin relatif."""
    path = Path(rel)
    fs.write_fit(path, content)
    return path


@pytest.mark.unit
class TestListFitFiles:
    def test_empty_when_directory_missing(self, fs) -> None:
        assert fs.list_fit_files("Workouts") == []

    def test_lists_fit_files_sorted(self, fs) -> None:
        _write(fs, "Workouts/b_run.FIT")
        _write(fs, "Workouts/a_run.fit")
        assert fs.list_fit_files("Workouts") == [
            Path("Workouts/a_run.fit"),
            Path("Workouts/b_run.FIT"),
        ]

    def test_ignores_non_fit_files(self, fs) -> None:
        _write(fs, "Workouts/foo.FIT")
        _write(fs, "Workouts/notes.txt")
        assert fs.list_fit_files("Workouts") == [Path("Workouts/foo.FIT")]

    def test_ignores_subdirectories(self, fs) -> None:
        _write(fs, "Workouts/foo.FIT")
        # Sous-dossiers présents sur la FR55 (Guided, Schedule) — non listés.
        (fs._mount_path / "GARMIN" / "Workouts" / "Guided").mkdir(parents=True)
        assert fs.list_fit_files("Workouts") == [Path("Workouts/foo.FIT")]

    def test_extension_case_insensitive(self, fs) -> None:
        # FAT32 : .fit et .FIT coexistent (cf. tree-FR55).
        _write(fs, "Workouts/upper.FIT")
        _write(fs, "Workouts/lower.fit")
        assert fs.list_fit_files("Workouts") == [
            Path("Workouts/lower.fit"),
            Path("Workouts/upper.FIT"),
        ]

    def test_invalid_category_raises(self, fs) -> None:
        with pytest.raises(ValueError):
            fs.list_fit_files("Nope")


@pytest.mark.unit
class TestWriteFit:
    def test_creates_parent_directory(self, fs) -> None:
        # Le dossier Workouts/ n'existe pas encore : write_fit doit le créer.
        fs.write_fit(Path("Workouts/foo.FIT"), b"payload")
        assert (fs._mount_path / "GARMIN" / "Workouts" / "foo.FIT").is_file()

    def test_writes_under_garmin_root(self, fs, tmp_path) -> None:
        fs.write_fit(Path("Workouts/foo.FIT"), b"payload")
        # Le fichier doit atterrir dans {mount}/GARMIN/Workouts/, pas {mount}/Workouts/.
        assert (tmp_path / "GARMIN" / "Workouts" / "foo.FIT").read_bytes() == b"payload"
        assert not (tmp_path / "Workouts").exists()

    def test_overwrites_existing_file(self, fs) -> None:
        fs.write_fit(Path("Workouts/foo.FIT"), b"v1")
        fs.write_fit(Path("Workouts/foo.FIT"), b"v2")
        assert (fs._mount_path / "GARMIN" / "Workouts" / "foo.FIT").read_bytes() == b"v2"

    def test_roundtrip_read_write(self, fs) -> None:
        fs.write_fit(Path("Workouts/foo.FIT"), b"roundtrip")
        assert fs.read_fit(Path("Workouts/foo.FIT")) == b"roundtrip"


@pytest.mark.unit
class TestReadFit:
    def test_reads_relative_path(self, fs) -> None:
        _write(fs, "Workouts/foo.FIT", b"contenu")
        assert fs.read_fit(Path("Workouts/foo.FIT")) == b"contenu"

    def test_missing_file_raises_oserror(self, fs) -> None:
        with pytest.raises(OSError):
            fs.read_fit(Path("Workouts/inexistant.FIT"))


@pytest.mark.unit
class TestFileSize:
    def test_returns_size_in_bytes(self, fs) -> None:
        _write(fs, "Activity/run.fit", b"\x0e" * 1234)
        assert fs.file_size(Path("Activity/run.fit")) == 1234

    def test_missing_file_raises_oserror(self, fs) -> None:
        with pytest.raises(OSError):
            fs.file_size(Path("Activity/inexistant.fit"))


@pytest.mark.unit
class TestAbsolutePath:
    def test_resolves_relative_to_garmin_root(self, fs, tmp_path) -> None:
        assert fs.absolute_path(Path("Activity/run.fit")) == (
            tmp_path / "GARMIN" / "Activity" / "run.fit"
        )

    def test_resolved_path_is_writable(self, fs) -> None:
        # Le chemin absolu retourné doit pointer sur le fichier réellement écrit.
        _write(fs, "Activity/run.fit", b"data")
        assert fs.absolute_path(Path("Activity/run.fit")).read_bytes() == b"data"
