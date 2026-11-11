use anyhow::{Context, Result, anyhow, bail};
use rusqlite::{Connection, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::path::Path;
use unicode_normalization::UnicodeNormalization;
use url::Url;

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct DraftOptionInput {
    pub text: String,
    pub reply_probability: u8,
    pub stars: u8,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct DraftSetInput {
    pub project_short: String,
    pub language: String,
    pub recommended_option: u8,
    pub options: Vec<DraftOptionInput>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SaveDraftsResult {
    pub draft_ids: Vec<i64>,
    pub recommended_option: u8,
    pub duplicate_check_posted_replies: i64,
    pub duplicate_check_prior_drafts: i64,
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct StatusSummary {
    pub integrity: String,
    pub account_handle: Option<String>,
    pub account_confirmed: bool,
    pub browser_label: Option<String>,
    pub dedicated_browser_designated: bool,
    pub posts: i64,
    pub drafts: i64,
    pub recorded_replies: i64,
}

pub fn connect_database(path: &Path) -> Result<Connection> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("creating database directory {}", parent.display()))?;
    }
    let connection =
        Connection::open(path).with_context(|| format!("opening database {}", path.display()))?;
    connection.busy_timeout(std::time::Duration::from_secs(5))?;
    initialize_schema(&connection)?;
    Ok(connection)
}

pub fn initialize_schema(connection: &Connection) -> Result<()> {
    connection.execute_batch("PRAGMA foreign_keys = ON;")?;
    connection.execute_batch(include_str!("../schema.sql"))?;
    ensure_column(connection, "posts", "project_short", "TEXT")?;

    let defaults = [
        ("browser_mode", "headless_or_isolated_debug; separate browser profile required"),
        ("access_mode", "multi_browser_bidi_cdp; X API disabled"),
        ("auto_like", "enabled via isolated headless browser workflow when user requests"),
        ("auto_reply", "enabled via isolated headless browser workflow when user requests"),
        ("draft_count", "3"),
        ("report_format", "markdown_table"),
        (
            "duplicate_scope",
            "normalized replies recorded in posted_replies",
        ),
    ];
    for (key, value) in defaults {
        connection.execute(
            "INSERT INTO workflow_config (key, value) VALUES (?1, ?2) \
             ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
            params![key, value],
        )?;
    }
    connection.execute(
        "INSERT INTO workflow_config (key, value) VALUES ('reply_prompt', ?1) \
         ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
        [include_str!("../reply_prompt.md")],
    )?;
    Ok(())
}

fn ensure_column(connection: &Connection, table: &str, column: &str, sql_type: &str) -> Result<()> {
    let mut statement = connection.prepare(&format!("PRAGMA table_info({table})"))?;
    let columns = statement
        .query_map([], |row| row.get::<_, String>(1))?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    if !columns.iter().any(|existing| existing == column) {
        connection.execute(
            &format!("ALTER TABLE {table} ADD COLUMN {column} {sql_type}"),
            [],
        )?;
    }
    Ok(())
}

fn set_config(connection: &Connection, key: &str, value: &str) -> Result<()> {
    connection.execute(
        "INSERT INTO workflow_config (key, value) VALUES (?1, ?2) \
         ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
        params![key, value],
    )?;
    Ok(())
}

fn record_event(connection: &Connection, event_type: &str, details: &str) -> Result<()> {
    connection.execute(
        "INSERT INTO workflow_events (event_type, details) VALUES (?1, ?2)",
        params![event_type, details],
    )?;
    Ok(())
}

pub fn confirm_account(connection: &Connection, handle: &str, display_name: &str) -> Result<()> {
    let handle = handle.trim();
    if !handle.starts_with('@') || handle.len() < 2 || handle.chars().any(char::is_whitespace) {
        bail!("account handle must start with @ and contain no whitespace");
    }
    if display_name.trim().is_empty() {
        bail!("display name cannot be empty");
    }
    let has_browser_label: bool = connection
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM workflow_config WHERE key = 'browser_label')",
            [],
            |row| row.get(0),
        )?;
    let browser_flag = i64::from(has_browser_label);
    connection.execute(
        "INSERT INTO accounts (handle, display_name, platform, confirmed_by_user, browser_separate_designated) \
         VALUES (?1, ?2, 'x', 1, ?3) \
         ON CONFLICT(handle) DO UPDATE SET \
           display_name = excluded.display_name, \
           confirmed_by_user = 1, \
           browser_separate_designated = MAX(accounts.browser_separate_designated, excluded.browser_separate_designated), \
           updated_at = CURRENT_TIMESTAMP",
        params![handle, display_name.trim(), browser_flag],
    )?;
    set_config(connection, "account_handle", handle)?;
    record_event(
        connection,
        "account_confirmed",
        &format!("User confirmed {handle} as the active X account."),
    )?;
    Ok(())
}

