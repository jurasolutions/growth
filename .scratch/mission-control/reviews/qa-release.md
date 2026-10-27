# QA trace at the release gate: mission control and browser publishing

QA lead, 2026-10-27. Branch `crew/mission-control` at `0354503`. Test strategy:
`reviews/test-strategy-v3.md` (sections 4.1 to 4.3 and 5.2).

No per-ticket `qa-NN.md` was written during the build. Each ticket's tests were checked by its code
review and by the conductor's merge runs. So this file is the first trace of the strategy's rows to
test node ids, made at the gate from a fresh run.

## How it was made

- **Run:** `uv run pytest -rs -p no:cacheprovider -o addopts="" --junitxml=<scratch>/junit.xml`, with
  `JURA_ROOT` set and `JURA_GROWTH_DATA_DIR` and `JURA_GROWTH_OUTPUTS_DIR` on fresh temp folders. It
  gave 3305 passed, 0 failed, 0 errors and 0 skipped. Every one of the 3305 JUnit cases passed.
- **Mapping:** a row is traced to a test function in two ways. Either the function's own source
  cites the row's id, or I matched it by behaviour, reading the test names and, where a name was
  not enough, the test body. The "Passing nodes" column counts the JUnit cases (parametrised cases
  included) under the named functions. Every one of them passed.
- **Manual parts** are the rows the strategy marks "yes, plus recorded". None of their U or R steps
  has been run yet. They are listed, not traced.

## Result

- 170 ids: 80 AC-M, 36 AC-P, X1 to X15, and G1 to G38 with G4a and G4b.
- **168 are traced** to passing tests.
- **G34 has no test.** The strategy names "E6 grep and a generated test over `headless.leaves(cli)`".
  The grep half holds. The generated test doesn't exist. At the gate I walked the 77 CLI leaves
  myself, and none takes both a kind and a subject.
- **G38 is traced, with a narrower scope than the strategy asks for.** The strategy wants every kind
  × every D7 state. The tests cover the fake kind's pending record, three ways of typing it, the
  no-TTY subprocess, the orphaned-expect probe, and `decide()` with each refused origin.
  `test_a_terminal_refusal_asks_for_nothing_and_opens_no_database` shows the refusal comes before
  any database is opened, so no state can change the outcome. Still, the strategy's case isn't
  covered as written.
- **Five rows have a manual part that isn't recorded:** AC-M7.5 (U16), AC-M8.11 (U17), AC-M14.1
  (U4), AC-P9.4 (U11) and AC-P11.1 (R6).

## Matrix coverage (section 5.2)

`tests/test_approval_gates.py` ran each "every kind" case once per adapter, nine in all: fake,
`outreach-email`, `app-build`, `app-release`, `group-rules`, `social-post`, `community-post`,
`group-join` and its answers step. The "not applied on decide" cases (G4b, G7, G17) ran for the
seven kinds they apply to. G9, G19, G21 and G22 for `app-build` and `group-rules` are traced in
their own test files, as the harness docstring says.

## Fixtures that prove themselves (E4)

| Fixture | Assertion | Where |
|---|---|---|
| Network guard self-test | refuses and records a lookup of `discord.com` and a connect outside loopback; a swallowed refusal is still recorded | `test_network_guard::test_a_lookup_and_a_connection_outside_loopback_are_refused_and_recorded`, `::test_a_swallowed_refusal_is_still_recorded` |
| D4 hot journal | raises "the D4 journal is not hot" unless a throwaway copy rolls back | `tests/mission_world.py:117-155`, used by `test_mission_read::test_a_hot_journal_is_shown_as_an_unfinished_write_and_never_rolled_back` |
| Sweep marker | `assert_clean` first asserts the double received `sweep-marker-7c1f` | `tests/sweep.py:100-103` |
| Fake `claude` ran | `fake.started` (argv file written) or "the fake claude never ran" | `tests/publish_fake.py:130-133`, `test_publish_run.py:106,145`; `test_agent_decisions.py:49` |
| Resend hook ran (G21) | `seen_at_call() == [True]`: exactly one call, with the claim already committed | `test_approval_gates::test_g21_the_claim_is_committed_before_the_outward_call[outreach-email]` |
| Temp landing-page path | every `git -C` path resolves under `tmp_path` | `test_app_releases::test_released_only_reads_the_temp_landing_page_repository` |

## Trace

