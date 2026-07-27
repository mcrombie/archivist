import json

import pytest

from evidence_policy import (
    AnchorMatchKind,
    AnchorMatchRule,
    EvidenceDecision,
    EvidenceLane,
    EvidenceTargetRole,
    assess_corpus_integrity,
    build_immediate_neighbor_map,
    classify_anchor_match,
    classify_evidence_lanes,
    decide_evidence,
    decide_multi_subject_evidence,
    evidence_diagnostics,
    normalize_anchor,
    scan_broader_related,
    scan_evidence_target,
    split_compound_named_anchor,
    tokenize_anchor,
)


MANIFEST_SHA256 = "a" * 64


def chunk(
    chunk_id: str,
    text: str,
    *,
    document: str = "synthetic-a.md",
) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document": document,
        "text": text,
    }


def matching_integrity(
    chunks: list[dict[str, object]],
    *,
    manifest_sha256: str = MANIFEST_SHA256,
):
    chunk_ids = [str(item["chunk_id"]) for item in chunks]
    return assess_corpus_integrity(
        chunks,
        manifest_eligible_chunk_ids=chunk_ids,
        expected_manifest_sha256=manifest_sha256,
        loaded_manifest_sha256=manifest_sha256,
        expected_collection_count=len(chunks),
        collection_count=len(chunks),
    )


def scan(
    target_id: str,
    surface: str,
    chunks: list[dict[str, object]],
    *,
    absence_checkable: bool = True,
    role: EvidenceTargetRole = EvidenceTargetRole.SUBJECT,
):
    return scan_evidence_target(
        target_id,
        surface,
        chunks,
        absence_checkable=absence_checkable,
        corpus_integrity=matching_integrity(chunks),
        role=role,
    )


def test_anchor_normalization_handles_unicode_possessives_hyphens_and_numerics():
    assert tokenize_anchor("  ＸＲ–３７’s ORBIT-RELAY  ") == (
        "xr",
        "37",
        "orbit",
        "relay",
    )
    assert normalize_anchor("S.R.C.’s") == "src"
    assert tokenize_anchor("unit 7") == ("unit", "7")


@pytest.mark.parametrize(
    ("anchor", "passage"),
    [
        ("XR-37", "The XR37 unit completed a synthetic trial."),
        ("Orbit Relay", "The orbit-relay's charter was revised."),
        ("S.R.C.", "SRC issued a synthetic notice."),
    ],
)
def test_full_token_sequences_are_strong_across_mechanical_forms(anchor, passage):
    match = classify_anchor_match(anchor, passage)

    assert match.kind is AnchorMatchKind.STRONG
    assert match.rule is AnchorMatchRule.FULL_TOKEN_SEQUENCE


def test_weak_match_uses_an_inclusive_twelve_token_window():
    ten_fillers = "amber birch cedar delta ember fern granite harbor ivory juniper"
    within_twelve = classify_anchor_match(
        "orchid relay",
        f"orchid {ten_fillers} relay",
    )
    outside_twelve = classify_anchor_match(
        "orchid relay",
        f"orchid {ten_fillers} kelp relay",
    )

    assert within_twelve.kind is AnchorMatchKind.WEAK
    assert within_twelve.rule is AnchorMatchRule.TWELVE_TOKEN_WINDOW
    assert outside_twelve.kind is AnchorMatchKind.PARTIAL_TOKEN_COLLISION


def test_mechanically_derived_initialism_is_weak_without_an_expansion():
    match = classify_anchor_match(
        "Synthetic Research Council",
        "The SRC convened after the trial.",
    )

    assert match.kind is AnchorMatchKind.WEAK
    assert match.rule is AnchorMatchRule.MECHANICAL_INITIALISM


def test_mechanical_initialism_does_not_match_an_ordinary_lowercase_word():
    match = classify_anchor_match(
        "United States",
        "They asked us to leave.",
    )

    assert match.kind is AnchorMatchKind.NONE
    assert match.rule is AnchorMatchRule.NONE


