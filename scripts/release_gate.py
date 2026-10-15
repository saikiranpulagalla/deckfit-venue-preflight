from pathlib import Path
import argparse
import hashlib
import os
import shutil
import tempfile
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
RESOURCE_TIMEOUT_S = 120
_RUN_COUNTER = 0

CRITICAL_ARTIFACTS = [
    ROOT / "backend/tests/fixtures/safe_large.pptx",
    ROOT / "backend/tests/fixtures/small_text.pptx",
    ROOT / "backend/tests/fixtures/mixed_sizes.pptx",
    ROOT / "backend/tests/fixtures/image_only.pptx",
    ROOT / "demo/venue-agent-demo.pptx",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_artifacts() -> dict[str, str]:
    missing = [str(p) for p in CRITICAL_ARTIFACTS if not p.exists()]
    if missing:
        raise SystemExit(f"Missing critical release artifacts: {missing}")
    return {str(p.relative_to(ROOT)): sha256(p) for p in CRITICAL_ARTIFACTS}


def assert_artifacts_unchanged(before: dict[str, str]) -> None:
    after = snapshot_artifacts()
    changed = [name for name, digest in before.items() if after.get(name) != digest]
    if changed:
        raise SystemExit(f"P0 release-gate failure: tracked source/demo artifacts changed during tests: {changed}")


def run(args, *, timeout: int = RESOURCE_TIMEOUT_S):
    global _RUN_COUNTER
    _RUN_COUNTER += 1
    print("+", " ".join(args), flush=True)
    session_root = Path(tempfile.gettempdir()) / f"venue-agent-gate-{os.getpid()}-{_RUN_COUNTER}"
    shutil.rmtree(session_root, ignore_errors=True)
    env = os.environ.copy()
    env["VENUE_SESSION_ROOT"] = str(session_root)
    try:
        p = subprocess.run(args, cwd=BACKEND, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        raise SystemExit(f"Test subprocess timed out after {timeout}s: {' '.join(args)}") from e
    finally:
        shutil.rmtree(session_root, ignore_errors=True)
    if p.returncode != 0:
        raise SystemExit(p.returncode)


parser = argparse.ArgumentParser()
parser.add_argument("--full", action="store_true", help="run every LibreOffice/resource regression in fresh pytest processes")
args = parser.parse_args()

artifact_snapshot = snapshot_artifacts()
try:
    run([sys.executable, "-m", "pytest", "-q", "-m", "not resource"], timeout=60)
    # Mandatory resource gates are isolated one test per pytest process.
    # Repeated LibreOffice conversions can leave runner-finalization state behind
    # in constrained CI; isolation makes the gate evidence about the product, not
    # about cross-test office-process cleanup.
    mandatory_resource_nodes = [
        "tests/integration/test_vertical_slice.py::test_full_vertical_slice_small_text",
        "tests/integration/test_vertical_slice.py::test_image_only_is_never_green",
        "tests/integration/test_multi_plan_demo.py::test_demo_requires_and_verifies_multi_issue_plan",
        "tests/integration/test_duplicate_text_mapping.py::test_same_text_in_two_shapes_keeps_distinct_rendered_identity",
        "tests/integration/test_v12_safety_roundtrip.py::test_visual_overlap_or_wrap_cannot_receive_verified",
        "tests/integration/test_v12_safety_roundtrip.py::test_missing_requested_font_is_never_auto_mutable",
        "tests/integration/test_v12_safety_roundtrip.py::test_table_text_remains_explicitly_not_analyzed",
        "tests/integration/test_v12_safety_roundtrip.py::test_candidate_simulation_blocks_target_seeking_scale_that_wraps_or_overlaps",
        "tests/integration/test_v12_safety_roundtrip.py::test_unknown_content_remaining_after_successful_target_repair_cannot_be_verified",
        "tests/integration/test_v12_safety_roundtrip.py::test_opaque_visual_overlay_blocks_whole_deck_verified",
        "tests/integration/test_unknown_state_api.py::test_image_only_deck_is_review_required_not_no_action",
        "tests/integration/test_unknown_state_api.py::test_outside_reference_deck_is_review_required_not_no_action",
        "tests/integration/test_v14_deep_readiness.py::test_deep_readiness_performs_real_cached_demo_render",
        "tests/adversarial/test_r5_coverage_and_intake.py::test_public_api_never_verifies_deck_with_unmodeled_visual_content[opaque_text_overlay.pptx]",
        "tests/adversarial/test_r5_coverage_and_intake.py::test_public_api_never_verifies_deck_with_unmodeled_visual_content[background-image.pptx]",
        "tests/adversarial/test_r5_coverage_and_intake.py::test_public_api_never_verifies_deck_with_unmodeled_visual_content[picture-placeholder-repair.pptx]",
        "tests/adversarial/test_r6_corrective_gates.py::test_actual_rendered_mask_does_not_verify_in_public_api",
        "tests/adversarial/test_r7_release_gates.py::test_outlined_textbox_never_reaches_verified_during_authenticated_roundtrip",
        "tests/adversarial/test_r7_release_gates.py::test_authenticated_plan_recovery_after_refresh_and_stale_invalidation",
        "tests/adversarial/test_r8_closure.py::test_theme_styled_overlay_cannot_verify_via_public_api",
        "tests/adversarial/test_r8_closure.py::test_hidden_middle_slide_maps_visible_last_slide",
        "tests/adversarial/test_r8_closure.py::test_hidden_image_is_not_reported_as_visible_unknown",
    ]
    for node in mandatory_resource_nodes:
        run([sys.executable, "-m", "pytest", "-q", "-m", "resource", node])

    if args.full:
        # Do not maintain a fragile hardcoded list that silently misses newly
        # marked LibreOffice tests. Isolate and run EVERY collected resource
        # node exactly once; skip ones already exercised by the mandatory gate.
        collected = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "resource"],
            cwd=BACKEND, capture_output=True, text=True, timeout=60, check=True,
        )
        resource_nodes = [line.strip() for line in collected.stdout.splitlines()
                          if line.startswith("tests/") and "::" in line]
        if not resource_nodes or len(resource_nodes) != len(set(resource_nodes)):
            raise SystemExit("Resource collection failed or contained duplicate nodes")
        if not set(mandatory_resource_nodes).issubset(resource_nodes):
            raise SystemExit("Mandatory resource test missing from collection")
        for node in resource_nodes:
            if node not in mandatory_resource_nodes:
                run([sys.executable, "-m", "pytest", "-q", "-m", "resource", node])
finally:
    assert_artifacts_unchanged(artifact_snapshot)

print("RELEASE GATE PASS")