pub fn designate_browser(connection: &Connection, label: &str) -> Result<()> {
    let label = label.trim();
    if label.is_empty() {
        bail!("browser label cannot be empty");
    }
    set_config(connection, "browser_label", label)?;
    if let Ok(account) = active_account(connection) {
        connection.execute(
            "UPDATE accounts SET browser_separate_designated = 1, updated_at = CURRENT_TIMESTAMP \
             WHERE handle = ?1 AND confirmed_by_user = 1",
            [&account],
        )?;
    }
    record_event(
        connection,
        "browser_designated",
        &format!("User designated a separate browser: {label}."),
    )?;
    Ok(())
}

fn active_account(connection: &Connection) -> Result<String> {
    connection
        .query_row(
            "SELECT value FROM workflow_config WHERE key = 'account_handle'",
            [],
            |row| row.get(0),
        )
        .optional()?
        .ok_or_else(|| anyhow!("no active X account is confirmed in the database"))
}

fn require_ready_account(connection: &Connection) -> Result<String> {
    let handle = active_account(connection)?;
    let (confirmed, browser_designated): (i64, i64) = connection.query_row(
        "SELECT confirmed_by_user, browser_separate_designated FROM accounts WHERE handle = ?1",
        [&handle],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;
    if confirmed != 1 {
        bail!("active X account has not been confirmed by the user");
    }
    if browser_designated != 1 {
        bail!("a separate dedicated browser has not been designated by the user");
    }
    Ok(handle)
}

pub fn extract_status_id(post_url: &str) -> Result<String> {
    let parsed = Url::parse(post_url).context("invalid post URL")?;
    let host = parsed
        .host_str()
        .unwrap_or_default()
        .trim_start_matches("www.");
    if host != "x.com" && host != "twitter.com" {
        bail!("only x.com or twitter.com post links are accepted");
    }
    let segments: Vec<&str> = parsed
        .path_segments()
        .ok_or_else(|| anyhow!("post URL has no path"))?
        .collect();
    let status_index = segments
        .iter()
        .position(|segment| *segment == "status")
        .ok_or_else(|| anyhow!("URL does not contain a status segment"))?;
    let id = segments
        .get(status_index + 1)
        .ok_or_else(|| anyhow!("post ID is missing"))?;
    if id.is_empty() || !id.bytes().all(|byte| byte.is_ascii_digit()) {
        bail!("post ID must contain digits only");
    }
    Ok((*id).to_owned())
}

pub fn normalize_reply(text: &str) -> String {
    let normalized: String = text
        .nfkc()
        .flat_map(char::to_lowercase)
        .map(|character| {
            if character.is_alphanumeric() {
                character
            } else {
                ' '
            }
        })
        .collect();
    normalized.split_whitespace().collect::<Vec<_>>().join(" ")
}

pub fn add_post(
    connection: &Connection,
    post_url: &str,
    body_text: &str,
    language: &str,
) -> Result<i64> {
    let account = require_ready_account(connection)?;
    let status_id = extract_status_id(post_url)?;
    let body_text = body_text.trim();
    if body_text.is_empty() {
        bail!("post text is empty; only save text actually read in the designated browser");
    }
    if language.trim().is_empty() {
        bail!("post language is required");
    }
    let canonical_url = format!("https://x.com/i/status/{status_id}");
    let existing: Option<i64> = connection
        .query_row(
            "SELECT id FROM posts WHERE x_url = ?1 OR status_id = ?2",
            params![canonical_url, status_id],
            |row| row.get(0),
        )
        .optional()?;
    if let Some(existing_id) = existing {
        bail!("post already exists in the database as ID {existing_id}");
    }
    connection.execute(
        "INSERT INTO posts (x_url, status_id, account_handle, body_text, language, read_status, read_at) \
         VALUES (?1, ?2, ?3, ?4, ?5, 'read', CURRENT_TIMESTAMP)",
        params![canonical_url, status_id, account, body_text, language.trim()],
    )?;
    let post_id = connection.last_insert_rowid();
    connection.execute(
        "INSERT INTO engagement_status (post_id) VALUES (?1)",
        [post_id],
    )?;
    record_event(
        connection,
        "post_recorded",
        &format!("Recorded visible post {canonical_url} as database row {post_id}."),
    )?;
    Ok(post_id)
}

fn validate_draft_set(draft_set: &DraftSetInput) -> Result<Vec<String>> {
    if draft_set.options.len() != 3 {
        bail!("exactly three draft options are required");
    }
    if !(1..=3).contains(&draft_set.recommended_option) {
        bail!("recommended_option must be 1, 2, or 3");
    }
    let project = draft_set.project_short.trim();
    if project.is_empty() || project.contains('@') || project.contains('_') {
        bail!("provide the short project name without @ or underscores");
    }
    let normalized_project = normalize_reply(project);
    if normalized_project.is_empty() {
        bail!("project name has no searchable characters");
    }
    let language = draft_set.language.trim().to_lowercase();
    if language.is_empty() {
        bail!("language is required");
    }
    let language_key = language.split('-').next().unwrap_or("und");
    if !language_key.eq_ignore_ascii_case("en") {
        bail!("drafts must be written in English (en), even when the post is in another language");
    }
    let warnings = Vec::new();

    let mut seen = HashSet::new();
    for (index, option) in draft_set.options.iter().enumerate() {
        let text = option.text.trim();
        let option_no = index + 1;
        if text.is_empty() || text.contains('\n') || text.contains('\r') {
            bail!("option {option_no} must contain one non-empty line");
        }
        if option.reply_probability > 100 {
            bail!("option {option_no} reply probability must be between 0 and 100");
        }
        if !(1..=5).contains(&option.stars) {
            bail!("option {option_no} star score must be between 1 and 5");
        }
        if text.chars().any(is_forbidden_symbol) {
            bail!("option {option_no} contains a forbidden quote, dash, or emoji");
        }
        if text.contains('?') || text.contains('？') {
            bail!("option {option_no} must not contain a question mark");
        }
        let normalized = normalize_reply(text);
        if !normalized.contains(&normalized_project) {
            bail!("option {option_no} does not include project name {project}");
        }
        let words = text.split_whitespace().count();
        if !(7..=9).contains(&words) {
            bail!("option {option_no} has {words} whitespace-separated words; expected 7–9");
        }
        if !seen.insert(normalized) {
            bail!("the three draft options contain a duplicate");
        }
    }
    Ok(warnings)
}

fn is_forbidden_symbol(character: char) -> bool {
    matches!(character, '"' | '\'' | '“' | '”' | '‘' | '’' | '—' | '–') || is_emoji(character)
}

fn is_emoji(character: char) -> bool {
    matches!(
        character as u32,
        0x1F000..=0x1FAFF | 0x2600..=0x27BF | 0xFE0F
    )
}

pub fn duplicate_status(connection: &Connection, account_handle: &str, text: &str) -> Result<bool> {
    let normalized = normalize_reply(text);
    if normalized.is_empty() {
        bail!("cannot check an empty reply");
    }
    let found: bool = connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM posted_replies \
         WHERE account_handle = ?1 AND normalized_text = ?2)",
        params![account_handle, normalized],
        |row| row.get(0),
    )?;
    Ok(found)
}