@pytest.mark.parametrize("initialism", ["US", "U.S."])
def test_mechanical_initialism_matches_explicit_uppercase_forms(initialism):
    match = classify_anchor_match(
        "United States",
        f"The {initialism} issued a synthetic notice.",
    )

    assert match.kind is AnchorMatchKind.WEAK
    assert match.rule is AnchorMatchRule.MECHANICAL_INITIALISM


def test_partial_multiword_token_collisions_never_become_direct_evidence():
    chunks = [
        chunk("c1", "Copper deposits appeared in the sample."),
        chunk("c2", "A signal crossed the test rig."),
        chunk("c3", "The bureau logged a separate result."),
    ]
    target_scan = scan("T0", "Copper Signal Bureau", chunks)

    assert target_scan.direct_chunk_ids == ()
    assert target_scan.partial_chunk_ids == ("c1", "c2", "c3")
    assert target_scan.certified_direct_absence is True


def test_compound_person_names_split_without_splitting_organization_names():
    assert split_compound_named_anchor("John Foster and Allen Dulles") == (
        "John Foster",
        "Allen Dulles",
    )
    organization = "Briar Council and Moss Company"
    assert split_compound_named_anchor(organization) == (organization,)


def test_trusted_target_scan_checks_the_complete_eligible_chunk_set():
    chunks = [
        chunk("c1", "Unrelated synthetic material."),
        chunk("c2", "More unrelated synthetic material."),
        chunk("c3", "The Orchid Relay appears in this final chunk."),
    ]
    target_scan = scan("T0", "Orchid Relay", chunks)

    assert target_scan.scanned_chunk_count == 3
    assert target_scan.strong_chunk_ids == ("c3",)
    assert target_scan.direct_present is True
    assert target_scan.certified_direct_absence is False


def test_scan_scope_mismatch_fails_closed_even_when_the_subset_has_a_hit():
    chunks = [
        chunk("c1", "The Orchid Relay appears here."),
        chunk("c2", "A second eligible chunk."),
    ]
    integrity = matching_integrity(chunks)
    target_scan = scan_evidence_target(
        "T0",
        "Orchid Relay",
        chunks[:1],
        absence_checkable=True,
        corpus_integrity=integrity,
    )

    assert target_scan.direct_present is True
    assert "scan_scope_mismatch" in target_scan.integrity.failure_codes
    assert decide_evidence(target_scan).decision is EvidenceDecision.INDETERMINATE


def test_same_chunk_subject_and_facet_support_a_direct_answer():
    chunks = [
        chunk(
            "c1",
            "The Orchid Relay used thermal mapping during the synthetic trial.",
        )
    ]
    subject_scan = scan("T0", "Orchid Relay", chunks)
    facet_scan = scan(
        "T1",
        "thermal mapping",
        chunks,
        absence_checkable=False,
        role=EvidenceTargetRole.FACET,
    )
    lanes = classify_evidence_lanes(
        chunks,
        subject_scan=subject_scan,
        facet_scan=facet_scan,
    )
    result = decide_evidence(
        subject_scan,
        facet_scan=facet_scan,
        lane_assignments=lanes,
    )

    assert result.decision is EvidenceDecision.DIRECT_ANSWER
    assert result.relationship_chunk_ids == ("c1",)
    assert lanes[0].lane is EvidenceLane.DIRECT
    assert result.allowed_source_numbers == (1,)


def test_immediate_neighbors_can_support_a_relationship_but_distant_chunks_cannot():
    chunks = [
        chunk("c1", "The Orchid Relay was activated."),
        chunk("c2", "Thermal mapping guided its synthetic route."),
        chunk("c3", "A neutral separator passage."),
        chunk("c4", "Pressure balancing was tested much later."),
    ]
    neighbors = build_immediate_neighbor_map(chunks)
    subject_scan = scan("T0", "Orchid Relay", chunks)
    nearby_facet = scan(
        "T1",
        "thermal mapping",
        chunks,
        absence_checkable=False,
        role=EvidenceTargetRole.FACET,
    )
    distant_facet = scan(
        "T2",
        "pressure balancing",
        chunks,
        absence_checkable=False,
        role=EvidenceTargetRole.FACET,
    )

    nearby = decide_evidence(
        subject_scan,
        facet_scan=nearby_facet,
        immediate_neighbors=neighbors,
    )
    distant = decide_evidence(
        subject_scan,
        facet_scan=distant_facet,
        immediate_neighbors=neighbors,
    )

    assert nearby.decision is EvidenceDecision.DIRECT_ANSWER
    assert nearby.relationship_chunk_ids == ("c1", "c2")
    assert distant.decision is EvidenceDecision.PARTIAL_ANSWER
    assert distant.relationship_chunk_ids == ()


