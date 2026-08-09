import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.models import PriceObservation, utc_now
from app.core.state import BotState


class LatestLiveMarkTests(unittest.TestCase):
    def test_uses_newest_accepted_observation_beyond_oldest_storage_page(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            observed_at = utc_now() - timedelta(minutes=5)
            for index in range(1, 102):
                state.storage.save_price_observation(
                    PriceObservation(
                        id=f"px_page_{index}",
                        source="pumpportal",
                        mint="MintLatestMarkPage",
                        observed_at=observed_at + timedelta(seconds=index),
                        price=index / 1_000_000,
                        price_source="direct",
                        confidence=0.9,
                        accepted=True,
                    )
                )

            mark = state._latest_live_mark_price_snapshot("MintLatestMarkPage")

            self.assertEqual(mark["price"], 0.000101)
            self.assertEqual(mark["observed_at"], observed_at + timedelta(seconds=101))

    def test_uses_newest_accepted_observation_after_rejected_newest_observation(self) -> None:
        with TemporaryDirectory() as directory:
            state = BotState(database_path=str(Path(directory) / "test.db"))
            observed_at = utc_now() - timedelta(minutes=5)
            observations = (
                PriceObservation(
                    id="px_old_accepted",
                    source="pumpportal",
                    mint="MintLatestMark",
                    observed_at=observed_at,
                    price=0.00001,
                    price_source="direct",
                    confidence=0.7,
                    accepted=True,
                ),
                PriceObservation(
                    id="px_new_accepted",
                    source="pumpportal",
                    mint="MintLatestMark",
                    observed_at=observed_at + timedelta(seconds=1),
                    price=0.00002,
                    price_source="direct",
                    confidence=0.8,
                    accepted=True,
                ),
                PriceObservation(
                    id="px_newest_rejected",
                    source="pumpportal",
                    mint="MintLatestMark",
                    observed_at=observed_at + timedelta(seconds=2),
                    price=0.00003,
                    price_source="direct",
                    confidence=0.9,
                    accepted=False,
                ),
            )
            for observation in observations:
                state.storage.save_price_observation(observation)

            stored = state.storage.load_price_observations(100, mint="MintLatestMark")
            mark = state._latest_live_mark_price_snapshot("MintLatestMark")

            self.assertEqual([observation.id for observation in stored], [
                "px_old_accepted",
                "px_new_accepted",
                "px_newest_rejected",
            ])
            self.assertEqual(mark["price"], 0.00002)
            self.assertEqual(mark["source"], "pumpportal:direct")
            self.assertEqual(mark["observed_at"], observed_at + timedelta(seconds=1))


if __name__ == "__main__":
    unittest.main()