pub fn record_imported_reply(
    connection: &Connection,
    account_handle: &str,
    text: &str,
) -> Result<()> {
    let text = text.trim();
    let normalized = normalize_reply(text);
    if text.is_empty() || normalized.is_empty() {
        bail!("cannot import an empty reply");
    }
    let account_exists: bool = connection.query_row(
        "SELECT EXISTS(SELECT 1 FROM accounts WHERE handle = ?1 AND confirmed_by_user = 1)",
        [account_handle],
        |row| row.get(0),
    )?;
    if !account_exists {
        bail!("account must be confirmed before importing reply history");
    }
    connection
        .execute(
            "INSERT INTO posted_replies (account_handle, text, normalized_text, source) \
         VALUES (?1, ?2, ?3, 'imported')",
            params![account_handle, text, normalized],
        )
        .context("duplicate imported reply or database constraint failed")?;
    record_event(connection, "reply_history_imported", account_handle)?;
    Ok(())
}

pub fn save_drafts(
    connection: &Connection,
    post_id: i64,
    draft_set: &DraftSetInput,
) -> Result<SaveDraftsResult> {
    let warnings = validate_draft_set(draft_set)?;
    let active_handle = require_ready_account(connection)?;
    let (post_handle, _post_language, post_exists): (String, String, bool) = connection.query_row(
        "SELECT account_handle, COALESCE(language, 'und'), \
         (read_status = 'read' AND body_text IS NOT NULL) \
         FROM posts WHERE id = ?1",
        [post_id],
        |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
    )?;
    if !post_exists {
        bail!("post text has not been recorded as read");
    }
    if post_handle != active_handle {
        bail!("post belongs to a different X account than the confirmed active account");
    }

    let posted_count: i64 = connection.query_row(
        "SELECT COUNT(*) FROM posted_replies WHERE account_handle = ?1",
        [&active_handle],
        |row| row.get(0),
    )?;
    let prior_draft_count: i64 = connection.query_row(
        "SELECT COUNT(*) FROM reply_drafts d \
         JOIN posts p ON p.id = d.post_id \
         WHERE p.account_handle = ?1 AND d.status IN ('draft', 'recommended', 'posted')",
        [&active_handle],
        |row| row.get(0),
    )?;

    let transaction = connection.unchecked_transaction()?;
    let mut normalized_options = HashSet::new();
    for option in &draft_set.options {
        let normalized = normalize_reply(&option.text);
        if !normalized_options.insert(normalized.clone()) {
            bail!("the three draft options contain a duplicate");
        }
        let posted_duplicate: bool = transaction.query_row(
            "SELECT EXISTS(SELECT 1 FROM posted_replies \
             WHERE account_handle = ?1 AND normalized_text = ?2)",
            params![active_handle, normalized],
            |row| row.get(0),
        )?;
        if posted_duplicate {
            bail!("draft duplicates a reply already recorded as posted/imported");
        }
        let prior_draft_duplicate: bool = transaction.query_row(
            "SELECT EXISTS(SELECT 1 FROM reply_drafts d \
             JOIN posts p ON p.id = d.post_id \
             WHERE p.account_handle = ?1 AND d.normalized_text = ?2 \
               AND d.status IN ('draft', 'recommended', 'posted'))",
            params![active_handle, normalized],
            |row| row.get(0),
        )?;
        if prior_draft_duplicate {
            bail!("draft duplicates wording already stored in an earlier draft");
        }
    }

    transaction.execute(
        "UPDATE posts SET project_short = ?1 WHERE id = ?2",
        params![draft_set.project_short.trim(), post_id],
    )?;
    let mut draft_ids = Vec::with_capacity(3);
    for (index, option) in draft_set.options.iter().enumerate() {
        let option_no = (index + 1) as u8;
        let recommended = option_no == draft_set.recommended_option;
        transaction.execute(
            "INSERT INTO reply_drafts \
             (post_id, option_no, text, normalized_text, reply_probability, stars, recommended, status) \
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            params![
                post_id,
                option_no,
                option.text.trim(),
                normalize_reply(&option.text),
                option.reply_probability,
                option.stars,
                i64::from(recommended),
                if recommended { "recommended" } else { "draft" },
            ],
        )?;
        draft_ids.push(transaction.last_insert_rowid());
    }
    transaction.execute(
        "INSERT INTO workflow_events (event_type, details) VALUES ('drafts_saved', ?1)",
        [format!(
            "Saved 3 drafts for post {post_id}; checked {posted_count} recorded replies and {prior_draft_count} prior drafts."
        )],
    )?;
    transaction.commit()?;

    Ok(SaveDraftsResult {
        draft_ids,
        recommended_option: draft_set.recommended_option,
        duplicate_check_posted_replies: posted_count,
        duplicate_check_prior_drafts: prior_draft_count,
        warnings,
    })
}