def test_partial_answer_suppresses_distant_semantic_relationship_material():
    chunks = [
        chunk("c1", "The Orchid Relay was activated."),
        chunk("c2", "A neutral separator passage."),
        chunk("c3", "Pressure balancing was tested independently."),
    ]
    neighbors = build_immediate_neighbor_map(chunks)
    subject_scan = scan("T0", "Orchid Relay", chunks)
    facet_scan = scan(
        "T1",
        "pressure balancing",
        chunks,
        absence_checkable=False,
        role=EvidenceTargetRole.FACET,
    )
    selected = [chunks[0], chunks[2]]
    lanes = classify_evidence_lanes(
        selected,
        subject_scan=subject_scan,
        facet_scan=facet_scan,
        immediate_neighbors=neighbors,
    )
    result = decide_evidence(
        subject_scan,
        facet_scan=facet_scan,
        lane_assignments=lanes,
        immediate_neighbors=neighbors,
    )

    assert [assignment.lane for assignment in lanes] == [
        EvidenceLane.DIRECT,
        EvidenceLane.GENERIC_SEMANTIC,
    ]
    assert result.decision is EvidenceDecision.PARTIAL_ANSWER
    assert result.allowed_source_numbers == (1,)
    assert result.suppressed_source_numbers == (2,)


def test_all_direct_multi_subjects_admit_the_full_retrieved_context():
    chunks = [
        chunk("c1", "Avery North appears in this synthetic record."),
        chunk("c2", "Blake South appears in another synthetic record."),
        chunk("c3", "A retrieved contextual passage connects the argument."),
    ]
    scans = (
        scan("T1", "Avery North", chunks),
        scan("T2", "Blake South", chunks),
    )
    lanes = classify_evidence_lanes(
        chunks,
        subject_scan=scans[0],
        additional_subject_scans=scans[1:],
    )

    result = decide_multi_subject_evidence(
        scans,
        lane_assignments=lanes,
    )

    assert result.decision is EvidenceDecision.DIRECT_ANSWER
    assert result.rules_fired == ("all_subject_targets_direct",)
    assert result.allowed_source_numbers == (1, 2, 3)
    assert result.suppressed_source_numbers == ()


def test_partial_multi_subject_result_admits_only_present_subject_material():
    chunks = [
        chunk("c1", "Avery North appears in this synthetic record."),
        chunk("c2", "An unrelated retrieved contextual passage."),
    ]
    scans = (
        scan("T1", "Avery North", chunks),
        scan("T2", "Blake South", chunks),
    )
    lanes = classify_evidence_lanes(
        chunks,
        subject_scan=scans[0],
        additional_subject_scans=scans[1:],
    )

    result = decide_multi_subject_evidence(
        scans,
        lane_assignments=lanes,
    )

    assert result.decision is EvidenceDecision.PARTIAL_ANSWER
    assert result.certified_direct_absence is False
    assert result.rules_fired == ("some_subject_targets_direct",)
    assert result.allowed_source_numbers == (1,)
    assert result.suppressed_source_numbers == (2,)


def test_multi_subject_absence_requires_every_target_to_be_certifiable():
    chunks = [chunk("c1", "Only unrelated synthetic material appears.")]
    certifiable = (
        scan("T1", "Avery North", chunks),
        scan("T2", "Blake South", chunks),
    )
    uncertain = (
        certifiable[0],
        scan(
            "T2",
            "Blake South",
            chunks,
            absence_checkable=False,
        ),
    )

    absent = decide_multi_subject_evidence(certifiable)
    indeterminate = decide_multi_subject_evidence(uncertain)

    assert absent.decision is EvidenceDecision.CLEAN_ABSTENTION
    assert absent.certified_direct_absence is True
    assert indeterminate.decision is EvidenceDecision.INDETERMINATE
    assert indeterminate.certified_direct_absence is False


