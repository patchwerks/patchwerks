# Acceptance specification only; no Gherkin runner is installed or claimed.
# Runnable mappings below refer to unittest methods, not executed BDD steps.
Feature: Hostile contribution isolation and advisory artifact qualification
  Scenario: A candidate cannot select its own enforcement checker
    Given an independently selected accepted commit with a synthetic worker policy
    When the candidate replaces its checker and policy
    Then the accepted checker bytes are staged separately
    # test_policy_from_base_despite_candidate_replacement
    # test_mutable_worktree_not_used; test_replacement_refs_are_ignored

  Scenario: Missing trust and malformed snapshots fail closed
    Given a missing accepted policy or an unsafe candidate snapshot
    When the launcher prepares exact Git objects
    Then it refuses without a HEAD fallback or candidate execution
    # test_missing_policy_does_not_fall_back_to_worktree
    # test_requires_exact_commit_not_tag_tree_or_branch; test_duplicate_policy_keys_rejected
    # test_symlink_rejected; test_gitlink_rejected; test_blob_bound
    # test_count_and_total_bounds; test_unsafe_paths; test_snapshot_deadline

  Scenario: Real hostile fixtures cannot reach host authority
    Given explicitly enabled Docker tests and a separately provisioned immutable image
    When a synthetic checker attempts network home socket and outside writes
    Then those capabilities are unavailable and forged output remains advisory
    # test_real_isolation (real Docker; skipped unless PATCHWERKS_DOCKER_TESTS=1)
    # test_fake_docker_orchestration_only proves command construction only

  Scenario: Runtime and output remain bounded
    Given a fixture that stalls or floods output
    When its time or combined output budget expires
    Then its owned container is removed and the result fails closed
    # test_real_timeout_and_output_limit (real Docker)
    # test_cleanup_after_timeout_or_output_limit; test_combined_output_limit; test_timeout
    # test_docker_unavailable_has_no_container_to_clean; test_timeout_validation

  Scenario: Artifact metadata and independent review must agree
    Given synthetic provider observations and a separately selected trusted policy
    When provenance freshness identity archive bytes or exact-head review disagree
    Then eligibility is refused
    # test_mutations_fail_closed; test_publisher_and_author_cannot_approve_even_if_allowed
    # test_latest_review_supersedes_old_approval; test_other_allowed_reviewer_changes_requested_blocks
    # test_archive_bytes_and_symlink_and_oversize; test_exact_policy_commit_no_head_fallback
    # test_pagination_incomplete_and_api_failure; test_missing_evidence_and_forged_success

  Scenario: Observed eligibility cannot authorize deployment
    Given synthetic observations that satisfy every eligibility comparison
    When the read-only verifier returns its result
    Then deployment authorization remains false
    And a future executor must revalidate after the observation
    # test_synthetic_eligibility_never_authorizes_deployment
    # test_collector_exact_routes_and_readback; test_gh_is_read_only_fixed_host_no_shell
    # test_body_instructions_are_inert; test_other_privileged_event_is_rejected
    # test_policy_rejects_unknown_keys_types_and_duplicates