pub fn confirm_posted(connection: &Connection, draft_id: i64) -> Result<()> {
    let (post_id, account_handle, text, normalized, status): (i64, String, String, String, String) =
        connection.query_row(
            "SELECT d.post_id, p.account_handle, d.text, d.normalized_text, d.status \
             FROM reply_drafts d JOIN posts p ON p.id = d.post_id WHERE d.id = ?1",
            [draft_id],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                ))
            },
        )?;
    if status == "posted" {
        bail!("draft is already recorded as posted");
    }
    connection
        .execute(
            "INSERT INTO posted_replies \
         (account_handle, post_id, draft_id, text, normalized_text, source, posted_at) \
         VALUES (?1, ?2, ?3, ?4, ?5, 'user_confirmed', CURRENT_TIMESTAMP)",
            params![account_handle, post_id, draft_id, text, normalized],
        )
        .context("duplicate reply or database constraint failed")?;
    connection.execute(
        "UPDATE reply_drafts SET status = 'posted' WHERE id = ?1",
        [draft_id],
    )?;
    connection.execute(
        "UPDATE engagement_status SET reply_manual_status = 'user_posted', \
         verification_note = 'Verified in designated browser', verified_at = CURRENT_TIMESTAMP \
         WHERE post_id = ?1",
        [post_id],
    )?;
    record_event(
        connection,
        "reply_user_confirmed",
        &format!("Confirmed reply draft {draft_id} was posted."),
    )?;
    Ok(())
}