def test_absent_target_plus_analogue_produces_clean_abstention():
    chunks = [chunk("c1", "The Mirror Council managed a separate synthetic system.")]
    subject_scan = scan("T0", "Orchid Relay", chunks)
    lanes = classify_evidence_lanes(
        chunks,
        subject_scan=subject_scan,
        analogue_chunk_ids={"c1"},
    )
    result = decide_evidence(
        subject_scan,
        lane_assignments=lanes,
    )

    assert lanes[0].lane is EvidenceLane.ANALOGUE
    assert result.decision is EvidenceDecision.CLEAN_ABSTENTION
    assert result.certified_direct_absence is True
    assert result.skip_answer_generation is True
    assert result.allowed_source_numbers == ()
    assert result.suppressed_source_numbers == (1,)


def test_broader_term_and_additional_probe_in_a_neighbor_qualify_near_match():
    chunks = [
        chunk("c1", "Regional councils coordinated synthetic requests."),
        chunk("c2", "Supply allocation was their documented mechanism."),
        chunk("c3", "A peer organization used another process."),
    ]
    neighbors = build_immediate_neighbor_map(chunks)
    subject_scan = scan("T0", "Orchid Relay", chunks)
    broader_scan = scan_broader_related(
        "regional councils",
        ["supply allocation"],
        chunks,
        immediate_neighbors=neighbors,
    )
    lanes = classify_evidence_lanes(
        chunks,
        subject_scan=subject_scan,
        broader_related_scan=broader_scan,
        analogue_chunk_ids={"c3"},
        immediate_neighbors=neighbors,
    )
    result = decide_evidence(
        subject_scan,
        lane_assignments=lanes,
        broader_related_scan=broader_scan,
        immediate_neighbors=neighbors,
    )

    assert broader_scan.qualifying_pairs == (("c1", "c2"),)
    assert [assignment.lane for assignment in lanes] == [
        EvidenceLane.BROADER_RELATED,
        EvidenceLane.BROADER_RELATED,
        EvidenceLane.ANALOGUE,
    ]
    assert result.decision is EvidenceDecision.QUALIFIED_NEAR_MATCH
    assert result.allowed_source_numbers == (1, 2)
    assert result.suppressed_source_numbers == (3,)


def test_qualified_near_match_admission_is_capped_at_two_sources():
    chunks = [
        chunk("c1", "The first planner-qualified related passage."),
        chunk("c2", "The second planner-qualified related passage."),
        chunk("c3", "The third planner-qualified related passage."),
    ]
    subject_scan = scan("T0", "Orchid Relay", chunks)
    lanes = classify_evidence_lanes(
        chunks,
        subject_scan=subject_scan,
        qualified_related_chunk_ids={"c1", "c2", "c3"},
    )

    result = decide_evidence(subject_scan, lane_assignments=lanes)

    assert result.decision is EvidenceDecision.QUALIFIED_NEAR_MATCH
    assert result.allowed_source_numbers == (1, 2)
    assert result.suppressed_source_numbers == (3,)


def test_broad_term_alone_cannot_qualify_a_near_match():
    chunks = [
        chunk("c1", "Regional councils coordinated synthetic requests."),
        chunk("c2", "A generic passage without the related probe."),
    ]
    subject_scan = scan("T0", "Orchid Relay", chunks)
    broader_scan = scan_broader_related(
        "regional councils",
        ["supply allocation"],
        chunks,
    )
    lanes = classify_evidence_lanes(
        chunks,
        subject_scan=subject_scan,
        broader_related_scan=broader_scan,
    )
    result = decide_evidence(
        subject_scan,
        lane_assignments=lanes,
        broader_related_scan=broader_scan,
    )

    assert broader_scan.broader_strong_chunk_ids == ("c1",)
    assert broader_scan.qualified_chunk_ids == ()
    assert all(assignment.lane is EvidenceLane.GENERIC_SEMANTIC for assignment in lanes)
    assert result.decision is EvidenceDecision.CLEAN_ABSTENTION


