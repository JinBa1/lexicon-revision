from src.access.models import (
    CollectionAccessListing,
    CollectionCommunitySummary,
    CollectionListItem,
    CollectionYearRange,
    SupportedUniversity,
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


def test_collection_list_item_json_roundtrip():
    item = CollectionListItem(
        name="cam-cs-tripos",
        display_name="Cambridge CS Tripos",
        community=CollectionCommunitySummary(id="c-cam", display_name="Cambridge"),
        paper_count=744,
        year_range=CollectionYearRange(start=2018, end=2025),
        metadata_schema=None,
        access_state="accessible",
        lock_reason=None,
    )
    payload = item.model_dump(mode="json")
    assert payload["access_state"] == "accessible"
    assert payload["year_range"] == {"start": 2018, "end": 2025}


def test_collection_list_item_rejects_unknown_fields():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CollectionListItem.model_validate(
            {
                "name": "cam",
                "display_name": "Cambridge",
                "community": None,
                "paper_count": 1,
                "year_range": None,
                "metadata_schema": None,
                "access_state": "accessible",
                "lock_reason": None,
                "stray": "extra",
            }
        )


def test_supported_university_json_shape():
    uni = SupportedUniversity(
        id="c-cam",
        display_name="Cambridge",
        email_domains=["cam.ac.uk"],
    )
    payload = uni.model_dump(mode="json")
    assert payload == {
        "id": "c-cam",
        "display_name": "Cambridge",
        "email_domains": ["cam.ac.uk"],
    }