pub fn confirm_liked(connection: &Connection, post_id: i64) -> Result<()> {
    let changed = connection.execute(
        "UPDATE engagement_status SET like_manual_status = 'user_liked', \
         verification_note = 'Verified in designated browser', verified_at = CURRENT_TIMESTAMP \
         WHERE post_id = ?1",
        [post_id],
    )?;
    if changed == 0 {
        bail!("post ID {post_id} is not in the database");
    }
    record_event(
        connection,
        "like_user_confirmed",
        &format!("Confirmed Like recorded for post row {post_id}."),
    )?;
    Ok(())
}

pub fn status_summary(connection: &Connection) -> Result<StatusSummary> {
    let integrity: String = connection.query_row("PRAGMA integrity_check", [], |row| row.get(0))?;
    let active_handle = connection
        .query_row(
            "SELECT value FROM workflow_config WHERE key = 'account_handle'",
            [],
            |row| row.get::<_, String>(0),
        )
        .optional()?;
    let browser_label: Option<String> = connection
        .query_row(
            "SELECT value FROM workflow_config WHERE key = 'browser_label'",
            [],
            |row| row.get(0),
        )
        .optional()?;
    let (account_confirmed, browser_designated) = if let Some(handle) = active_handle.as_deref() {
        connection
            .query_row(
                "SELECT confirmed_by_user, browser_separate_designated FROM accounts WHERE handle = ?1",
                [handle],
                |row| Ok((row.get::<_, i64>(0)? == 1, row.get::<_, i64>(1)? == 1)),
            )
            .optional()?
            .unwrap_or((false, browser_label.is_some()))
    } else {
        (false, browser_label.is_some())
    };
    let count = |table: &str| -> Result<i64> {
        Ok(
            connection.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |row| {
                row.get(0)
            })?,
        )
    };
    Ok(StatusSummary {
        integrity,
        account_handle: active_handle,
        account_confirmed,
        browser_label,
        dedicated_browser_designated: browser_designated,
        posts: count("posts")?,
        drafts: count("reply_drafts")?,
        recorded_replies: count("posted_replies")?,
    })
}

