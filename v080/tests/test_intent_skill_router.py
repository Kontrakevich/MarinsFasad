from fastapi.testclient import TestClient

from app.intelligence.intent_router import IntentSkillRouter
from app.main import app


client = TestClient(app)


def test_router_promotes_outpaint_with_object_removal_to_hybrid() -> None:
    route = IntentSkillRouter.route(
        "outpaint",
        [
            "Дорисуй залитые темные места",
            "Удали столбы и провода.",
            "Дорисуй окружение в нижних углах.",
        ],
    )
    assert route["auto_routed"] is True
    assert route["requested_mode"] == "outpaint"
    assert route["effective_mode"] == "hybrid"
    assert "semantic_object_removal" in route["signals"]
    assert "visible_pixel_repair" in route["signals"]


def test_router_keeps_pure_missing_region_request_as_outpaint() -> None:
    route = IntentSkillRouter.route(
        "outpaint",
        ["Дорисуй отсутствующее окружение в нижних углах изображения."],
    )
    assert route["auto_routed"] is False
    assert route["effective_mode"] == "outpaint"
    assert route["signals"] == []


def test_router_keeps_local_lighting_and_wetness_as_outpaint_context() -> None:
    route = IntentSkillRouter.route(
        "outpaint",
        ["Продолжить мокрый асфальт и вечернее освещение в отсутствующих областях."],
    )
    assert route["auto_routed"] is False
    assert route["effective_mode"] == "outpaint"
    assert "scene_wide_relight_or_weather" not in route["signals"]


def test_router_promotes_explicit_global_relight_from_outpaint_to_hybrid() -> None:
    route = IntentSkillRouter.route(
        "outpaint",
        ["Сделай вечернее освещение по всему кадру и дорисуй отсутствующие углы."],
    )
    assert route["auto_routed"] is True
    assert route["effective_mode"] == "hybrid"
    assert "scene_wide_relight_or_weather" in route["signals"]


def test_compiled_prompt_uses_effective_hybrid_for_conflicting_outpaint_intent() -> None:
    created = client.post("/api/projects", data={"name": "Intent router conflict"})
    assert created.status_code == 200
    project_id = created.json()["id"]

    for comment in (
        "__MARINS_GENERATION_MODE__:outpaint",
        "__MARINS_GENERATION_QUALITY__:max",
        "Дорисуй залитые темные места",
        "Удали столбы и провода.",
        "Дорисуй окружение в нижних углах.",
    ):
        response = client.post(
            f"/api/projects/{project_id}/comments/environment",
            data={"comment": comment},
        )
        assert response.status_code == 200

    compiled = client.get(f"/api/projects/{project_id}/prompt/environment")
    assert compiled.status_code == 200
    payload = compiled.json()

    assert payload["requested_generation_mode"] == "outpaint"
    assert payload["effective_generation_mode"] == "hybrid"
    assert payload["generation_mode"] == "hybrid"
    assert payload["intent_router"]["auto_routed"] is True
    assert "GENERATION MODE\nHYBRID" in payload["prompt"]
    assert "Requested skill: OUTPAINT" in payload["prompt"]
    assert "Effective skill: HYBRID" in payload["prompt"]
    assert "Удали столбы и провода." in payload["prompt"]
    assert "__MARINS_GENERATION_MODE__" not in payload["prompt"]


def test_compiled_prompt_keeps_pure_outpaint() -> None:
    created = client.post("/api/projects", data={"name": "Intent router pure outpaint"})
    project_id = created.json()["id"]
    client.post(
        f"/api/projects/{project_id}/comments/environment",
        data={"comment": "__MARINS_GENERATION_MODE__:outpaint"},
    )
    client.post(
        f"/api/projects/{project_id}/comments/environment",
        data={"comment": "Дорисуй отсутствующее окружение в нижних углах изображения."},
    )

    payload = client.get(f"/api/projects/{project_id}/prompt/environment").json()
    assert payload["requested_generation_mode"] == "outpaint"
    assert payload["effective_generation_mode"] == "outpaint"
    assert payload["intent_router"]["auto_routed"] is False
    assert "GENERATION MODE\nOUTPAINT" in payload["prompt"]