| Id | Trace | Passing nodes | Test functions (`file::function`) | Manual part | Note |
|---|---|---|---|---|---|
| AC-M1.1 | passed | 5 | `test_one_pager::test_the_header_and_the_sections_come_in_order`<br>`test_one_pager::test_under_2000_characters_it_is_one_message`<br>`test_one_pager::test_past_2000_characters_it_splits_at_lines_through_discord_split`<br>`test_one_pager_post::test_past_2000_characters_it_splits_and_the_png_rides_on_the_last_piece_only`<br>(+1 more) | - |  |
| AC-M1.2 | passed | 18 | `test_one_pager::test_nothing_in_the_health_strip_reads_nothing_needs_you`<br>`test_one_pager::test_each_health_item_appears_when_its_cause_is_planted`<br>`test_one_pager::test_the_health_items_follow_the_order_in_mc_5_4` | - |  |
| AC-M1.3 | passed | 1 | `test_one_pager::test_approvals_waiting_counts_by_kind_names_the_oldest_and_what_lapses_first` | - |  |
| AC-M1.4 | passed | 2 | `test_one_pager::test_a_social_post_past_its_decide_by_yesterday_is_not_waiting`<br>`test_mission_read::test_a_request_past_its_decide_by_is_lapsed_by_the_clock_without_a_write` | - |  |
| AC-M1.5 | passed | 1 | `test_headless::test_never_holds_the_decision_and_remote_commands_and_not_the_one_pager` | - |  |
| AC-M1.6 | passed | 2 | `test_one_pager_post::test_remote_one_pager_twice_posts_twice_and_answers_each_time`<br>`test_one_pager_post::test_one_pager_twice_posts_twice` | - |  |
| AC-M10.1 | passed | 1 | `test_remote_apps::test_a_real_process_answers_handoffs_with_the_handoff` | - |  |
| AC-M10.2 | passed | 76 | `test_remote::test_every_leaf_not_on_the_allowlist_is_refused`<br>`test_remote::test_every_command_that_takes_a_path_is_refused`<br>`test_remote::test_run_social_is_refused`<br>`test_remote::test_the_generated_lists_are_not_empty_and_name_run_social` | - |  |
| AC-M10.3 | passed | 8 | `test_growth_remote::test_hostile_words_arrive_as_literal_words_and_run_nothing`<br>`test_growth_remote::test_the_words_reach_jura_growth_remote_split_without_a_shell`<br>`test_growth_remote::test_the_wrapper_never_invokes_a_shell`<br>`test_remote::test_hostile_words_after_a_command_are_refused_and_run_nothing` | - |  |
| AC-M10.4 | passed | 2 | `test_remote::test_each_call_writes_one_event_with_the_actor_and_the_words`<br>`test_remote::test_the_event_holds_the_words_and_never_the_output` | - |  |
| AC-M10.5 | passed | 4 | `test_remote::test_the_json_answer_has_the_contract_shape`<br>`test_remote::test_the_contracts_answer_table_is_the_codes_enum_and_exit_codes`<br>`test_remote::test_the_json_answer_stays_under_64_kb`<br>`test_remote::test_every_answer_is_from_the_closed_enum_with_one_exit_code_each` | - |  |
| AC-M10.6 | passed | 3 | `test_group_rules::test_approve_without_days_through_remote_is_refused_and_with_them_it_sets_the_days`<br>`test_group_rules::test_the_same_words_typed_in_terminal_are_refused_with_the_pointer`<br>`test_remote::test_the_key_value_grammar_reaches_on_approve_with_both_arguments` | - |  |
| AC-M10.7 | passed | 1 | `test_remote::test_resume_all_with_a_pause_file_resumes_the_agents_and_says_the_file_stays` | - |  |
| AC-M11.1 | passed | 1 | `test_app_releases::test_an_app_release_card_and_its_edits_carry_nothing_planted` | - |  |
| AC-M11.2 | passed | 2 | `test_mission_health::test_an_unset_key_reads_not_set_and_every_line_has_a_known_shape`<br>`test_mission_health::test_status_and_the_health_strip_list_the_same_gaps_from_one_fixture` | - |  |
| AC-M11.3 | passed | 2 | `test_discord_redaction::test_two_posts_differing_only_in_a_secret_dedupe_as_one`<br>`test_discord_redaction::test_post_makes_no_keychain_lookup_of_its_own` | - |  |
| AC-M12.1 | passed | 1 | `test_app_releases::test_an_app_release_card_and_its_edits_carry_nothing_planted` | - |  |
| AC-M12.2 | passed | 1 | `test_outreach_greeting::test_queue_drops_a_draft_that_greets_a_person_so_no_card_can_show_it` | - |  |
| AC-M13.1 | passed | 3 | `test_mission_read::test_a_hot_journal_is_shown_as_an_unfinished_write_and_never_rolled_back`<br>`test_mission_read::test_without_a_hot_journal_the_same_database_reads_cleanly`<br>`test_one_pager::test_with_a_hot_journal_the_one_pager_says_unfinished_write_and_changes_nothing` | - |  |
| AC-M13.2 | passed | 4 | `test_mission_read::test_the_whole_one_pager_on_the_fortnight_never_reaches_a_writer_or_a_lock`<br>`test_mission_read::test_a_locked_database_is_the_same_unfinished_write`<br>`test_mission_read::test_a_missing_growth_db_is_a_value_and_nothing_is_created`<br>`test_mission_read::test_a_part_migrated_database_names_what_is_missing_and_reads_the_rest` | - |  |
| AC-M14.1 | passed | 3 | `test_mission_setup_guides::test_the_morning_brief_guide_tells_ting_yu_to_remove_the_line`<br>`test_mission_setup_guides::test_the_discord_guide_names_both_new_channels_and_approvals_notifies_on_all_messages`<br>`test_mission_setup_guides::test_the_1730_digest_still_writes_daily_summary_json` | U4 (#13) |  |
| AC-M15.1 | passed | 2 | `test_network_guard::test_a_lookup_and_a_connection_outside_loopback_are_refused_and_recorded`<br>`test_network_guard::test_a_swallowed_refusal_is_still_recorded` | - |  |
| AC-M2.1 | passed | 24 | `test_mission_slots::test_ac_m2_1_the_fortnight_table`<br>`test_mission_slots::test_ac_m2_1_publish_collapses_to_one_cell_with_counts` | - |  |
| AC-M2.2 | passed | 7 | `test_mission_slots::test_ac_m2_2_the_same_quiet_skip_from_events_and_the_mirror_counts_once`<br>`test_mission_slots::test_ac_m2_2_the_fortnight_read_from_both_sources_counts_each_record_once`<br>`test_mission_read::test_a_record_in_both_events_and_the_mirror_reaches_the_classifier_once` | - |  |
| AC-M2.3 | passed | 33 | `test_mission_slots::test_ac_m2_3_the_worst_status_wins_the_day_cell`<br>`test_mission_slots::test_ac_m2_3_the_order_is_the_one_in_the_prd`<br>`test_mission_slots::test_ac_m2_3_scout_send_on_a_mixed_day`<br>`test_mission_slots::test_ac_m2_3_publish_on_a_mixed_day` | - |  |
| AC-M2.4 | passed | 4 | `test_mission_slots::test_ac_m2_4_a_job_not_loaded_in_launchd_keeps_its_past_and_loses_its_future`<br>`test_mission_read::test_a_job_not_loaded_with_history_keeps_its_past_and_lists_as_not_installed` | - |  |
| AC-M3.1 | passed | 2 | `test_run_update::test_a_social_run_posts_one_run_update_in_social_drafts`<br>`test_run_update::test_a_social_run_counts_only_its_own_drafts` | - |  |
| AC-M3.2 | passed | 1 | `test_run_update::test_a_social_run_paused_by_hand_posts_one_skip` | - |  |
| AC-M3.3 | passed | 3 | `test_run_update::test_the_pause_file_posts_no_run_update`<br>`test_runner::test_the_pause_file_gets_no_run_update`<br>`test_one_pager::test_the_one_pager_on_the_fortnight_writes_nothing_and_lists_the_pause_file` | - |  |
| AC-M3.4 | passed | 4 | `test_run_update::test_a_lock_skip_posts_one_update_without_opening_the_database`<br>`test_run_update::test_a_lock_skip_goes_to_the_outbox_when_discord_is_down`<br>`test_runner::test_the_lock_skip_gets_one_run_update_without_opening_the_database` | - |  |
| AC-M3.5 | passed | 1 | `test_run_update::test_a_community_failure_with_a_secret_in_its_error_posts_it_redacted_in_one_line` | - |  |
| AC-M3.6 | passed | 6 | `test_run_update::test_failed_social_runs_record_and_auto_pause_the_same_whatever_discord_answers`<br>`test_run_update::test_a_plug_in_run_update_that_raises_still_posts_and_never_changes_the_run`<br>`test_runner::test_a_failing_run_update_never_changes_the_run`<br>`test_runner::test_an_after_run_that_raises_leaves_the_outcome_and_logs_an_error` | - |  |
| AC-M3.7 | passed | 7 | `test_run_update::test_run_update_is_on_for_exactly_the_four_agents_jobs`<br>`test_run_update::test_the_other_jobs_post_no_run_update`<br>`test_one_pager_post::test_the_job_posts_no_run_update` | - |  |
| AC-M4.1 | passed | 4 | `test_approvals::test_use_refuses_with_its_reason_and_claims_nothing` | - |  |
| AC-M4.2 | passed | 7 | `test_approval_gates::test_g9_content_changed_after_approval_refuses_supersedes_and_raises_the_new_request` | - |  |
| AC-M4.3 | passed | 8 | `test_app_builds::test_dispatch_sees_the_handoff_only_after_the_claim_commits`<br>`test_approval_gates::test_g21_the_claim_is_committed_before_the_outward_call` | - |  |
| AC-M4.4 | passed | 1 | `test_outreach_claim::test_two_connections_claiming_one_approval_at_once_one_wins` | - |  |
| AC-M4.5 | passed | 1 | `test_outreach_claim::test_a_crash_after_resend_retries_under_the_same_key_with_no_second_claim` | - |  |
| AC-M4.6 | passed | 25 | `test_app_builds::test_a_paused_factory_refuses_the_approval_without_claiming`<br>`test_approval_gates::test_g19_a_kill_switch_refuses_without_claiming_until_it_clears`<br>`test_group_rules::test_a_paused_community_agent_refuses_the_approval_until_the_brake_clears` | - |  |
| AC-M4.7 | passed | 4 | `test_app_builds::test_without_the_apps_plugin_nothing_is_handed_off_or_expired`<br>`test_app_releases::test_without_the_apps_plugin_no_release_is_planned_or_expired`<br>`test_group_rules::test_without_the_community_plugin_nothing_is_confirmed_or_expired`<br>`test_outreach_claim::test_without_its_plugin_the_kind_fails_closed` | - |  |
| AC-M5.1 | passed | 1 | `test_outreach_cards::test_the_card_for_lead_233_says_what_why_and_when` | - |  |
| AC-M5.2 | passed | 3 | `test_approval_cards::test_a_post_that_fails_after_the_commit_is_posted_once_by_the_next_sweep`<br>`test_approval_lapses::test_the_heartbeat_posts_a_card_a_crash_left_unposted`<br>`test_mission_read::test_an_unposted_card_is_read_as_unposted` | - |  |
| AC-M5.3 | passed | 6 | `test_approval_cards::test_an_approval_edits_the_first_line_and_keeps_the_rest`<br>`test_approval_cards::test_a_skip_edits_the_card`<br>`test_approval_cards::test_a_lapse_edits_the_card`<br>`test_approval_cards::test_a_supersede_edits_the_card_and_names_the_new_request`<br>(+2 more) | - |  |
| AC-M5.4 | passed | 2 | `test_approvals_cli::test_thirty_pending_lists_the_fifteen_soonest_to_lapse_then_the_rest_by_kind`<br>`test_remote::test_thirty_pending_through_remote_lists_the_fifteen_soonest_then_the_rest` | - |  |
| AC-M5.5 | passed | 1 | `test_approval_cards::test_a_card_with_eleven_files_is_refused_before_anything_is_posted` | - |  |
| AC-M6.1 | passed | 1 | `test_approvals::test_an_ssh_approval_records_actor_origin_growths_time_hash_and_ref` | - |  |
| AC-M6.2 | passed | 1 | `test_approvals::test_the_same_ref_twice_records_once_and_returns_the_first_answer` | - |  |
| AC-M6.3 | passed | 57 | `test_approvals::test_the_trigger_aborts_every_other_change`<br>`test_approvals::test_the_trigger_allows_each_a7_transition`<br>`test_approvals::test_a_decided_or_closed_record_is_never_deleted` | - |  |
| AC-M6.4 | passed | 1 | `test_approvals::test_there_is_no_terminal_origin_and_a_lookalike_decides_nothing` | - |  |
| AC-M7.1 | passed | 50 | `test_approvals_cli::test_every_configured_job_is_refused`<br>`test_headless::test_never_holds_the_decision_and_remote_commands_and_not_the_one_pager`<br>`test_headless::test_claude_rules_deny_the_decision_and_remote_commands_bare_and_with_arguments`<br>`test_remote::test_every_configured_job_is_refused` | - |  |
| AC-M7.2 | passed | 1 | `test_origin_processes::test_without_a_terminal_a_decision_is_refused_and_points_to_approvals` | - |  |
| AC-M7.3 | passed | 5 | `test_origin_processes::test_the_orphaned_expect_probe_is_refused`<br>`test_approvals_cli::test_a_terminal_refusal_asks_for_nothing_and_opens_no_database` | - |  |
| AC-M7.4 | passed | 10 | `test_origin::test_claude_at_any_depth_or_with_a_path_prefix_is_found`<br>`test_origin::test_any_claude_code_marker_is_refused_even_under_sshd`<br>`test_origin::test_a_claude_ancestor_under_sshd_is_refused`<br>`test_origin_processes::test_the_forced_command_variable_alone_is_not_the_dispatch_origin` | - |  |
| AC-M7.5 | passed | 5 | `test_origin::test_no_sshd_ancestor_is_refused`<br>`test_origin::test_no_forced_command_is_refused`<br>`test_remote::test_a_real_process_without_an_sshd_ancestor_exits_2`<br>`test_origin_processes::test_a_symlink_named_sshd_is_not_the_dispatch_origin` | U16 (#14) |  |
| AC-M7.6 | passed | 1 | `test_approvals::test_an_ssh_actor_that_is_not_the_control_user_is_refused_and_logged` | - |  |
| AC-M7.7 | passed | 6 | `test_agent_decisions::test_a_claude_job_that_tries_to_approve_is_refused`<br>`test_agent_decisions::test_the_four_claude_jobs_are_all_covered` | - |  |
| AC-M8.1 | passed | 1 | `test_outreach_gate::test_live_send_due_sends_nothing_while_the_request_is_pending` | - |  |
| AC-M8.10 | passed | 3 | `test_outreach_decisions::test_an_approved_email_shadow_sent_after_a_switch_back_keeps_its_approval_until_its_use_by`<br>`test_outreach_email_kind::test_a_shadow_sent_message_keeps_its_content_so_its_approval_lapses_rather_than_supersedes`<br>`test_outreach_gate::test_shadow_mode_raises_nothing` | - |  |
| AC-M8.11 | passed | 3 | `test_outreach_gate::test_no_request_is_raised_while_the_buttons_are_off` | U17 (#15) |  |
| AC-M8.12 | passed | 6 | `test_outreach_gate::test_the_spacing_probability_counts_approved_emails_only`<br>`test_outreach_requeue::test_requeued_email_still_passes_every_send_time_check`<br>`test_outreach_requeue::test_requeued_emails_count_against_the_live_warm_up`<br>`test_outreach_requeue::test_requeued_emails_send_live_with_a_live_token`<br>(+2 more) | - |  |
| AC-M8.13 | passed | 2 | `test_outreach_gate::test_requeue_shadow_in_live_mode_raises_requests_only_up_to_todays_quota`<br>`test_uat_seed_outreach::test_shadow_trial_then_requeue_shadow_asks_only_up_to_todays_quota` | - |  |
| AC-M8.2 | passed | 2 | `test_outreach_gate::test_queue_raises_requests_only_up_to_todays_quota`<br>`test_outreach_gate::test_sends_and_skips_open_room_for_more_requests` | - |  |
| AC-M8.3 | passed | 1 | `test_outreach_gate::test_a_follow_up_raises_no_request_until_its_day` | - |  |
| AC-M8.4 | passed | 2 | `test_outreach_decisions::test_an_unanswered_request_expires_after_its_decide_by_and_the_lead_stays_new`<br>`test_outreach_decisions::test_send_due_never_sends_an_unanswered_request_at_its_decide_by` | - |  |
| AC-M8.5 | passed | 1 | `test_outreach_decisions::test_an_approval_the_limits_never_reached_lapses_at_its_use_by` | - |  |
| AC-M8.6 | passed | 1 | `test_outreach_decisions::test_a_skip_cancels_the_email_and_closes_the_lead_for_good` | - |  |
| AC-M8.7 | passed | 2 | `test_outreach_decisions::test_a_skip_after_approval_wins_until_the_claim`<br>`test_outreach_decisions::test_a_skip_after_the_send_answers_already_sent` | - |  |
| AC-M8.8 | passed | 2 | `test_outreach_decisions::test_an_unsubscribe_supersedes_an_approved_email_at_the_next_read`<br>`test_outreach_decisions::test_an_unsubscribe_supersedes_an_approved_email_at_the_next_send_due` | - |  |
| AC-M8.9 | passed | 4 | `test_outreach_email_kind::test_a_new_unsubscribe_token_in_the_footer_still_matches`<br>`test_outreach_email_kind::test_one_character_changed_in_recipient_subject_or_draft_doesnt_match` | - |  |
| AC-M9.1 | passed | 3 | `test_app_builds::test_no_message_carries_the_old_approved_build_line`<br>`test_apps::test_submit_prd_files_updates_backlog_and_raises_an_app_build_request`<br>`test_apps::test_the_template_says_a_build_starts_with_its_app_build_request_not_a_typed_reply` | - |  |
| AC-M9.10 | passed | 2 | `test_app_builds::test_seven_prds_waiting_for_a_decision_stop_the_factory`<br>`test_apps::test_prds_with_no_app_build_request_are_not_in_the_waiting_pile` | - |  |
| AC-M9.11 | passed | 1 | `test_app_builds::test_the_one_off_pass_raises_one_request_for_each_factory_prd_already_pending` | - |  |
| AC-M9.2 | passed | 3 | `test_app_builds::test_approving_claims_the_request_and_writes_one_handoff_in_the_same_transaction`<br>`test_app_builds::test_handoffs_json_carries_the_handoff_and_lists_it_until_it_is_built`<br>`test_remote_apps::test_handoffs_carries_the_approved_prd_text_verbatim_and_lists_it_until_it_is_built` | - |  |
| AC-M9.3 | passed | 2 | `test_app_builds::test_the_answer_and_the_one_pager_say_how_it_gets_built` | - |  |
| AC-M9.4 | passed | 1 | `test_app_builds::test_a_prd_changed_by_one_byte_is_not_handed_off_and_a_new_request_is_raised` | - |  |
| AC-M9.5 | passed | 1 | `test_app_builds::test_a_skipped_prd_moves_to_skipped_and_its_idea_never_comes_back` | - |  |
| AC-M9.6 | passed | 1 | `test_app_builds::test_an_unanswered_prd_expires_and_its_idea_is_offered_again_from_day_30` | - |  |
| AC-M9.7 | passed | 4 | `test_app_releases::test_built_raises_an_app_release_card_with_the_preview_link_and_the_short_sha`<br>`test_app_releases::test_built_on_a_build_that_was_never_handed_off_exits_1_and_raises_nothing`<br>`test_remote_apps::test_built_through_remote_raises_an_app_release_card_with_the_preview_and_the_short_sha`<br>`test_remote_apps::test_built_through_remote_on_a_build_never_handed_off_exits_1_and_raises_nothing` | - |  |
| AC-M9.8 | passed | 4 | `test_app_releases::test_release_plan_claims_the_approval_and_prints_the_merge_of_the_approved_sha_only`<br>`test_app_releases::test_release_plan_with_no_approved_release_exits_1_and_prints_nothing_to_run`<br>`test_remote_apps::test_release_plan_through_remote_claims_then_answers_with_the_merge_of_the_approved_sha_only`<br>`test_remote_apps::test_release_plan_through_remote_with_nothing_approved_exits_1_and_gives_nothing_to_run` | - |  |
| AC-M9.9 | passed | 4 | `test_app_releases::test_released_with_no_claimed_release_exits_1_and_the_prd_stays_in_pending`<br>`test_app_releases::test_released_when_main_lacks_the_approved_sha_exits_1_and_the_prd_stays_in_pending`<br>`test_app_releases::test_released_records_the_release_and_moves_the_prd_to_done_with_both_approvals`<br>`test_remote_apps::test_released_through_remote_records_the_release_and_moves_the_prd_to_done` | - |  |
| AC-P1.1 | passed | 4 | `test_publish_items::test_submit_raises_one_social_post_request_for_facebook_only`<br>`test_publish_items::test_the_social_drafts_message_for_facebook_points_at_the_card`<br>`test_publish_instagram_linkedin::test_submit_raises_exactly_one_social_post_request_for_the_platform_in_browser_mode` | - |  |
| AC-P1.2 | passed | 1 | `test_publish_items::test_a_variant_that_fails_the_brand_gate_gets_no_item_and_no_request` | - |  |
| AC-P1.3 | passed | 6 | `test_publish_community::test_a_changed_approved_community_post_gets_a_fresh_request_on_the_same_item` | - |  |
| AC-P1.4 | passed | 1 | `test_publish_items::test_drafts_written_before_a_platform_moved_to_browser_get_no_item` | - |  |
| AC-P10.1 | passed | 4 | `test_publish_run::test_a_claim_with_neither_done_nor_stopped_becomes_unknown_and_names_both_resolve_forms`<br>`test_publish_queue::test_after_run_settles_a_claim_left_open_as_unknown`<br>`test_publish_regressions::test_sp1_the_next_runs_claim_settles_an_orphan_pauses_alerts_and_claims_nothing`<br>`test_publish_precheck::test_an_orphan_whose_run_still_reads_running_settles_pauses_and_alerts_before_claude` | - |  |
| AC-P10.2 | passed | 5 | `test_publish_queue::test_a_headless_run_cant_resume_or_resolve`<br>`test_publish_remote::test_a_headless_run_cant_resolve_through_remote_either`<br>`test_publish_remote::test_resolve_posted_from_discord_settles_the_item`<br>`test_publish_remote::test_resolve_not_posted_from_discord_withdraws_the_item` | - |  |
| AC-P11.1 | passed | 7 | `test_publish_prompt::test_the_browser_check_comes_before_the_claim`<br>`test_publish_prompt::test_the_identity_check_comes_before_any_typing_and_stops_on_a_mismatch`<br>`test_publish_run::test_the_wrong_identity_stops_before_any_typing`<br>`test_publish_run_instagram_linkedin::test_the_wrong_identity_stops_before_any_typing_pauses_and_alerts_once`<br>(+2 more) | R6 (BP-03, uat.md Part D) |  |
| AC-P2.1 | passed | 5 | `test_publish_queue::test_an_item_whose_request_isnt_approved_is_never_due`<br>`test_publish_run::test_nothing_due_inside_the_run_ends_skip_with_no_page_call_and_no_update` | - |  |
| AC-P2.2 | passed | 2 | `test_publish_queue::test_publish_next_claims_the_approval_and_the_item_before_it_prints`<br>`test_publish_run::test_a_clean_post_claims_before_any_page_tool_posts_and_reports_once` | - |  |
| AC-P2.3 | passed | 2 | `test_publish_queue::test_a_skip_after_approval_withdraws_the_item_and_records_the_social_skip`<br>`test_publish_queue::test_a_skip_after_the_claim_answers_already_used` | - |  |
| AC-P3.1 | passed | 3 | `test_publish_queue::test_claimable_at_17_59_59`<br>`test_publish_queue::test_at_18_00_or_the_next_morning_nothing_is_claimed_and_the_request_is_expired` | - |  |
| AC-P3.2 | passed | 1 | `test_publish_queue::test_an_approve_recorded_at_18_02_is_expired_whatever_discords_time` | - |  |
| AC-P3.3 | passed | 2 | `test_publish_queue::test_the_deadlines_are_the_end_of_the_configured_window` | - |  |
| AC-P3.4 | passed | 2 | `test_publish_community::test_a_join_proposed_monday_is_decided_by_sunday_18_00`<br>`test_publish_community::test_an_answers_item_raised_tuesday_is_decided_by_friday_18_00` | - |  |
| AC-P4.1 | passed | 4 | `test_publish_join_run::test_an_approved_join_with_no_questions_is_requested_on_its_single_approval`<br>`test_publish_joins::test_a_join_records_its_outcome_and_join_status_and_raises_nothing` | - |  |
| AC-P4.2 | passed | 3 | `test_publish_join_run::test_questions_submit_nothing_and_a_later_run_submits_exactly_the_approved_answers`<br>`test_publish_joins::test_questions_record_the_join_and_raise_the_answers_as_their_own_item_and_card`<br>`test_publish_joins::test_answers_that_fail_the_brand_gate_raise_nothing_and_may_be_fixed_once` | - |  |
| AC-P4.3 | passed | 6 | `test_publish_joins::test_pages_not_allowed_skips_the_group_for_good_without_alert_or_pause`<br>`test_publish_joins::test_pages_not_allowed_supersedes_every_item_still_waiting_for_the_group`<br>`test_publish_join_run::test_a_join_screen_for_personal_profiles_only_skips_the_group_without_alert_or_pause`<br>`test_publish_community_run::test_a_composer_with_no_way_to_post_as_the_page_skips_the_group_without_alert_or_pause` | - |  |
| AC-P4.4 | passed | 1 | `test_publish_joins::test_a_membership_joins_the_group_as_the_page_but_posts_wait_for_a_rules_decision` | - |  |
| AC-P5.1 | passed | 22 | `test_publish_queue::test_line_1_a_second_facebook_item_for_the_same_day_is_refused`<br>`test_publish_queue::test_line_6_the_gap_is_measured_between_the_runs_start_times`<br>`test_publish_queue::test_line_7_claims_only_inside_the_posting_window`<br>`test_publish_queue::test_line_11_a_second_publish_next_in_the_same_run_is_refused`<br>(+10 more) | - |  |
| AC-P5.2 | passed | 2 | `test_publish_queue::test_a_claim_that_ended_badly_still_counts_against_the_day` | - |  |
| AC-P5.3 | passed | 13 | `test_publish_queue::test_a_kill_switch_claims_nothing_and_keeps_the_approval`<br>`test_publish_community::test_with_community_browser_off_nothing_is_claimed_and_the_approval_is_kept`<br>`test_publish_run::test_a_kill_switch_never_starts_claude_and_keeps_the_approval` | - |  |
| AC-P5.4 | passed | 9 | `test_publish_limits::test_a_looser_value_gives_the_hard_one_and_a_tighter_one_is_honoured`<br>`test_publish_limits::test_a_wider_window_gives_the_hard_window_and_a_narrower_one_is_honoured`<br>`test_publish_community::test_joins_per_week_in_community_yaml_may_only_lower_the_cap` | - |  |
| AC-P6.1 | passed | 2 | `test_publish_queue::test_publish_stopped_marks_the_item_pauses_publish_and_alerts`<br>`test_publish_run::test_a_login_wall_stops_the_item_pauses_publish_and_alerts_once_with_the_run` | - |  |
| AC-P6.2 | passed | 3 | `test_publish_community_posts::test_a_removal_or_admin_warning_in_a_group_also_removes_the_group`<br>`test_publish_community_run::test_an_admin_warning_in_the_group_stops_everything_and_skips_the_group_for_good` | - |  |
| AC-P6.3 | passed | 3 | `test_publish_queue::test_a_headless_run_cant_resume_or_resolve`<br>`test_publish_remote::test_resume_publish_from_discord_works_after_a_stop` | - |  |
| AC-P7.1 | passed | 1 | `test_publish_queue::test_publish_done_records_the_post_its_url_and_the_run` | - |  |
| AC-P7.2 | passed | 55 | `test_publish_queue::test_a_url_off_the_platforms_hosts_exits_1_and_records_nothing`<br>`test_publish_queue::test_the_platforms_own_hosts_are_accepted`<br>`test_publish_instagram_linkedin::test_look_alikes_other_hosts_and_non_post_addresses_exit_1_and_record_nothing`<br>`test_publish_instagram_linkedin::test_the_new_platforms_post_addresses_are_accepted_for_their_own_items` | - |  |
| AC-P7.3 | passed | 8 | `test_publish_queue::test_live_text_is_compared_after_nfc_collapsed_whitespace_and_trimming`<br>`test_publish_queue::test_nfc_equivalent_text_matches`<br>`test_publish_run::test_a_live_text_mismatch_alerts_pauses_and_says_so_in_the_update` | - |  |
| AC-P8.1 | passed | 3 | `test_publish_run::test_a_clean_post_claims_before_any_page_tool_posts_and_reports_once`<br>`test_publish_run::test_a_login_wall_stops_the_item_pauses_publish_and_alerts_once_with_the_run`<br>`test_publish_run::test_skips_never_post_a_run_update` | - |  |
| AC-P8.2 | passed | 3 | `test_publish_precheck::test_nothing_claimable_starts_no_claude_and_leaves_one_quiet_trace` | - |  |
| AC-P8.3 | passed | 1 | `test_publish_queue::test_the_digest_counts_the_days_posted_skipped_expired_and_stopped` | - |  |
| AC-P9.1 | passed | 8 | `test_publish_argv::test_only_publish_gains_chrome_and_browser_rules`<br>`test_publish_argv::test_a_job_outside_browser_jobs_that_asks_for_a_browser_raises`<br>`test_publish_argv::test_community_keeps_its_facebook_fetch_denials`<br>`test_publish_argv::test_chrome_flag_appears_only_in_the_runners_browser_jobs_branch` | - |  |
| AC-P9.2 | passed | 3 | `test_publish_argv::test_bp04_one_domain_rule_per_host_of_each_platform_in_browser_mode` | - |  |
| AC-P9.3 | passed | 6 | `test_publish_run::test_a_navigation_off_the_hosts_fails_the_run_pauses_publish_and_alerts`<br>`test_publish_run::test_a_tab_left_open_is_a_warning_in_the_run_update`<br>`test_publish_audit::test_a_discord_host_fails_and_says_so`<br>`test_publish_audit::test_typing_before_the_claim_fails_even_the_approved_text` | - |  |
| AC-P9.4 | passed | 1 | `test_publish_run::test_no_browser_ends_skip_claims_nothing_and_alerts_once_a_day` | U11 (BP-01) |  |
| AC-P9.5 | passed | 4 | `test_publish_precheck::test_an_auth_variable_skips_with_its_name_as_a_plain_skip`<br>`test_publish_precheck::test_an_auth_variable_is_a_setup_gap_by_name_only` | - |  |
| X1 | passed | 9 | `test_runner::test_a_quiet_job_with_nothing_to_do_writes_one_run_quiet_and_no_run_row`<br>`test_runner::test_a_quiet_run_that_did_work_records_its_real_start`<br>`test_runner::test_a_nothing_to_do_precheck_writes_run_quiet_with_its_reason_and_no_run_row`<br>`test_runner::test_a_quiet_claude_job_gets_its_run_row_before_claude_starts`<br>(+4 more) | - |  |
| X2 | passed | 6 | `test_app_builds::test_an_app_build_has_seven_days_to_decide_and_one_day_to_use`<br>`test_app_releases::test_an_app_release_has_seven_days_to_decide_and_fourteen_to_use` | - |  |
| X3 | passed | 5 | `test_app_builds::test_a_configured_app_build_deadline_may_shorten_and_never_lengthen`<br>`test_app_releases::test_a_configured_app_release_deadline_may_shorten_and_never_lengthen`<br>`test_approvals::test_a_configured_deadline_can_shorten_but_never_lengthen`<br>`test_approvals::test_no_deadline_runs_past_the_hard_ceiling`<br>(+1 more) | - |  |
| X4 | passed | 6 | `test_mission_slots::test_every_job_in_settings_gets_its_slots`<br>`test_mission_slots::test_publish_has_its_27_slots_on_a_weekend_and_a_holiday_too` | - |  |
| X5 | passed | 1 | `test_publish_retention::test_publish_transcripts_go_after_7_days_and_the_rest_after_30` | - |  |
| X6 | passed | 1 | `test_publish_items::test_a_saturday_draft_on_a_browser_platform_raises_a_request` | - |  |
| X7 | passed | 5 | `test_approvals::test_a_database_at_mains_schema_migrates_through_0003_with_no_row_changed`<br>`test_app_builds::test_the_app_build_migrations_change_no_existing_row`<br>`test_publish_queue::test_the_publish_items_migration_changes_no_existing_row`<br>`test_publish_community::test_the_community_groups_migration_changes_no_existing_row`<br>(+1 more) | - |  |
| X8 | passed | 2 | `test_publish_argv::test_publish_argv_keeps_the_runner_flags_and_has_no_add_dir`<br>`test_publish_queue::test_publish_next_copies_the_items_images_into_the_runs_scratch_folder` | - |  |
| X9 | passed | 3 | `test_group_rules::test_rules_confirmed_yes_raises_a_request_and_confirms_nothing`<br>`test_group_rules::test_researched_rules_never_raise_a_request`<br>`test_group_rules::test_the_pass_runs_once_so_a_later_confirmation_without_a_decision_is_never_written_down` | - |  |
| X10 | passed | 1 | `test_publish_joins::test_note_rules_records_the_rules_seen_and_raises_one_group_rules_request` | - |  |
| X11 | passed | 3 | `test_approval_buttons::test_no_buttons_while_post_buttons_is_off`<br>`test_approval_buttons::test_with_post_buttons_on_a_card_carries_approve_and_skip`<br>`test_approval_buttons::test_a_card_that_needs_typed_arguments_gets_no_buttons` | - |  |
| X12 | passed | 5 | `test_approval_lapses::test_the_scheduled_writer_expires_a_lapsed_request_once`<br>`test_approval_lapses::test_the_heartbeat_posts_a_card_a_crash_left_unposted`<br>`test_one_pager_post::test_the_job_writes_the_lapse_on_its_writable_connection_before_the_read_model_runs`<br>`test_one_pager_post::test_the_one_pager_posts_no_new_card` | - |  |
| X13 | passed | 3 | `test_uat_seed::test_a_folder_that_isnt_temporary_is_refused`<br>`test_uat_seed::test_the_live_data_folder_is_refused`<br>`test_d1_stub::test_the_override_is_refused_unless_the_data_folder_is_temporary` | - |  |
| X14 | passed | 4 | `test_one_pager_grid::test_the_grid_png_is_a_valid_png_of_the_expected_size`<br>`test_one_pager_grid::test_one_cell_per_job_per_day`<br>`test_one_pager_grid::test_the_grid_uses_design_system_tokens_only`<br>`test_one_pager_grid::test_every_status_shows_as_text_as_well_as_colour` | - |  |
| X15 | passed | 3 | `test_mission_read::test_spend_is_recorded_cost_either_side_of_sgt_midnight_and_yesterday_is_the_digest`<br>`test_one_pager::test_yesterday_is_the_digest_for_yesterday_and_both_spend_figures`<br>`test_one_pager::test_yesterday_names_no_day_of_its_own` | - |  |
| G1 | passed | 9 | `test_approval_gates::test_g1_no_approval_record_refuses` | - |  |
| G2 | passed | 22 | `test_approval_gates::test_g2_a_pending_request_refuses`<br>`test_brand_check::test_number_word_counting_nothing_passes`<br>`test_brand_check::test_review_04_number_words_counting_nothing_pass`<br>`test_scout_leads::test_free_mail_published_on_the_company_site_is_accepted` | - |  |
| G3 | passed | 9 | `test_approval_gates::test_g3_a_skipped_request_refuses_and_its_skip_action_ran_once` | - |  |
| G4a | passed | 6 | `test_approvals::test_approve_at_the_decide_by_answers_expired_and_writes_the_transition`<br>`test_approvals::test_use_refuses_with_its_reason_and_claims_nothing`<br>`test_outreach_decisions::test_an_unanswered_request_expires_after_its_decide_by_and_the_lead_stays_new` | - |  |
| G4b | passed | 5 | `test_approvals::test_use_refuses_with_its_reason_and_claims_nothing`<br>`test_outreach_decisions::test_an_approval_the_limits_never_reached_lapses_at_its_use_by` | - |  |
| G5 | passed | 15 | `test_approval_gates::test_g5_expire_due_writes_each_lapse_once_and_both_refuse`<br>`test_approvals::test_use_refuses_with_its_reason_and_claims_nothing`<br>`test_outreach_decisions::test_an_approval_the_limits_never_reached_lapses_at_its_use_by`<br>`test_outreach_decisions::test_an_unanswered_request_expires_after_its_decide_by_and_the_lead_stays_new` | - |  |
| G6 | passed | 14 | `test_approval_gates::test_g6_a_request_superseded_before_its_decision_refuses`<br>`test_approvals::test_a_decision_on_changed_content_answers_superseded_and_raises_the_new_request`<br>`test_approvals::test_use_refuses_with_its_reason_and_claims_nothing` | - |  |
| G7 | passed | 9 | `test_approval_gates::test_g7_an_approval_is_used_once`<br>`test_uat_seed::test_g4_and_g7_keep_the_ids_uat_md_types`<br>`test_uat_seed::test_s8_the_two_community_groups` | - |  |
| G8 | passed | 3 | `test_publish_queue::test_two_publish_next_calls_racing_for_one_item_give_one_claim`<br>`test_approvals::test_ac_m4_4_two_connections_claiming_at_once_give_exactly_one_claim`<br>`test_outreach_claim::test_two_connections_claiming_one_approval_at_once_one_wins` | - |  |
| G9 | passed | 17 | `test_app_builds::test_a_prd_changed_by_one_byte_is_not_handed_off_and_a_new_request_is_raised`<br>`test_group_rules::test_rules_changed_before_the_decision_supersede_it_and_set_nothing`<br>`test_app_releases::test_release_plan_refuses_a_release_whose_branch_moved_on_after_the_approval`<br>`test_approval_gates::test_g9_content_changed_after_approval_refuses_supersedes_and_raises_the_new_request`<br>(+2 more) | - |  |
| G10 | passed | 9 | `test_approval_gates::test_g10_the_right_content_for_the_wrong_subject_refuses` | - |  |
| G11 | passed | 1 | `test_approvals::test_g11_the_right_subject_under_the_wrong_kind_refuses` | - |  |
| G12 | passed | 1 | `test_approvals::test_an_ssh_actor_that_is_not_the_control_user_is_refused_and_logged` | - |  |
| G13 | passed | 50 | `test_approvals_cli::test_every_configured_job_is_refused`<br>`test_headless::test_claude_rules_deny_the_decision_and_remote_commands_bare_and_with_arguments`<br>`test_agent_decisions::test_a_claude_job_that_tries_to_approve_is_refused`<br>`test_publish_audit::test_a_discord_host_fails_and_says_so`<br>(+1 more) | - |  |
| G14 | passed | 1 | `test_approvals::test_approve_at_the_decide_by_answers_expired_and_writes_the_transition` | - |  |
| G15 | passed | 10 | `test_approval_gates::test_g15_a_second_decision_answers_already_decided_and_changes_nothing`<br>`test_approvals::test_a_second_decision_answers_already_decided_and_changes_nothing` | - |  |
| G16 | passed | 2 | `test_approvals::test_the_same_ref_arriving_while_the_first_is_deciding_gets_the_first_answer`<br>`test_approvals::test_the_same_ref_twice_records_once_and_returns_the_first_answer` | - |  |
| G17 | passed | 8 | `test_approval_gates::test_g17_a_skip_after_approval_wins_until_the_claim`<br>`test_outreach_decisions::test_a_skip_after_approval_wins_until_the_claim` | - |  |
| G18 | passed | 10 | `test_approval_gates::test_g18_a_skip_after_use_answers_already_used_and_changes_nothing`<br>`test_outreach_decisions::test_a_skip_after_the_send_answers_already_sent` | - |  |
| G19 | passed | 25 | `test_app_builds::test_a_paused_factory_refuses_the_approval_without_claiming`<br>`test_approval_gates::test_g19_a_kill_switch_refuses_without_claiming_until_it_clears`<br>`test_group_rules::test_a_paused_community_agent_refuses_the_approval_until_the_brake_clears` | - |  |
| G20 | passed | 1 | `test_outreach_decisions::test_an_approved_email_shadow_sent_after_a_switch_back_keeps_its_approval_until_its_use_by` | - |  |
| G21 | passed | 8 | `test_app_builds::test_dispatch_sees_the_handoff_only_after_the_claim_commits`<br>`test_approval_gates::test_g21_the_claim_is_committed_before_the_outward_call` | - |  |
| G22 | passed | 8 | `test_app_builds::test_a_failed_handoff_write_rolls_the_decision_back`<br>`test_approval_gates::test_g22_a_failed_in_flight_write_rolls_the_claim_back` | - |  |
| G23 | passed | 1 | `test_outreach_claim::test_a_crash_after_resend_retries_under_the_same_key_with_no_second_claim` | - |  |
| G24 | passed | 1 | `test_outreach_claim::test_completion_never_rechecks_a_deadline` | - |  |
| G25 | passed | 18 | `test_approval_gates::test_g25_a_gone_item_approved_but_unclaimed_supersedes_too`<br>`test_approval_gates::test_g25_a_gone_item_supersedes_at_the_next_claim_and_raises_nothing`<br>`test_group_rules::test_a_removed_group_supersedes_its_request`<br>`test_outreach_decisions::test_an_unsubscribe_supersedes_an_approved_email_at_the_next_read` | - |  |
| G26 | passed | 2 | `test_approvals::test_a_second_live_row_for_one_subject_fails_on_the_partial_unique_index`<br>`test_approvals::test_request_twice_over_the_same_content_returns_the_same_record` | - |  |
| G27 | passed | 1 | `test_approvals::test_ac_m4_7_a_kind_whose_plugin_failed_to_import_is_refused_and_left_alone` | - |  |
| G28 | passed | 1 | `test_approval_cards::test_a_post_that_fails_after_the_commit_is_posted_once_by_the_next_sweep` | - |  |
| G29 | passed | 9 | `test_approval_gates::test_g29_every_transition_leaves_one_event_with_actor_origin_ref_hash_and_time` | - |  |
| G30 | passed | 4 | `test_publish_queue::test_g30_resolve_takes_only_an_a_id` | - |  |
| G31 | passed | 2 | `test_app_builds::test_no_plugin_migration_names_a_decision_column`<br>`test_publish_queue::test_publish_items_holds_no_approval_state` | - |  |
| G32 | passed | 52 | `test_approvals::test_the_trigger_aborts_every_other_change`<br>`test_approvals::test_the_trigger_allows_each_a7_transition` | - |  |
| G33 | passed | 18 | `test_approvals_cli::test_every_answer_has_one_exit_code`<br>`test_remote::test_every_answer_is_from_the_closed_enum_with_one_exit_code_each`<br>`test_remote::test_dispatch_answers` | - |  |
| G34 | gate evidence, no test | 0 | - | - | No generated test exists. Gate evidence instead: the E6 grep (7 `approvals.request(` call sites, all behind A11's raisers) and a fresh walk of `headless.leaves(cli)` (77 leaves, none taking a kind and a subject). |
| G35 | passed | 3 | `test_outreach_gate::test_queue_raises_requests_only_up_to_todays_quota`<br>`test_outreach_gate::test_requeue_shadow_in_live_mode_raises_requests_only_up_to_todays_quota`<br>`test_outreach_gate::test_sends_and_skips_open_room_for_more_requests` | - |  |
| G36 | passed | 3 | `test_approvals::test_g36_decide_writes_a_due_expiry_once_and_the_others_find_it_written`<br>`test_approvals::test_g36_expire_due_writes_a_due_expiry_once_and_the_others_find_it_written`<br>`test_approvals::test_g36_use_writes_a_due_lapse_once_in_the_callers_transaction` | - |  |
| G37 | passed | 8 | `test_app_builds::test_an_app_build_takes_no_decision_arguments`<br>`test_approvals::test_a_claim_refused_inside_on_approve_answers_refused_and_records_nothing`<br>`test_group_rules::test_missing_or_unreadable_days_are_refused_and_nothing_is_recorded` | - |  |
| G38 | passed, scope gap | 11 | `test_approvals_cli::test_a_decision_typed_in_terminal_is_refused_and_points_to_approvals`<br>`test_approvals_cli::test_a_terminal_refusal_asks_for_nothing_and_opens_no_database`<br>`test_approvals::test_a_refused_origin_decides_nothing`<br>`test_approvals::test_there_is_no_terminal_origin_and_a_lookalike_decides_nothing`<br>(+1 more) | - | Scope gap: the Terminal refusal is tested on the fake kind's pending record, not per kind and per D7 state. It is state-independent by construction, because `test_a_terminal_refusal_asks_for_nothing_and_opens_no_database` proves the refusal happens before any database is opened. |