pub fn stored_prompt(connection: &Connection) -> Result<String> {
    connection
        .query_row(
            "SELECT value FROM workflow_config WHERE key = 'reply_prompt'",
            [],
            |row| row.get(0),
        )
        .optional()?
        .ok_or_else(|| anyhow!("reply prompt is missing from workflow_config"))
}

pub fn report_markdown(connection: &Connection) -> Result<String> {
    let mut output = String::from(
        "| Post ID | URL | Read | Drafts | Recommended draft | Reply | Like |\n|---:|---|---|---:|---|---|---|\n",
    );
    let mut statement = connection.prepare(
        "SELECT p.id, p.x_url, p.read_status, COUNT(d.id), \
         COALESCE(e.reply_manual_status, 'unknown'), \
         COALESCE(e.like_manual_status, 'unknown') \
         FROM posts p \
         LEFT JOIN reply_drafts d ON d.post_id = p.id \
         LEFT JOIN engagement_status e ON e.post_id = p.id \
         GROUP BY p.id ORDER BY p.id",
    )?;
    let post_rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, i64>(3)?,
                row.get::<_, String>(4)?,
                row.get::<_, String>(5)?,
            ))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    drop(statement);

    if post_rows.is_empty() {
        output.push_str("| — | — | — | 0 | — | not_confirmed | not_confirmed |\n");
    }
    for (id, url, read, draft_count, reply, like) in post_rows {
        let mut draft_statement = connection.prepare(
            "SELECT option_no, text, reply_probability, stars, recommended \
             FROM reply_drafts WHERE post_id = ?1 ORDER BY option_no",
        )?;
        let drafts = draft_statement
            .query_map([id], |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, Option<i64>>(2)?.unwrap_or(0),
                    row.get::<_, Option<i64>>(3)?.unwrap_or(0),
                    row.get::<_, i64>(4)? == 1,
                ))
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        let draft_lines: Vec<String> = drafts
            .iter()
            .map(|(number, text, probability, stars, _)| {
                format!(
                    "{number}. {} ({probability}%, {stars}/5)",
                    markdown_cell(text)
                )
            })
            .collect();
        let recommended = drafts
            .iter()
            .find(|(_, _, _, _, selected)| *selected)
            .map(|(number, text, probability, stars, _)| {
                format!(
                    "{number}. {} ({probability}%, {stars}/5)",
                    markdown_cell(text)
                )
            })
            .unwrap_or_else(|| "—".to_owned());
        output.push_str(&format!(
            "| {id} | {} | {read} | {draft_count}<br>{} | {} | {reply} | {like} |\n",
            markdown_cell(&url),
            if draft_lines.is_empty() {
                "—".to_owned()
            } else {
                draft_lines.join("<br>")
            },
            recommended,
        ));
    }
    let recorded: i64 =
        connection.query_row("SELECT COUNT(*) FROM posted_replies", [], |row| row.get(0))?;
    output.push_str(&format!(
        "\nDB duplicate-check history: {recorded} recorded replies. Checks cover recorded normalized text only.\n"
    ));
    Ok(output)
}

fn markdown_cell(text: &str) -> String {
    text.replace('|', "\\|")
        .replace('\r', " ")
        .replace('\n', "<br>")
}
