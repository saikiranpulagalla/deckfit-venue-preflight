from fastapi.testclient import TestClient
import hashlib
import pytest

from app.main import STORE, app

pytestmark = pytest.mark.resource


def test_api_closed_loop(project_root):
    with TestClient(app) as client:
        src = project_root / "backend/tests/fixtures/small_text.pptx"
        with src.open("rb") as f:
            r = client.post(
                "/api/upload",
                files={"file": ("small_text.pptx", f, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
            )
        assert r.status_code == 200, r.text
        sid = r.json()["session_id"]
        headers = {"X-Venue-Token": r.json()["session_token"]}
        r = client.post(
            f"/api/sessions/{sid}/analyze",
            headers=headers,
            json={"venue": {"active_image_height_m": 1.8, "farthest_viewer_distance_m": 10.8, "measurement_basis": "MEASURED"}},
        )
        assert r.status_code == 200, r.text
        assert r.json()["analysis"]["summary"]["below_target_elements"] >= 1
        r = client.post(
            f"/api/sessions/{sid}/plan",
            headers=headers,
            json={"constraints": {"max_mutations": 1, "max_scale_factor": 1.6, "minimum_target_coverage": 0.9, "protect_titles": True, "semantic_rewrite": False}},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["state"] == "AWAITING_APPROVAL"
        cid = body["decision"]["selected_candidate_ids"][0]
        r = client.post(
            f"/api/sessions/{sid}/approve-and-apply",
            headers=headers,
            json={"candidate_id": cid, "plan_hash": body["plan_hash"], "idempotency_key": "test-idem-1", "approve": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "VERIFIED", r.json()
        verification = r.json()["verification"]
        out = client.get(f"/api/sessions/{sid}/output", headers=headers)
        assert out.status_code == 200
        assert len(out.content) > 1000
        assert out.headers["cache-control"] == "private, no-store, max-age=0"
        assert out.headers["x-content-type-options"] == "nosniff"
        downloaded_sha = hashlib.sha256(out.content).hexdigest()
        assert downloaded_sha == verification["output_sha256"]
        assert out.headers["x-venue-output-sha256"] == downloaded_sha

        # The download path re-binds the bytes to the artifact verified above.
        # A post-verification mutation must fail closed rather than serving a
        # different file under a previous VERIFIED state.
        with STORE.locked(sid) as session:
            assert session.output_path is not None
            session.output_path.write_bytes(session.output_path.read_bytes() + b"tamper")
        tampered = client.get(f"/api/sessions/{sid}/output", headers=headers)
        assert tampered.status_code == 409
        assert tampered.json()["detail"] == "Output artifact changed after verification"
        status = client.get(f"/api/sessions/{sid}", headers=headers)
        assert status.status_code == 200
        assert status.json()["state"] == "FAILED"
        assert status.json()["has_output"] is False
        assert status.json()["output_sha256"] is None
