use rusqlite::Connection;
use x_social_draft_workflow::{
    DraftOptionInput, DraftSetInput, add_post, confirm_account, confirm_liked, confirm_posted,
    designate_browser, duplicate_status, initialize_schema, normalize_reply, record_imported_reply,
    report_markdown, save_drafts,
};

fn ready_db() -> Connection {
    let connection = Connection::open_in_memory().unwrap();
    initialize_schema(&connection).unwrap();
    confirm_account(&connection, "@tester", "Tester").unwrap();
    designate_browser(&connection, "Dedicated Firefox").unwrap();
    connection
}

fn sample_drafts() -> DraftSetInput {
    DraftSetInput {
        project_short: "Glint".to_owned(),
        language: "en".to_owned(),
        recommended_option: 1,
        options: vec![
            DraftOptionInput {
                text: "Glint makes this upgrade immediately useful for builders".to_owned(),
                reply_probability: 72,
                stars: 4,
            },
            DraftOptionInput {
                text: "Glint keeps shipping while most timelines chase narratives".to_owned(),
                reply_probability: 61,
                stars: 3,
            },
            DraftOptionInput {
                text: "The Glint thesis looks stronger with real usage data".to_owned(),
                reply_probability: 55,
                stars: 3,
            },
        ],
    }
}

#[test]
fn normalization_collapses_case_punctuation_and_nfkc_variants() {
    assert_eq!(
        normalize_reply("Ｇｌｉｎｔ,   IS shipping!"),
        "glint is shipping"
    );
}

#[test]
fn x_link_parser_accepts_only_x_status_urls() {
    let id =
        x_social_draft_workflow::extract_status_id("https://x.com/alice/status/1234567890?s=20")
            .unwrap();
    assert_eq!(id, "1234567890");
    assert!(
        x_social_draft_workflow::extract_status_id("https://evil.example/alice/status/1234567890")
            .is_err()
    );
    assert!(
        x_social_draft_workflow::extract_status_id("https://x.com/alice/status/not-a-number")
            .is_err()
    );
}

#[test]
fn post_cannot_be_saved_until_a_dedicated_browser_is_designated() {
    let connection = Connection::open_in_memory().unwrap();
    initialize_schema(&connection).unwrap();
    confirm_account(&connection, "@tester", "Tester").unwrap();

    let result = add_post(
        &connection,
        "https://x.com/alice/status/1234567890",
        "A public post about Glint.",
        "en",
    );
    assert!(result.is_err());
}

#[test]
fn saving_three_valid_drafts_is_atomic_and_creates_recommendation() {
    let connection = ready_db();
    let post_id = add_post(
        &connection,
        "https://x.com/alice/status/1234567890",
        "A public post about Glint.",
        "en",
    )
    .unwrap();

    let result = save_drafts(&connection, post_id, &sample_drafts()).unwrap();
    assert_eq!(result.draft_ids.len(), 3);
    assert_eq!(result.recommended_option, 1);
    let count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM reply_drafts WHERE post_id = ?1",
            [post_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(count, 3);
}

#[test]
fn duplicate_against_imported_history_blocks_the_whole_draft_batch() {
    let connection = ready_db();
    let post_id = add_post(
        &connection,
        "https://x.com/alice/status/1234567890",
        "A public post about Glint.",
        "en",
    )
    .unwrap();
    record_imported_reply(
        &connection,
        "@tester",
        "Glint keeps shipping while most timelines chase narratives!",
    )
    .unwrap();

    let result = save_drafts(&connection, post_id, &sample_drafts());
    assert!(result.is_err());
    let count: i64 = connection
        .query_row(
            "SELECT COUNT(*) FROM reply_drafts WHERE post_id = ?1",
            [post_id],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(count, 0);
}

#[test]
fn manually_confirmed_reply_and_like_are_recorded_only_as_status() {
    let connection = ready_db();
    let post_id = add_post(
        &connection,
        "https://x.com/alice/status/1234567890",
        "A public post about Glint.",
        "en",
    )
    .unwrap();
    let result = save_drafts(&connection, post_id, &sample_drafts()).unwrap();
    confirm_posted(&connection, result.draft_ids[0]).unwrap();
    confirm_liked(&connection, post_id).unwrap();

    let (reply, like): (String, String) = connection
        .query_row(
            "SELECT reply_manual_status, like_manual_status FROM engagement_status WHERE post_id = ?1",
            [post_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .unwrap();
    assert_eq!(reply, "user_posted");
    assert_eq!(like, "user_liked");
    assert!(duplicate_status(&connection, "@tester", &sample_drafts().options[0].text).unwrap());
}

#[test]
fn report_is_markdown_and_includes_post_and_manual_action_status() {
    let connection = ready_db();
    let post_id = add_post(
        &connection,
        "https://x.com/alice/status/1234567890",
        "A public post about Glint.",
        "en",
    )
    .unwrap();
    save_drafts(&connection, post_id, &sample_drafts()).unwrap();

    let report = report_markdown(&connection).unwrap();
    assert!(
        report.contains("| Post ID | URL | Read | Drafts | Recommended draft | Reply | Like |")
    );
    assert!(report.contains("https://x.com/i/status/1234567890"));
    assert!(report.contains("Glint makes this upgrade immediately useful for builders"));
    assert!(report.contains("Glint keeps shipping while most timelines chase narratives"));
    assert!(report.contains("not_confirmed"));
}

#[test]
fn english_drafts_are_accepted_for_indonesian_posts_and_questions_are_rejected() {
    let connection = ready_db();
    let post_id = add_post(
        &connection,
        "https://x.com/alice/status/1234567890",
        "Selamat pagi semua, update Glint makin mantap.",
        "id",
    )
    .unwrap();

    // Non-English draft language must be rejected.
    let mut non_en = sample_drafts();
    non_en.language = "id".to_owned();
    assert!(save_drafts(&connection, post_id, &non_en).is_err());

    // Question mark in any option must be rejected.
    let mut with_question = sample_drafts();
    with_question.options[0].text = "Could Glint explain how this upgrade helps builders?".to_owned();
    assert!(save_drafts(&connection, post_id, &with_question).is_err());

    // English non-question drafts succeed for an Indonesian post.
    assert!(save_drafts(&connection, post_id, &sample_drafts()).is_ok());
}

#[test]
fn same_status_id_is_not_added_twice_via_another_x_domain() {
    let connection = ready_db();
    add_post(
        &connection,
        "https://x.com/alice/status/1234567890",
        "A public post about Glint.",
        "en",
    )
    .unwrap();

    assert!(
        add_post(
            &connection,
            "https://twitter.com/alice/status/1234567890",
            "Same post from alternate host.",
            "en",
        )
        .is_err()
    );
}

#[test]
fn designating_browser_before_confirm_account_is_preserved() {
    let connection = Connection::open_in_memory().unwrap();
    initialize_schema(&connection).unwrap();
    designate_browser(&connection, "Brave Browser headless isolated (Agent)").unwrap();
    let status_before = x_social_draft_workflow::status_summary(&connection).unwrap();
    assert!(status_before.dedicated_browser_designated);
    assert!(!status_before.account_confirmed);

    confirm_account(&connection, "@tester", "Tester").unwrap();
    let status_after = x_social_draft_workflow::status_summary(&connection).unwrap();
    assert!(status_after.account_confirmed);
    assert!(status_after.dedicated_browser_designated);

    let post_id = add_post(
        &connection,
        "https://x.com/alice/status/1234567890",
        "A public post about Glint.",
        "en",
    )
    .unwrap();
    assert_eq!(post_id, 1);
}
