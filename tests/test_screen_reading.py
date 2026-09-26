from unittest.mock import Mock

from src.poetore.screen_reading import ScreenReadingCoordinator


def test_screen_reading_coordinator_serializes_features_and_releases_owner():
    ocr = Mock()
    coordinator = ScreenReadingCoordinator(ocr)

    assert coordinator.try_begin("expedition")
    assert not coordinator.try_begin("desecration")
    coordinator.finish("desecration")
    assert coordinator.owner == "expedition"
    coordinator.finish("expedition")
    assert coordinator.try_begin("desecration")


def test_screen_reading_coordinator_delegates_and_closes():
    ocr = Mock()
    ocr.recognize.return_value = ["ok"]
    coordinator = ScreenReadingCoordinator(ocr)

    coordinator.start()
    assert coordinator.recognize([b"image"]) == ["ok"]
    coordinator.try_begin("expedition")
    coordinator.close()

    ocr.start.assert_called_once_with()
    ocr.recognize.assert_called_once_with([b"image"])
    ocr.close.assert_called_once_with()
    assert coordinator.owner is None
