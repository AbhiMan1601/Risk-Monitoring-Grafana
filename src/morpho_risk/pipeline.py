from __future__ import annotations

import logging
import time

from psycopg import connect

from .anomaly import RobustHealthFactorDetector
from .config import Settings
from .db import DbClient
from .morpho_source import MorphoApiSource, MorphoSource, SyntheticMorphoSource


def build_source(settings: Settings) -> MorphoSource:
    if settings.use_synthetic_source:
        return SyntheticMorphoSource(vault_count=settings.synthetic_vaults)
    if not settings.morpho_api_url:
        raise ValueError("MORPHO_API_URL is required when USE_SYNTHETIC_SOURCE=false")
    return MorphoApiSource(url=settings.morpho_api_url, api_key=settings.morpho_api_key or None)


def run() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger = logging.getLogger("morpho-risk")

    source = build_source(settings)

    with connect(settings.database_url, autocommit=False) as conn:
        db = DbClient(conn)
        detector = RobustHealthFactorDetector(settings)
        detector.load_state(db.load_detector_states())

        logger.info("Risk engine started. poll_interval_seconds=%s", settings.poll_interval_seconds)

        while True:
            try:
                snapshots = source.fetch_snapshots()
                db.insert_snapshots(snapshots)

                events = []
                for snapshot in snapshots:
                    event = detector.score_snapshot(snapshot)
                    if event:
                        events.append(event)

                db.insert_anomalies(events)
                db.upsert_detector_state(detector.export_state())

                logger.info(
                    "Cycle complete snapshots=%s anomalies=%s",
                    len(snapshots),
                    len(events),
                )
            except Exception:
                logger.exception("Cycle failed")

            time.sleep(settings.poll_interval_seconds)