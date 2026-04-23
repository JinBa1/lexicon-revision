from src.access.models import (
    CollectionAccessListing,
    SupportedUniversityRecord,
)


def test_collection_access_listing_is_frozen_dataclass():
    listing = CollectionAccessListing(
        collection_name="cam-cs-tripos",
        display_name="Cambridge CS Tripos",
        community_id="c-cam",
        community_display_name="Cambridge",
        paper_count=744,
        year_start=2018,
        year_end=2025,
        access_state="accessible",
        lock_reason=None,
        metadata_schema={"version": 1, "fields": []},
    )
    try:
        listing.collection_name = "other"  # type: ignore[misc]
    except Exception:
        pass
    assert listing.collection_name == "cam-cs-tripos"


def test_supported_university_record_holds_required_fields():
    record = SupportedUniversityRecord(
        community_id="c-cam",
        display_name="Cambridge",
        email_domains=("cam.ac.uk",),
    )
    assert record.email_domains == ("cam.ac.uk",)