def test_non_checkable_absence_is_indeterminate():
    chunks = [chunk("c1", "Only generic synthetic material appears.")]
    subject_scan = scan(
        "T0",
        "the conceptual pattern",
        chunks,
        absence_checkable=False,
    )

    result = decide_evidence(subject_scan)

    assert result.decision is EvidenceDecision.INDETERMINATE
    assert result.certified_direct_absence is False


def test_corpus_manifest_or_collection_mismatch_overrides_positive_evidence():
    chunks = [chunk("c1", "The Orchid Relay appears here.")]
    integrity = assess_corpus_integrity(
        chunks,
        manifest_eligible_chunk_ids=["c1", "c2"],
        expected_manifest_sha256=MANIFEST_SHA256,
        loaded_manifest_sha256="b" * 64,
        expected_collection_count=2,
        collection_count=1,
    )
    subject_scan = scan_evidence_target(
        "T0",
        "Orchid Relay",
        chunks,
        absence_checkable=True,
        corpus_integrity=integrity,
    )
    result = decide_evidence(
        subject_scan,
        premise_contradiction_chunk_ids={"c1"},
    )

    assert subject_scan.direct_present is True
    assert integrity.passed is False
    assert "manifest_identity_mismatch" in integrity.failure_codes
    assert "eligible_chunk_ids_mismatch" in integrity.failure_codes
    assert "collection_count_mismatch" in integrity.failure_codes
    assert result.decision is EvidenceDecision.INDETERMINATE
    assert result.premise_correction_required is False


def test_source_backed_premise_contradiction_precedes_certified_absence():
    chunks = [chunk("c1", "A source establishes a competing synthetic frame.")]
    subject_scan = scan("T0", "Orchid Relay", chunks)
    lanes = classify_evidence_lanes(chunks, subject_scan=subject_scan)

    result = decide_evidence(
        subject_scan,
        lane_assignments=lanes,
        premise_contradiction_chunk_ids={"c1"},
    )

    assert subject_scan.certified_direct_absence is True
    assert result.decision is EvidenceDecision.DIRECT_ANSWER
    assert result.premise_correction_required is True
    assert result.allowed_source_numbers == (1,)


def test_evidence_diagnostics_are_text_free():
    private_target = "Private Quasar 37"
    private_passage = "SENTINEL_MANUSCRIPT_PASSAGE"
    private_probe = "SENTINEL_RELATED_PROBE"
    chunks = [chunk("c1", private_passage)]
    subject_scan = scan("T0", private_target, chunks)
    broader_scan = scan_broader_related(
        "synthetic class",
        [private_probe],
        chunks,
    )
    lanes = classify_evidence_lanes(
        chunks,
        subject_scan=subject_scan,
        broader_related_scan=broader_scan,
    )
    result = decide_evidence(
        subject_scan,
        lane_assignments=lanes,
        broader_related_scan=broader_scan,
    )
    diagnostics = evidence_diagnostics(
        result,
        subject_scan=subject_scan,
        broader_related_scan=broader_scan,
    )
    serialized = json.dumps(diagnostics, sort_keys=True)

    assert private_target not in serialized
    assert private_passage not in serialized
    assert private_probe not in serialized
    assert len(diagnostics["targets"][0]["target_sha256"]) == 64
    assert diagnostics["targets"][0]["strong_hit_count"] == 0
    assert diagnostics["decision"]["value"] == "clean_abstention"

    forbidden_keys = {
        "text",
        "question",
        "query_surface_span",
        "broader_term",
        "related_probe",
    }

    def assert_no_forbidden_keys(value: object) -> None:
        if isinstance(value, dict):
            assert forbidden_keys.isdisjoint(str(key).casefold() for key in value)
            for nested in value.values():
                assert_no_forbidden_keys(nested)
        elif isinstance(value, list):
            for nested in value:
                assert_no_forbidden_keys(nested)

    assert_no_forbidden_keys(diagnostics)
