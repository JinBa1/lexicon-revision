from src.search.models import (
    ChunkDetailResponse,
    ChunkParentContext,
    MediaRefResponse,
)


def test_chunk_detail_response_json_shape():
    response = ChunkDetailResponse(
        chunk_id="cam-2022-p5-q3b",
        chunk_level="sub_question",
        parent_chunk_id="cam-2022-p5-q3",
        sub_question_label="(b)",
        text="Give an amortized analysis…",
        metadata={"year": 2022},
        media=[
            MediaRefResponse(
                media_id="m-1",
                kind="image",
                object_key="collections/cam/media/m-1.png",
                access_url="https://example.test/media/m-1",
                relation="direct",
            )
        ],
        collection="cam-cs-tripos",
        parent=ChunkParentContext(
            text="Consider a dynamic array…",
            metadata={"year": 2022},
        ),
    )
    payload = response.model_dump(mode="json")
    assert payload["collection"] == "cam-cs-tripos"
    assert payload["media"][0]["media_id"] == "m-1"
    assert payload["parent"]["text"].startswith("Consider")


def test_chunk_detail_response_rejects_unknown_fields():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChunkDetailResponse.model_validate(
            {
                "chunk_id": "x",
                "chunk_level": "question",
                "parent_chunk_id": None,
                "sub_question_label": None,
                "text": "t",
                "metadata": {},
                "media": [],
                "collection": "c",
                "parent": None,
                "stray": "extra",
            }
        )
